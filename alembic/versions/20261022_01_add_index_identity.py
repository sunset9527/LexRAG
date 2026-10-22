"""Add persistent identity fields for knowledge-base indexes.

Revision ID: 20261022_01
Revises: 20261021_01
Create Date: 2026-10-22
"""

import sqlalchemy as sa

from alembic import op

revision = "20261022_01"
down_revision = "20261021_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}

    if "source_hash" not in columns:
        op.add_column("knowledge_bases", sa.Column("source_hash", sa.String(length=64)))
    if "embedding_fingerprint" not in columns:
        op.add_column(
            "knowledge_bases", sa.Column("embedding_fingerprint", sa.String(length=128))
        )
    if "index_schema_version" not in columns:
        op.add_column("knowledge_bases", sa.Column("index_schema_version", sa.Integer()))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("knowledge_bases")}

    for column_name in ("index_schema_version", "embedding_fingerprint", "source_hash"):
        if column_name in columns:
            op.drop_column("knowledge_bases", column_name)
