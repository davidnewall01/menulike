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
    """Build the S3 object key for a photo: sites/{site_id}/photos/{photo_id}.{ext}"""
    return f"sites/{site_id}/photos/{photo_id}.{ext}"


def public_url(key: str) -> str:
    """Public URL for an S3 object via the configured base URL."""
    _require_config()
    base = settings.S3_PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/{key}"


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


async def delete(key: str) -> None:
    """Delete an object from S3."""
    _require_config()
    session = _session()
    async with session.client("s3") as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
