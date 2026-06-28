"""022 -- Add thumbnail_key to site for showcase screenshots.

A marketing screenshot stored in S3, NOT a restaurant photo. Only
populated for showcase sites; nullable for everyone else. Does not
go through photo_service / image-role system.

Revision ID: 022
Revises: 021
"""

import sqlalchemy as sa
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site",
        sa.Column("thumbnail_key", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site", "thumbnail_key")
