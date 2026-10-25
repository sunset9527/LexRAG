"""Persist locally supplied legal-source candidates for Stage 4 review.

Revision ID: 20261024_01
Revises: 20261022_01
Create Date: 2026-10-24
"""

import sqlalchemy as sa

from alembic import op

revision = "20261024_01"
down_revision = "20261022_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "legal_source_imports" in inspector.get_table_names():
        return

    op.create_table(
        "legal_source_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("law_slug", sa.String(length=64), nullable=False),
        sa.Column("law_name", sa.String(length=128), nullable=False),
        sa.Column("version_id", sa.String(length=128), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("promulgated_on", sa.Date(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("source_status", sa.String(length=40), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("authority_status", sa.String(length=40), nullable=False),
        sa.Column("authority_url", sa.String(length=1024), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "raw_sha256", name="uq_legal_source_import_version_raw"),
    )
    op.create_index("ix_legal_source_imports_law_slug", "legal_source_imports", ["law_slug"])
    op.create_index("ix_legal_source_imports_version_id", "legal_source_imports", ["version_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "legal_source_imports" in inspector.get_table_names():
        op.drop_table("legal_source_imports")
