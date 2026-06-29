"""Site queries and mutations."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.auth.context import AuthContext
from app.models.content_block import ContentBlock
from app.models.location import Location
from app.models.menu import Menu, MenuFooterBlock, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteDetailsForm
from app.services.exceptions import AlreadyHasSite, InvalidTemplate, NoSiteInScope, SiteNotFound
from app.services import template_meta_service


# Shared eager-load options for public-render site queries. Used by both
# get_site_by_slug and get_site_by_id_public to avoid duplication.
_PUBLIC_SITE_OPTIONS = (
    selectinload(Site.menus.and_(Menu.is_published.is_(True)))
    .selectinload(Menu.sections)
    .selectinload(Section.subsections)
    .selectinload(Subsection.items)
    .selectinload(MenuItem.variants),
    selectinload(Site.menus.and_(Menu.is_published.is_(True)))
    .selectinload(Menu.sections)
    .selectinload(Section.photo),
    selectinload(Site.menus.and_(Menu.is_published.is_(True)))
    .selectinload(Menu.footer_blocks),
    selectinload(Site.locations)
    .selectinload(Location.regular_hours),
    selectinload(Site.locations)
    .selectinload(Location.hours_exceptions),
    selectinload(Site.content_blocks)
    .selectinload(ContentBlock.image),
)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_site_by_slug(db: AsyncSession, slug: str) -> Site | None:
    """Load a site with all public-render data eager-loaded.

    Eager-loads: menus tree, locations (with regular_hours + hours_exceptions),
    content_blocks (+ nested image).
    Read-only — no flush, no commit.
    """
    stmt = (
        select(Site)
        .where(Site.slug == slug)
        .options(*_PUBLIC_SITE_OPTIONS)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_site_by_id_public(
    db: AsyncSession, site_id: uuid.UUID,
) -> Site | None:
    """Load a site by ID with public-render eager-loading.

    Same eager-loading as get_site_by_slug but keyed by site_id instead of
    slug. Used by the custom-domain resolution path.
    Read-only — no flush, no commit.
    """
    stmt = (
        select(Site)
        .where(Site.site_id == site_id)
        .options(*_PUBLIC_SITE_OPTIONS)
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


async def get_owner_site_with_drafts(
    db: AsyncSession, auth_ctx: AuthContext,
) -> Site | None:
    """Load the owner's site with ALL menus (including drafts) eager-loaded.

    Used for the authenticated preview — drafts must be visible to the owner
    but never to the public. Do NOT use this for the public render path
    (that's get_site_by_slug, which filters is_published).
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    stmt = (
        select(Site)
        .where(Site.site_id == auth_ctx.scoped_site_id)
        .options(
            selectinload(Site.menus)
            .selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants),
            selectinload(Site.menus)
            .selectinload(Menu.footer_blocks),
        )
    )
    result = await db.execute(stmt)
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")
    return site


async def get_owner_site_full(
    db: AsyncSession, auth_ctx: AuthContext,
) -> Site:
    """Load the owner's site with all relationships the resolver needs.

    Eager-loads menus, locations (with regular_hours + hours_exceptions),
    content_blocks (with images). Used by the publish route to feed the
    resolver for can_publish eligibility checks.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    stmt = (
        select(Site)
        .where(Site.site_id == auth_ctx.scoped_site_id)
        .options(
            selectinload(Site.menus),
            selectinload(Site.locations)
            .selectinload(Location.regular_hours),
            selectinload(Site.locations)
            .selectinload(Location.hours_exceptions),
            selectinload(Site.content_blocks)
            .selectinload(ContentBlock.image),
        )
    )
    result = await db.execute(stmt)
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")
    return site


async def get_owner_site_preview(
    db: AsyncSession, auth_ctx: AuthContext,
) -> Site:
    """Load the owner's site with everything needed for preview rendering.

    Combines the full menu tree (including drafts) with locations (hours),
    and content_blocks (+ nested image). Used by the preview routes to
    feed the resolver in preview mode.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    stmt = (
        select(Site)
        .where(Site.site_id == auth_ctx.scoped_site_id)
        .options(
            selectinload(Site.menus)
            .selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants),
            selectinload(Site.menus)
            .selectinload(Menu.sections)
            .selectinload(Section.photo),
            selectinload(Site.menus)
            .selectinload(Menu.footer_blocks),
            selectinload(Site.locations)
            .selectinload(Location.regular_hours),
            selectinload(Site.locations)
            .selectinload(Location.hours_exceptions),
            selectinload(Site.content_blocks)
            .selectinload(ContentBlock.image),
        )
    )
    result = await db.execute(stmt)
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")
    return site


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def create_site(
    db: AsyncSession,
    auth_ctx: AuthContext,
    restaurant_name: str,
    slug: str,
) -> Site:
    """Create a new site and bind it to the authenticated owner.

    INVERTED GUARD vs every other write service: this one asserts
    site_id IS None. An owner who already has a site cannot create a
    second one. This is deliberate — do not "fix" it to match the
    normal scoped_site_id-must-be-present pattern.

    Flushes but does NOT commit (coordinator commits).
    """
    if auth_ctx.site_id is not None:
        raise AlreadyHasSite()

    site = Site(
        slug=slug,
        restaurant_name=restaurant_name,
        settings={},
    )
    db.add(site)
    await db.flush()  # site_id is now assigned

    # Every site must have at least one location (the default)
    default_location = Location(site_id=site.site_id, position=0)
    db.add(default_location)

    # Bind the user to the new site
    result = await db.execute(select(User).where(User.user_id == auth_ctx.user_id))
    user = result.scalar_one()
    user.site_id = site.site_id
    await db.flush()

    return site


