"""Tests for menu publish/draft state — filter, toggle, IDOR."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site
from app.services import menu_service, site_service
from app.services.exceptions import MenuNotFound
from tests.conftest import make_menu, make_owner, make_site


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


# ---------------------------------------------------------------------------
# Public filter: get_site_by_slug returns only published menus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_site_by_slug_filters_unpublished(db_session):
    """Only published menus come back from the public load path."""
    site = await make_site(db_session, slug="filtertest")
    await make_menu(db_session, site, name="Published Menu", position=10, is_published=True)
    await make_menu(db_session, site, name="Draft Menu", position=20, is_published=False)
    await db_session.flush()

    loaded = await site_service.get_site_by_slug(db_session, "filtertest")
    assert loaded is not None
    menu_names = [m.name for m in loaded.menus]
    assert "Published Menu" in menu_names
    assert "Draft Menu" not in menu_names


@pytest.mark.asyncio
async def test_get_site_by_slug_all_published(db_session):
    """When all menus are published, all appear."""
    site = await make_site(db_session, slug="allpub")
    await make_menu(db_session, site, name="A", position=10)
    await make_menu(db_session, site, name="B", position=20)
    await db_session.flush()

    loaded = await site_service.get_site_by_slug(db_session, "allpub")
    assert len(loaded.menus) == 2


@pytest.mark.asyncio
async def test_get_site_by_slug_none_published(db_session):
    """When no menus are published, the list is empty."""
    site = await make_site(db_session, slug="nonepub")
    await make_menu(db_session, site, name="Hidden", position=10, is_published=False)
    await db_session.flush()

    loaded = await site_service.get_site_by_slug(db_session, "nonepub")
    assert loaded.menus == []


# ---------------------------------------------------------------------------
# Service: set_menu_published
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_menu_published_unpublish(db_session):
    """Unpublishing a menu sets is_published=False."""
    site = await make_site(db_session, slug="toggle")
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Live Menu", position=10)
    auth = _auth(owner)

    result = await menu_service.set_menu_published(db_session, auth, menu.menu_id, False)
    assert result.is_published is False


@pytest.mark.asyncio
async def test_set_menu_published_republish(db_session):
    """Re-publishing a draft menu sets is_published=True."""
    site = await make_site(db_session, slug="repub")
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Draft", position=10, is_published=False)
    auth = _auth(owner)

    result = await menu_service.set_menu_published(db_session, auth, menu.menu_id, True)
    assert result.is_published is True


# ---------------------------------------------------------------------------
# IDOR: foreign menu_id -> MenuNotFound
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_menu_published_idor(db_session):
    """A menu belonging to another site cannot be toggled — raises MenuNotFound."""
    site_a = await make_site(db_session, slug="sitea")
    site_b = await make_site(db_session, slug="siteb")
    owner_a = await make_owner(db_session, site_a)
    menu_b = await make_menu(db_session, site_b, name="Other Menu", position=10)
    auth_a = _auth(owner_a)

    with pytest.raises(MenuNotFound):
        await menu_service.set_menu_published(db_session, auth_a, menu_b.menu_id, False)


# ---------------------------------------------------------------------------
# Admin list: unfiltered (owner sees drafts)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_owner_menus_includes_drafts(db_session):
    """The admin list returns all menus regardless of is_published."""
    site = await make_site(db_session, slug="adminlist")
    owner = await make_owner(db_session, site)
    await make_menu(db_session, site, name="Published", position=10, is_published=True)
    await make_menu(db_session, site, name="Draft", position=20, is_published=False)
    auth = _auth(owner)

    menus = await menu_service.list_owner_menus(db_session, auth)
    names = [m.name for m in menus]
    assert "Published" in names
    assert "Draft" in names
