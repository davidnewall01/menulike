"""Tests for Phase B3b: menu upload in first-run, summary, commit, preview."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.security import encode_session
from app.schemas.extraction import ExtractedMenu
from tests.conftest import (
    csrf_token_for,
    make_owner,
    make_owner_no_site,
    make_site,
)

# A minimal but valid extraction result for testing
SIMPLE_EXTRACTION = {
    "menu_name": "Test Menu",
    "menu_note": "All prices GST inclusive",
    "ignored": ["Allergy disclaimer"],
    "sections": [
        {
            "name": "Mains",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Burger",
                            "description": "Beef burger",
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "18.00"}],
                            "extras": [],
                        },
                        {
                            "name": "Salad",
                            "description": "Garden salad",
                            "dietary_tags": ["V", "GF"],
                            "variants": [{"label": None, "price": "14.00"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
        {
            "name": "Desserts",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Gelato",
                            "description": None,
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "10.00"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
    ],
}

# Extraction result with zero dishes
EMPTY_EXTRACTION = {
    "menu_name": "Empty Menu",
    "menu_note": None,
    "ignored": [],
    "sections": [
        {"name": "Mains", "note": None, "subsections": [{"name": None, "items": []}]},
    ],
}

# Extraction with priceless items
PRICELESS_EXTRACTION = {
    "menu_name": "Test Menu",
    "menu_note": None,
    "ignored": [],
    "sections": [
        {
            "name": "Mains",
            "note": None,
            "subsections": [
                {
                    "name": None,
                    "items": [
                        {
                            "name": "Mystery Dish",
                            "description": None,
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": None}],
                            "extras": [],
                        },
                        {
                            "name": "Priced Dish",
                            "description": None,
                            "dietary_tags": [],
                            "variants": [{"label": None, "price": "15.00"}],
                            "extras": [],
                        },
                    ],
                }
            ],
        },
    ],
}


def _make_pdf_bytes():
    """Minimal placeholder bytes (tests mock extract_from_pdf, not the real PDF)."""
    return b"%PDF-1.4 fake"


# ---------------------------------------------------------------------------
# First-run redirect chain
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestFirstRunRedirect:
    async def test_name_restaurant_redirects_to_setup_menu(
        self, client: AsyncClient, db_session
    ):
        """After naming, owner lands on /setup/menu not /admin/."""
        user = await make_owner_no_site(db_session, email="redirect@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/restaurant",
            data={"restaurant_name": "Redirect Test", "csrf_token": csrf},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/setup/menu"


# ---------------------------------------------------------------------------
# /setup/menu GET
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSetupMenuPage:
    async def test_renders_upload_form(self, client: AsyncClient, db_session):
        site = await make_site(db_session, slug="menu-test")
        user = await make_owner(db_session, site, email="menu@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get("/setup/menu", cookies={"session": token})
        assert resp.status_code == 200
        assert "Upload" in resp.text or "upload" in resp.text
        assert "Skip" in resp.text or "skip" in resp.text

    async def test_no_site_redirects_to_restaurant_setup(
        self, client: AsyncClient, db_session
    ):
        user = await make_owner_no_site(db_session, email="nosite@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get(
            "/setup/menu",
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/setup/restaurant"


# ---------------------------------------------------------------------------
# /setup/menu POST — extraction success → summary
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSetupMenuUpload:
    async def test_successful_upload_shows_summary(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="upload-ok")
        user = await make_owner(db_session, site, email="upload@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        extracted = ExtractedMenu.model_validate(SIMPLE_EXTRACTION)

        with patch(
            "app.web.auth.menu_extraction_service.extract_from_pdf",
            new_callable=AsyncMock,
            return_value=extracted,
        ):
            resp = await client.post(
                "/setup/menu",
                data={"csrf_token": csrf},
                files={"file": ("menu.pdf", _make_pdf_bytes(), "application/pdf")},
                cookies={"session": token},
            )

        assert resp.status_code == 200
        assert "We found your menu" in resp.text
        assert "2" in resp.text  # 2 sections
        assert "3" in resp.text  # 3 dishes
        assert "Mains" in resp.text
        assert "Desserts" in resp.text
        assert "All prices GST inclusive" in resp.text  # menu_note
        assert "Allergy disclaimer" in resp.text  # ignored

    async def test_not_pdf_shows_error(self, client: AsyncClient, db_session):
        site = await make_site(db_session, slug="not-pdf")
        user = await make_owner(db_session, site, email="notpdf@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/menu",
            data={"csrf_token": csrf},
            files={"file": ("menu.txt", b"not a pdf", "text/plain")},
            cookies={"session": token},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.text

    async def test_no_file_shows_error(self, client: AsyncClient, db_session):
        site = await make_site(db_session, slug="no-file")
        user = await make_owner(db_session, site, email="nofile@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/menu",
            data={"csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 400
        assert "select" in resp.text.lower() or "PDF" in resp.text

    async def test_extraction_failed_shows_friendly_error(
        self, client: AsyncClient, db_session
    ):
        from app.services.menu_extraction_service import ExtractionFailed

        site = await make_site(db_session, slug="fail-extract")
        user = await make_owner(db_session, site, email="fail@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        with patch(
            "app.web.auth.menu_extraction_service.extract_from_pdf",
            new_callable=AsyncMock,
            side_effect=ExtractionFailed("bad json", raw_text="garbage"),
        ):
            resp = await client.post(
                "/setup/menu",
                data={"csrf_token": csrf},
                files={"file": ("menu.pdf", _make_pdf_bytes(), "application/pdf")},
                cookies={"session": token},
            )

        assert resp.status_code == 422
        assert "couldn't make sense" in resp.text.lower() or "skip" in resp.text.lower()
        # Must NOT show raw model response
        assert "garbage" not in resp.text

    async def test_invalid_pdf_shows_friendly_error(
        self, client: AsyncClient, db_session
    ):
        from app.services.menu_extraction_service import InvalidPDF

        site = await make_site(db_session, slug="bad-pdf")
        user = await make_owner(db_session, site, email="badpdf@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        with patch(
            "app.web.auth.menu_extraction_service.extract_from_pdf",
            new_callable=AsyncMock,
            side_effect=InvalidPDF("PDF has 20 pages (max 15)."),
        ):
            resp = await client.post(
                "/setup/menu",
                data={"csrf_token": csrf},
                files={"file": ("menu.pdf", _make_pdf_bytes(), "application/pdf")},
                cookies={"session": token},
            )

        assert resp.status_code == 400
        assert "couldn't read" in resp.text.lower() or "pages" in resp.text.lower()


# ---------------------------------------------------------------------------
# Empty/degenerate extraction guard
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestEmptyExtractionGuard:
    async def test_zero_dishes_shows_error_not_summary(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="empty-extract")
        user = await make_owner(db_session, site, email="empty@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        extracted = ExtractedMenu.model_validate(EMPTY_EXTRACTION)

        with patch(
            "app.web.auth.menu_extraction_service.extract_from_pdf",
            new_callable=AsyncMock,
            return_value=extracted,
        ):
            resp = await client.post(
                "/setup/menu",
                data={"csrf_token": csrf},
                files={"file": ("menu.pdf", _make_pdf_bytes(), "application/pdf")},
                cookies={"session": token},
            )

        assert resp.status_code == 422
        assert "menu items" in resp.text.lower()
        assert "We found your menu" not in resp.text


# ---------------------------------------------------------------------------
# Priceless items in summary
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPricelessItems:
    async def test_priceless_items_flagged_in_summary(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="priceless")
        user = await make_owner(db_session, site, email="priceless@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        extracted = ExtractedMenu.model_validate(PRICELESS_EXTRACTION)

        with patch(
            "app.web.auth.menu_extraction_service.extract_from_pdf",
            new_callable=AsyncMock,
            return_value=extracted,
        ):
            resp = await client.post(
                "/setup/menu",
                data={"csrf_token": csrf},
                files={"file": ("menu.pdf", _make_pdf_bytes(), "application/pdf")},
                cookies={"session": token},
            )

        assert resp.status_code == 200
        assert "Mystery Dish" in resp.text
        assert "without a price" in resp.text.lower()


# ---------------------------------------------------------------------------
# /setup/menu/confirm POST — commit + redirect to preview
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSetupMenuConfirm:
    async def test_commit_creates_draft_and_redirects_to_preview(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="confirm-test")
        user = await make_owner(db_session, site, email="confirm@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        extraction_json = json.dumps(SIMPLE_EXTRACTION)

        resp = await client.post(
            "/setup/menu/confirm",
            data={"csrf_token": csrf, "extraction_json": extraction_json},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/admin/preview/menu" in resp.headers["location"]

        # Verify draft menu was created
        from sqlalchemy import select
        from app.models.menu import Menu
        result = await db_session.execute(
            select(Menu).where(Menu.site_id == site.site_id)
        )
        menu = result.scalar_one()
        assert menu.name == "Test Menu"
        assert menu.is_published is False

    async def test_invalid_json_shows_error(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="bad-json")
        user = await make_owner(db_session, site, email="badjson@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/menu/confirm",
            data={"csrf_token": csrf, "extraction_json": "not json"},
            cookies={"session": token},
        )
        assert resp.status_code == 400
        assert "try uploading" in resp.text.lower() or "wrong" in resp.text.lower()


# ---------------------------------------------------------------------------
# /admin/preview/menu — draft-inclusive preview
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPreviewMenu:
    async def test_preview_shows_draft_menu(
        self, client: AsyncClient, db_session
    ):
        """The preview route loads draft menus through the real Linen template."""
        site = await make_site(db_session, slug="preview-test")
        user = await make_owner(db_session, site, email="preview@test.dev")

        # Create a draft menu directly
        from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
        menu = Menu(
            site_id=site.site_id, name="Draft Menu",
            is_published=False, position=10,
        )
        sec = Section(name="Starters", position=10)
        menu.sections.append(sec)
        sub = Subsection(name=None, position=10)
        sec.subsections.append(sub)
        item = MenuItem(
            name="Bruschetta", description="Toasted bread",
            dietary_tags=[], extras=[], featured=False, position=10,
        )
        sub.items.append(item)
        from decimal import Decimal
        variant = MenuItemVariant(label=None, price=Decimal("12.00"), position=10)
        item.variants.append(variant)
        db_session.add(menu)
        await db_session.flush()

        token = encode_session(user.user_id)
        resp = await client.get(
            "/admin/preview/menu",
            cookies={"session": token},
        )
        assert resp.status_code == 200
        # Should contain menu content from the Linen template
        assert "Bruschetta" in resp.text
        assert "Draft Menu" in resp.text

    async def test_public_route_excludes_drafts(
        self, client: AsyncClient, db_session
    ):
        """The public /menu route must NOT show draft menus."""
        site = await make_site(db_session, slug="draft-hidden")
        from app.models.menu import Menu
        menu = Menu(
            site_id=site.site_id, name="Secret Draft",
            is_published=False, position=10,
        )
        db_session.add(menu)
        await db_session.flush()

        # Public route uses Host header for tenant resolution
        resp = await client.get(
            "/menu",
            headers={"host": f"draft-hidden.localhost"},
        )
        # The menu should NOT appear (filtered by is_published)
        assert "Secret Draft" not in resp.text


# ---------------------------------------------------------------------------
# Auth templates render without tenant contamination
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSetupMenuNoTenant:
    async def test_setup_menu_no_resolve_tenant(
        self, client: AsyncClient, db_session
    ):
        """GET /setup/menu on apex — no resolve_tenant, no 500."""
        site = await make_site(db_session, slug="no-tenant")
        user = await make_owner(db_session, site, email="notenant@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get("/setup/menu", cookies={"session": token})
        assert resp.status_code == 200
        assert "Internal Server Error" not in resp.text
