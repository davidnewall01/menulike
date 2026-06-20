"""Regular hours queries and mutations — scoped to the owner's site."""

import uuid
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.regular_hours import RegularHours
from app.services.exceptions import NoSiteInScope


class HoursRangeNotFound(Exception):
    """The range_id didn't resolve within the owner's scoped site."""


# ---------------------------------------------------------------------------
# Scoped-load (the IDOR primitive)
# ---------------------------------------------------------------------------

async def _get_owner_range(
    db: AsyncSession, auth_ctx: AuthContext, range_id: uuid.UUID
) -> RegularHours:
    """Load a range by id, scoped to the owner's site."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(RegularHours).where(
            RegularHours.regular_hours_id == range_id,
            RegularHours.site_id == auth_ctx.scoped_site_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HoursRangeNotFound(f"range_id={range_id}")
    return row


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_hours(
    db: AsyncSession, auth_ctx: AuthContext
) -> list[RegularHours]:
    """All regular hours for the owner's site, ordered by day then open_time."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(RegularHours)
        .where(RegularHours.site_id == auth_ctx.scoped_site_id)
        .order_by(RegularHours.day_of_week, RegularHours.open_time)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def add_range(
    db: AsyncSession, auth_ctx: AuthContext,
    day_of_week: int, open_time: time, close_time: time,
) -> RegularHours:
    """Add a time range to a day. No close>open validation — overnight is valid."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    row = RegularHours(
        site_id=auth_ctx.scoped_site_id,
        day_of_week=day_of_week,
        open_time=open_time,
        close_time=close_time,
    )
    db.add(row)
    await db.flush()
    return row


async def update_range(
    db: AsyncSession, auth_ctx: AuthContext,
    range_id: uuid.UUID, open_time: time, close_time: time,
) -> RegularHours:
    """Update an existing range's times. Scoped-load first (IDOR gate)."""
    row = await _get_owner_range(db, auth_ctx, range_id)
    row.open_time = open_time
    row.close_time = close_time
    await db.flush()
    return row


async def delete_range(
    db: AsyncSession, auth_ctx: AuthContext,
    range_id: uuid.UUID,
) -> None:
    """Delete a range. Scoped-load first (IDOR gate)."""
    row = await _get_owner_range(db, auth_ctx, range_id)
    await db.delete(row)
    await db.flush()
