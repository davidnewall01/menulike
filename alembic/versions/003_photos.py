"""photos table — per-site photo library.

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("photo_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("s3_key", sa.String, nullable=False),
        sa.Column("original_filename", sa.String, nullable=True),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("alt_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_photos_site_id", "photos", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_photos_site_id", table_name="photos")
    op.drop_table("photos")
