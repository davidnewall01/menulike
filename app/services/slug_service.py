"""Slug generation for tenant subdomains."""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import Site


def slugify(name: str) -> str:
    """Convert a restaurant name to a URL-safe slug.

    Strips accents (NFKD decomposition), lowercases, replaces non-alnum
    with hyphens, collapses runs, strips leading/trailing hyphens.
    """
    # Decompose unicode and drop combining marks (accents)
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))

    slug = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)  # non-alnum → hyphen
    slug = slug.strip("-")

    return slug or "restaurant"


async def generate_unique_slug(db: AsyncSession, name: str) -> str:
    """Generate a slug from `name`, appending -2, -3… on collision.

    Pre-checks the DB to avoid IntegrityError in normal flow.
    The unique index on site.slug is the backstop.
    """
    base = slugify(name)
    if not base:
        base = "restaurant"

    # Check base slug
    result = await db.execute(select(Site.site_id).where(Site.slug == base))
    if result.scalar_one_or_none() is None:
        return base

    # Collision — find next available suffix
    suffix = 2
    while True:
        candidate = f"{base}-{suffix}"
        result = await db.execute(
            select(Site.site_id).where(Site.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
        suffix += 1
