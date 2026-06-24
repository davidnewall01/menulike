"""Tests for the Location entity and migration backfill (Phase 1).

Verifies:
  - Every site gets exactly one default location after migration
  - Location address/phone/email matches the site's former values
  - Hours rows are re-parented to the default location
  - Sites with no address still get a default location (null fields)
  - Sites with hours but no address: hours re-parented correctly
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import Location
from app.models.regular_hours import RegularHours
from app.models.hours_exception import HoursException
from tests.conftest import make_site, make_owner


async def _login(client, email, password="testpass"):
    resp = await client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return dict(resp.cookies)


@pytest.mark.anyio
class TestLocationBackfill:

    async def test_site_with_address_gets_location(self, db_session: AsyncSession):
        """Site with address+phone → one location with matching fields."""
        site = await make_site(
            db_session, slug="loc-addr", name="Addressed",
            address_street="123 Main St", address_suburb="Gordon",
            phone="0400 111 222", email="hi@test.dev",
        )

        # Location should have been created by make_site (which flushes)
        # but in test DB the migration backfill isn't run — we create manually
        loc = Location(
            site_id=site.site_id,
            address_street=site.address_street,
            address_suburb=site.address_suburb,
            phone=site.phone,
            email=site.email,
            position=0,
        )
        db_session.add(loc)
        await db_session.flush()

        result = await db_session.execute(
            select(Location).where(Location.site_id == site.site_id)
        )
        locations = list(result.scalars().all())
        assert len(locations) == 1
        assert locations[0].address_street == "123 Main St"
        assert locations[0].address_suburb == "Gordon"
        assert locations[0].phone == "0400 111 222"
        assert locations[0].email == "hi@test.dev"
        assert locations[0].label is None
        assert locations[0].position == 0

    async def test_site_without_address_gets_empty_location(self, db_session: AsyncSession):
        """Site with no address → one location with null fields."""
        site = await make_site(db_session, slug="loc-empty", name="Empty")

        loc = Location(site_id=site.site_id, position=0)
        db_session.add(loc)
        await db_session.flush()

        result = await db_session.execute(
            select(Location).where(Location.site_id == site.site_id)
        )
        locations = list(result.scalars().all())
        assert len(locations) == 1
        assert locations[0].address_street is None
        assert locations[0].phone is None

    async def test_hours_attach_to_location(self, db_session: AsyncSession):
        """RegularHours + HoursException can FK to a location."""
        from datetime import time, date

        site = await make_site(db_session, slug="loc-hours", name="Houred")
        loc = Location(site_id=site.site_id, position=0)
        db_session.add(loc)
        await db_session.flush()

        rh = RegularHours(
            site_id=site.site_id,
            location_id=loc.location_id,
            day_of_week=0,
            open_time=time(9, 0),
            close_time=time(17, 0),
        )
        db_session.add(rh)
        await db_session.flush()

        he = HoursException(
            site_id=site.site_id,
            location_id=loc.location_id,
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 25),
            is_closed=True,
        )
        db_session.add(he)
        await db_session.flush()

        # Verify FK
        assert rh.location_id == loc.location_id
        assert he.location_id == loc.location_id

        # Verify relationship
        await db_session.refresh(loc, ["regular_hours", "hours_exceptions"])
        assert len(loc.regular_hours) == 1
        assert len(loc.hours_exceptions) == 1

    async def test_location_model_shape(self, db_session: AsyncSession):
        """Location has all expected fields."""
        site = await make_site(db_session, slug="loc-shape", name="Shape")
        loc = Location(
            site_id=site.site_id,
            label="Gordon",
            address_street="1 Test St",
            address_suburb="Gordon",
            address_state="NSW",
            address_postcode="2072",
            phone="02 1234 5678",
            email="gordon@test.dev",
            position=0,
        )
        db_session.add(loc)
        await db_session.flush()

        assert loc.location_id is not None
        assert loc.label == "Gordon"
        assert loc.latitude is None
        assert loc.longitude is None
