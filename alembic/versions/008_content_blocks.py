"""content_blocks — flexible content blocks per site, keyed by page.

Revision ID: 008
Revises: 007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_blocks",
        sa.Column("block_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_key", sa.String, nullable=False),
        sa.Column("heading", sa.String, nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column(
            "image_photo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("photos.photo_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_blocks_site_id", "content_blocks", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_content_blocks_site_id", table_name="content_blocks")
    op.drop_table("content_blocks")
