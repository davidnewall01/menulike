"""Menu queries and mutations — scoped to the owner's site."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.schemas.menu import ItemForm, MenuForm, SectionForm, SubsectionForm, VariantForm
from app.services.exceptions import (
    ItemNotFound,
    MenuNotFound,
    NoSiteInScope,
    ReorderMismatch,
    SectionNotFound,
    SubsectionNotFound,
    VariantNotFound,
)


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


# ---------------------------------------------------------------------------
# Section scoped-load + CRUD
# ---------------------------------------------------------------------------

async def get_owner_section(
    db: AsyncSession, auth_ctx: AuthContext, section_id: uuid.UUID
) -> Section:
    """Load a section by id, scoped to the owner's site.

    Joins section -> menu, filters menu.site_id == scoped_site_id.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Section)
        .join(Menu, Section.menu_id == Menu.menu_id)
        .where(
            Section.section_id == section_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
    )
    section = result.scalar_one_or_none()
    if section is None:
        raise SectionNotFound(f"section_id={section_id}")
    return section


async def create_section(
    db: AsyncSession, auth_ctx: AuthContext,
    menu_id: uuid.UUID, form: SectionForm
) -> Section:
    """Create a new section in a menu. Scoped-load the parent menu first."""
    menu = await get_owner_menu(db, auth_ctx, menu_id)

    result = await db.execute(
        select(func.coalesce(func.max(Section.position), 0))
        .where(Section.menu_id == menu.menu_id)
    )
    max_pos = result.scalar_one()

    section = Section(
        menu_id=menu.menu_id,
        name=form.name,
        description=form.description,
        position=max_pos + 10,
    )
    db.add(section)
    await db.flush()
    return section


async def update_section(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, form: SectionForm
) -> Section:
    """Update a section. Scoped-load first."""
    section = await get_owner_section(db, auth_ctx, section_id)
    section.name = form.name
    section.description = form.description
    await db.flush()
    return section


async def delete_section(
    db: AsyncSession, auth_ctx: AuthContext, section_id: uuid.UUID
) -> None:
    """Delete a section (cascade subsections->items->variants). Scoped-load first."""
    section = await get_owner_section(db, auth_ctx, section_id)
    await db.delete(section)
    await db.flush()


# ---------------------------------------------------------------------------
# Subsection CRUD
# ---------------------------------------------------------------------------

async def create_subsection(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, form: SubsectionForm
) -> Subsection:
    """Create a new subsection in a section. Scoped-load the parent first."""
    section = await get_owner_section(db, auth_ctx, section_id)

    result = await db.execute(
        select(func.coalesce(func.max(Subsection.position), 0))
        .where(Subsection.section_id == section.section_id)
    )
    max_pos = result.scalar_one()

    subsection = Subsection(
        section_id=section.section_id,
        name=form.name,
        description=form.description,
        position=max_pos + 10,
    )
    db.add(subsection)
    await db.flush()
    return subsection


async def update_subsection(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, form: SubsectionForm
) -> Subsection:
    """Update a subsection. Scoped-load first."""
    subsection = await get_owner_subsection(db, auth_ctx, subsection_id)
    subsection.name = form.name
    subsection.description = form.description
    await db.flush()
    return subsection


async def delete_subsection(
    db: AsyncSession, auth_ctx: AuthContext, subsection_id: uuid.UUID
) -> None:
    """Delete a subsection (cascade items->variants). Scoped-load first."""
    subsection = await get_owner_subsection(db, auth_ctx, subsection_id)
    await db.delete(subsection)
    await db.flush()


# ---------------------------------------------------------------------------
# Item scoped-loads
# ---------------------------------------------------------------------------

