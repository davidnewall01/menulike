"""Tests for the Location entity, services, and IDOR guards.

Phase 1: entity + backfill shape.
Phase 2: location CRUD, hours cutover, IDOR.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.location import Location
from app.models.regular_hours import RegularHours
from app.models.hours_exception import HoursException
from app.services import location_service, hours_service, hours_exception_service
from app.services.exceptions import LocationNotFound, NoSiteInScope
from app.services.hours_service import HoursRangeNotFound
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

    async def test_site_with_address_gets_default_location(self, db_session: AsyncSession):
        """make_site auto-creates a default location with matching address/contact."""
        site = await make_site(
            db_session, slug="loc-addr", name="Addressed",
            address_street="123 Main St", address_suburb="Gordon",
            phone="0400 111 222", email="hi@test.dev",
        )

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
        """Site with no address → one default location with null fields."""
        site = await make_site(db_session, slug="loc-empty", name="Empty")

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
        # Use the auto-created default location
        result = await db_session.execute(
            select(Location).where(Location.site_id == site.site_id)
        )
        loc = result.scalar_one()

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

        assert rh.location_id == loc.location_id
        assert he.location_id == loc.location_id

        await db_session.refresh(loc, ["regular_hours", "hours_exceptions"])
        assert len(loc.regular_hours) == 1
        assert len(loc.hours_exceptions) == 1

    async def test_location_model_shape(self, db_session: AsyncSession):
        """Location has all expected fields via explicit creation."""
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
            position=1,
        )
        db_session.add(loc)
        await db_session.flush()

        assert loc.location_id is not None
        assert loc.label == "Gordon"
        assert loc.latitude is None
        assert loc.longitude is None


# ---------------------------------------------------------------------------
# Phase 2 — Location service CRUD + IDOR
# ---------------------------------------------------------------------------

def _auth(site) -> AuthContext:
    """Build a fake auth context for the given site."""
    return AuthContext(
        user_id=uuid.uuid4(), email="test@test.dev",
        role="owner", site_id=site.site_id,
    )


@pytest.mark.anyio
class TestLocationServiceCRUD:

    async def test_create_and_list(self, db_session: AsyncSession):
        site = await make_site(db_session, slug="loc-crud", name="CRUD")
        auth = _auth(site)

        loc = await location_service.create_location(
            db_session, auth, label="Gordon",
            address_street="1 Test St", phone="0400",
        )
        await db_session.flush()

        locations = await location_service.list_locations(db_session, auth)
        assert any(l.location_id == loc.location_id for l in locations)
        assert loc.label == "Gordon"
        assert loc.phone == "0400"

    async def test_update(self, db_session: AsyncSession):
        site = await make_site(db_session, slug="loc-upd", name="Update")
        auth = _auth(site)
        loc = await location_service.create_location(
            db_session, auth, label="Old",
        )
        await db_session.flush()

        updated = await location_service.update_location(
            db_session, auth, loc.location_id, label="New", phone="9999",
        )
        assert updated.label == "New"
        assert updated.phone == "9999"

    async def test_delete(self, db_session: AsyncSession):
        site = await make_site(db_session, slug="loc-del", name="Delete")
        auth = _auth(site)
        loc = await location_service.create_location(db_session, auth, label="Gone")
        await db_session.flush()

        await location_service.delete_location(db_session, auth, loc.location_id)
        await db_session.flush()

        with pytest.raises(LocationNotFound):
            await location_service.get_owner_location(db_session, auth, loc.location_id)


@pytest.mark.anyio
class TestLocationIDOR:

    async def test_foreign_location_not_found(self, db_session: AsyncSession):
        """Requesting another site's location → LocationNotFound."""
        site_a = await make_site(db_session, slug="idor-a", name="A")
        site_b = await make_site(db_session, slug="idor-b", name="B")
        auth_a = _auth(site_a)
        auth_b = _auth(site_b)

        loc_a = await location_service.create_location(
            db_session, auth_a, label="A's place",
        )
        await db_session.flush()

        # B tries to access A's location
        with pytest.raises(LocationNotFound):
            await location_service.get_owner_location(
                db_session, auth_b, loc_a.location_id,
            )

    async def test_foreign_location_hours_idor(self, db_session: AsyncSession):
        """Adding hours under a foreign location_id → LocationNotFound."""
        from datetime import time

        site_a = await make_site(db_session, slug="h-idor-a", name="HA")
        site_b = await make_site(db_session, slug="h-idor-b", name="HB")
        auth_a = _auth(site_a)
        auth_b = _auth(site_b)

        loc_a = await location_service.create_location(db_session, auth_a)
        await db_session.flush()

        # B tries to add hours to A's location
        with pytest.raises(LocationNotFound):
            await hours_service.add_range(
                db_session, auth_b,
                day_of_week=0, open_time=time(9, 0), close_time=time(17, 0),
                location_id=loc_a.location_id,
            )


@pytest.mark.anyio
class TestHoursLocationCutover:

    async def test_hours_scoped_to_location(self, db_session: AsyncSession):
        """Hours added with location_id are scoped to that location."""
        from datetime import time

        site = await make_site(db_session, slug="h-scope", name="Scoped")
        auth = _auth(site)
        loc = await location_service.create_location(db_session, auth)
        await db_session.flush()

        rh = await hours_service.add_range(
            db_session, auth,
            day_of_week=1, open_time=time(10, 0), close_time=time(22, 0),
            location_id=loc.location_id,
        )
        assert rh.location_id == loc.location_id
        assert rh.site_id == site.site_id

        # List by location returns it
        hours = await hours_service.list_hours(db_session, auth, location_id=loc.location_id)
        assert len(hours) == 1

    async def test_default_location_fallback(self, db_session: AsyncSession):
        """Adding hours without location_id uses the site's default location."""
        from datetime import time

        site = await make_site(db_session, slug="h-default", name="Default")
        auth = _auth(site)
        # make_site auto-creates a default location (position=0)
        default = await location_service.get_default_location(db_session, auth)

        rh = await hours_service.add_range(
            db_session, auth,
            day_of_week=3, open_time=time(11, 0), close_time=time(23, 0),
            # No location_id — should use default
        )
        assert rh.location_id == default.location_id

    async def test_exception_with_location(self, db_session: AsyncSession):
        """Exceptions can be scoped to a location."""
        from datetime import date

        site = await make_site(db_session, slug="exc-loc", name="ExcLoc")
        auth = _auth(site)
        loc = await location_service.create_location(db_session, auth)
        await db_session.flush()

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            start_date=date(2026, 12, 25), end_date=date(2026, 12, 25),
            is_closed=True, special_hours=None, label="Christmas",
            location_id=loc.location_id,
        )
        assert exc.location_id == loc.location_id

        excs = await hours_exception_service.list_exceptions(
            db_session, auth, location_id=loc.location_id,
        )
        assert len(excs) == 1
