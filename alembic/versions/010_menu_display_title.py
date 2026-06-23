"""Add display_title to menus.

Nullable — null falls back to name in templates.

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menus",
        sa.Column("display_title", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("menus", "display_title")
