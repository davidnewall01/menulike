"""016 — Add photo_id FK to sections, subsections, and menu_items.

Allows attaching a single photo from the library to any section,
subsection, or menu item. Nullable — most entities won't have one.
ON DELETE SET NULL so deleting a photo doesn't cascade to menu structure.

Revision ID: 016
Revises: 015
"""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sections",
        sa.Column("photo_id", sa.UUID(as_uuid=True), sa.ForeignKey("photos.photo_id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "subsections",
        sa.Column("photo_id", sa.UUID(as_uuid=True), sa.ForeignKey("photos.photo_id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "menu_items",
        sa.Column("photo_id", sa.UUID(as_uuid=True), sa.ForeignKey("photos.photo_id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("menu_items", "photo_id")
    op.drop_column("subsections", "photo_id")
    op.drop_column("sections", "photo_id")
