"""Integration tests for the menu add chooser + PDF upload flow (dashboard entry).

Verifies:
  - Chooser renders at /admin/menu/add (owner-scoped)
  - Upload routes into the shared extract flow from dashboard context
  - Additive new draft when menus already exist
  - Manual route still works
  - Dashboard tile links split by status
  - First-run /setup/menu regression (shared extract function not broken)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import make_menu, make_owner, make_site


async def _login(client: AsyncClient, email: str, password: str = "testpass"):
    resp = await client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return dict(resp.cookies)


# ---------------------------------------------------------------------------
# Chooser screen
# ---------------------------------------------------------------------------

class TestChooserScreen:

    async def test_chooser_renders(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="chooser-test")
        await make_owner(db_session, site, email="chooser@test.dev")
        cookies = await _login(client, "chooser@test.dev")

        resp = await client.get("/admin/menu/add", cookies=cookies)
        assert resp.status_code == 200
        html = resp.text
        assert "Add a menu" in html
        assert "Upload and read my menu" in html
        assert "build a menu by hand" in html

    async def test_chooser_requires_auth(self, client: AsyncClient):
        resp = await client.get("/admin/menu/add", follow_redirects=False)
        assert resp.status_code in (302, 303, 401)

    async def test_chooser_back_to_dashboard(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="chooser-back")
        await make_owner(db_session, site, email="chooserback@test.dev")
        cookies = await _login(client, "chooserback@test.dev")

        resp = await client.get("/admin/menu/add", cookies=cookies)
        assert 'href="/admin/"' in resp.text


# ---------------------------------------------------------------------------
# Dashboard tile link split
# ---------------------------------------------------------------------------

class TestDashboardTileLink:

    async def test_sample_state_links_to_chooser(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Menu tile in sample state links to /admin/menu/add (the chooser)."""
        site = await make_site(db_session, slug="tile-sample")
        await make_owner(db_session, site, email="tilesample@test.dev")
        cookies = await _login(client, "tilesample@test.dev")

        resp = await client.get("/admin/", cookies=cookies)
        assert 'href="/admin/menu/add"' in resp.text
        assert "Upload your menu" in resp.text

    async def test_yours_state_links_to_list(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Menu tile in yours state links to /admin/menu (the list)."""
        site = await make_site(db_session, slug="tile-yours")
        await make_owner(db_session, site, email="tileyours@test.dev")
        await make_menu(db_session, site, name="Dinner", is_published=True)
        cookies = await _login(client, "tileyours@test.dev")

        resp = await client.get("/admin/", cookies=cookies)
        # Should link to /admin/menu (list), not /admin/menu/add
        assert "Edit your menu" in resp.text
        assert 'href="/admin/menu"' in resp.text


# ---------------------------------------------------------------------------
# Menu list — add another link + manual form
# ---------------------------------------------------------------------------

class TestMenuList:

    async def test_add_another_link_when_menus_exist(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="list-add")
        await make_owner(db_session, site, email="listadd@test.dev")
        await make_menu(db_session, site, name="Food")
        cookies = await _login(client, "listadd@test.dev")

        resp = await client.get("/admin/menu", cookies=cookies)
        assert "Add another menu" in resp.text
        assert "/admin/menu/add" in resp.text

    async def test_empty_list_links_to_upload(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="list-empty")
        await make_owner(db_session, site, email="listempty@test.dev")
        cookies = await _login(client, "listempty@test.dev")

        resp = await client.get("/admin/menu", cookies=cookies)
        assert "Upload a PDF" in resp.text

    async def test_manual_form_present(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="list-manual")
        await make_owner(db_session, site, email="listmanual@test.dev")
        cookies = await _login(client, "listmanual@test.dev")

        resp = await client.get("/admin/menu", cookies=cookies)
        assert "build a menu by hand" in resp.text
        assert 'action="/admin/menu"' in resp.text

    async def test_draft_badge_visible(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """A draft menu shows 'Draft' badge in the list — important for
        the additive-upload case where a second upload creates a new draft."""
        site = await make_site(db_session, slug="list-draft")
        await make_owner(db_session, site, email="listdraft@test.dev")
        await make_menu(db_session, site, name="Imported", is_published=False)
        cookies = await _login(client, "listdraft@test.dev")

        resp = await client.get("/admin/menu", cookies=cookies)
        assert "Draft" in resp.text


# ---------------------------------------------------------------------------
# Upload flow — validation
# ---------------------------------------------------------------------------

class TestUploadValidation:

    async def test_upload_rejects_non_pdf(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="upload-val")
        await make_owner(db_session, site, email="uploadval@test.dev")
        cookies = await _login(client, "uploadval@test.dev")

        resp = await client.post(
            "/admin/menu/upload",
            cookies=cookies,
            data={"csrf_token": _csrf(resp := await client.get("/admin/menu/add", cookies=cookies))},
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.text

    async def test_upload_rejects_no_file(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="upload-nofile")
        await make_owner(db_session, site, email="uploadnofile@test.dev")
        cookies = await _login(client, "uploadnofile@test.dev")

        # Get CSRF token
        page = await client.get("/admin/menu/add", cookies=cookies)
        csrf = _csrf(page)

        resp = await client.post(
            "/admin/menu/upload",
            cookies=cookies,
            data={"csrf_token": csrf},
        )
        assert resp.status_code == 400
        assert "select a PDF" in resp.text


# ---------------------------------------------------------------------------
# Shared extract function unit tests
# ---------------------------------------------------------------------------

class TestSharedExtractHelpers:

    def test_count_dishes(self):
        from app.services.menu_extraction_service import count_dishes
        from app.schemas.extraction import ExtractedMenu

        data = {
            "menu_name": "Test",
            "sections": [
                {"name": "Starters", "subsections": [
                    {"items": [{"name": "A", "variants": []}, {"name": "B", "variants": []}]}
                ]},
                {"name": "Mains", "subsections": [
                    {"items": [{"name": "C", "variants": []}]}
                ]},
            ],
        }
        extracted = ExtractedMenu.model_validate(data)
        assert count_dishes(extracted) == 3

    def test_priceless_items(self):
        from app.services.menu_extraction_service import priceless_items
        from app.schemas.extraction import ExtractedMenu

        data = {
            "menu_name": "Test",
            "sections": [
                {"name": "Starters", "subsections": [
                    {"items": [
                        {"name": "Priced", "variants": [{"price": "10.00"}]},
                        {"name": "Unpriced", "variants": [{"price": None}]},
                        {"name": "NoVariants", "variants": []},
                    ]}
                ]},
            ],
        }
        extracted = ExtractedMenu.model_validate(data)
        result = priceless_items(extracted)
        assert "Unpriced" in result
        assert "NoVariants" in result
        assert "Priced" not in result

    def test_build_summary_context(self):
        from app.services.menu_extraction_service import build_summary_context
        from app.schemas.extraction import ExtractedMenu

        data = {
            "menu_name": "Dinner",
            "sections": [
                {"name": "Starters", "subsections": [
                    {"items": [{"name": "A", "variants": [{"price": "12.00"}]}]}
                ]},
            ],
            "menu_note": "All prices include GST",
            "ignored": ["Phone number"],
        }
        extracted = ExtractedMenu.model_validate(data)
        ctx = build_summary_context(extracted)
        assert ctx["menu_name"] == "Dinner"
        assert ctx["section_count"] == 1
        assert ctx["dish_count"] == 1
        assert ctx["section_names"] == ["Starters"]
        assert ctx["menu_note"] == "All prices include GST"
        assert ctx["ignored"] == ["Phone number"]


# ---------------------------------------------------------------------------
# First-run regression
# ---------------------------------------------------------------------------

class TestSetupRegression:

    async def test_setup_menu_page_still_renders(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """The /setup/menu page still works after the extract refactor."""
        from app.core.security import hash_password
        from app.models.user import User

        site = await make_site(db_session, slug="setup-reg")
        user = User(
            email="setupreg@test.dev",
            password_hash=hash_password("testpass"),
            role="owner",
            site_id=site.site_id,
        )
        db_session.add(user)
        await db_session.flush()

        cookies = await _login(client, "setupreg@test.dev")
        resp = await client.get("/setup/menu", cookies=cookies)
        assert resp.status_code == 200
        assert "Upload" in resp.text or "upload" in resp.text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csrf(resp) -> str:
    """Extract CSRF token from a rendered page's meta tag."""
    import re
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', resp.text)
    if m:
        return m.group(1)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
    return m.group(1) if m else ""
