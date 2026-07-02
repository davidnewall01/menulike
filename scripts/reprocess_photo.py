"""Reprocess a single photo's WebP derivatives from its raw source.

Downloads s3_key_raw, runs it through the current image_variants pipeline,
and uploads the regenerated variants back to the photo's existing S3 keys.
Backs up each existing derivative to a .bak suffix before overwriting.

Usage:
    python -m scripts.reprocess_photo <photo_id>

Requires DATABASE_URL and AWS credentials in environment (same as the app).
"""

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.photo import Photo
from app.services import storage
from app.services.image_variants import generate_variants
from app.services.storage import variant_key

# Maps variant name (from image_variants) -> Photo column holding its S3 key.
VARIANT_TO_ATTR = {
    "original_webp": "s3_key",
    "large": "s3_key_large",
    "medium": "s3_key_medium",
    "thumb": "s3_key_thumb",
}


async def reprocess(photo_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Photo).where(Photo.photo_id == photo_id)
        )
        photo = result.scalar_one_or_none()
        if photo is None:
            print(f"ERROR: no photo with id {photo_id}")
            sys.exit(1)

        if not photo.s3_key_raw:
            print(f"ERROR: photo {photo_id} has no s3_key_raw — nothing to reprocess from")
            sys.exit(1)

        print(f"Photo:    {photo_id}")
        print(f"Site:     {photo.site_id}")
        print(f"Raw key:  {photo.s3_key_raw}")
        print()

        # 1. Download raw source
        print("Downloading raw source ...")
        raw_bytes = await storage.download(photo.s3_key_raw)
        print(f"  {len(raw_bytes):,} bytes")

        # 2. Generate variants with the current (fixed) pipeline
        print("Generating variants ...")
        variants = generate_variants(raw_bytes)

        # 3. Back up existing derivatives, then upload new ones
        for v in variants:
            attr = VARIANT_TO_ATTR[v.name]
            existing_key = getattr(photo, attr)
            if existing_key:
                bak_key = existing_key + ".bak"
                print(f"  Backing up {v.name:15s} -> {bak_key}")
                await storage.copy(existing_key, bak_key)

                print(f"  Uploading  {v.name:15s}   {len(v.data):,} bytes  {v.width}x{v.height}")
                await storage.upload(v.data, existing_key, "image/webp")
            else:
                print(f"  SKIP {v.name} — no existing key on photo row")

        print()
        print("Done. Derivatives reprocessed. .bak copies preserved.")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.reprocess_photo <photo_id>")
        sys.exit(1)

    try:
        photo_id = uuid.UUID(sys.argv[1])
    except ValueError:
        print(f"ERROR: invalid UUID: {sys.argv[1]}")
        sys.exit(1)

    asyncio.run(reprocess(photo_id))


if __name__ == "__main__":
    main()
