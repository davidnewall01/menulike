"""Photo library queries and mutations — scoped to the owner's site."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.photo import Photo
from app.services import storage
from app.services.exceptions import InvalidImage, NoSiteInScope, PhotoNotFound
from app.services.image_variants import generate_variants

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
    """Validate, generate WebP variants, upload all to S3, create DB row.

    Uploads the raw original plus four WebP variants (original_webp, large,
    medium, thumb).  s3_key points at the original_webp (the primary serve
    target); s3_key_raw holds the untouched upload for future reprocessing.

    Order: S3 uploads THEN row creation. A failed upload writes nothing.
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

    # Generate WebP variants (also validates the image is readable)
    try:
        variants = generate_variants(file_data)
    except Exception as exc:
        raise InvalidImage(f"Could not process image: {exc}") from exc

    # Determine extension from content type (for the raw original)
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    raw_ext = ext_map.get(content_type, "bin")

    photo_id = uuid.uuid4()
    site_id = auth_ctx.scoped_site_id

    # Build S3 keys
    raw_key = storage.variant_key(site_id, photo_id, "raw", raw_ext)
    variant_keys: dict[str, str] = {}
    for v in variants:
        variant_keys[v.name] = storage.variant_key(
            site_id, photo_id, v.name, "webp"
        )

    # Upload raw original first
    await storage.upload(file_data, raw_key, content_type)

    # Upload WebP variants
    for v in variants:
        await storage.upload(v.data, variant_keys[v.name], "image/webp")

    # Dimensions from the original_webp variant (post-orientation-fix)
    original_v = next(v for v in variants if v.name == "original_webp")

    photo = Photo(
        photo_id=photo_id,
        site_id=site_id,
        s3_key=variant_keys["original_webp"],
        s3_key_raw=raw_key,
        s3_key_large=variant_keys["large"],
        s3_key_medium=variant_keys["medium"],
        s3_key_thumb=variant_keys["thumb"],
        original_filename=filename,
        content_type=content_type,
        width=original_v.width,
        height=original_v.height,
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
    """Delete a photo and all its S3 variants from storage + DB."""
    photo = await get_owner_photo(db, auth_ctx, photo_id)
    # Delete all S3 objects for this photo
    keys_to_delete = [
        photo.s3_key,
        photo.s3_key_raw,
        photo.s3_key_large,
        photo.s3_key_medium,
        photo.s3_key_thumb,
    ]
    for key in keys_to_delete:
        if key:
            await storage.delete(key)
    await db.delete(photo)
    await db.flush()
