"""Hours exception coordinator — owns the commit boundary."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.hours_exception import HoursException
from app.services import hours_exception_service


async def add_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    start_date: date, end_date: date,
    is_closed: bool, special_hours: list | None,
    label: str | None,
) -> HoursException:
    row = await hours_exception_service.add_exception(
        db, auth_ctx, start_date, end_date, is_closed, special_hours, label
    )
    await db.commit()
    return row


async def update_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    exception_id: uuid.UUID,
    start_date: date, end_date: date,
    is_closed: bool, special_hours: list | None,
    label: str | None,
) -> HoursException:
    row = await hours_exception_service.update_exception(
        db, auth_ctx, exception_id, start_date, end_date, is_closed, special_hours, label
    )
    await db.commit()
    return row


async def delete_exception(
    db: AsyncSession, auth_ctx: AuthContext,
    exception_id: uuid.UUID,
) -> None:
    await hours_exception_service.delete_exception(db, auth_ctx, exception_id)
    await db.commit()
