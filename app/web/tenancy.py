"""Tenant resolution from the Host header.

Two-stage resolution:
  1. Exact match in custom_domain (active) → site_id.
  2. Subdomain parse: {slug}.<PLATFORM_BASE_DOMAIN> → slug → site.
  3. Neither → 404.

The tenant is NEVER derived from route params.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.custom_domain import CustomDomain
from app.models.site import Site
from app.services import site_service


class SiteNotPublished(Exception):
    """The resolved site exists but is not published yet.

    Carries the restaurant_name so the exception handler can render the
    coming-soon page without any other tenant data.
    """

    def __init__(self, restaurant_name: str) -> None:
        self.restaurant_name = restaurant_name
        super().__init__(restaurant_name)


def normalise_host(host: str) -> str:
    """Lowercase, strip port, strip trailing dot.

    Shared normalisation used at both lookup-time (resolver) and store-time
    (domain INSERT). MUST be identical in both paths or matches silently fail.
    """
    return host.split(":")[0].lower().rstrip(".")


def extract_slug(host: str, base_domain: str) -> str | None:
    """Extract the tenant slug from a Host header value.

    Pure function — no DB, no side effects.

    Returns the subdomain label if host is ``<slug>.<base_domain>``
    (with or without a port suffix, case-insensitive, trailing-dot safe).
    Returns None for the apex domain or any unrecognised host.
    """
    hostname = normalise_host(host)
    base = normalise_host(base_domain)

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

    Stage 1: custom domain exact match (active only).
    Stage 2: subdomain parse against PLATFORM_BASE_DOMAIN.
    Stage 3: no match → 404.

    Raises SiteNotPublished for unpublished sites — caught by the
    exception handler in main.py to render the coming-soon page.

    Admin preview routes never call this (they use require_owner_site),
    so the publish gate cannot accidentally catch preview.
    """
    # Approximated sends the original hostname in apx-incoming-host;
    # fall back to the standard Host header for direct/subdomain access.
    raw_host = (
        request.headers.get("apx-incoming-host")
        or request.headers.get("host")
        or ""
    )
    host = normalise_host(raw_host)

    site: Site | None = None

    # Stage 1: custom domain lookup
    result = await db.execute(
        select(CustomDomain.site_id)
        .where(CustomDomain.domain == host, CustomDomain.status == "active")
    )
    custom_site_id = result.scalar_one_or_none()
    if custom_site_id is not None:
        site = await site_service.get_site_by_id_public(db, custom_site_id)

    # Stage 2: subdomain parse
    if site is None:
        slug = extract_slug(raw_host, settings.PLATFORM_BASE_DOMAIN)
        if slug is not None:
            site = await site_service.get_site_by_slug(db, slug)

    # Stage 3: no match
    if site is None:
        raise HTTPException(status_code=404, detail="Unknown site")

    # Published gate — same for both resolution paths
    if not site.is_published:
        raise SiteNotPublished(site.restaurant_name)

    return site
