"""add audit logs and usage aggregates

Revision ID: 20261002_02
Revises: 20261002_01
Create Date: 2026-10-02
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_02"
down_revision = "20261002_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=64), nullable=False),
            sa.Column("target_id", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("event_id", name="uq_audit_logs_event_id"),
        )
        for column in ("event_id", "organization_id", "actor_user_id", "action", "request_id"):
            op.create_index(f"ix_audit_logs_{column}", "audit_logs", [column])
    if not inspector.has_table("usage_daily"):
        op.create_table(
            "usage_daily",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("query_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cache_hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("estimated_token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("organization_id", "stat_date", name="uq_usage_daily_org_date"),
        )
        op.create_index("ix_usage_daily_organization_id", "usage_daily", ["organization_id"])
    if not inspector.has_table("usage_events"):
        op.create_table(
            "usage_events",
            sa.Column("event_id", sa.String(length=64), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )
        op.create_index("ix_usage_events_organization_id", "usage_events", ["organization_id"])
        op.create_index("ix_usage_events_actor_user_id", "usage_events", ["actor_user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("usage_events", "usage_daily", "audit_logs"):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
