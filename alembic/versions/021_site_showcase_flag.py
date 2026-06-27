"""021 -- Add showcase flag to site.

Marks admin-owned sites used as curated template demos in the picker.
Showcase sites are normal Site rows with no bound owner user.
showcase_position controls display order in the picker (NULL for non-showcase).

Revision ID: 021
Revises: 020
"""

import sqlalchemy as sa
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site",
        sa.Column("is_showcase", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "site",
        sa.Column("showcase_position", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site", "showcase_position")
    op.drop_column("site", "is_showcase")
