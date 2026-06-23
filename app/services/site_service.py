"""Site queries and mutations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.content_block import ContentBlock
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site
from app.models.user import User
from app.schemas.site import SiteDetailsForm
from app.services.exceptions import AlreadyHasSite, InvalidTemplate, NoSiteInScope, SiteNotFound
from app.web.template_resolver import AVAILABLE_TEMPLATES


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_site_by_slug(db: AsyncSession, slug: str) -> Site | None:
    """Load a site with all public-render data eager-loaded.

    Eager-loads: menus tree, regular_hours, hours_exceptions,
    content_blocks (+ nested image).
    Read-only — no flush, no commit.
    """
    stmt = (
        select(Site)
        .where(Site.slug == slug)
        .options(
            selectinload(Site.menus.and_(Menu.is_published.is_(True)))
            .selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants),
            selectinload(Site.regular_hours),
            selectinload(Site.hours_exceptions),
            selectinload(Site.content_blocks)
            .selectinload(ContentBlock.image),
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

    Eager-loads menus, regular_hours, hours_exceptions, content_blocks
    (with images). Used by the publish route to feed the resolver for
    can_publish eligibility checks.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    stmt = (
        select(Site)
        .where(Site.site_id == auth_ctx.scoped_site_id)
        .options(
            selectinload(Site.menus),
            selectinload(Site.regular_hours),
            selectinload(Site.hours_exceptions),
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

    Combines the full menu tree (including drafts) with regular_hours,
    hours_exceptions, and content_blocks (+ nested image). Used by the
    preview routes to feed the resolver in preview mode.
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
            selectinload(Site.regular_hours),
            selectinload(Site.hours_exceptions),
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

    # Bind the user to the new site
    result = await db.execute(select(User).where(User.user_id == auth_ctx.user_id))
    user = result.scalar_one()
    user.site_id = site.site_id
    await db.flush()

    return site


_DETAIL_FIELDS = [
    "restaurant_name", "tagline",
    "address_street", "address_suburb", "address_state", "address_postcode",
    "phone", "email",
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


_AVAILABLE_KEYS = {k for k, _ in AVAILABLE_TEMPLATES}


async def set_template(
    db: AsyncSession, auth_ctx: AuthContext, template: str
) -> Site:
    """Set the template for the owner's scoped site. Flush only.

    Validates the template value against AVAILABLE_TEMPLATES.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    if template not in _AVAILABLE_KEYS:
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

def can_publish(site_view: dict) -> tuple[bool, list[str]]:
    """Check whether a site is eligible to go live.

    Pure function — reads the resolver's SiteView (mode-independent status).
    Returns (eligible, reasons) where reasons lists unmet requirements.

    Minimum bar for the pilot: menu is real AND home hero is real.
    Keys on the mode-independent status/source, so can_publish agrees
    with the dashboard tiles by construction.
    """
    reasons: list[str] = []

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
