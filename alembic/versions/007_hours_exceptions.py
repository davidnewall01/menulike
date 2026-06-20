"""hours_exceptions — date-specific closures and special hours per site.

Revision ID: 007
Revises: 006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hours_exceptions",
        sa.Column("hours_exception_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            UUID(as_uuid=True),
            sa.ForeignKey("site.site_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("is_closed", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("special_hours", JSONB, nullable=True),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hours_exceptions_site_id", "hours_exceptions", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_hours_exceptions_site_id", table_name="hours_exceptions")
    op.drop_table("hours_exceptions")
