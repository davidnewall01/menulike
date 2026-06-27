"""019 -- Add nullable event_date to content_blocks.

Enables content_block reuse for events: blocks with an event_date are
"upcoming events" (date-sorted, auto-hide after date passes); blocks
without are "standing specials" (drag-ordered, never auto-hide).

Revision ID: 019
Revises: 018
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_blocks",
        sa.Column("event_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_blocks", "event_date")
