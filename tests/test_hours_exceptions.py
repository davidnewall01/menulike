"""Hours exception tests — CRUD, IDOR, date validation."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.auth.context import AuthContext
from app.models.hours_exception import HoursException
from app.services import hours_exception_service
from app.services.hours_exception_service import (
    HoursExceptionNotFound,
    InvalidDateRange,
)
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
# Add
# ---------------------------------------------------------------------------

class TestAddException:

    async def test_add_closure(self, db_session):
        site = await make_site(db_session, slug="exc-add")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            start_date=date(2026, 12, 25), end_date=date(2026, 12, 25),
            is_closed=True, special_hours=None, label="Christmas Day",
        )
        assert exc.start_date == date(2026, 12, 25)
        assert exc.end_date == date(2026, 12, 25)
        assert exc.is_closed is True
        assert exc.label == "Christmas Day"

    async def test_add_special_hours(self, db_session):
        site = await make_site(db_session, slug="exc-special")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            start_date=date(2026, 12, 31), end_date=date(2026, 12, 31),
            is_closed=False,
            special_hours=[{"open": "18:00", "close": "01:00"}],
            label="NYE",
        )
        assert exc.is_closed is False
        assert exc.special_hours == [{"open": "18:00", "close": "01:00"}]

    async def test_add_date_range(self, db_session):
        site = await make_site(db_session, slug="exc-range")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            start_date=date(2026, 7, 22), end_date=date(2026, 8, 30),
            is_closed=True, special_hours=None, label="Summer break",
        )
        assert exc.start_date == date(2026, 7, 22)
        assert exc.end_date == date(2026, 8, 30)

    async def test_end_before_start_rejected(self, db_session):
        site = await make_site(db_session, slug="exc-bad-range")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        with pytest.raises(InvalidDateRange):
            await hours_exception_service.add_exception(
                db_session, auth,
                start_date=date(2026, 12, 25), end_date=date(2026, 12, 20),
                is_closed=True, special_hours=None, label="Bad",
            )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

class TestUpdateException:

    async def test_update_exception(self, db_session):
        site = await make_site(db_session, slug="exc-update")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            date(2026, 1, 1), date(2026, 1, 1),
            True, None, "New Year",
        )
        updated = await hours_exception_service.update_exception(
            db_session, auth, exc.hours_exception_id,
            date(2026, 1, 1), date(2026, 1, 2),
            True, None, "New Year extended",
        )
        assert updated.end_date == date(2026, 1, 2)
        assert updated.label == "New Year extended"

    async def test_update_foreign_exception_returns_404(self, db_session):
        site_a = await make_site(db_session, slug="exc-idor-upd-a")
        site_b = await make_site(db_session, slug="exc-idor-upd-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        exc_b = await hours_exception_service.add_exception(
            db_session, auth_b,
            date(2026, 6, 1), date(2026, 6, 1),
            True, None, "B's closure",
        )

        with pytest.raises(HoursExceptionNotFound):
            await hours_exception_service.update_exception(
                db_session, auth_a, exc_b.hours_exception_id,
                date(2026, 6, 1), date(2026, 6, 1),
                False, [{"open": "10:00", "close": "14:00"}], "Hijacked",
            )

        await db_session.refresh(exc_b)
        assert exc_b.label == "B's closure"

    async def test_update_end_before_start_rejected(self, db_session):
        site = await make_site(db_session, slug="exc-upd-bad")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            date(2026, 3, 1), date(2026, 3, 5),
            True, None, "Ok",
        )

        with pytest.raises(InvalidDateRange):
            await hours_exception_service.update_exception(
                db_session, auth, exc.hours_exception_id,
                date(2026, 3, 5), date(2026, 3, 1),
                True, None, "Bad",
            )


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestDeleteException:

    async def test_delete_exception(self, db_session):
        site = await make_site(db_session, slug="exc-delete")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        exc = await hours_exception_service.add_exception(
            db_session, auth,
            date(2026, 4, 1), date(2026, 4, 1),
            True, None, "April Fools",
        )
        exc_id = exc.hours_exception_id
        await hours_exception_service.delete_exception(db_session, auth, exc_id)

        result = await db_session.execute(
            select(HoursException).where(HoursException.hours_exception_id == exc_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_foreign_exception_returns_404(self, db_session):
        site_a = await make_site(db_session, slug="exc-idor-del-a")
        site_b = await make_site(db_session, slug="exc-idor-del-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        exc_b = await hours_exception_service.add_exception(
            db_session, auth_b,
            date(2026, 5, 1), date(2026, 5, 1),
            True, None, "B's day off",
        )

        with pytest.raises(HoursExceptionNotFound):
            await hours_exception_service.delete_exception(db_session, auth_a, exc_b.hours_exception_id)

        result = await db_session.execute(
            select(HoursException).where(HoursException.hours_exception_id == exc_b.hours_exception_id)
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# List + scope
# ---------------------------------------------------------------------------

class TestListExceptions:

    async def test_list_returns_own_site_only(self, db_session):
        site_a = await make_site(db_session, slug="exc-list-a")
        site_b = await make_site(db_session, slug="exc-list-b")
        owner_a = await make_owner(db_session, site_a)
        owner_b = await make_owner(db_session, site_b)
        auth_a = _auth(owner_a)
        auth_b = _auth(owner_b)

        await hours_exception_service.add_exception(
            db_session, auth_a, date(2026, 1, 1), date(2026, 1, 1), True, None, "A"
        )
        await hours_exception_service.add_exception(
            db_session, auth_b, date(2026, 1, 1), date(2026, 1, 1), True, None, "B"
        )

        excs_a = await hours_exception_service.list_exceptions(db_session, auth_a)
        assert len(excs_a) == 1
        assert excs_a[0].label == "A"

    async def test_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)
        with pytest.raises(NoSiteInScope):
            await hours_exception_service.list_exceptions(db_session, auth)
