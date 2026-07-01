"""027 -- Add hours service-period label + location hours_display_mode.

`regular_hours.label` tags a range as a named service period
(None | breakfast | lunch | dinner) so the public template can group hours
by service. `location.hours_display_mode` chooses how hours render publicly:
"detailed" (every day listed) or "summary" (grouped).

Revision ID: 027
Revises: 026
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "regular_hours",
        sa.Column("label", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "location",
        sa.Column(
            "hours_display_mode",
            sa.String(),
            nullable=False,
            server_default="detailed",
        ),
    )


def downgrade() -> None:
    op.drop_column("location", "hours_display_mode")
    op.drop_column("regular_hours", "label")
