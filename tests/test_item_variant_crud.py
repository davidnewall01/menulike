"""Item + variant CRUD tests — scoping, IDOR, CSRF, position."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_session
from app.models.menu import MenuItem, MenuItemVariant
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


# ---------------------------------------------------------------------------
# Helpers — build a full tree for a site
# ---------------------------------------------------------------------------

async def _tree(db_session, slug="itemsite", site_name="Item Site"):
    """Create site -> menu -> section -> subsection, return (site, owner, menu, subsection)."""
    site = await make_site(db_session, slug=slug, name=site_name)
    owner = await make_owner(db_session, site)
    menu = await make_menu(db_session, site, name="Dinner", position=10)
    section = await make_section(db_session, menu, name="Starters")
    subsection = await make_subsection(db_session, section)
    return site, owner, menu, subsection


# ===========================================================================
# Item CRUD
# ===========================================================================

class TestItemCreate:
    async def test_create_item(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="ic1")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/item",
            data={
                "name": "Bruschetta",
                "description": "Tomato & basil",
                "dietary_tags": "vegetarian, gluten-free",
                "csrf_token": csrf,
                "subsection_id": str(sub.subsection_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(MenuItem).where(MenuItem.subsection_id == sub.subsection_id)
        )
        items = result.scalars().all()
        assert len(items) == 1
        assert items[0].name == "Bruschetta"
        assert items[0].description == "Tomato & basil"
        assert items[0].dietary_tags == ["vegetarian", "gluten-free"]
        assert items[0].position == 10

    async def test_create_item_position_increments(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="ic2")
        await make_item(db_session, sub, name="First", position=10)
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/item",
            data={
                "name": "Second",
                "csrf_token": csrf,
                "subsection_id": str(sub.subsection_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(MenuItem)
            .where(MenuItem.subsection_id == sub.subsection_id)
            .order_by(MenuItem.position)
        )
        items = result.scalars().all()
        assert len(items) == 2
        assert items[1].name == "Second"
        assert items[1].position == 20

    async def test_create_item_without_csrf_returns_403(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="ic3")
        token = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/item",
            data={
                "name": "Nope",
                "subsection_id": str(sub.subsection_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
        )
        assert resp.status_code == 403


class TestItemUpdate:
    async def test_update_item(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="iu1")
        item = await make_item(db_session, sub, name="Old")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}",
            data={
                "name": "New",
                "description": "Updated",
                "dietary_tags": "vegan",
                "featured": "on",
                "_action": "update",
                "csrf_token": csrf,
            },
            cookies={"session": token},
        )
        assert resp.status_code == 200

        await db_session.refresh(item)
        assert item.name == "New"
        assert item.description == "Updated"
        assert item.dietary_tags == ["vegan"]
        assert item.featured is True


class TestItemDelete:
    async def test_delete_item_cascades_variants(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="id1")
        item = await make_item(db_session, sub, name="Doomed")
        variant = await make_variant(db_session, item, price="15.00", label="Large")
        item_id = item.menu_item_id
        variant_id = variant.menu_item_variant_id
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/item/{item_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 200

        result = await db_session.execute(
            select(MenuItem).where(MenuItem.menu_item_id == item_id)
        )
        assert result.scalar_one_or_none() is None

        result = await db_session.execute(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_variant_id == variant_id)
        )
        assert result.scalar_one_or_none() is None


class TestItemIDOR:
    async def test_update_foreign_item_returns_404(self, client, db_session):
        _, owner_a, _, sub_a = await _tree(db_session, slug="iia")
        _, _, _, sub_b = await _tree(db_session, slug="iib")
        item_b = await make_item(db_session, sub_b, name="B's Item")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/item/{item_b.menu_item_id}",
            data={"name": "Hacked", "_action": "update", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        await db_session.refresh(item_b)
        assert item_b.name == "B's Item"

    async def test_delete_foreign_item_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="iida")
        _, _, _, sub_b = await _tree(db_session, slug="iidb")
        item_b = await make_item(db_session, sub_b, name="B's Precious")
        item_b_id = item_b.menu_item_id

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/item/{item_b_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(MenuItem).where(MenuItem.menu_item_id == item_b_id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_create_item_under_foreign_subsection_returns_404(self, client, db_session):
        _, owner_a, menu_a, _ = await _tree(db_session, slug="iisa")
        _, _, _, sub_b = await _tree(db_session, slug="iisb")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            "/admin/item",
            data={
                "name": "Injected",
                "subsection_id": str(sub_b.subsection_id),
                "menu_id": str(menu_a.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        # No item created under B's subsection
        result = await db_session.execute(
            select(MenuItem).where(MenuItem.subsection_id == sub_b.subsection_id)
        )
        assert result.scalars().all() == []


# ===========================================================================
# Variant CRUD
# ===========================================================================

class TestVariantCreate:
    async def test_create_variant(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="vc1")
        item = await make_item(db_session, sub, name="Pizza")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/variant",
            data={
                "label": "Large",
                "price": "24.50",
                "csrf_token": csrf,
                "item_id": str(item.menu_item_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_id == item.menu_item_id)
        )
        variants = result.scalars().all()
        assert len(variants) == 1
        assert variants[0].label == "Large"
        assert float(variants[0].price) == 24.50
        assert variants[0].position == 10

    async def test_create_variant_without_csrf_returns_403(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="vc2")
        item = await make_item(db_session, sub, name="Pizza")
        token = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/variant",
            data={
                "label": "Small",
                "price": "18.00",
                "item_id": str(item.menu_item_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
        )
        assert resp.status_code == 403


class TestVariantUpdate:
    async def test_update_variant(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="vu1")
        item = await make_item(db_session, sub, name="Pizza")
        variant = await make_variant(db_session, item, price="20.00", label="Medium")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/variant/{variant.menu_item_variant_id}",
            data={
                "label": "Regular",
                "price": "22.00",
                "_action": "update",
                "csrf_token": csrf,
            },
            cookies={"session": token},
        )
        assert resp.status_code == 200

        await db_session.refresh(variant)
        assert variant.label == "Regular"
        assert float(variant.price) == 22.00


class TestVariantDelete:
    async def test_delete_variant(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="vd1")
        item = await make_item(db_session, sub, name="Pizza")
        variant = await make_variant(db_session, item, price="20.00")
        variant_id = variant.menu_item_variant_id
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            f"/admin/variant/{variant_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 200

        result = await db_session.execute(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_variant_id == variant_id)
        )
        assert result.scalar_one_or_none() is None


class TestVariantIDOR:
    async def test_update_foreign_variant_returns_404(self, client, db_session):
        _, owner_a, _, sub_a = await _tree(db_session, slug="via")
        _, _, _, sub_b = await _tree(db_session, slug="vib")
        item_b = await make_item(db_session, sub_b, name="B's Item")
        variant_b = await make_variant(db_session, item_b, price="30.00", label="B's Variant")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/variant/{variant_b.menu_item_variant_id}",
            data={"label": "Hacked", "price": "1.00", "_action": "update", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        await db_session.refresh(variant_b)
        assert variant_b.label == "B's Variant"
        assert float(variant_b.price) == 30.00

    async def test_delete_foreign_variant_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="vida")
        _, _, _, sub_b = await _tree(db_session, slug="vidb")
        item_b = await make_item(db_session, sub_b, name="B's Item")
        variant_b = await make_variant(db_session, item_b, price="30.00")
        variant_b_id = variant_b.menu_item_variant_id

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            f"/admin/variant/{variant_b_id}",
            data={"_action": "delete", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_variant_id == variant_b_id)
        )
        assert result.scalar_one_or_none() is not None

    async def test_create_variant_on_foreign_item_returns_404(self, client, db_session):
        _, owner_a, menu_a, _ = await _tree(db_session, slug="vica")
        _, _, _, sub_b = await _tree(db_session, slug="vicb")
        item_b = await make_item(db_session, sub_b, name="B's Item")

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)

        resp = await client.post(
            "/admin/variant",
            data={
                "label": "Injected",
                "price": "1.00",
                "item_id": str(item_b.menu_item_id),
                "menu_id": str(menu_a.menu_id),
                "csrf_token": csrf,
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 404

        result = await db_session.execute(
            select(MenuItemVariant).where(MenuItemVariant.menu_item_id == item_b.menu_item_id)
        )
        assert result.scalars().all() == []


class TestGetPartialIDOR:
    """GET partial endpoints must also scope — owner A cannot view B's edit forms."""

    async def test_get_item_edit_foreign_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="gpia")
        _, _, _, sub_b = await _tree(db_session, slug="gpib")
        item_b = await make_item(db_session, sub_b, name="B Secret Item")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/item/{item_b.menu_item_id}/edit",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Secret Item" not in resp.text

    async def test_get_item_display_foreign_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="gpda")
        _, _, _, sub_b = await _tree(db_session, slug="gpdb")
        item_b = await make_item(db_session, sub_b, name="B Hidden Dish")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/item/{item_b.menu_item_id}",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Hidden Dish" not in resp.text

    async def test_get_variant_edit_foreign_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="gpvea")
        _, _, _, sub_b = await _tree(db_session, slug="gpveb")
        item_b = await make_item(db_session, sub_b, name="B Item")
        variant_b = await make_variant(db_session, item_b, price="99.00", label="B Secret Label")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/variant/{variant_b.menu_item_variant_id}/edit",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Secret Label" not in resp.text

    async def test_get_variant_display_foreign_returns_404(self, client, db_session):
        _, owner_a, _, _ = await _tree(db_session, slug="gpvda")
        _, _, _, sub_b = await _tree(db_session, slug="gpvdb")
        item_b = await make_item(db_session, sub_b, name="B Item")
        variant_b = await make_variant(db_session, item_b, price="77.00", label="B Visible Label")

        token = encode_session(owner_a.user_id)
        resp = await client.get(
            f"/admin/variant/{variant_b.menu_item_variant_id}",
            cookies={"session": token},
        )
        assert resp.status_code == 404
        assert "B Visible Label" not in resp.text


class TestDietaryTagsEdgeCases:
    async def test_empty_dietary_tags_stored_as_empty_list(self, client, db_session):
        site, owner, menu, sub = await _tree(db_session, slug="dtag")
        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)

        resp = await client.post(
            "/admin/item",
            data={
                "name": "Plain Dish",
                "dietary_tags": "",
                "csrf_token": csrf,
                "subsection_id": str(sub.subsection_id),
                "menu_id": str(menu.menu_id),
            },
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        result = await db_session.execute(
            select(MenuItem).where(MenuItem.subsection_id == sub.subsection_id)
        )
        item = result.scalar_one()
        assert item.dietary_tags == []
