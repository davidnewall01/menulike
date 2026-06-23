"""Tests for menu display_title — create, update, empty→None normalisation."""

import uuid

import pytest

from app.auth.context import AuthContext
from app.models.menu import Menu
from app.schemas.menu import MenuForm
from app.services import menu_service
from tests.conftest import make_menu, make_owner, make_site


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


# ---------------------------------------------------------------------------
# Schema: empty string normalises to None
# ---------------------------------------------------------------------------

def test_menu_form_empty_display_title_to_none():
    """Blank display_title normalises to None."""
    form = MenuForm(name="Dinner", display_title="", description="", availability_note="")
    assert form.display_title is None


def test_menu_form_whitespace_display_title_to_none():
    """Whitespace-only display_title normalises to None."""
    form = MenuForm(name="Dinner", display_title="   ")
    assert form.display_title is None


def test_menu_form_preserves_display_title():
    """Non-empty display_title is preserved."""
    form = MenuForm(name="Winter Dinner", display_title="Dinner")
    assert form.display_title == "Dinner"


# ---------------------------------------------------------------------------
# Service: create with display_title
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_menu_with_display_title(db_session):
    """Creating a menu with display_title persists it."""
    site = await make_site(db_session, slug="create-dt")
    owner = await make_owner(db_session, site)
    auth = _auth(owner)

    form = MenuForm(name="Winter Dinner", display_title="Dinner")
    menu = await menu_service.create_menu(db_session, auth, form)
    assert menu.display_title == "Dinner"
    assert menu.name == "Winter Dinner"


@pytest.mark.asyncio
async def test_create_menu_without_display_title(db_session):
    """Creating a menu without display_title leaves it None."""
    site = await make_site(db_session, slug="create-nodt")
    owner = await make_owner(db_session, site)
    auth = _auth(owner)

    form = MenuForm(name="Lunch")
    menu = await menu_service.create_menu(db_session, auth, form)
    assert menu.display_title is None


# ---------------------------------------------------------------------------
# Service: update sets/clears display_title
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_menu_sets_display_title(db_session):
    """Updating a menu can set display_title."""
    site = await make_site(db_session, slug="update-dt")
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Summer Dinner")
    auth = _auth(owner)

    form = MenuForm(name="Summer Dinner", display_title="Dinner")
    updated = await menu_service.update_menu(db_session, auth, menu.menu_id, form)
    assert updated.display_title == "Dinner"


@pytest.mark.asyncio
async def test_update_menu_clears_display_title(db_session):
    """Updating with empty display_title clears it to None."""
    site = await make_site(db_session, slug="clear-dt")
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Dinner", display_title="Custom Title")
    auth = _auth(owner)

    form = MenuForm(name="Dinner", display_title="")
    updated = await menu_service.update_menu(db_session, auth, menu.menu_id, form)
    assert updated.display_title is None
