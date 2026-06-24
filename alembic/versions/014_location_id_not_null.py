"""014 — Set location_id NOT NULL on regular_hours and hours_exceptions.

Phase 1 (013) added location_id as nullable and backfilled all existing rows.
This migration asserts completeness, then applies the NOT NULL constraint.

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"


def upgrade() -> None:
    # Verify no nulls exist before applying constraint
    conn = op.get_bind()
    null_hours = conn.execute(sa.text(
        "SELECT COUNT(*) FROM regular_hours WHERE location_id IS NULL"
    )).scalar()
    null_exc = conn.execute(sa.text(
        "SELECT COUNT(*) FROM hours_exceptions WHERE location_id IS NULL"
    )).scalar()
    if null_hours or null_exc:
        raise RuntimeError(
            f"Cannot apply NOT NULL: {null_hours} regular_hours and "
            f"{null_exc} hours_exceptions rows have NULL location_id"
        )

    op.alter_column("regular_hours", "location_id", nullable=False)
    op.alter_column("hours_exceptions", "location_id", nullable=False)


def downgrade() -> None:
    op.alter_column("hours_exceptions", "location_id", nullable=True)
    op.alter_column("regular_hours", "location_id", nullable=True)
