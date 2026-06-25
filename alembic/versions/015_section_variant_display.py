"""015 — Add variant_display column to sections.

Allows per-section choice of how item variants are rendered:
  "inline"   — variants listed under each item (default, existing behaviour)
  "columnar" — variant labels as column headers, prices in a grid

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sections",
        sa.Column(
            "variant_display",
            sa.String(),
            nullable=False,
            server_default="inline",
        ),
    )


def downgrade() -> None:
    op.drop_column("sections", "variant_display")
