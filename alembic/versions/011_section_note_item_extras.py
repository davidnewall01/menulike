"""Add Section.note (text) and MenuItem.extras (JSONB)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sections", sa.Column("note", sa.Text(), nullable=True))
    op.add_column(
        "menu_items",
        sa.Column("extras", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("menu_items", "extras")
    op.drop_column("sections", "note")
