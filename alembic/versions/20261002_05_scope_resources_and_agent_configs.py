"""scope user resources and add safe agent configs

Revision ID: 20261002_05
Revises: 20261002_04
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_05"
down_revision = "20261002_04"
branch_labels = None
depends_on = None


def _add_organization_column(table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    names = {column["name"] for column in inspector.get_columns(table_name)}
    if "organization_id" not in names:
        op.add_column(table_name, sa.Column("organization_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_organization_id",
            table_name,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(f"ix_{table_name}_organization_id", table_name, ["organization_id"])
    # 历史个人资源只能落到演示组织，避免升级后隐式跨组织读取。
    op.execute(
        sa.text(
            "UPDATE "
            + table_name
            + " SET organization_id = (SELECT id FROM organizations WHERE slug = 'local-demo') WHERE organization_id IS NULL"
        )
    )


def upgrade() -> None:
    for table_name in ("sessions", "chat_history", "favorites", "scenario_jobs"):
        _add_organization_column(table_name)
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_configs"):
        op.create_table(
            "agent_configs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "case_search_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "graph_search_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
            sa.Column(
                "model_alias", sa.String(64), nullable=False, server_default="browser-configured"
            ),
            sa.Column("version_note", sa.String(256), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint("organization_id", name="uq_agent_configs_organization"),
        )
        op.create_index("ix_agent_configs_organization_id", "agent_configs", ["organization_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("agent_configs"):
        op.drop_table("agent_configs")
    for table_name in ("scenario_jobs", "favorites", "chat_history", "sessions"):
        if inspector.has_table(table_name):
            names = {column["name"] for column in inspector.get_columns(table_name)}
            if "organization_id" in names:
                op.drop_constraint(
                    f"fk_{table_name}_organization_id", table_name, type_="foreignkey"
                )
                op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)
                op.drop_column(table_name, "organization_id")
