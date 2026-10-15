"""add organizations and RBAC

Revision ID: 20261002_01
Revises: 20261001_03
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_01"
down_revision = "20261001_03"
branch_labels = None
depends_on = None


PERMISSIONS = (
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
    "admin": set(PERMISSIONS),
    "lawyer": {"knowledge_bases:read", "queries:create", "cases:read"},
    "member": {"knowledge_bases:read", "queries:create"},
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        )
        op.create_index("ix_organizations_slug", "organizations", ["slug"])
    if not inspector.has_table("roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.UniqueConstraint("code", name="uq_roles_code"),
        )
        op.create_index("ix_roles_code", "roles", ["code"])
    if not inspector.has_table("permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.UniqueConstraint("code", name="uq_permissions_code"),
        )
        op.create_index("ix_permissions_code", "permissions", ["code"])
    if not inspector.has_table("role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column(
                "role_id",
                sa.Integer(),
                sa.ForeignKey("roles.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "permission_id",
                sa.Integer(),
                sa.ForeignKey("permissions.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )
    if not inspector.has_table("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "role_id",
                sa.Integer(),
                sa.ForeignKey("roles.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "user_id", "organization_id", name="uq_user_roles_user_organization"
            ),
        )
        op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
        op.create_index("ix_user_roles_organization_id", "user_roles", ["organization_id"])
        op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    organizations = sa.table("organizations", sa.column("id"), sa.column("name"), sa.column("slug"))
    roles = sa.table("roles", sa.column("id"), sa.column("code"), sa.column("name"))
    permissions = sa.table("permissions", sa.column("id"), sa.column("code"), sa.column("name"))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id"), sa.column("permission_id")
    )
    user_roles = sa.table(
        "user_roles", sa.column("user_id"), sa.column("organization_id"), sa.column("role_id")
    )
    op.bulk_insert(organizations, [{"name": "本机演示组织", "slug": "local-demo"}])
    op.bulk_insert(
        roles,
        [
            {"code": "admin", "name": "管理员"},
            {"code": "lawyer", "name": "律师"},
            {"code": "member", "name": "普通用户"},
        ],
    )
    op.bulk_insert(permissions, [{"code": code, "name": code} for code in PERMISSIONS])

    role_ids = {
        code: role_id for role_id, code in bind.execute(sa.text("SELECT id, code FROM roles")).all()
    }
    permission_ids = {
        code: permission_id
        for permission_id, code in bind.execute(sa.text("SELECT id, code FROM permissions")).all()
    }
    organization_id = bind.execute(
        sa.text("SELECT id FROM organizations WHERE slug = 'local-demo'")
    ).scalar_one()
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role], "permission_id": permission_ids[permission]}
            for role, permission_codes in ROLE_PERMISSIONS.items()
            for permission in sorted(permission_codes)
        ],
    )
    existing_users = bind.execute(sa.text("SELECT id, is_superuser FROM users")).mappings().all()
    if existing_users:
        op.bulk_insert(
            user_roles,
            [
                {
                    "user_id": row["id"],
                    "organization_id": organization_id,
                    "role_id": role_ids["admin" if row["is_superuser"] else "member"],
                }
                for row in existing_users
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("user_roles", "role_permissions", "permissions", "roles", "organizations"):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
