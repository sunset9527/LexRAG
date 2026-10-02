"""v3.0 组织 RBAC：授权必须从数据库实时读取，不能信任客户端角色。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.user import User

try:
    from app.models.organization import Organization
    from app.models.rbac import Permission, Role, UserRole
    from app.services.authorization_service import (
        AuthorizationError,
        AuthorizationService,
        DEFAULT_PERMISSIONS,
    )
except ImportError:
    Organization = Permission = Role = UserRole = None
    AuthorizationError = AuthorizationService = None
    DEFAULT_PERMISSIONS = ()


def make_service():
    assert AuthorizationService is not None, "v3.0 应提供 AuthorizationService"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(id=1, username="admin", hashed_password="hash"),
                User(id=2, username="lawyer", hashed_password="hash"),
                User(id=3, username="member", hashed_password="hash"),
                User(id=4, username="outsider", hashed_password="hash"),
            ]
        )
        db.commit()
    service = AuthorizationService(factory)
    organization = service.ensure_demo_organization()
    service.assign_role(user_id=1, organization_id=organization["id"], role_code="admin")
    service.assign_role(user_id=2, organization_id=organization["id"], role_code="lawyer")
    service.assign_role(user_id=3, organization_id=organization["id"], role_code="member")
    return service, organization


def test_demo_organization_and_rbac_seed_are_idempotent():
    service, organization = make_service()

    second = service.ensure_demo_organization()

    assert second == organization
    assert {"members:manage", "audit:read", "analytics:read"}.issubset(DEFAULT_PERMISSIONS)
    with service.session_factory() as db:
        assert db.query(Organization).count() == 1
        assert db.query(Role).count() == 3
        assert db.query(Permission).count() == len(DEFAULT_PERMISSIONS)
        assert db.query(UserRole).count() == 3


def test_authorization_context_uses_current_membership_and_permission_matrix():
    service, organization = make_service()

    admin = service.build_context(user_id=1, organization_id=organization["id"])
    lawyer = service.build_context(user_id=2, organization_id=organization["id"])
    member = service.build_context(user_id=3, organization_id=organization["id"])

    assert admin.can("members:manage") is True
    assert admin.can("audit:read") is True
    assert lawyer.can("knowledge_bases:read") is True
    assert lawyer.can("members:manage") is False
    assert member.can("knowledge_bases:read") is True
    assert member.can("audit:read") is False


def test_unknown_or_non_member_organization_cannot_build_context():
    service, organization = make_service()

    with pytest.raises(AuthorizationError):
        service.build_context(user_id=4, organization_id=organization["id"])
    with pytest.raises(AuthorizationError):
        service.build_context(user_id=1, organization_id=organization["id"] + 99)


def test_role_change_is_visible_to_next_request_without_reissuing_token():
    service, organization = make_service()

    assert service.build_context(user_id=2, organization_id=organization["id"]).can("audit:read") is False
    service.assign_role(user_id=2, organization_id=organization["id"], role_code="admin")

    assert service.build_context(user_id=2, organization_id=organization["id"]).can("audit:read") is True


def test_default_context_is_allowed_only_when_the_user_has_one_active_organization():
    service, organization = make_service()

    assert service.build_default_context(user_id=3).organization_id == organization["id"]

    with service.session_factory() as db:
        other = Organization(name="第二组织", slug="second-demo")
        db.add(other)
        db.commit()
        other_id = other.id
    service.assign_role(user_id=3, organization_id=other_id, role_code="member")

    with pytest.raises(AuthorizationError):
        service.build_default_context(user_id=3)
