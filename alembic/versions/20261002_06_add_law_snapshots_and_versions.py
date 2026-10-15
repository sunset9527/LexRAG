"""add law source snapshots and confirmed versions

Revision ID: 20261002_06
Revises: 20261002_05
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_06"
down_revision = "20261002_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("law_source_snapshots"):
        op.create_table(
            "law_source_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "subscription_id",
                sa.Integer(),
                sa.ForeignKey("law_subscriptions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "fetched_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "subscription_id", "content_hash", name="uq_law_snapshot_subscription_hash"
            ),
        )
        op.create_index(
            "ix_law_source_snapshots_subscription_id", "law_source_snapshots", ["subscription_id"]
        )
        op.create_index(
            "ix_law_source_snapshots_content_hash", "law_source_snapshots", ["content_hash"]
        )
    if not inspector.has_table("law_versions"):
        op.create_table(
            "law_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "subscription_id",
                sa.Integer(),
                sa.ForeignKey("law_subscriptions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "snapshot_id",
                sa.Integer(),
                sa.ForeignKey("law_source_snapshots.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column(
                "confirmed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")
            ),
            sa.Column(
                "confirmed_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "subscription_id", "content_hash", name="uq_law_version_subscription_hash"
            ),
        )
        op.create_index("ix_law_versions_subscription_id", "law_versions", ["subscription_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("law_versions"):
        op.drop_table("law_versions")
    if inspector.has_table("law_source_snapshots"):
        op.drop_table("law_source_snapshots")
