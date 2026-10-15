"""link law subscriptions to statute knowledge bases

Revision ID: 20261002_07
Revises: 20261002_06
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_07"
down_revision = "20261002_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("law_subscriptions")}
    if "knowledge_base_slug" not in columns:
        op.add_column(
            "law_subscriptions", sa.Column("knowledge_base_slug", sa.String(64), nullable=True)
        )
        op.create_index(
            "ix_law_subscriptions_knowledge_base_slug", "law_subscriptions", ["knowledge_base_slug"]
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("law_subscriptions")}
    if "knowledge_base_slug" in columns:
        op.drop_index("ix_law_subscriptions_knowledge_base_slug", table_name="law_subscriptions")
        op.drop_column("law_subscriptions", "knowledge_base_slug")
