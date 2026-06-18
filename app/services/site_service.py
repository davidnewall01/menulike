"""Read-only site queries for the public render path."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site


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
