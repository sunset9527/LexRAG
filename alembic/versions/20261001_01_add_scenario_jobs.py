"""add scenario jobs

Revision ID: 20261001_01
Revises:
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("scenario_jobs"):
        return
    op.create_table(
        "scenario_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scenario_type", sa.String(length=48), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("result_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scenario_jobs_user_id", "scenario_jobs", ["user_id"])
    op.create_index("ix_scenario_jobs_scenario_type", "scenario_jobs", ["scenario_type"])


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("scenario_jobs"):
        op.drop_table("scenario_jobs")
