"""Section + subsection CRUD tests — create, edit, delete, cascade, headingless,
description, move-item, IDOR (including double-scope on move), CSRF."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_session
from app.models.menu import MenuItem, MenuItemVariant, Section, Subsection
from tests.conftest import (
    csrf_token_for,
    make_item,
    make_menu,
    make_owner,
    make_section,
    make_site,
    make_subsection,
    make_variant,
)


async def _tree(db_session, slug="secsite"):
    """Site -> owner -> menu, return (site, owner, menu)."""
    site = await make_site(db_session, slug=slug, name=f"Site {slug}")
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Dinner", position=10)
    return site, owner, menu


# ===========================================================================
# Section CRUD
# ===========================================================================

class TestSectionCreate:
    async def test_create_section(self, client, db_session):
        site, owner, menu = await _tree(db_session, slug="sc1")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/section",
            data={
                "name": "Starters",
                "description": "To begin",
                "csrf_token": csrf,
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Section).where(Section.menu_id == menu.menu_id)
        )
        sections = result.scalars().all()
        assert len(sections) == 1
        assert sections[0].name == "Starters"
        assert sections[0].description == "To begin"
        assert sections[0].position == 10

    async def test_create_section_position_increments(self, client, db_session):
        site, owner, menu = await _tree(db_session, slug="sc2")
        await make_section(db_session, menu, name="First", position=10)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/section",
            data={"name": "Second", "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Section)
            .where(Section.menu_id == menu.menu_id)
            .order_by(Section.position)
        )
        sections = result.scalars().all()
        assert len(sections) == 2
        assert sections[1].name == "Second"
        assert sections[1].position == 20

    async def test_create_section_without_csrf_returns_403(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="sc3")
        token = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/section",
            data={"name": "Nope", "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        assert resp.status_code == 403


class TestSectionUpdate:
    async def test_update_section(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="su1")
        section = await make_section(db_session, menu, name="Old")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/section/{section.section_id}",
            data={
                "name": "New",
                "description": "Updated desc",
                "_action": "update",
                "csrf_token": csrf,
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
        )
        assert resp.status_code == 200

        await db_session.refresh(section)
        assert section.name == "New"
        assert section.description == "Updated desc"

    async def test_description_round_trips(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="su2")
        section = await make_section(db_session, menu, name="Sec")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        # Set description
        await client.post(
            f"/admin/section/{section.section_id}",
            data={"name": "Sec", "description": "A fine section", "_action": "update",
                  "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        await db_session.refresh(section)
        assert section.description == "A fine section"

        # Clear description
        csrf2 = csrf_token_for(owner)
        await client.post(
            f"/admin/section/{section.section_id}",
            data={"name": "Sec", "description": "", "_action": "update",
                  "csrf_token": csrf2, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        await db_session.refresh(section)
        assert section.description is None


class TestSectionDelete:
    async def test_delete_section_cascades(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="sd1")
        section = await make_section(db_session, menu, name="Doomed")
        sub = await make_subsection(db_session, section)
        item = await make_item(db_session, sub, name="Gone Item")
        variant = await make_variant(db_session, item, price="10.00")
        section_id = section.section_id
        sub_id = sub.subsection_id
        item_id = item.menu_item_id
        variant_id = variant.menu_item_variant_id

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/section/{section_id}",
            data={"_action": "delete", "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        for model, pk_col, pk_val in [
            (Section, Section.section_id, section_id),
            (Subsection, Subsection.subsection_id, sub_id),
            (MenuItem, MenuItem.menu_item_id, item_id),
            (MenuItemVariant, MenuItemVariant.menu_item_variant_id, variant_id),
        ]:
            result = await db_session.execute(select(model).where(pk_col == pk_val))
            assert result.scalar_one_or_none() is None, f"{model.__name__} not cascaded"


class TestSectionIDOR:
    async def test_update_foreign_section_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="sia")
        _, _, menu_b = await _tree(db_session, slug="sib")
        section_b = await make_section(db_session, menu_b, name="B's Section")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/section/{section_b.section_id}",
            data={"name": "Hacked", "_action": "update", "csrf_token": csrf,
                  "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        await db_session.refresh(section_b)
        assert section_b.name == "B's Section"

    async def test_delete_foreign_section_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="sida")
        _, _, menu_b = await _tree(db_session, slug="sidb")
        section_b = await make_section(db_session, menu_b, name="B's Keep")
        section_b_id = section_b.section_id

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/section/{section_b_id}",
            data={"_action": "delete", "csrf_token": csrf, "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(Section).where(Section.section_id == section_b_id)
        )
        assert result.scalar_one_or_none() is not None


# ===========================================================================
# Subsection CRUD
# ===========================================================================

class TestSubsectionCreate:
    async def test_create_subsection(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="ssc1")
        section = await make_section(db_session, menu, name="Mains")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/subsection",
            data={
                "name": "Fish",
                "description": "From the sea",
                "csrf_token": csrf,
                "section_id": str(section.section_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Subsection).where(Subsection.section_id == section.section_id)
        )
        subs = result.scalars().all()
        assert len(subs) == 1
        assert subs[0].name == "Fish"
        assert subs[0].description == "From the sea"
        assert subs[0].position == 10

    async def test_create_headingless_subsection(self, client, db_session):
        """Blank name -> stored as None (headingless subsection)."""
        _, owner, menu = await _tree(db_session, slug="ssc2")
        section = await make_section(db_session, menu, name="Pizza")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/subsection",
            data={
                "name": "",
                "csrf_token": csrf,
                "section_id": str(section.section_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(Subsection).where(Subsection.section_id == section.section_id)
        )
        sub = result.scalar_one()
        assert sub.name is None

    async def test_create_subsection_without_csrf_returns_403(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="ssc3")
        section = await make_section(db_session, menu, name="S")
        token = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/subsection",
            data={"name": "X", "section_id": str(section.section_id),
                  "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        assert resp.status_code == 403


class TestSubsectionUpdate:
    async def test_update_subsection(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="ssu1")
        section = await make_section(db_session, menu, name="S")
        sub = await make_subsection(db_session, section, name="Old")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/subsection/{sub.subsection_id}",
            data={"name": "New", "description": "Updated", "_action": "update",
                  "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        assert resp.status_code == 200

        await db_session.refresh(sub)
        assert sub.name == "New"
        assert sub.description == "Updated"

    async def test_subsection_description_round_trips(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="ssu2")
        section = await make_section(db_session, menu, name="S")
        sub = await make_subsection(db_session, section, name="Sub")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        await client.post(
            f"/admin/subsection/{sub.subsection_id}",
            data={"name": "Sub", "description": "Desc here", "_action": "update",
                  "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        await db_session.refresh(sub)
        assert sub.description == "Desc here"

        csrf2 = csrf_token_for(owner)
        await client.post(
            f"/admin/subsection/{sub.subsection_id}",
            data={"name": "Sub", "description": "", "_action": "update",
                  "csrf_token": csrf2, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
        )
        await db_session.refresh(sub)
        assert sub.description is None


class TestSubsectionDelete:
    async def test_delete_subsection_cascades_items(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="ssd1")
        section = await make_section(db_session, menu, name="S")
        sub = await make_subsection(db_session, section, name="Doomed")
        item = await make_item(db_session, sub, name="Gone")
        sub_id = sub.subsection_id
        item_id = item.menu_item_id

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/subsection/{sub_id}",
            data={"_action": "delete", "csrf_token": csrf, "menu_id": str(menu.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        for model, col, val in [
            (Subsection, Subsection.subsection_id, sub_id),
            (MenuItem, MenuItem.menu_item_id, item_id),
        ]:
            result = await db_session.execute(select(model).where(col == val))
            assert result.scalar_one_or_none() is None


class TestSubsectionIDOR:
    async def test_update_foreign_subsection_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="ssia")
        _, _, menu_b = await _tree(db_session, slug="ssib")
        sec_b = await make_section(db_session, menu_b, name="B Sec")
        sub_b = await make_subsection(db_session, sec_b, name="B Sub")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/subsection/{sub_b.subsection_id}",
            data={"name": "Hacked", "_action": "update", "csrf_token": csrf,
                  "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        await db_session.refresh(sub_b)
        assert sub_b.name == "B Sub"


# ===========================================================================
# Move Item
# ===========================================================================

class TestMoveItem:
    async def test_move_item_to_another_subsection(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="mv1")
        sec = await make_section(db_session, menu, name="S")
        sub_a = await make_subsection(db_session, sec, name="A")
        sub_b = await make_subsection(db_session, sec, name="B", position=20)
        item = await make_item(db_session, sub_a, name="Movable", position=10)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}/move",
            data={
                "target_subsection_id": str(sub_b.subsection_id),
                "menu_id": str(menu.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(item)
        assert item.subsection_id == sub_b.subsection_id
        assert item.position == 10  # first item in target -> 10

    async def test_move_item_appends_at_end(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="mv2")
        sec = await make_section(db_session, menu, name="S")
        sub_a = await make_subsection(db_session, sec, name="A")
        sub_b = await make_subsection(db_session, sec, name="B", position=20)
        await make_item(db_session, sub_b, name="Existing", position=10)
        item = await make_item(db_session, sub_a, name="Movable", position=10)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}/move",
            data={
                "target_subsection_id": str(sub_b.subsection_id),
                "menu_id": str(menu.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(item)
        assert item.subsection_id == sub_b.subsection_id
        assert item.position == 20  # after existing (10) -> 20

    async def test_move_without_csrf_returns_403(self, client, db_session):
        _, owner, menu = await _tree(db_session, slug="mv3")
        sec = await make_section(db_session, menu, name="S")
        sub_a = await make_subsection(db_session, sec, name="A")
        sub_b = await make_subsection(db_session, sec, name="B", position=20)
        item = await make_item(db_session, sub_a, name="Item")

        token = encode_session(owner.user_id)

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}/move",
            data={
                "target_subsection_id": str(sub_b.subsection_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
        )
        assert resp.status_code == 403


class TestMoveItemIDOR:
    async def test_move_foreign_item_returns_404(self, client, db_session):
        """Owner A tries to move B's item -> 404, B untouched."""
        _, owner_a, menu_a = await _tree(db_session, slug="mia")
        sec_a = await make_section(db_session, menu_a, name="A Sec")
        sub_a = await make_subsection(db_session, sec_a, name="A Sub")

        _, _, menu_b = await _tree(db_session, slug="mib")
        sec_b = await make_section(db_session, menu_b, name="B Sec")
        sub_b = await make_subsection(db_session, sec_b, name="B Sub")
        item_b = await make_item(db_session, sub_b, name="B's Item")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/item/{item_b.menu_item_id}/move",
            data={
                "target_subsection_id": str(sub_a.subsection_id),
                "menu_id": str(menu_a.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        await db_session.refresh(item_b)
        assert item_b.subsection_id == sub_b.subsection_id

    async def test_move_own_item_to_foreign_subsection_returns_404(self, client, db_session):
        """Owner A tries to move their item into B's subsection -> 404."""
        _, owner_a, menu_a = await _tree(db_session, slug="misa")
        sec_a = await make_section(db_session, menu_a, name="A Sec")
        sub_a = await make_subsection(db_session, sec_a, name="A Sub")
        item_a = await make_item(db_session, sub_a, name="A's Item")

        _, _, menu_b = await _tree(db_session, slug="misb")
        sec_b = await make_section(db_session, menu_b, name="B Sec")
        sub_b = await make_subsection(db_session, sec_b, name="B Sub")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/item/{item_a.menu_item_id}/move",
            data={
                "target_subsection_id": str(sub_b.subsection_id),
                "menu_id": str(menu_a.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        await db_session.refresh(item_a)
        assert item_a.subsection_id == sub_a.subsection_id


class TestCreateUnderForeignParent:
    async def test_create_section_under_foreign_menu_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="cfpa")
        _, _, menu_b = await _tree(db_session, slug="cfpb")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            "/admin/section",
            data={"name": "Injected", "csrf_token": csrf, "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(Section).where(Section.menu_id == menu_b.menu_id)
        )
        assert result.scalars().all() == []

    async def test_create_subsection_under_foreign_section_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="cfsa")
        _, _, menu_b = await _tree(db_session, slug="cfsb")
        sec_b = await make_section(db_session, menu_b, name="B Sec")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            "/admin/subsection",
            data={"name": "Injected", "csrf_token": csrf,
                  "section_id": str(sec_b.section_id), "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(Subsection).where(Subsection.section_id == sec_b.section_id)
        )
        assert result.scalars().all() == []


class TestGetEditPartialIDOR:
    async def test_get_section_edit_foreign_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="gepa")
        _, _, menu_b = await _tree(db_session, slug="gepb")
        sec_b = await make_section(db_session, menu_b, name="B Secret Section")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/section/{sec_b.section_id}/edit",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Secret Section" not in resp.text

    async def test_get_subsection_edit_foreign_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="gesa")
        _, _, menu_b = await _tree(db_session, slug="gesb")
        sec_b = await make_section(db_session, menu_b, name="B Sec")
        sub_b = await make_subsection(db_session, sec_b, name="B Secret Sub")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/subsection/{sub_b.subsection_id}/edit",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Secret Sub" not in resp.text


class TestDeleteForeignSubsection:
    async def test_delete_foreign_subsection_returns_404(self, client, db_session):
        _, owner_a, _ = await _tree(db_session, slug="dfsa")
        _, _, menu_b = await _tree(db_session, slug="dfsb")
        sec_b = await make_section(db_session, menu_b, name="B Sec")
        sub_b = await make_subsection(db_session, sec_b, name="B Precious Sub")
        sub_b_id = sub_b.subsection_id

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/subsection/{sub_b_id}",
            data={"_action": "delete", "csrf_token": csrf, "menu_id": str(menu_b.menu_id)},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(Subsection).where(Subsection.subsection_id == sub_b_id)
        )
        assert result.scalar_one_or_none() is not None
