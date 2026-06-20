"""Regular hours tests — CRUD, IDOR, overnight ranges."""

import uuid
from datetime import time

import pytest
from sqlalchemy import select

from app.auth.context import AuthContext
from app.models.regular_hours import RegularHours
from app.services import hours_service
from app.services.hours_service import HoursRangeNotFound
from app.services.exceptions import NoSiteInScope
from tests.conftest import make_owner, make_site


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


# ---------------------------------------------------------------------------
# Add range
# ---------------------------------------------------------------------------

class TestAddRange:

    async def test_add_range(self, db_session):
        site = await make_site(db_session, slug="hours-add")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        row = await hours_service.add_range(db_session, auth, 0, time(9, 0), time(17, 0))
        assert row.day_of_week == 0
        assert row.open_time == time(9, 0)
        assert row.close_time == time(17, 0)
        assert row.site_id == site.site_id

    async def test_multiple_ranges_per_day(self, db_session):
        site = await make_site(db_session, slug="hours-multi")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        await hours_service.add_range(db_session, auth, 5, time(12, 0), time(15, 0))
        await hours_service.add_range(db_session, auth, 5, time(17, 30), time(22, 0))

        hours = await hours_service.list_hours(db_session, auth)
        sat_hours = [h for h in hours if h.day_of_week == 5]
        assert len(sat_hours) == 2
        assert sat_hours[0].open_time == time(12, 0)  # lunch sorts first
        assert sat_hours[1].open_time == time(17, 30)  # dinner sorts second

    async def test_overnight_range_accepted(self, db_session):
        """close_time < open_time is valid (e.g. 18:00-01:00 overnight)."""
        site = await make_site(db_session, slug="hours-overnight")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        row = await hours_service.add_range(db_session, auth, 4, time(18, 0), time(1, 0))
        assert row.open_time == time(18, 0)
        assert row.close_time == time(1, 0)


# ---------------------------------------------------------------------------
# Update range
# ---------------------------------------------------------------------------

class TestUpdateRange:

    async def test_update_range(self, db_session):
        site = await make_site(db_session, slug="hours-update")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        row = await hours_service.add_range(db_session, auth, 1, time(9, 0), time(17, 0))
        updated = await hours_service.update_range(db_session, auth, row.regular_hours_id, time(10, 0), time(22, 0))
        assert updated.open_time == time(10, 0)
        assert updated.close_time == time(22, 0)

    async def test_update_foreign_range_returns_404(self, db_session):
        """Cannot update a range belonging to another site."""
        site_a = await make_site(db_session, slug="hours-idor-upd-a")
        site_b = await make_site(db_session, slug="hours-idor-upd-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        row_b = await hours_service.add_range(db_session, auth_b, 2, time(9, 0), time(17, 0))

        with pytest.raises(HoursRangeNotFound):
            await hours_service.update_range(db_session, auth_a, row_b.regular_hours_id, time(10, 0), time(18, 0))

        # B's range untouched
        await db_session.refresh(row_b)
        assert row_b.open_time == time(9, 0)


# ---------------------------------------------------------------------------
# Delete range
# ---------------------------------------------------------------------------

class TestDeleteRange:

    async def test_delete_range(self, db_session):
        site = await make_site(db_session, slug="hours-delete")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        row = await hours_service.add_range(db_session, auth, 3, time(9, 0), time(17, 0))
        range_id = row.regular_hours_id
        await hours_service.delete_range(db_session, auth, range_id)

        result = await db_session.execute(
            select(RegularHours).where(RegularHours.regular_hours_id == range_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_foreign_range_returns_404(self, db_session):
        """Cannot delete a range belonging to another site."""
        site_a = await make_site(db_session, slug="hours-idor-del-a")
        site_b = await make_site(db_session, slug="hours-idor-del-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        row_b = await hours_service.add_range(db_session, auth_b, 4, time(18, 0), time(23, 0))

        with pytest.raises(HoursRangeNotFound):
            await hours_service.delete_range(db_session, auth_a, row_b.regular_hours_id)

        # B's range still exists
        result = await db_session.execute(
            select(RegularHours).where(RegularHours.regular_hours_id == row_b.regular_hours_id)
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestListHours:

    async def test_list_returns_own_site_only(self, db_session):
        site_a = await make_site(db_session, slug="hours-list-a")
        site_b = await make_site(db_session, slug="hours-list-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await hours_service.add_range(db_session, auth_a, 0, time(9, 0), time(17, 0))
        await hours_service.add_range(db_session, auth_b, 0, time(10, 0), time(18, 0))

        hours_a = await hours_service.list_hours(db_session, auth_a)
        assert len(hours_a) == 1
        assert hours_a[0].site_id == site_a.site_id

    async def test_list_empty(self, db_session):
        site = await make_site(db_session, slug="hours-list-empty")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        hours = await hours_service.list_hours(db_session, auth)
        assert hours == []


# ---------------------------------------------------------------------------
# No scope
# ---------------------------------------------------------------------------

class TestNoScope:

    async def test_add_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)
        with pytest.raises(NoSiteInScope):
            await hours_service.add_range(db_session, auth, 0, time(9, 0), time(17, 0))

    async def test_list_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)
        with pytest.raises(NoSiteInScope):
            await hours_service.list_hours(db_session, auth)
