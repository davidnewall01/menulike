"""Hours coordinator — owns the commit boundary for regular hours writes."""

import uuid
from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.regular_hours import RegularHours
from app.services import hours_service


async def add_range(
    db: AsyncSession, auth_ctx: AuthContext,
    day_of_week: int, open_time: time, close_time: time,
) -> RegularHours:
    row = await hours_service.add_range(db, auth_ctx, day_of_week, open_time, close_time)
    await db.commit()
    return row


async def update_range(
    db: AsyncSession, auth_ctx: AuthContext,
    range_id: uuid.UUID, open_time: time, close_time: time,
) -> RegularHours:
    row = await hours_service.update_range(db, auth_ctx, range_id, open_time, close_time)
    await db.commit()
    return row


async def delete_range(
    db: AsyncSession, auth_ctx: AuthContext,
    range_id: uuid.UUID,
) -> None:
    await hours_service.delete_range(db, auth_ctx, range_id)
    await db.commit()