async def get_owner_subsection(
    db: AsyncSession, auth_ctx: AuthContext, subsection_id: uuid.UUID
) -> Subsection:
    """Load a subsection by id, scoped to the owner's site via the FK chain.

    Joins subsection -> section -> menu, filters menu.site_id == scoped_site_id.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(Subsection)
        .join(Section, Subsection.section_id == Section.section_id)
        .join(Menu, Section.menu_id == Menu.menu_id)
        .where(
            Subsection.subsection_id == subsection_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise SubsectionNotFound(f"subsection_id={subsection_id}")
    return sub


async def get_owner_item(
    db: AsyncSession, auth_ctx: AuthContext, item_id: uuid.UUID
) -> MenuItem:
    """Load an item by id, scoped to the owner's site via the FK chain.

    Joins item -> subsection -> section -> menu, filters menu.site_id.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(MenuItem)
        .join(Subsection, MenuItem.subsection_id == Subsection.subsection_id)
        .join(Section, Subsection.section_id == Section.section_id)
        .join(Menu, Section.menu_id == Menu.menu_id)
        .where(
            MenuItem.menu_item_id == item_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ItemNotFound(f"item_id={item_id}")
    return item


async def get_owner_item_with_variants(
    db: AsyncSession, auth_ctx: AuthContext, item_id: uuid.UUID
) -> MenuItem:
    """Load an item with its variants eagerly loaded."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(MenuItem)
        .join(Subsection, MenuItem.subsection_id == Subsection.subsection_id)
        .join(Section, Subsection.section_id == Section.section_id)
        .join(Menu, Section.menu_id == Menu.menu_id)
        .where(
            MenuItem.menu_item_id == item_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
        .options(selectinload(MenuItem.variants))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ItemNotFound(f"item_id={item_id}")
    return item


# ---------------------------------------------------------------------------
# Item writes (flush only)
# ---------------------------------------------------------------------------

async def create_item(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, form: ItemForm
) -> MenuItem:
    """Create a new item in a subsection. Scoped-load the parent first."""
    subsection = await get_owner_subsection(db, auth_ctx, subsection_id)

    result = await db.execute(
        select(func.coalesce(func.max(MenuItem.position), 0))
        .where(MenuItem.subsection_id == subsection.subsection_id)
    )
    max_pos = result.scalar_one()

    item = MenuItem(
        subsection_id=subsection.subsection_id,
        name=form.name,
        description=form.description,
        dietary_tags=form.parsed_dietary_tags(),
        featured=form.featured,
        position=max_pos + 10,
    )
    db.add(item)
    await db.flush()
    return item


async def update_item(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, form: ItemForm
) -> MenuItem:
    """Update an item. Scoped-load first."""
    item = await get_owner_item(db, auth_ctx, item_id)
    item.name = form.name
    item.description = form.description
    item.dietary_tags = form.parsed_dietary_tags()
    item.featured = form.featured
    await db.flush()
    return item


async def delete_item(
    db: AsyncSession, auth_ctx: AuthContext, item_id: uuid.UUID
) -> None:
    """Delete an item (cascade deletes variants). Scoped-load first."""
    item = await get_owner_item(db, auth_ctx, item_id)
    await db.delete(item)
    await db.flush()


async def move_item(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, target_subsection_id: uuid.UUID
) -> MenuItem:
    """Move an item to a different subsection. Double-scoped: both the item
    and the destination subsection must belong to the owner's site.

    A foreign item_id OR a foreign target_subsection_id -> 404.
    """
    item = await get_owner_item(db, auth_ctx, item_id)
    target = await get_owner_subsection(db, auth_ctx, target_subsection_id)

    result = await db.execute(
        select(func.coalesce(func.max(MenuItem.position), 0))
        .where(MenuItem.subsection_id == target.subsection_id)
    )
    max_pos = result.scalar_one()

    item.subsection_id = target.subsection_id
    item.position = max_pos + 10
    await db.flush()
    return item


# ---------------------------------------------------------------------------
# Variant scoped-load
# ---------------------------------------------------------------------------

async def get_owner_variant(
    db: AsyncSession, auth_ctx: AuthContext, variant_id: uuid.UUID
) -> MenuItemVariant:
    """Load a variant by id, scoped to the owner's site via the FK chain.

    Joins variant -> item -> subsection -> section -> menu, filters menu.site_id.
    Deepest scoped-load in the menu tree.
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(MenuItemVariant)
        .join(MenuItem, MenuItemVariant.menu_item_id == MenuItem.menu_item_id)
        .join(Subsection, MenuItem.subsection_id == Subsection.subsection_id)
        .join(Section, Subsection.section_id == Section.section_id)
        .join(Menu, Section.menu_id == Menu.menu_id)
        .where(
            MenuItemVariant.menu_item_variant_id == variant_id,
            Menu.site_id == auth_ctx.scoped_site_id,
        )
    )
    variant = result.scalar_one_or_none()
    if variant is None:
        raise VariantNotFound(f"variant_id={variant_id}")
    return variant


