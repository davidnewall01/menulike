"""Photo library queries and mutations — scoped to the owner's site."""

import io
import uuid

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.photo import Photo
from app.services import storage
from app.services.exceptions import InvalidImage, NoSiteInScope, PhotoNotFound

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Scoped-load (the IDOR primitive)
# ---------------------------------------------------------------------------

async def get_owner_photo(
    db: AsyncSession, auth_ctx: AuthContext, photo_id: uuid.UUID
) -> Photo:
    """Load a photo by id, scoped to the owner's site."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Photo).where(
            Photo.photo_id == photo_id,
            Photo.site_id == auth_ctx.scoped_site_id,
        )
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        raise PhotoNotFound(f"photo_id={photo_id}")
    return photo


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_photos(
    db: AsyncSession, auth_ctx: AuthContext
) -> list[Photo]:
    """List all photos for the owner's site, newest first."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Photo)
        .where(Photo.site_id == auth_ctx.scoped_site_id)
        .order_by(Photo.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def create_photo(
    db: AsyncSession, auth_ctx: AuthContext,
    file_data: bytes, filename: str | None, content_type: str
) -> Photo:
    """Validate, upload to S3, create the DB row. Flush only.

    Order: S3 upload THEN row creation. A failed upload writes nothing.
    An orphaned S3 object on a later commit failure is acceptable for now.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    # Validate content type
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImage(
            f"File type '{content_type}' not allowed. "
            f"Accepted: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    # Validate size
    if len(file_data) > MAX_UPLOAD_BYTES:
        raise InvalidImage(
            f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit."
        )

    # Read dimensions via Pillow (no resize)
    width, height = None, None
    try:
        img = Image.open(io.BytesIO(file_data))
        width, height = img.size
    except Exception:
        pass  # dimensions are optional; a corrupt header doesn't block upload

    # Determine extension from content type
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    ext = ext_map.get(content_type, "bin")

    photo_id = uuid.uuid4()
    key = storage.photo_key(auth_ctx.scoped_site_id, photo_id, ext)

    # S3 upload first — if this fails, no DB row is written
    await storage.upload(file_data, key, content_type)

    photo = Photo(
        photo_id=photo_id,
        site_id=auth_ctx.scoped_site_id,
        s3_key=key,
        original_filename=filename,
        content_type=content_type,
        width=width,
        height=height,
    )
    db.add(photo)
    await db.flush()
    return photo


async def update_photo_alt(
    db: AsyncSession, auth_ctx: AuthContext,
    photo_id: uuid.UUID, alt_text: str | None
) -> Photo:
    """Update a photo's alt text. Scoped-load first."""
    photo = await get_owner_photo(db, auth_ctx, photo_id)
    photo.alt_text = alt_text if alt_text and alt_text.strip() else None
    await db.flush()
    return photo


async def delete_photo(
    db: AsyncSession, auth_ctx: AuthContext, photo_id: uuid.UUID
) -> None:
    """Delete a photo from S3 and the DB. Scoped-load first."""
    photo = await get_owner_photo(db, auth_ctx, photo_id)
    # Delete from S3 first
    await storage.delete(photo.s3_key)
    await db.delete(photo)
    await db.flush()
