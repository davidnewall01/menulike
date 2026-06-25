"""013 — Location entity + re-parent hours to location (expand step).

Creates the `location` table, backfills one default Location per site
from Site.address_*/phone/email, adds nullable location_id FK to
regular_hours and hours_exceptions, backfills location_id from site_id
join. The NOT NULL constraint is applied in 014 (contract step).

Revision ID: 013
Revises: 012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "013"
down_revision = "012"


def upgrade() -> None:
    # 1. Create location table
    op.create_table(
        "location",
        sa.Column("location_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("site_id", UUID(as_uuid=True), sa.ForeignKey("site.site_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("address_street", sa.String, nullable=True),
        sa.Column("address_suburb", sa.String, nullable=True),
        sa.Column("address_state", sa.String, nullable=True),
        sa.Column("address_postcode", sa.String, nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("position", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Backfill one default Location per site, copying address + contact
    op.execute("""
        INSERT INTO location (site_id, label, address_street, address_suburb,
                              address_state, address_postcode, phone, email, position)
        SELECT site_id, NULL, address_street, address_suburb,
               address_state, address_postcode, phone, email, 0
        FROM site
    """)

    # 3. Add nullable location_id to regular_hours
    op.add_column("regular_hours", sa.Column(
        "location_id", UUID(as_uuid=True), nullable=True, index=True,
    ))

    # 4. Add nullable location_id to hours_exceptions
    op.add_column("hours_exceptions", sa.Column(
        "location_id", UUID(as_uuid=True), nullable=True, index=True,
    ))

    # 5. Backfill location_id on regular_hours from the site's default location
    op.execute("""
        UPDATE regular_hours rh
        SET location_id = loc.location_id
        FROM location loc
        WHERE loc.site_id = rh.site_id
    """)

    # 6. Backfill location_id on hours_exceptions
    op.execute("""
        UPDATE hours_exceptions he
        SET location_id = loc.location_id
        FROM location loc
        WHERE loc.site_id = he.site_id
    """)

    # 7. Verify backfill completeness (warn, don't block — existing rows are covered)
    conn = op.get_bind()
    null_hours = conn.execute(sa.text(
        "SELECT COUNT(*) FROM regular_hours WHERE location_id IS NULL"
    )).scalar()
    null_exc = conn.execute(sa.text(
        "SELECT COUNT(*) FROM hours_exceptions WHERE location_id IS NULL"
    )).scalar()
    if null_hours or null_exc:
        raise RuntimeError(
            f"Backfill incomplete: {null_hours} regular_hours and "
            f"{null_exc} hours_exceptions rows still have NULL location_id"
        )

    # 8. Add FK constraints (keep nullable — NOT NULL applied in Phase 2
    # after services are cut over to always provide location_id)
    op.create_foreign_key(
        "fk_regular_hours_location_id",
        "regular_hours", "location",
        ["location_id"], ["location_id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_hours_exceptions_location_id",
        "hours_exceptions", "location",
        ["location_id"], ["location_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Drop FK constraints on location_id
    op.drop_constraint("fk_hours_exceptions_location_id", "hours_exceptions", type_="foreignkey")
    op.drop_constraint("fk_regular_hours_location_id", "regular_hours", type_="foreignkey")

    # Drop location_id columns
    op.drop_column("hours_exceptions", "location_id")
    op.drop_column("regular_hours", "location_id")

    # Drop location table
    op.drop_table("location")
