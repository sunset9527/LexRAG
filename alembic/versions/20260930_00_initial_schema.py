"""Create the schema that existed before the versioned migration chain.

Revision ID: 20260930_00
Revises:
Create Date: 2026-09-30

This is intentionally a real baseline, rather than an Alembic stamp.  The
tables and constraints match the pre-2026-10-01 ORM models so an empty MySQL
database can upgrade through every later revision without application startup
creating tables out of band.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260930_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("hashed_password", sa.String(length=256), nullable=False),
            sa.Column("email", sa.String(length=128), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if not inspector.has_table("knowledge_bases"):
        op.create_table(
            "knowledge_bases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("type", sa.String(length=32), nullable=False),
            sa.Column("law_area", sa.String(length=64), nullable=False),
            sa.Column("collection_name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("document_count", sa.Integer(), nullable=False),
            sa.Column("chunk_count", sa.Integer(), nullable=False),
            sa.Column("last_indexed_at", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint("collection_name", name="uq_knowledge_bases_collection_name"),
        )
        op.create_index("ix_knowledge_bases_slug", "knowledge_bases", ["slug"], unique=True)

    if not inspector.has_table("chat_history"):
        op.create_table(
            "chat_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("intent", sa.String(length=32), nullable=True),
            sa.Column("citations", sa.JSON(), nullable=True),
            sa.Column("verification_status", sa.String(length=16), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index("ix_chat_history_user_id", "chat_history", ["user_id"])
        op.create_index("ix_chat_history_session_id", "chat_history", ["session_id"])

    if not inspector.has_table("prompts"):
        op.create_table(
            "prompts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.String(length=512), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.create_index("ix_prompts_name", "prompts", ["name"], unique=True)
        op.create_index("ix_prompts_category", "prompts", ["category"])

    if not inspector.has_table("document_jobs"):
        op.create_table(
            "document_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "knowledge_base_slug",
                sa.String(length=64),
                sa.ForeignKey("knowledge_bases.slug"),
                nullable=False,
            ),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("storage_path", sa.String(length=1024), nullable=False),
            sa.Column("parsed_text_path", sa.String(length=1024), nullable=True),
            sa.Column("file_type", sa.String(length=16), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False),
            sa.Column("chunk_size", sa.Integer(), nullable=False),
            sa.Column("chunk_overlap", sa.Integer(), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=True),
            sa.Column("character_count", sa.Integer(), nullable=True),
            sa.Column("chunk_count", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_document_jobs_knowledge_base_slug", "document_jobs", ["knowledge_base_slug"]
        )
        op.create_index("ix_document_jobs_sha256", "document_jobs", ["sha256"])

    if not inspector.has_table("favorites"):
        op.create_table(
            "favorites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("answer_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("citations", sa.JSON(), nullable=True),
            sa.Column("knowledge_base_slug", sa.String(length=128), nullable=True),
            sa.Column("law_area", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.UniqueConstraint(
                "user_id", "answer_fingerprint", name="uq_favorites_user_fingerprint"
            ),
        )
        op.create_index("ix_favorites_user_id", "favorites", ["user_id"])
        op.create_index("ix_favorites_knowledge_base_slug", "favorites", ["knowledge_base_slug"])
        op.create_index("ix_favorites_law_area", "favorites", ["law_area"])

    if not inspector.has_table("case_sources"):
        op.create_table(
            "case_sources",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("domain", sa.String(length=64), nullable=False),
            sa.Column("source_path", sa.String(length=1024), nullable=False),
            sa.Column("original_filename", sa.String(length=512), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=False),
            sa.Column("publisher_note", sa.Text(), nullable=False),
            sa.Column("origin_label", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("processed_pages", sa.Integer(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("ocr_engine", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("file_sha256", name="uq_case_sources_file_sha256"),
        )
        op.create_index("ix_case_sources_domain", "case_sources", ["domain"])

    if not inspector.has_table("case_ingestion_jobs"):
        op.create_table(
            "case_ingestion_jobs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("case_sources.id"), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("current_page", sa.Integer(), nullable=False),
            sa.Column("total_pages", sa.Integer(), nullable=False),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_case_ingestion_jobs_source_id", "case_ingestion_jobs", ["source_id"])

    if not inspector.has_table("legal_cases"):
        op.create_table(
            "legal_cases",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("case_sources.id"), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=512), nullable=True),
            sa.Column("domain", sa.String(length=64), nullable=False),
            sa.Column("case_cause", sa.String(length=255), nullable=False),
            sa.Column("court_name", sa.String(length=255), nullable=True),
            sa.Column("case_number", sa.String(length=255), nullable=True),
            sa.Column("judgment_date", sa.String(length=32), nullable=True),
            sa.Column("key_facts", sa.Text(), nullable=False),
            sa.Column("issues", sa.Text(), nullable=True),
            sa.Column("court_reasoning", sa.Text(), nullable=True),
            sa.Column("judgment_result", sa.Text(), nullable=True),
            sa.Column("judge_commentary", sa.Text(), nullable=True),
            sa.Column("legal_basis", sa.JSON(), nullable=False),
            sa.Column("source_start_page", sa.Integer(), nullable=False),
            sa.Column("source_end_page", sa.Integer(), nullable=False),
            sa.Column("extraction_warnings", sa.JSON(), nullable=False),
            sa.Column("indexed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_legal_cases_source_id", "legal_cases", ["source_id"])
        op.create_index("ix_legal_cases_domain", "legal_cases", ["domain"])
        op.create_index("ix_legal_cases_case_cause", "legal_cases", ["case_cause"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name in (
        "legal_cases",
        "case_ingestion_jobs",
        "case_sources",
        "favorites",
        "document_jobs",
        "prompts",
        "chat_history",
        "knowledge_bases",
        "users",
    ):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