_DETAIL_FIELDS = [
    "restaurant_name",
]


async def update_tagline(
    db: AsyncSession, auth_ctx: AuthContext, tagline: str | None,
) -> Site:
    """Set the site tagline. Flush only."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")

    site.tagline = tagline
    await db.flush()
    return site


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


async def update_seo(
    db: AsyncSession,
    auth_ctx: AuthContext,
    meta_title: str | None,
    meta_description: str | None,
) -> Site:
    """Set SEO override fields. None = revert to derived. Flush only."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")

    site.meta_title = meta_title
    site.meta_description = meta_description
    await db.flush()
    return site


async def set_template(
    db: AsyncSession, auth_ctx: AuthContext, template: str
) -> Site:
    """Set the template for the owner's scoped site. Flush only.

    Validates the template value against the template_meta DB table.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    available = await template_meta_service.get_available_keys(db)
    if template not in available:
        raise InvalidTemplate(f"Unknown template '{template}'")

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")

    site.template = template
    await db.flush()
    return site


# ---------------------------------------------------------------------------
# Publish / go-live
# ---------------------------------------------------------------------------

def can_publish(
    site_view: dict, *, template_available: bool = True,
) -> tuple[bool, list[str]]:
    """Check whether a site is eligible to go live.

    Pure function — reads the resolver's SiteView (mode-independent status)
    plus an optional template_available flag (resolved by the caller from DB).
    Returns (eligible, reasons) where reasons lists unmet requirements.

    Minimum bar: menu is real AND home hero is real AND template is available.
    """
    reasons: list[str] = []

    if not template_available:
        reasons.append("Template not available yet")

    if site_view["menu"].status == "sample":
        reasons.append("Add your menu")

    if site_view["home"].fields["hero"].source != "real":
        reasons.append("Add a hero photo")

    return (len(reasons) == 0, reasons)


async def set_published(
    db: AsyncSession, auth_ctx: AuthContext, *, is_published: bool,
) -> Site:
    """Set the publish state for the owner's scoped site. Flush only.

    Scoped via auth_ctx.scoped_site_id — never accepts a site_id param.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Site).where(Site.site_id == auth_ctx.scoped_site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise SiteNotFound(f"site_id={auth_ctx.scoped_site_id}")

    site.is_published = is_published
    await db.flush()
    return site


async def create_showcase_site(
    db: AsyncSession, restaurant_name: str, slug: str, template: str = "linen",
) -> Site:
    """Create an orphan showcase site (no bound User). Flush only."""
    site = Site(
        restaurant_name=restaurant_name,
        slug=slug,
        template=template,
        is_showcase=True,
        is_published=False,
    )
    db.add(site)
    await db.flush()
    return site


async def list_all_sites(db: AsyncSession) -> list[Site]:
    """Return ALL sites. ADMIN-ONLY picker query — do NOT reuse for
    customer-facing metrics/counts (includes showcase sites)."""
    result = await db.execute(
        select(Site).order_by(Site.restaurant_name)
    )
    return list(result.scalars().all())


async def list_showcase_sites(db: AsyncSession) -> list[Site]:
    """Return all showcase sites, ordered by showcase_position (nulls last)."""
    result = await db.execute(
        select(Site)
        .where(Site.is_showcase.is_(True))
        .order_by(
            Site.showcase_position.asc().nullslast(),
            Site.restaurant_name,
        )
    )
    return list(result.scalars().all())
