"""add document analysis tables

Revision ID: 20261001_02
Revises: 20261001_01
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_02"
down_revision = "20261001_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("document_pages"):
        op.create_table(
            "document_pages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "document_id",
                sa.String(length=36),
                sa.ForeignKey("document_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("raw_text", sa.Text(), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("ocr_confidence", sa.Float(), nullable=True),
            sa.Column("tables", sa.JSON(), nullable=True),
            sa.Column("header", sa.Text(), nullable=True),
            sa.Column("footer", sa.Text(), nullable=True),
            sa.Column("parse_warnings", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.CheckConstraint("page_number >= 1", name="ck_document_pages_page_number"),
            sa.UniqueConstraint(
                "document_id", "page_number", name="uq_document_pages_document_page"
            ),
        )
        op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])

    if not inspector.has_table("document_structures"):
        op.create_table(
            "document_structures",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "document_id",
                sa.String(length=36),
                sa.ForeignKey("document_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("document_type", sa.String(length=32), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("parser_version", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("document_id", name="uq_document_structures_document"),
        )
        op.create_index(
            "ix_document_structures_document_id", "document_structures", ["document_id"]
        )

    if not inspector.has_table("document_relations"):
        op.create_table(
            "document_relations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "source_document_id",
                sa.String(length=36),
                sa.ForeignKey("document_jobs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source_locator", sa.String(length=128), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.String(length=128), nullable=False),
            sa.Column("relation_type", sa.String(length=32), nullable=False),
            sa.Column("law_article", sa.String(length=128), nullable=True),
            sa.Column("similarity", sa.Float(), nullable=True),
            sa.Column("evidence_text", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=32), nullable=False),
            sa.Column("engine_version", sa.String(length=32), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "law_article IS NOT NULL OR similarity IS NOT NULL OR evidence_text IS NOT NULL",
                name="ck_document_relations_evidence",
            ),
        )
        op.create_index(
            "ix_document_relations_source_document_id", "document_relations", ["source_document_id"]
        )
        op.create_index("ix_document_relations_target_id", "document_relations", ["target_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in ("document_relations", "document_structures", "document_pages"):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
