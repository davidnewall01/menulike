"""024 -- Add is_available flag to template_meta.

Gates which templates are offered as choices (create-showcase, appearance
picker). Existing sites on an unavailable template keep rendering — this
flag controls OFFERING only, never rendering.

Seed: Linen=available (complete), Olive/Slate=unavailable (homepage spikes).

Revision ID: 024
Revises: 023
"""

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "template_meta",
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Linen is the only complete template
    op.execute("UPDATE template_meta SET is_available = true WHERE template_key = 'linen'")


def downgrade() -> None:
    op.drop_column("template_meta", "is_available")
