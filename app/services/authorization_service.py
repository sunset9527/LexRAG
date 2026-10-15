"""组织级授权：权限始终从数据库成员关系实时计算。"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.organization import Organization
from app.models.rbac import Permission, Role, UserRole
from app.models.user import User

DEFAULT_PERMISSIONS = (
    "members:manage",
    "knowledge_bases:manage",
    "knowledge_bases:read",
    "prompts:manage",
    "agents:manage",
    "audit:read",
    "analytics:read",
    "law_updates:manage",
    "queries:create",
    "cases:read",
)

ROLE_PERMISSIONS = {
    "admin": set(DEFAULT_PERMISSIONS),
    "lawyer": {"knowledge_bases:read", "queries:create", "cases:read"},
    "member": {"knowledge_bases:read", "queries:create"},
}

ROLE_NAMES = {"admin": "管理员", "lawyer": "律师", "member": "普通用户"}


class AuthorizationError(ValueError):
    """当前用户不是目标组织成员或组织不可用。"""


@dataclass(frozen=True)
class AuthorizationContext:
    user_id: int
    organization_id: int
    role_code: str
    permission_codes: frozenset[str]

    def can(self, permission_code: str) -> bool:
        return permission_code in self.permission_codes


class AuthorizationService:
    """RBAC 种子化、成员角色分配与实时上下文构造。"""

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def ensure_demo_organization(self) -> dict[str, object]:
        with self.session_factory() as db:
            self._ensure_seed_data(db)
            organization = db.scalar(select(Organization).where(Organization.slug == "local-demo"))
            if organization is None:
                organization = Organization(name="本机演示组织", slug="local-demo")
                db.add(organization)
                db.flush()
            db.commit()
            return {"id": organization.id, "name": organization.name, "slug": organization.slug}

    def assign_role(self, *, user_id: int, organization_id: int, role_code: str) -> None:
        with self.session_factory() as db:
            self._ensure_seed_data(db)
            role = db.scalar(select(Role).where(Role.code == role_code))
            organization = db.get(Organization, organization_id)
            user = db.get(User, user_id)
            if role is None or organization is None or user is None or not organization.is_active:
                raise AuthorizationError("用户、角色或组织不可用")
            membership = db.scalar(
                select(UserRole).where(
                    UserRole.user_id == user_id,
                    UserRole.organization_id == organization_id,
                )
            )
            if membership is None:
                db.add(UserRole(user_id=user_id, organization_id=organization_id, role_id=role.id))
            else:
                membership.role_id = role.id
            db.commit()

    def enroll_new_local_user(self, *, user_id: int) -> str:
        """本机演示注册即加入默认组织；首个成员成为组织管理员。"""
        organization = self.ensure_demo_organization()
        with self.session_factory() as db:
            has_members = (
                db.scalar(
                    select(UserRole.id)
                    .where(UserRole.organization_id == organization["id"])
                    .limit(1)
                )
                is not None
            )
        role_code = "member" if has_members else "admin"
        self.assign_role(
            user_id=user_id,
            organization_id=int(organization["id"]),
            role_code=role_code,
        )
        return role_code

    def build_context(self, *, user_id: int, organization_id: int) -> AuthorizationContext:
        with self.session_factory() as db:
            membership = db.scalar(
                select(UserRole).where(
                    UserRole.user_id == user_id,
                    UserRole.organization_id == organization_id,
                )
            )
            organization = db.get(Organization, organization_id)
            if membership is None or organization is None or not organization.is_active:
                raise AuthorizationError("当前用户不是活动组织成员")
            role = db.get(Role, membership.role_id)
            if role is None:
                raise AuthorizationError("成员角色不可用")
            permissions = db.scalars(
                select(Permission).join(Role.permissions).where(Role.id == role.id)
            ).all()
            return AuthorizationContext(
                user_id=user_id,
                organization_id=organization_id,
                role_code=role.code,
                permission_codes=frozenset(item.code for item in permissions),
            )

    def build_default_context(self, *, user_id: int) -> AuthorizationContext:
        """仅当用户恰有一个活动组织时允许兼容旧客户端自动选择。"""
        with self.session_factory() as db:
            organization_ids = db.scalars(
                select(UserRole.organization_id)
                .join(Organization, Organization.id == UserRole.organization_id)
                .where(UserRole.user_id == user_id, Organization.is_active.is_(True))
                .order_by(UserRole.organization_id)
            ).all()
        if len(organization_ids) != 1:
            raise AuthorizationError("请通过 X-Organization-ID 选择活动组织")
        return self.build_context(user_id=user_id, organization_id=organization_ids[0])

    def list_members(self, *, organization_id: int) -> list[dict[str, object]]:
        with self.session_factory() as db:
            rows = db.execute(
                select(UserRole, User, Role)
                .join(User, User.id == UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.organization_id == organization_id)
                .order_by(User.id)
            ).all()
            return [
                {
                    "user_id": user.id,
                    "username": user.username,
                    "is_active": user.is_active,
                    "role": role.code,
                }
                for _membership, user, role in rows
            ]

    @staticmethod
    def _ensure_seed_data(db: Session) -> None:
        permission_by_code = {
            permission.code: permission for permission in db.scalars(select(Permission)).all()
        }
        for code in DEFAULT_PERMISSIONS:
            if code not in permission_by_code:
                permission = Permission(code=code, name=code)
                db.add(permission)
                permission_by_code[code] = permission
        db.flush()

        role_by_code = {role.code: role for role in db.scalars(select(Role)).all()}
        for code, permission_codes in ROLE_PERMISSIONS.items():
            role = role_by_code.get(code)
            if role is None:
                role = Role(code=code, name=ROLE_NAMES[code])
                db.add(role)
                db.flush()
            role.permissions = [permission_by_code[item] for item in sorted(permission_codes)]
        db.flush()
