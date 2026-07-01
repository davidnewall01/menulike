"""Regular hours queries and mutations — scoped via location → site ownership."""

import uuid
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.location import Location
from app.models.regular_hours import RegularHours
from app.services.exceptions import LocationNotFound, NoSiteInScope


class HoursRangeNotFound(Exception):
    """The range_id didn't resolve within the owner's scoped site."""


class InvalidHoursLabel(Exception):
    """Label wasn't one of the allowed service-period values."""


# Allowed service-period labels (None = unlabelled all-day range).
HOURS_LABELS = frozenset({"breakfast", "lunch", "dinner"})


def _normalise_label(label: str | None) -> str | None:
    """Blank -> None; otherwise lowercase and validate against HOURS_LABELS."""
    if label is None:
        return None
    label = label.strip().lower()
    if not label:
        return None
    if label not in HOURS_LABELS:
        raise InvalidHoursLabel(f"label={label!r}")
    return label


# ---------------------------------------------------------------------------
# Scoped-load helpers
# ---------------------------------------------------------------------------

async def _verify_location_ownership(
    db: AsyncSession, auth_ctx: AuthContext, location_id: uuid.UUID,
) -> Location:
    """Validate location belongs to the scoped site. IDOR gate."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    result = await db.execute(
        select(Location).where(
            Location.location_id == location_id,
            Location.site_id == auth_ctx.scoped_site_id,
        )
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        raise LocationNotFound(f"location_id={location_id}")
    return loc


async def _get_owner_range(
    db: AsyncSession, auth_ctx: AuthContext, range_id: uuid.UUID
) -> RegularHours:
    """Load a range by id, scoped to the owner's site via site_id."""
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
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID | None = None,
) -> list[RegularHours]:
    """Regular hours ordered by day then open_time.

    If location_id is given, returns hours for that location (validates ownership).
    Otherwise returns all hours for the scoped site (backward compat for existing callers).
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    if location_id is not None:
        await _verify_location_ownership(db, auth_ctx, location_id)
        result = await db.execute(
            select(RegularHours)
            .where(RegularHours.location_id == location_id)
            .order_by(RegularHours.day_of_week, RegularHours.open_time)
        )
    else:
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
    location_id: uuid.UUID | None = None,
    label: str | None = None,
) -> RegularHours:
    """Add a time range to a day. Validates location ownership if given.

    If location_id is None, uses the site's default (first) location.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    label = _normalise_label(label)

    if location_id is not None:
        await _verify_location_ownership(db, auth_ctx, location_id)
        loc_id = location_id
    else:
        # Backward compat: resolve default location for the site
        from app.services import location_service
        default = await location_service.get_default_location(db, auth_ctx)
        loc_id = default.location_id

    row = RegularHours(
        site_id=auth_ctx.scoped_site_id,
        location_id=loc_id,
        day_of_week=day_of_week,
        open_time=open_time,
        close_time=close_time,
        label=label,
    )
    db.add(row)
    await db.flush()
    return row


async def update_range(
    db: AsyncSession, auth_ctx: AuthContext,
    range_id: uuid.UUID, open_time: time, close_time: time,
    label: str | None = None,
) -> RegularHours:
    """Update an existing range's times + label. Scoped-load first (IDOR gate)."""
    label = _normalise_label(label)
    row = await _get_owner_range(db, auth_ctx, range_id)
    row.open_time = open_time
    row.close_time = close_time
    row.label = label
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
