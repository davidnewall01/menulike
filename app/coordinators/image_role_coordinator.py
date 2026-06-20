"""Image-role coordinator — owns the commit boundary for role assignment writes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.site_image_role import SiteImageRole
from app.services import image_role_service


async def assign(
    db: AsyncSession, auth_ctx: AuthContext,
    role: str, photo_id: uuid.UUID,
) -> SiteImageRole:
    assignment = await image_role_service.assign(db, auth_ctx, role, photo_id)
    await db.commit()
    return assignment


async def clear(
    db: AsyncSession, auth_ctx: AuthContext, role: str
) -> None:
    await image_role_service.clear(db, auth_ctx, role)
    await db.commit()


async def add_to_role(
    db: AsyncSession, auth_ctx: AuthContext,
    role: str, photo_id: uuid.UUID,
) -> SiteImageRole:
    assignment = await image_role_service.add_to_role(db, auth_ctx, role, photo_id)
    await db.commit()
    return assignment


async def remove_from_role(
    db: AsyncSession, auth_ctx: AuthContext,
    role: str, photo_id: uuid.UUID,
) -> None:
    await image_role_service.remove_from_role(db, auth_ctx, role, photo_id)
    await db.commit()


async def reorder_role(
    db: AsyncSession, auth_ctx: AuthContext,
    role: str, ordered_photo_ids: list[uuid.UUID],
) -> None:
    await image_role_service.reorder_role(db, auth_ctx, role, ordered_photo_ids)
    await db.commit()
