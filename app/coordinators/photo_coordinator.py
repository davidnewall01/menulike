"""Photo coordinator — owns the commit boundary for photo writes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.photo import Photo
from app.services import photo_service


async def create_photo(
    db: AsyncSession, auth_ctx: AuthContext,
    file_data: bytes, filename: str | None, content_type: str
) -> Photo:
    photo = await photo_service.create_photo(
        db, auth_ctx, file_data, filename, content_type
    )
    await db.commit()
    return photo


async def update_photo_alt(
    db: AsyncSession, auth_ctx: AuthContext,
    photo_id: uuid.UUID, alt_text: str | None
) -> Photo:
    photo = await photo_service.update_photo_alt(db, auth_ctx, photo_id, alt_text)
    await db.commit()
    return photo


async def delete_photo(
    db: AsyncSession, auth_ctx: AuthContext, photo_id: uuid.UUID
) -> None:
    await photo_service.delete_photo(db, auth_ctx, photo_id)
    await db.commit()
