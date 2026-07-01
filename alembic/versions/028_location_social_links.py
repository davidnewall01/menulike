"""028 -- Add social_links to location.

Per-location social handles as a JSONB list of {platform, url}, defaulting to
[]. Feeds the visit resolver -> Crema footer social row. Admin editing comes
in a later task.

Revision ID: 028
Revises: 027
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "location",
        sa.Column("social_links", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("location", "social_links")
