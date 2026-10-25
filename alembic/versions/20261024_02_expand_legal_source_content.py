"""Expand local legal-source body storage beyond MySQL TEXT capacity.

Revision ID: 20261024_02
Revises: 20261024_01
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "20261024_02"
down_revision = "20261024_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "legal_source_imports" not in inspector.get_table_names():
        return
    op.alter_column("legal_source_imports", "content", existing_type=sa.Text(), type_=mysql.MEDIUMTEXT())


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "legal_source_imports" not in inspector.get_table_names():
        return
    op.alter_column(
        "legal_source_imports", "content", existing_type=mysql.MEDIUMTEXT(), type_=sa.Text()
    )
