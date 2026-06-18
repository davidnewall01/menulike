"""Tenant resolution from the Host header.

Public path: Host → slug → Site. The tenant is NEVER derived from route params.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.site import Site
from app.services import site_service


def extract_slug(host: str, base_domain: str) -> str | None:
    """Extract the tenant slug from a Host header value.

    Pure function — no DB, no side effects.

    Returns the subdomain label if host is ``<slug>.<base_domain>``
    (with or without a port suffix). Returns None for the apex domain
    or any unrecognised host.
    """
    # Strip port if present (e.g. "portoazzurro.localhost:8000" -> "portoazzurro.localhost")
    hostname = host.split(":")[0]
    base = base_domain.split(":")[0]

    if hostname == base:
        return None  # apex

    suffix = "." + base
    if hostname.endswith(suffix):
        slug = hostname[: -len(suffix)]
        return slug if slug else None

    return None


async def resolve_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Site:
    """FastAPI dependency: resolve the current tenant from the Host header.

    Raises 404 for apex hits, unknown subdomains, or missing tenants.
    """
    host = request.headers.get("host", "")
    slug = extract_slug(host, settings.PLATFORM_BASE_DOMAIN)

    if slug is None:
        raise HTTPException(status_code=404, detail="Unknown site")

    site = await site_service.get_site_by_slug(db, slug)
    if site is None:
        raise HTTPException(status_code=404, detail="Unknown site")

    return site
