"""Menu coordinator — owns the commit boundary for menu writes."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.menu import Menu
from app.schemas.menu import MenuForm
from app.services import menu_service


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
