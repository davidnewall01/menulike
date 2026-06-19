"""Reorder tests — valid reorder, integrity/IDOR rejection, CSRF, all four levels."""

import uuid
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encode_session
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
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


def _encode_reorder(csrf: str, ids: list) -> str:
    """Build form-encoded body with repeated ordered_ids fields."""
    pairs = [("csrf_token", csrf)]
    for i in ids:
        pairs.append(("ordered_ids", str(i)))
    return urlencode(pairs)


FORM_CT = {"content-type": "application/x-www-form-urlencoded"}


# ===========================================================================
# Reorder sections
# ===========================================================================

class TestReorderSections:
    async def test_reorder_sections_valid(self, client, db_session):
        site = await make_site(db_session, slug="rs1", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        s1 = await make_section(db_session, menu, name="A", position=10)
        s2 = await make_section(db_session, menu, name="B", position=20)
        s3 = await make_section(db_session, menu, name="C", position=30)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [s3.section_id, s1.section_id, s2.section_id])

        resp = await client.post(
            f"/admin/menu/{menu.menu_id}/reorder-sections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 204

        await db_session.refresh(s1)
        await db_session.refresh(s2)
        await db_session.refresh(s3)
        assert s3.position == 10
        assert s1.position == 20
        assert s2.position == 30

    async def test_reorder_sections_missing_id_rejected(self, client, db_session):
        site = await make_site(db_session, slug="rs2", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        s1 = await make_section(db_session, menu, name="A", position=10)
        s2 = await make_section(db_session, menu, name="B", position=20)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [s1.section_id])  # missing s2

        resp = await client.post(
            f"/admin/menu/{menu.menu_id}/reorder-sections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 400

    async def test_reorder_sections_foreign_menu_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="rs3a", name="A")
        owner_a = await make_owner(db_session, site_a)

        site_b = await make_site(db_session, slug="rs3b", name="B")
        menu_b = await make_menu(db_session, site_b, name="MB", position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)
        body = _encode_reorder(csrf, [])

        resp = await client.post(
            f"/admin/menu/{menu_b.menu_id}/reorder-sections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 404

    async def test_reorder_sections_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="rs4", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)

        token = encode_session(owner.user_id)
        body = urlencode([("ordered_ids", str(uuid.uuid4()))])

        resp = await client.post(
            f"/admin/menu/{menu.menu_id}/reorder-sections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 403


# ===========================================================================
# Reorder subsections
# ===========================================================================

class TestReorderSubsections:
    async def test_reorder_subsections_valid(self, client, db_session):
        site = await make_site(db_session, slug="rsub1", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        section = await make_section(db_session, menu, name="Sec", position=10)
        sub1 = await make_subsection(db_session, section, name="X", position=10)
        sub2 = await make_subsection(db_session, section, name="Y", position=20)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [sub2.subsection_id, sub1.subsection_id])

        resp = await client.post(
            f"/admin/section/{section.section_id}/reorder-subsections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 204

        await db_session.refresh(sub1)
        await db_session.refresh(sub2)
        assert sub2.position == 10
        assert sub1.position == 20

    async def test_reorder_subsections_foreign_section_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="rsub2a", name="A")
        owner_a = await make_owner(db_session, site_a)

        site_b = await make_site(db_session, slug="rsub2b", name="B")
        menu_b = await make_menu(db_session, site_b, name="MB", position=10)
        sec_b = await make_section(db_session, menu_b, name="SB", position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)
        body = _encode_reorder(csrf, [])

        resp = await client.post(
            f"/admin/section/{sec_b.section_id}/reorder-subsections",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 404


# ===========================================================================
# Reorder items
# ===========================================================================

class TestReorderItems:
    async def test_reorder_items_valid(self, client, db_session):
        site = await make_site(db_session, slug="ri1", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        sec = await make_section(db_session, menu, name="S", position=10)
        sub = await make_subsection(db_session, sec, position=10)
        i1 = await make_item(db_session, sub, name="A", position=10)
        i2 = await make_item(db_session, sub, name="B", position=20)
        i3 = await make_item(db_session, sub, name="C", position=30)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [i3.menu_item_id, i1.menu_item_id, i2.menu_item_id])

        resp = await client.post(
            f"/admin/subsection/{sub.subsection_id}/reorder-items",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 204

        await db_session.refresh(i1)
        await db_session.refresh(i2)
        await db_session.refresh(i3)
        assert i3.position == 10
        assert i1.position == 20
        assert i2.position == 30

    async def test_reorder_items_foreign_id_in_list_rejected(self, client, db_session):
        """Owner A's subsection, but slips in B's item id -> 400, positions unchanged."""
        site_a = await make_site(db_session, slug="ri2a", name="A")
        owner_a = await make_owner(db_session, site_a)
        menu_a = await make_menu(db_session, site_a, name="MA", position=10)
        sec_a = await make_section(db_session, menu_a, name="SA", position=10)
        sub_a = await make_subsection(db_session, sec_a, position=10)
        item_a = await make_item(db_session, sub_a, name="A Item", position=10)

        site_b = await make_site(db_session, slug="ri2b", name="B")
        menu_b = await make_menu(db_session, site_b, name="MB", position=10)
        sec_b = await make_section(db_session, menu_b, name="SB", position=10)
        sub_b = await make_subsection(db_session, sec_b, position=10)
        item_b = await make_item(db_session, sub_b, name="B Item", position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)
        body = _encode_reorder(csrf, [item_b.menu_item_id, item_a.menu_item_id])

        resp = await client.post(
            f"/admin/subsection/{sub_a.subsection_id}/reorder-items",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 400

        await db_session.refresh(item_a)
        assert item_a.position == 10

    async def test_reorder_items_missing_id_rejected(self, client, db_session):
        site = await make_site(db_session, slug="ri3", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        sec = await make_section(db_session, menu, name="S", position=10)
        sub = await make_subsection(db_session, sec, position=10)
        i1 = await make_item(db_session, sub, name="A", position=10)
        i2 = await make_item(db_session, sub, name="B", position=20)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [i1.menu_item_id])

        resp = await client.post(
            f"/admin/subsection/{sub.subsection_id}/reorder-items",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 400

    async def test_reorder_items_foreign_subsection_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="ri4a", name="A")
        owner_a = await make_owner(db_session, site_a)

        site_b = await make_site(db_session, slug="ri4b", name="B")
        menu_b = await make_menu(db_session, site_b, name="MB", position=10)
        sec_b = await make_section(db_session, menu_b, name="SB", position=10)
        sub_b = await make_subsection(db_session, sec_b, position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)
        body = _encode_reorder(csrf, [])

        resp = await client.post(
            f"/admin/subsection/{sub_b.subsection_id}/reorder-items",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 404

    async def test_reorder_items_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="ri5", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        sec = await make_section(db_session, menu, name="S", position=10)
        sub = await make_subsection(db_session, sec, position=10)

        token = encode_session(owner.user_id)
        body = urlencode([("ordered_ids", str(uuid.uuid4()))])

        resp = await client.post(
            f"/admin/subsection/{sub.subsection_id}/reorder-items",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 403


# ===========================================================================
# Reorder variants
# ===========================================================================

class TestReorderVariants:
    async def test_reorder_variants_valid(self, client, db_session):
        site = await make_site(db_session, slug="rv1", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        sec = await make_section(db_session, menu, name="S", position=10)
        sub = await make_subsection(db_session, sec, position=10)
        item = await make_item(db_session, sub, name="Pizza", position=10)
        v1 = await make_variant(db_session, item, price="18.00", label="Small", position=10)
        v2 = await make_variant(db_session, item, price="24.00", label="Large", position=20)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [v2.menu_item_variant_id, v1.menu_item_variant_id])

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}/reorder-variants",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 204

        await db_session.refresh(v1)
        await db_session.refresh(v2)
        assert v2.position == 10
        assert v1.position == 20

    async def test_reorder_variants_foreign_item_returns_404(self, client, db_session):
        site_a = await make_site(db_session, slug="rv2a", name="A")
        owner_a = await make_owner(db_session, site_a)

        site_b = await make_site(db_session, slug="rv2b", name="B")
        menu_b = await make_menu(db_session, site_b, name="MB", position=10)
        sec_b = await make_section(db_session, menu_b, name="SB", position=10)
        sub_b = await make_subsection(db_session, sec_b, position=10)
        item_b = await make_item(db_session, sub_b, name="B Item", position=10)

        token = encode_session(owner_a.user_id)
        csrf = csrf_token_for(owner_a)
        body = _encode_reorder(csrf, [])

        resp = await client.post(
            f"/admin/item/{item_b.menu_item_id}/reorder-variants",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 404

    async def test_reorder_variants_extra_id_rejected(self, client, db_session):
        site = await make_site(db_session, slug="rv3", name="S")
        owner = await make_owner(db_session, site)
        menu = await make_menu(db_session, site, name="M", position=10)
        sec = await make_section(db_session, menu, name="S", position=10)
        sub = await make_subsection(db_session, sec, position=10)
        item = await make_item(db_session, sub, name="I", position=10)
        v1 = await make_variant(db_session, item, price="10.00", position=10)

        token = encode_session(owner.user_id)
        csrf = csrf_token_for(owner)
        body = _encode_reorder(csrf, [v1.menu_item_variant_id, uuid.uuid4()])

        resp = await client.post(
            f"/admin/item/{item.menu_item_id}/reorder-variants",
            content=body, headers=FORM_CT,
            cookies={"session": token},
        )
        assert resp.status_code == 400
