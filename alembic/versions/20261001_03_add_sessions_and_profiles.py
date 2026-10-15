"""add sessions and user profiles

Revision ID: 20261001_03
Revises: 20261001_02
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_03"
down_revision = "20261001_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=120), nullable=False),
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
        )
        op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
        op.create_index(
            "ix_sessions_user_active_updated", "sessions", ["user_id", "is_active", "updated_at"]
        )
    if not inspector.has_table("user_profiles"):
        op.create_table(
            "user_profiles",
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("law_area_counts", sa.JSON(), nullable=False),
            sa.Column("intent_counts", sa.JSON(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("user_profiles"):
        op.drop_table("user_profiles")
    if inspector.has_table("sessions"):
        op.drop_table("sessions")
