"""Add Site.is_published (boolean, NOT NULL, server_default false).

New sites start unpublished — the owner publishes deliberately from the
dashboard once core content is real.

Back-fill: all pre-existing sites are set to is_published=true because
they were previously live with no publish gate. The server_default=false
governs only genuinely new rows created after this migration.
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site",
        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Back-fill: every site that existed before this migration was previously
    # live (no publish gate existed). Set them all to published so they don't
    # go dark. The server_default=false handles all future rows.
    op.execute("UPDATE site SET is_published = true")


def downgrade() -> None:
    op.drop_column("site", "is_published")
