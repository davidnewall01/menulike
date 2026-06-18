"""Menu queries and mutations — scoped to the owner's site."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.schemas.menu import MenuForm
from app.services.exceptions import MenuNotFound, NoSiteInScope


# ---------------------------------------------------------------------------
# Reads (scoped-load — the IDOR primitive)
# ---------------------------------------------------------------------------

async def get_owner_menu(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID
) -> Menu:
    """Load a menu by id, scoped to the owner's site.

    A foreign menu_id (belonging to another site) returns no row -> MenuNotFound.
    This is the IDOR boundary: the caller supplies a menu_id, but the query
    filters on scoped_site_id so a crafted foreign id cannot reach another
    tenant's data.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Menu).where(
            Menu.menu_id == menu_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
    )
    menu = result.scalar_one_or_none()
    if menu is None:
        raise MenuNotFound(f"menu_id={menu_id}")
    return menu


async def get_owner_menu_with_tree(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID
) -> Menu:
    """Load a menu with the full tree for the canvas render."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Menu)
        .where(
            Menu.menu_id == menu_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
        .options(
            selectinload(Menu.sections)
            .selectinload(Section.subsections)
            .selectinload(Subsection.items)
            .selectinload(MenuItem.variants)
        )
    )
    menu = result.scalar_one_or_none()
    if menu is None:
        raise MenuNotFound(f"menu_id={menu_id}")
    return menu


async def list_owner_menus(
    db: AsyncSession, auth_ctx: AuthContext
) -> list[Menu]:
    """List all menus for the owner's site, ordered by position."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Menu)
        .where(Menu.site_id == auth_ctx.scoped_site_id)
        .order_by(Menu.position)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def create_menu(
    db: AsyncSession, auth_ctx: AuthContext, form: MenuForm
) -> Menu:
    """Create a new menu on the owner's site.

    position = max existing + 10 (or 10 if first). site_id comes from
    scoped_site_id, never from input.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(func.coalesce(func.max(Menu.position), 0))
        .where(Menu.site_id == auth_ctx.scoped_site_id)
    )
    max_pos = result.scalar_one()

    menu = Menu(
        site_id=auth_ctx.scoped_site_id,
        name=form.name,
        description=form.description,
        availability_note=form.availability_note,
        position=max_pos + 10,
    )
    db.add(menu)
    await db.flush()
    return menu


async def update_menu(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID, form: MenuForm
) -> Menu:
    """Rename / update a menu. Scoped-load first (IDOR boundary)."""
    menu = await get_owner_menu(db, auth_ctx, menu_id)
    menu.name = form.name
    menu.description = form.description
    menu.availability_note = form.availability_note
    await db.flush()
    return menu


async def delete_menu(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID
) -> None:
    """Delete a menu and its entire tree (cascade). Scoped-load first."""
    menu = await get_owner_menu(db, auth_ctx, menu_id)
    await db.delete(menu)
    await db.flush()
