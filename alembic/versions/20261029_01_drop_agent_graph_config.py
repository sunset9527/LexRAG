"""drop retired knowledge graph configuration

Revision ID: 20261029_01
Revises: 20261024_03
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_01"
down_revision = "20261024_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_configs"):
        return
    names = {column["name"] for column in inspector.get_columns("agent_configs")}
    if "graph_search_enabled" in names:
        op.drop_column("agent_configs", "graph_search_enabled")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_configs"):
        return
    names = {column["name"] for column in inspector.get_columns("agent_configs")}
    if "graph_search_enabled" not in names:
        op.add_column(
            "agent_configs",
            sa.Column("graph_search_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
