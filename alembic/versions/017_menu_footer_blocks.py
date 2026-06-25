"""017 — Add menu_footer_blocks table.

Stores per-menu footer information: charges, dietary legends, glossary,
house rules. Each block has a type, optional title, and JSONB entries
(list of {label, description} pairs).

Revision ID: 017
Revises: 016
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "menu_footer_blocks",
        sa.Column("footer_block_id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "menu_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("menus.menu_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("block_type", sa.String(), nullable=False, server_default="info"),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("entries", JSONB(), nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("menu_footer_blocks")
