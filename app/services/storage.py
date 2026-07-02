"""S3 storage plumbing — upload, delete, public URL.

Pure S3 operations with no DB or tenant scoping (that lives in photo_service).
Fails with a clear error at use-time if S3 is not configured, so the app still
boots and runs all non-photo features without AWS creds.
"""

import uuid
from typing import BinaryIO

import aioboto3

from app.core.config import settings


class StorageNotConfigured(RuntimeError):
    """Raised when S3 is used but AWS creds / bucket are not set."""


def _require_config() -> None:
    """Fail-closed guard — fires at use-time, not boot-time."""
    missing = []
    if not settings.AWS_ACCESS_KEY_ID:
        missing.append("AWS_ACCESS_KEY_ID")
    if not settings.AWS_SECRET_ACCESS_KEY:
        missing.append("AWS_SECRET_ACCESS_KEY")
    if not settings.S3_BUCKET:
        missing.append("S3_BUCKET")
    if not settings.S3_PUBLIC_BASE_URL:
        missing.append("S3_PUBLIC_BASE_URL")
    if missing:
        raise StorageNotConfigured(
            f"S3 is not configured. Set the following env vars: {', '.join(missing)}"
        )


def photo_key(site_id: uuid.UUID, photo_id: uuid.UUID, ext: str) -> str:
    """Build the S3 object key for a photo: sites/{site_id}/photos/{photo_id}.{ext}

    Legacy flat key — kept for reference but new uploads use variant_key().
    """
    return f"sites/{site_id}/photos/{photo_id}.{ext}"


def variant_key(
    site_id: uuid.UUID, photo_id: uuid.UUID, variant: str, ext: str
) -> str:
    """Build S3 key for an image variant.

    Layout: sites/{site_id}/photos/{photo_id}/{variant}.{ext}
    """
    return f"sites/{site_id}/photos/{photo_id}/{variant}.{ext}"


def public_url(key: str) -> str:
    """Public URL for an S3 object via the configured base URL."""
    _require_config()
    base = settings.S3_PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/{key}"


# Variant name → Photo column holding that variant's S3 key.
_VARIANT_ATTRS: dict[str, str] = {
    "thumb": "s3_key_thumb",
    "medium": "s3_key_medium",
    "large": "s3_key_large",
    "original": "s3_key",  # s3_key = original_webp after pipeline
}

# Fallback chain: if the requested variant is missing, try the next larger.
_FALLBACK_ORDER = ("thumb", "medium", "large", "original")


def pick_variant_key(photo: object, variant: str) -> str:
    """Pick the best S3 key for the requested variant, with fallback.

    If the requested variant key is None (pre-pipeline photo), walks up the
    fallback chain (thumb → medium → large → original) to the first populated
    key. Returns a raw S3 key — caller applies public_url().
    """
    try:
        start = _FALLBACK_ORDER.index(variant)
    except ValueError:
        start = 0
    for v in _FALLBACK_ORDER[start:]:
        key = getattr(photo, _VARIANT_ATTRS[v], None)
        if key:
            return key
    return photo.s3_key


def photo_variant_url(photo: object, variant: str) -> str:
    """Public URL for a specific image variant with graceful fallback."""
    return public_url(pick_variant_key(photo, variant))


def _session() -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.S3_REGION,
    )


async def upload(data: bytes, key: str, content_type: str) -> None:
    """Upload bytes to S3. No ACL — bucket policy controls public read."""
    _require_config()
    session = _session()
    async with session.client("s3") as s3:
        await s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )


async def download(key: str) -> bytes:
    """Download an object's bytes from S3."""
    _require_config()
    session = _session()
    async with session.client("s3") as s3:
        resp = await s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
        return await resp["Body"].read()


async def copy(src_key: str, dst_key: str) -> None:
    """Copy an object within the same bucket."""
    _require_config()
    session = _session()
    async with session.client("s3") as s3:
        await s3.copy_object(
            Bucket=settings.S3_BUCKET,
            CopySource={"Bucket": settings.S3_BUCKET, "Key": src_key},
            Key=dst_key,
        )


async def delete(key: str) -> None:
    """Delete an object from S3."""
    _require_config()
    session = _session()
    async with session.client("s3") as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
