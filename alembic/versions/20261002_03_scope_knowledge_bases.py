"""scope knowledge bases by organization

Revision ID: 20261002_03
Revises: 20261002_02
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_03"
down_revision = "20261002_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
    if "organization_id" not in columns:
        op.add_column("knowledge_bases", sa.Column("organization_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_knowledge_bases_organization_id",
            "knowledge_bases",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_knowledge_bases_organization_id", "knowledge_bases", ["organization_id"]
        )
    if "is_system_shared" not in columns:
        op.add_column(
            "knowledge_bases",
            sa.Column("is_system_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # 旧库没有可靠的组织归属；保守地保留为显式系统共享，避免升级后失去现有法规。
        op.execute(sa.text("UPDATE knowledge_bases SET is_system_shared = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}
    if "organization_id" in columns:
        op.drop_constraint(
            "fk_knowledge_bases_organization_id", "knowledge_bases", type_="foreignkey"
        )
        op.drop_index("ix_knowledge_bases_organization_id", table_name="knowledge_bases")
        op.drop_column("knowledge_bases", "organization_id")
    if "is_system_shared" in columns:
        op.drop_column("knowledge_bases", "is_system_shared")
