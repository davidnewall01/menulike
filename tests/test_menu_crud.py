"""Menu CRUD tests — create, rename, delete, IDOR, CSRF, first-menu position."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_session
from app.models.menu import Menu
from tests.conftest import csrf_token_for, make_menu, make_owner, make_site


class TestMenuList:
    async def test_list_shows_own_menus(self, client, db_session):
        site = await make_site(db_session, slug="listsite", name="List Site")
        owner = await make_owner(db_session, site)
        await make_menu(db_session, site, name="Dinner", position=10)
        await make_menu(db_session, site, name="Drinks", position=20)

        token = encode_session(owner.user_id)
        resp = await client.get("/admin/menu", cookies={"session": token})
        assert resp.status_code == 200
        assert "Dinner" in resp.text
        assert "Drinks" in resp.text

    async def test_list_excludes_other_sites_menus(self, client, db_session):
        site_a = await make_site(db_session, slug="lista", name="Site A")
        site_b = await make_site(db_session, slug="listb", name="Site B")
        owner_a = await make_owner(db_session, site_a)
        await make_menu(db_session, site_a, name="A Menu", position=10)
        await make_menu(db_session, site_b, name="B Menu", position=10)

        token = encode_session(owner_a.user_id)
        resp = await client.get("/admin/menu", cookies={"session": token})
        assert resp.status_code == 200
        assert "A Menu" in resp.text
        assert "B Menu" not in resp.text


class TestMenuCreate:
    async def test_create_menu(self, client, db_session):
        site = await make_site(db_session, slug="createsite", name="Create Site")
        owner = await make_owner(db_session, site)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/menu",
            data={"name": "Lunch", "description": "Midday eats", "availability_note": "12-3pm", "csrf_token": csrf},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Menu).where(Menu.site_id == site.site_id)
        )
        menus = result.scalars().all()
        assert len(menus) == 1
        assert menus[0].name == "Lunch"
        assert menus[0].description == "Midday eats"
        assert menus[0].availability_note == "12-3pm"
        assert menus[0].site_id == site.site_id

    async def test_create_first_menu_gets_position_10(self, client, db_session):
        """First menu on a site with zero menus gets position 10 (COALESCE path)."""
        site = await make_site(db_session, slug="firstmenu", name="First Menu Site")
        owner = await make_owner(db_session, site)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/menu",
            data={"name": "First", "csrf_token": csrf},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Menu).where(Menu.site_id == site.site_id)
        )
        menu = result.scalar_one()
        assert menu.position == 10

    async def test_create_menu_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="nocsrf", name="No CSRF")
        owner = await make_owner(db_session, site)
        token = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/menu",
            data={"name": "Nope"},
            cookies={"session": token},
        )
        assert resp.status_code == 403

    async def test_create_menu_blank_name_rejected(self, client, db_session):
        site = await make_site(db_session, slug="blankname", name="Blank Name")
        owner = await make_owner(db_session, site)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/menu",
            data={"name": "   ", "csrf_token": csrf},
            cookies={"session": token},
        )
        # Should re-render the list with an error, not create
        assert resp.status_code == 200
        result = await db_session.execute(
            select(Menu).where(Menu.site_id == site.site_id)
        )
        assert result.scalars().all() == []


class TestMenuUpdate:
    async def test_rename_menu(self, client, db_session):
        site = await make_site(db_session, slug="renamesite", name="Rename Site")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="Old Name", position=10)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/menu/{menu.menu_id}",
            data={"name": "New Name", "availability_note": "Evenings", "_action": "update", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 200
        assert "Menu updated" in resp.text

        await db_session.refresh(menu)
        assert menu.name == "New Name"
        assert menu.availability_note == "Evenings"


class TestMenuDelete:
    async def test_delete_menu(self, client, db_session):
        site = await make_site(db_session, slug="delsite", name="Del Site")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="Doomed", position=10)
        menu_id = menu.menu_id
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/menu/{menu_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 200
        assert "Menu deleted" in resp.text

        result = await db_session.execute(
            select(Menu).where(Menu.menu_id == menu_id)
        )
        assert result.scalar_one_or_none() is None


class TestMenuIDOR:
    """Owner A cannot update or delete site B's menu via a crafted menu_id."""

    async def test_update_foreign_menu_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="idora", name="IDOR A")
        site_b = await make_site(db_session, slug="idorb", name="IDOR B")
        owner_a = await make_owner(db_session, site_a)
        menu_b = await make_menu(db_session, site_b, name="B's Menu", position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/menu/{menu_b.menu_id}",
            data={"name": "Hacked", "_action": "update", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        # B's menu is untouched
        await db_session.refresh(menu_b)
        assert menu_b.name == "B's Menu"

    async def test_delete_foreign_menu_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="idorda", name="IDOR Del A")
        site_b = await make_site(db_session, slug="idordb", name="IDOR Del B")
        owner_a = await make_owner(db_session, site_a)
        menu_b = await make_menu(db_session, site_b, name="B's Precious", position=10)
        menu_b_id = menu_b.menu_id

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/menu/{menu_b_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        # B's menu still exists
        result = await db_session.execute(
            select(Menu).where(Menu.menu_id == menu_b_id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_view_foreign_menu_canvas_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="idorva", name="IDOR View A")
        site_b = await make_site(db_session, slug="idorvb", name="IDOR View B")
        owner_a = await make_owner(db_session, site_a)
        menu_b = await make_menu(db_session, site_b, name="B's Canvas", position=10)

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/menu/{menu_b.menu_id}",
            cookies={"session": token},
        )
        assert resp.status_code == 404

    async def test_nonexistent_menu_id_returns_404(self, client, db_session):
        site = await make_site(db_session, slug="ghost", name="Ghost Site")
        owner = await make_owner(db_session, site)
        token = encode_session(owner.user_id)

        fake_id = uuid.uuid4()
        resp = await client.get(
            f"/admin/menu/{fake_id}",
            cookies={"session": token},
        )
        assert resp.status_code == 404
