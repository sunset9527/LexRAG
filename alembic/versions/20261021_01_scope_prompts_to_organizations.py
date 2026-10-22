"""Scope prompt versions to organizations.

Revision ID: 20261021_01
Revises: 20261002_07
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_01"
down_revision = "20261002_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = inspector.get_unique_constraints("prompts")
    unique_indexes = inspector.get_indexes("prompts")
    unique_name_constraint = next(
        (
            item.get("name")
            for item in unique_constraints
            if item.get("column_names") == ["name"] and item.get("name")
        ),
        None,
    )
    unique_name_index = next(
        (
            item.get("name")
            for item in unique_indexes
            if item.get("unique")
            and item.get("column_names") == ["name"]
            and item.get("name")
        ),
        None,
    )

    with op.batch_alter_table("prompts") as batch:
        if unique_name_constraint:
            batch.drop_constraint(unique_name_constraint, type_="unique")
        elif unique_name_index:
            batch.drop_index(unique_name_index)
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_prompts_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint(
            "uq_prompts_organization_name_version",
            ["organization_id", "name", "version"],
        )
        batch.create_index("ix_prompts_organization_id", ["organization_id"])


def downgrade() -> None:
    with op.batch_alter_table("prompts") as batch:
        batch.drop_index("ix_prompts_organization_id")
        batch.drop_constraint("uq_prompts_organization_name_version", type_="unique")
        batch.drop_constraint("fk_prompts_organization_id", type_="foreignkey")
        batch.drop_column("organization_id")
        batch.create_unique_constraint("uq_prompts_name", ["name"])
