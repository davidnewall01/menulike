"""Site queries and mutations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site
from app.schemas.site import SiteDetailsForm
from app.services.exceptions import NoSiteInScope, SiteNotFound


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_site_by_slug(db: AsyncSession, slug: str) -> Site | None:
    """Load a site and its full menu tree by slug.

    Eager-loads the entire chain: menus -> sections -> subsections -> items -> variants.
    Read-only — no flush, no commit.
    """
    stmt = (
        select(Site)
        .where(Site.slug == slug)
        .options(
            selectinload(Site.menus)
            .selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants)
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_owner_site(db: AsyncSession, auth_ctx: AuthContext) -> Site | None:
    """Load the site scoped to this auth context.

    Returns None for internal_admin (no scoped site). Raises 400 if the
    scoped site_id doesn't resolve — fail closed.
    """
    if auth_ctx.scoped_site_id is None:
        return None

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")
    return site


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

_DETAIL_FIELDS = [
    "restaurant_name", "tagline", "hero_heading", "hero_subheading",
    "about_story", "address_street", "address_suburb", "address_state",
    "address_postcode", "address_country", "phone", "email",
    "booking_url", "order_url", "meta_title", "meta_description",
]


async def update_site_details(
    db: AsyncSession,
    auth_ctx: AuthContext,
    form: SiteDetailsForm,
) -> Site:
    """Apply validated detail edits to the owner's scoped site.

    Resolves the target site from auth_ctx.scoped_site_id ONLY — never
    accepts a site_id from the caller. Flushes but does NOT commit.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")

    for field in _DETAIL_FIELDS:
        setattr(site, field, getattr(form, field))

    await db.flush()
    return site
