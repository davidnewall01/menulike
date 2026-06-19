"""site_image_roles — image role assignments linking sites to library photos.

Revision ID: 004
Revises: 003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_image_roles",
        sa.Column("site_image_role_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String, nullable=False),
        sa.Column(
            "photo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("photos.photo_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("site_id", "role", "position", name="uq_site_role_position"),
    )
    op.create_index("ix_site_image_roles_site_id", "site_image_roles", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_site_image_roles_site_id", table_name="site_image_roles")
    op.drop_table("site_image_roles")
