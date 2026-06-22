"""Menu coordinator — owns the commit boundary for menu writes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.schemas.menu import ItemForm, MenuForm, SectionForm, SubsectionForm, VariantForm
from app.services import menu_service


async def set_menu_published(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID, published: bool
) -> Menu:
    menu = await menu_service.set_menu_published(db, auth_ctx, menu_id, published)
    await db.commit()
    return menu


async def create_menu(
    db: AsyncSession, auth_ctx: AuthContext, form: MenuForm
) -> Menu:
    menu = await menu_service.create_menu(db, auth_ctx, form)
    await db.commit()
    return menu


async def update_menu(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID, form: MenuForm
) -> Menu:
    menu = await menu_service.update_menu(db, auth_ctx, menu_id, form)
    await db.commit()
    return menu


async def delete_menu(
    db: AsyncSession, auth_ctx: AuthContext, menu_id: uuid.UUID
) -> None:
    await menu_service.delete_menu(db, auth_ctx, menu_id)
    await db.commit()


# ---------------------------------------------------------------------------
# Section
# ---------------------------------------------------------------------------

async def create_section(
    db: AsyncSession, auth_ctx: AuthContext,
    menu_id: uuid.UUID, form: SectionForm
) -> Section:
    section = await menu_service.create_section(db, auth_ctx, menu_id, form)
    await db.commit()
    return section


async def update_section(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, form: SectionForm
) -> Section:
    section = await menu_service.update_section(db, auth_ctx, section_id, form)
    await db.commit()
    return section


async def delete_section(
    db: AsyncSession, auth_ctx: AuthContext, section_id: uuid.UUID
) -> None:
    await menu_service.delete_section(db, auth_ctx, section_id)
    await db.commit()


# ---------------------------------------------------------------------------
# Subsection
# ---------------------------------------------------------------------------

async def create_subsection(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, form: SubsectionForm
) -> Subsection:
    subsection = await menu_service.create_subsection(db, auth_ctx, section_id, form)
    await db.commit()
    return subsection


async def update_subsection(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, form: SubsectionForm
) -> Subsection:
    subsection = await menu_service.update_subsection(db, auth_ctx, subsection_id, form)
    await db.commit()
    return subsection


async def delete_subsection(
    db: AsyncSession, auth_ctx: AuthContext, subsection_id: uuid.UUID
) -> None:
    await menu_service.delete_subsection(db, auth_ctx, subsection_id)
    await db.commit()


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

async def create_item(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, form: ItemForm,
    extras: list[dict] | None = None,
) -> MenuItem:
    item = await menu_service.create_item(db, auth_ctx, subsection_id, form, extras=extras)
    await db.commit()
    return item


async def update_item(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, form: ItemForm,
    extras: list[dict] | None = None,
) -> MenuItem:
    item = await menu_service.update_item(db, auth_ctx, item_id, form, extras=extras)
    await db.commit()
    return item


async def delete_item(
    db: AsyncSession, auth_ctx: AuthContext, item_id: uuid.UUID
) -> None:
    await menu_service.delete_item(db, auth_ctx, item_id)
    await db.commit()


async def move_item(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, target_subsection_id: uuid.UUID
) -> MenuItem:
    item = await menu_service.move_item(db, auth_ctx, item_id, target_subsection_id)
    await db.commit()
    return item


# ---------------------------------------------------------------------------
# Variant
# ---------------------------------------------------------------------------

async def create_variant(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, form: VariantForm
) -> MenuItemVariant:
    variant = await menu_service.create_variant(db, auth_ctx, item_id, form)
    await db.commit()
    return variant


async def update_variant(
    db: AsyncSession, auth_ctx: AuthContext,
    variant_id: uuid.UUID, form: VariantForm
) -> MenuItemVariant:
    variant = await menu_service.update_variant(db, auth_ctx, variant_id, form)
    await db.commit()
    return variant


async def delete_variant(
    db: AsyncSession, auth_ctx: AuthContext, variant_id: uuid.UUID
) -> None:
    await menu_service.delete_variant(db, auth_ctx, variant_id)
    await db.commit()


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

async def reorder_sections(
    db: AsyncSession, auth_ctx: AuthContext,
    menu_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    await menu_service.reorder_sections(db, auth_ctx, menu_id, ordered_ids)
    await db.commit()


async def reorder_subsections(
    db: AsyncSession, auth_ctx: AuthContext,
    section_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    await menu_service.reorder_subsections(db, auth_ctx, section_id, ordered_ids)
    await db.commit()


async def reorder_items(
    db: AsyncSession, auth_ctx: AuthContext,
    subsection_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    await menu_service.reorder_items(db, auth_ctx, subsection_id, ordered_ids)
    await db.commit()


async def reorder_variants(
    db: AsyncSession, auth_ctx: AuthContext,
    item_id: uuid.UUID, ordered_ids: list[uuid.UUID]
) -> None:
    await menu_service.reorder_variants(db, auth_ctx, item_id, ordered_ids)
    await db.commit()
