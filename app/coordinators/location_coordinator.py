"""Location coordinator — owns the commit boundary for location writes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.location import Location
from app.services import location_service


async def create_location(
    db: AsyncSession, auth_ctx: AuthContext, **kwargs,
) -> Location:
    loc = await location_service.create_location(db, auth_ctx, **kwargs)
    await db.commit()
    return loc


async def update_location(
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID, **kwargs,
) -> Location:
    loc = await location_service.update_location(db, auth_ctx, location_id, **kwargs)
    await db.commit()
    return loc


async def set_hours_display_mode(
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID, mode: str,
) -> Location:
    loc = await location_service.set_hours_display_mode(db, auth_ctx, location_id, mode)
    await db.commit()
    return loc


async def delete_location(
    db: AsyncSession, auth_ctx: AuthContext,
    location_id: uuid.UUID,
) -> None:
    await location_service.delete_location(db, auth_ctx, location_id)
    await db.commit()
