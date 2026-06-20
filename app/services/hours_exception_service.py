"""Hours exceptions — date-specific closures and special hours, scoped to owner's site."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.hours_exception import HoursException
from app.services.exceptions import NoSiteInScope


class HoursExceptionNotFound(Exception):
    """The exception_id didn't resolve within the owner's scoped site."""


class InvalidDateRange(Exception):
    """end_date is before start_date."""


# ---------------------------------------------------------------------------
# Scoped-load (IDOR primitive)
# ---------------------------------------------------------------------------

async def _get_owner_exception(
    db: AsyncSession, auth_ctx: AuthContext, exception_id: uuid.UUID
) -> HoursException:
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(HoursException).where(
            HoursException.hours_exception_id == exception_id,
            HoursException.site_id == auth_ctx.scoped_site_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HoursExceptionNotFound(f"exception_id={exception_id}")
    return row


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_exceptions(
    db: AsyncSession, auth_ctx: AuthContext
) -> list[HoursException]:
    """All exceptions for the owner's site, ordered by start_date."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(HoursException)
        .where(HoursException.site_id == auth_ctx.scoped_site_id)
        .order_by(HoursException.start_date)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Writes (flush only)
# ---------------------------------------------------------------------------

async def add_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    start_date: date, end_date: date,
    is_closed: bool, special_hours: list | None,
    label: str | None,
) -> HoursException:
    """Add a date-specific exception. end_date must be >= start_date."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    if end_date < start_date:
        raise InvalidDateRange(f"end_date {end_date} is before start_date {start_date}")

    row = HoursException(
        site_id=auth_ctx.scoped_site_id,
        start_date=start_date,
        end_date=end_date,
        is_closed=is_closed,
        special_hours=special_hours,
        label=label,
    )
    db.add(row)
    await db.flush()
    return row


async def update_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    exception_id: uuid.UUID,
    start_date: date, end_date: date,
    is_closed: bool, special_hours: list | None,
    label: str | None,
) -> HoursException:
    """Update an existing exception. Scoped-load first (IDOR gate)."""
    if end_date < start_date:
        raise InvalidDateRange(f"end_date {end_date} is before start_date {start_date}")

    row = await _get_owner_exception(db, auth_ctx, exception_id)
    row.start_date = start_date
    row.end_date = end_date
    row.is_closed = is_closed
    row.special_hours = special_hours
    row.label = label
    await db.flush()
    return row


async def delete_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    exception_id: uuid.UUID,
) -> None:
    """Delete an exception. Scoped-load first (IDOR gate)."""
    row = await _get_owner_exception(db, auth_ctx, exception_id)
    await db.delete(row)
    await db.flush()
