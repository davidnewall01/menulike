"""030 -- Add service_info column to site.

A single pipe-delimited text field for venue service details
(e.g. "Dine-in or take away | Fully licensed | BYO wine only").

Revision ID: 030
Revises: 029
"""

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site", sa.Column("service_info", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("site", "service_info")
