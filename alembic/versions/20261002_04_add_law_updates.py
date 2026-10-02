"""add law update subscriptions

Revision ID: 20261002_04
Revises: 20261002_03
"""
import sqlalchemy as sa
from alembic import op
revision="20261002_04"; down_revision="20261002_03"; branch_labels=None; depends_on=None
def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("law_subscriptions"):
        op.create_table("law_subscriptions", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False), sa.Column("law_name",sa.String(128),nullable=False), sa.Column("source_url",sa.String(1024),nullable=False), sa.Column("last_content_hash",sa.String(64)), sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()), sa.Column("created_at",sa.DateTime(),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False), sa.UniqueConstraint("organization_id","law_name",name="uq_law_subscription_org_name"))
    if not inspector.has_table("law_update_events"):
        op.create_table("law_update_events", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("subscription_id",sa.Integer(),sa.ForeignKey("law_subscriptions.id",ondelete="CASCADE"),nullable=False), sa.Column("previous_hash",sa.String(64)),sa.Column("current_hash",sa.String(64),nullable=False),sa.Column("diff_preview",sa.Text(),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("reviewer_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("created_at",sa.DateTime(),server_default=sa.text("CURRENT_TIMESTAMP"),nullable=False),sa.Column("reviewed_at",sa.DateTime()))
def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("law_update_events"): op.drop_table("law_update_events")
    if inspector.has_table("law_subscriptions"): op.drop_table("law_subscriptions")
