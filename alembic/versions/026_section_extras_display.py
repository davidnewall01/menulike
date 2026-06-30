"""026 -- Add extras_display to sections.

Controls how item extras render: "inline" (compact, separated by middots)
or "stacked" (one per line, price right-aligned). Same pattern as the
existing variant_display field.

Revision ID: 026
Revises: 025
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sections",
        sa.Column("extras_display", sa.String(), nullable=False, server_default="inline"),
    )


def downgrade() -> None:
    op.drop_column("sections", "extras_display")
