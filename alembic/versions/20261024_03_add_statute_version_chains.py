"""Add verified-source provenance and statute version chains for Stage 4.

Revision ID: 20261024_03
Revises: 20261024_02
Create Date: 2026-10-24
"""

import sqlalchemy as sa

from alembic import op

revision = "20261024_03"
down_revision = "20261024_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    source_columns = {
        column["name"] for column in inspector.get_columns("legal_source_imports")
    }
    if "verified_by_user_id" not in source_columns:
        op.add_column("legal_source_imports", sa.Column("verified_by_user_id", sa.Integer()))
    if "verified_at" not in source_columns:
        op.add_column("legal_source_imports", sa.Column("verified_at", sa.DateTime()))

    tables = set(inspector.get_table_names())
    if "statute_version_chains" not in tables:
        op.create_table(
            "statute_version_chains",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("law_slug", sa.String(length=64), nullable=False),
            sa.Column("target_version_id", sa.String(length=128), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("consolidated_source_import_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["consolidated_source_import_id"], ["legal_source_imports.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("target_version_id"),
        )
        op.create_index("ix_statute_version_chains_law_slug", "statute_version_chains", ["law_slug"])
        op.create_index(
            "ix_statute_version_chains_effective_from",
            "statute_version_chains",
            ["effective_from"],
        )
        op.create_index(
            "ix_statute_version_chains_effective_to", "statute_version_chains", ["effective_to"]
        )
    if "statute_version_chain_members" not in tables:
        op.create_table(
            "statute_version_chain_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("chain_id", sa.Integer(), nullable=False),
            sa.Column("source_import_id", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(["chain_id"], ["statute_version_chains.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["source_import_id"], ["legal_source_imports.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("chain_id", "source_import_id", name="uq_statute_chain_member_source"),
            sa.UniqueConstraint("chain_id", "sequence", name="uq_statute_chain_member_sequence"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "statute_version_chain_members" in tables:
        op.drop_table("statute_version_chain_members")
    if "statute_version_chains" in tables:
        op.drop_table("statute_version_chains")

    source_columns = {
        column["name"] for column in inspector.get_columns("legal_source_imports")
    }
    if "verified_at" in source_columns:
        op.drop_column("legal_source_imports", "verified_at")
    if "verified_by_user_id" in source_columns:
        op.drop_column("legal_source_imports", "verified_by_user_id")
