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
