"""Content-block coordinator — owns the commit boundary."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.content_block import ContentBlock
from app.services import content_block_service


async def create_block(
    db: AsyncSession, auth_ctx: AuthContext,
    page_key: str, heading: str | None, body: str | None,
) -> ContentBlock:
    block = await content_block_service.create_block(db, auth_ctx, page_key, heading, body)
    await db.commit()
    return block


async def update_block(
    db: AsyncSession, auth_ctx: AuthContext,
    block_id: uuid.UUID, heading: str | None, body: str | None,
) -> ContentBlock:
    block = await content_block_service.update_block(db, auth_ctx, block_id, heading, body)
    await db.commit()
    return block


async def delete_block(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID
) -> None:
    await content_block_service.delete_block(db, auth_ctx, block_id)
    await db.commit()


async def set_block_image(
    db: AsyncSession, auth_ctx: AuthContext,
    block_id: uuid.UUID, photo_id: uuid.UUID,
) -> ContentBlock:
    block = await content_block_service.set_block_image(db, auth_ctx, block_id, photo_id)
    await db.commit()
    return block


async def clear_block_image(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID
) -> ContentBlock:
    block = await content_block_service.clear_block_image(db, auth_ctx, block_id)
    await db.commit()
    return block


async def reorder_blocks(
    db: AsyncSession, auth_ctx: AuthContext,
    page_key: str, ordered_ids: list[uuid.UUID],
) -> None:
    await content_block_service.reorder_blocks(db, auth_ctx, page_key, ordered_ids)
    await db.commit()
