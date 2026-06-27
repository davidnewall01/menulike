"""020 -- Add is_visible flag to content_blocks.

Per-block show/hide toggle. Defaults true so existing blocks are unaffected.
Hidden blocks are excluded from public/preview rendering but remain in admin
for the owner to toggle back.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_blocks",
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("content_blocks", "is_visible")