# ---------------------------------------------------------------------------
# Variant writes (flush only)
# ---------------------------------------------------------------------------

async def create_variant(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, form: VariantForm
) -> MenuItemVariant:
    """Create a new variant on an item. Scoped-load the parent item first."""
    item = await get_owner_item(db, auth_ctx, item_id)

    result = await db.execute(
        select(func.coalesce(func.max(MenuItemVariant.position), 0))
        .where(MenuItemVariant.menu_item_id == item.menu_item_id)
    )
    max_pos = result.scalar_one()

    variant = MenuItemVariant(
        menu_item_id=item.menu_item_id,
        label=form.label,
        price=form.parsed_price(),
        position=max_pos + 10,
    )
    db.add(variant)
    await db.flush()
    return variant


async def update_variant(
    db: AsyncSession, auth_ctx: AuthContext,
    variant_id: uuid.UUID, form: VariantForm
) -> MenuItemVariant:
    """Update a variant. Scoped-load first."""
    variant = await get_owner_variant(db, auth_ctx, variant_id)
    variant.label = form.label
    variant.price = form.parsed_price()
    await db.flush()
    return variant


async def delete_variant(
    db: AsyncSession, auth_ctx: AuthContext, variant_id: uuid.UUID
) -> None:
    """Delete a variant. Scoped-load first."""
    variant = await get_owner_variant(db, auth_ctx, variant_id)
    await db.delete(variant)
    await db.flush()


# ---------------------------------------------------------------------------
# Reorder (within a parent — flush only)
# ---------------------------------------------------------------------------

async def _reorder_children(db, parent_col, parent_id, pk_col, model, ordered_ids):
    """Generic reorder: verify ordered_ids is an exact permutation of the
    parent's current children, then renumber positions. Flush only."""
    result = await db.execute(
        select(pk_col).where(parent_col == parent_id)
    )
    current_ids = set(result.scalars().all())

    submitted = [uuid.UUID(str(i)) for i in ordered_ids]
    if set(submitted) != current_ids or len(submitted) != len(current_ids):
        raise ReorderMismatch(
            f"Submitted ids don't match parent's children: "
            f"expected {current_ids}, got {set(submitted)}"
        )

    result = await db.execute(
        select(model).where(parent_col == parent_id)
    )
    children = {getattr(c, pk_col.key): c for c in result.scalars().all()}
    for idx, child_id in enumerate(submitted):
        children[child_id].position = (idx + 1) * 10
    await db.flush()


async def reorder_sections(
    db: AsyncSession, auth_ctx: AuthContext,
    menu_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    """Reorder sections within a menu. Scoped-load the parent first."""
    await get_owner_menu(db, auth_ctx, menu_id)
    await _reorder_children(
        db, Section.menu_id, menu_id,
        Section.section_id, Section, ordered_ids,
    )


async def reorder_subsections(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    """Reorder subsections within a section. Scoped-load the parent first."""
    await get_owner_section(db, auth_ctx, section_id)
    await _reorder_children(
        db, Subsection.section_id, section_id,
        Subsection.subsection_id, Subsection, ordered_ids,
    )


async def reorder_items(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    """Reorder items within a subsection. Scoped-load the parent first."""
    await get_owner_subsection(db, auth_ctx, subsection_id)
    await _reorder_children(
        db, MenuItem.subsection_id, subsection_id,
        MenuItem.menu_item_id, MenuItem, ordered_ids,
    )


async def reorder_variants(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    """Reorder variants within an item. Scoped-load the parent first."""
    await get_owner_item(db, auth_ctx, item_id)
    await _reorder_children(
        db, MenuItemVariant.menu_item_id, item_id,
        MenuItemVariant.menu_item_variant_id, MenuItemVariant, ordered_ids,
    )
