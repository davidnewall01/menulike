"""Location queries and mutations — scoped to the owner's site."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.location import Location
from app.services.exceptions import LocationNotFound, NoSiteInScope


# ---------------------------------------------------------------------------
# Scoped-load (the IDOR primitive)
# ---------------------------------------------------------------------------

async def get_owner_location(
    db: AsyncSession, auth_ctx: AuthContext, location_id: uuid.UUID
) -> Location:
    """Load a location by id, scoped to the owner's site.

    Foreign location → LocationNotFound (the IDOR guard).
    """
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


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_locations(
    db: AsyncSession, auth_ctx: AuthContext,
) -> list[Location]:
    """All locations for the owner's site, ordered by position."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Location)
        .where(Location.site_id == auth_ctx.scoped_site_id)
        .order_by(Location.position)
    )
    return list(result.scalars().all())


async def get_default_location(
    db: AsyncSession, auth_ctx: AuthContext,
) -> Location:
    """Return the site's first (default) location. Every site has at least one."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Location)
        .where(Location.site_id == auth_ctx.scoped_site_id)
        .order_by(Location.position)
        .limit(1)
    )
    loc = result.scalar_one_or_none()
    if loc is None:
        raise LocationNotFound("No locations for this site")
    return loc


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def create_location(
    db: AsyncSession, auth_ctx: AuthContext,
    *,
    label: str | None = None,
    address_street: str | None = None,
    address_suburb: str | None = None,
    address_state: str | None = None,
    address_postcode: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> Location:
    """Create a new location for the owner's site. Flush only."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    # Position = next after existing max
    result = await db.execute(
        select(Location.position)
        .where(Location.site_id == auth_ctx.scoped_site_id)
        .order_by(Location.position.desc())
        .limit(1)
    )
    max_pos = result.scalar_one_or_none()
    next_pos = (max_pos or 0) + 1

    loc = Location(
        site_id=auth_ctx.scoped_site_id,
        label=label,
        address_street=address_street,
        address_suburb=address_suburb,
        address_state=address_state,
        address_postcode=address_postcode,
        phone=phone,
        email=email,
        position=next_pos,
    )
    db.add(loc)
    await db.flush()
    return loc


async def update_location(
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID,
    *,
    label: str | None = None,
    address_street: str | None = None,
    address_suburb: str | None = None,
    address_state: str | None = None,
    address_postcode: str | None = None,
    latitude=None,
    longitude=None,
    phone: str | None = None,
    email: str | None = None,
) -> Location:
    """Update a location's fields. Scoped-load first (IDOR gate). Flush only."""
    loc = await get_owner_location(db, auth_ctx, location_id)
    loc.label = label
    loc.address_street = address_street
    loc.address_suburb = address_suburb
    loc.address_state = address_state
    loc.address_postcode = address_postcode
    if latitude is not None or longitude is not None:
        loc.latitude = latitude
        loc.longitude = longitude
    loc.phone = phone
    loc.email = email
    await db.flush()
    return loc


async def delete_location(
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID,
) -> None:
    """Delete a location. Scoped-load first (IDOR gate). Flush only."""
    loc = await get_owner_location(db, auth_ctx, location_id)
    await db.delete(loc)
    await db.flush()
