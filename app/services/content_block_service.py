"""Content-block CRUD — scoped to the owner's site via auth_ctx."""

import uuid
from datetime import date

from sqlalchemy import case, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.content_block import ContentBlock
from app.services import photo_service
from app.services.exceptions import ContentBlockNotFound, EmptyBlock, NoSiteInScope

ALLOWED_PAGE_KEYS = {"our_story", "events"}

_SENTINEL = object()  # distinguishes "not provided" from None (clear image)


# ---------------------------------------------------------------------------
# Scoped-load (IDOR gate)
# ---------------------------------------------------------------------------

async def _get_owner_block(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID
) -> ContentBlock:
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(ContentBlock).where(
            ContentBlock.block_id == block_id,
            ContentBlock.site_id == auth_ctx.scoped_site_id,
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        raise ContentBlockNotFound(f"block_id={block_id}")
    return block


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_blocks(
    db: AsyncSession, auth_ctx: AuthContext, page_key: str,
    *, upcoming_only: bool = False, visible_only: bool = False,
) -> list[ContentBlock]:
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    stmt = (
        select(ContentBlock)
        .options(selectinload(ContentBlock.image))
        .where(
            ContentBlock.site_id == auth_ctx.scoped_site_id,
            ContentBlock.page_key == page_key,
        )
    )

    if visible_only:
        stmt = stmt.where(ContentBlock.is_visible.is_(True))

    if upcoming_only:
        # Hide past dated events; keep undated (standing specials) always
        today = date.today()
        stmt = stmt.where(
            (ContentBlock.event_date.is_(None)) | (ContentBlock.event_date >= today)
        )

    if page_key == "events":
        # Dated first (by date ASC), then undated (by position ASC)
        stmt = stmt.order_by(
            case((ContentBlock.event_date.is_(None), 1), else_=0),
            ContentBlock.event_date.asc(),
            ContentBlock.position,
        )
    else:
        stmt = stmt.order_by(ContentBlock.position)

    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

def _is_empty(heading: str | None, body: str | None, image_photo_id: uuid.UUID | None) -> bool:
    return not (heading and heading.strip()) and not (body and body.strip()) and image_photo_id is None


async def create_block(
    db: AsyncSession, auth_ctx: AuthContext,
    page_key: str,
    heading: str | None,
    body: str | None,
    *,
    event_date: date | None = None,
    image_photo_id: uuid.UUID | None = None,
) -> ContentBlock:
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    if _is_empty(heading, body, image_photo_id):
        raise EmptyBlock("A block must have at least a heading, body, or image.")

    # Validate photo ownership if provided
    if image_photo_id is not None:
        await photo_service.get_owner_photo(db, auth_ctx, image_photo_id)

    # Next position
    result = await db.execute(
        select(ContentBlock.position)
        .where(
            ContentBlock.site_id == auth_ctx.scoped_site_id,
            ContentBlock.page_key == page_key,
        )
        .order_by(ContentBlock.position.desc())
        .limit(1)
    )
    max_pos = result.scalar_one_or_none()
    next_pos = (max_pos + 1) if max_pos is not None else 0

    block = ContentBlock(
        site_id=auth_ctx.scoped_site_id,
        page_key=page_key,
        heading=heading.strip() if heading and heading.strip() else None,
        body=body.strip() if body and body.strip() else None,
        event_date=event_date,
        image_photo_id=image_photo_id,
        position=next_pos,
    )
    db.add(block)
    await db.flush()
    return block


async def update_block(
    db: AsyncSession, auth_ctx: AuthContext,
    block_id: uuid.UUID,
    heading: str | None,
    body: str | None,
    *,
    event_date: date | None = None,
    image_photo_id: uuid.UUID | None = _SENTINEL,
) -> ContentBlock:
    block = await _get_owner_block(db, auth_ctx, block_id)
    new_heading = heading.strip() if heading and heading.strip() else None
    new_body = body.strip() if body and body.strip() else None

    # Determine final image: _SENTINEL means "don't change", None means "clear"
    final_image_id = block.image_photo_id if image_photo_id is _SENTINEL else image_photo_id

    if _is_empty(new_heading, new_body, final_image_id):
        raise EmptyBlock("A block must have at least a heading, body, or image.")

    # Validate photo ownership if changing to a new photo
    if image_photo_id is not _SENTINEL and image_photo_id is not None:
        await photo_service.get_owner_photo(db, auth_ctx, image_photo_id)

    block.heading = new_heading
    block.body = new_body
    block.event_date = event_date
    if image_photo_id is not _SENTINEL:
        block.image_photo_id = image_photo_id
    await db.flush()
    return block


async def delete_block(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID
) -> None:
    block = await _get_owner_block(db, auth_ctx, block_id)
    await db.delete(block)
    await db.flush()


async def set_block_image(
    db: AsyncSession, auth_ctx: AuthContext,
    block_id: uuid.UUID, photo_id: uuid.UUID,
) -> ContentBlock:
    """Set the image for a block. Two IDOR gates: block + photo."""
    block = await _get_owner_block(db, auth_ctx, block_id)
    await photo_service.get_owner_photo(db, auth_ctx, photo_id)
    block.image_photo_id = photo_id
    await db.flush()
    return block


async def clear_block_image(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID
) -> ContentBlock:
    block = await _get_owner_block(db, auth_ctx, block_id)
    if _is_empty(block.heading, block.body, None):
        raise EmptyBlock("Cannot remove the image — block would be empty.")
    block.image_photo_id = None
    await db.flush()
    return block


async def reorder_blocks(
    db: AsyncSession, auth_ctx: AuthContext,
    page_key: str, ordered_ids: list[uuid.UUID],
) -> None:
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(ContentBlock)
        .where(
            ContentBlock.site_id == auth_ctx.scoped_site_id,
            ContentBlock.page_key == page_key,
        )
        .order_by(ContentBlock.position)
    )
    current = list(result.scalars().all())
    by_id = {b.block_id: b for b in current}

    valid_ids = [bid for bid in ordered_ids if bid in by_id]
    submitted_set = set(valid_ids)
    remaining = [b.block_id for b in current if b.block_id not in submitted_set]
    final_order = valid_ids + remaining

    for pos, bid in enumerate(final_order):
        by_id[bid].position = pos
    await db.flush()


async def toggle_visibility(
    db: AsyncSession, auth_ctx: AuthContext, block_id: uuid.UUID,
) -> ContentBlock:
    """Toggle is_visible on a block. IDOR-gated."""
    block = await _get_owner_block(db, auth_ctx, block_id)
    block.is_visible = not block.is_visible
    await db.flush()
    return block
