"""Add template column to site — drives public template resolution.

Revision ID: 005
Revises: 004
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site",
        sa.Column("template", sa.String, nullable=False, server_default="linen"),
    )


def downgrade() -> None:
    op.drop_column("site", "template")
