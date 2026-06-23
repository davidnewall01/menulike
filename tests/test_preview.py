"""Integration tests for the preview routes (Chunk 2).

Verifies:
  - Preview routes are owner-scoped and bypass the publish gate
  - Nav URLs are mode-aware (point at /admin/preview/* in preview)
  - Preview banner is present in preview, absent in public
  - Sample content appears in preview for empty sites
  - Sample menu partial shows when no menus exist
  - Never-sample fields show prompts, not fake data
  - Public render unchanged (view-model refactor regression)
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
# Preview routes: auth + bypass publish gate
# ---------------------------------------------------------------------------

class TestPreviewAuth:

    async def test_preview_home_requires_auth(self, client: AsyncClient):
        resp = await client.get("/admin/preview", follow_redirects=False)
        assert resp.status_code in (302, 303, 401)

    async def test_preview_routes_bypass_publish_gate(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Unpublished site can still be previewed by the owner."""
        site = await make_site(db_session, slug="unpub-prev", is_published=False)
        await make_owner(db_session, site, email="prev-owner@test.dev")
        cookies = await _login(client, "prev-owner@test.dev")

        for path in [
            "/admin/preview",
            "/admin/preview/menu",
            "/admin/preview/our-story",
            "/admin/preview/gallery",
            "/admin/preview/visit",
        ]:
            resp = await client.get(path, cookies=cookies)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"


# ---------------------------------------------------------------------------
# Nav is mode-aware
# ---------------------------------------------------------------------------

class TestNavModeAware:

    async def test_preview_nav_links_point_to_preview(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="nav-prev")
        await make_owner(db_session, site, email="nav@test.dev")
        cookies = await _login(client, "nav@test.dev")

        resp = await client.get("/admin/preview", cookies=cookies)
        html = resp.text
        # Desktop nav
        assert "/admin/preview/menu" in html
        assert "/admin/preview/our-story" in html
        assert "/admin/preview/gallery" in html
        assert "/admin/preview/visit" in html
        # Mobile menu also uses preview prefix
        assert html.count("/admin/preview/menu") >= 2  # desktop + mobile + hero

    async def test_public_nav_has_plain_links(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Public site nav should NOT contain /admin/preview paths."""
        site = await make_site(db_session, slug="nav-pub")
        await make_owner(db_session, site, email="navpub@test.dev")

        resp = await client.get(
            "/", headers={"host": f"nav-pub.{_platform_domain()}"},
        )
        assert resp.status_code == 200
        assert "/admin/preview" not in resp.text
        assert 'href="/menu"' in resp.text or "href=\"/menu\"" in resp.text


# ---------------------------------------------------------------------------
# Preview banner
# ---------------------------------------------------------------------------

class TestPreviewBanner:

    async def test_banner_present_in_preview(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="banner-prev")
        await make_owner(db_session, site, email="banner@test.dev")
        cookies = await _login(client, "banner@test.dev")

        resp = await client.get("/admin/preview", cookies=cookies)
        assert "preview-banner" in resp.text
        assert "Back to dashboard" in resp.text

    async def test_banner_absent_in_public(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="banner-pub")
        await make_owner(db_session, site, email="bannerpub@test.dev")

        resp = await client.get(
            "/", headers={"host": f"banner-pub.{_platform_domain()}"},
        )
        assert "preview-banner" not in resp.text


# ---------------------------------------------------------------------------
# Sample content in preview
# ---------------------------------------------------------------------------

class TestSampleContent:

    async def test_preview_home_shows_sample_tagline(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Empty site in preview shows sample tagline with badge."""
        site = await make_site(db_session, slug="sample-home")
        await make_owner(db_session, site, email="samplehome@test.dev")
        cookies = await _login(client, "samplehome@test.dev")

        resp = await client.get("/admin/preview", cookies=cookies)
        html = resp.text
        assert "sample-badge" in html
        assert "Sample" in html

    async def test_preview_menu_shows_sample_partial(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Site with no menus shows the sample menu in preview."""
        site = await make_site(db_session, slug="sample-menu")
        await make_owner(db_session, site, email="samplemenu@test.dev")
        cookies = await _login(client, "samplemenu@test.dev")

        resp = await client.get("/admin/preview/menu", cookies=cookies)
        html = resp.text
        assert "Sample Menu" in html
        assert "Burrata" in html  # sample item

    async def test_preview_menu_shows_real_when_exists(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Site WITH menus shows real menu, not sample."""
        site = await make_site(db_session, slug="real-menu")
        await make_owner(db_session, site, email="realmenu@test.dev")
        await make_menu(db_session, site, name="Dinner", is_published=True)
        cookies = await _login(client, "realmenu@test.dev")

        resp = await client.get("/admin/preview/menu", cookies=cookies)
        html = resp.text
        assert "Dinner" in html
        assert "Sample Menu" not in html


# ---------------------------------------------------------------------------
# Never-sample fields (visit)
# ---------------------------------------------------------------------------

class TestNeverSampleVisit:

    async def test_preview_visit_shows_prompts_not_fake(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Visit preview shows 'Add your hours/address' prompts, NOT fake data."""
        site = await make_site(db_session, slug="ns-visit")
        await make_owner(db_session, site, email="nsvisit@test.dev")
        cookies = await _login(client, "nsvisit@test.dev")

        resp = await client.get("/admin/preview/visit", cookies=cookies)
        html = resp.text
        assert "Add your hours" in html
        assert "Add your address" in html
        assert "Add contact details" in html

    async def test_public_visit_shows_generic_not_set(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Public visit page shows generic 'not set' messages."""
        site = await make_site(db_session, slug="ns-pub")
        await make_owner(db_session, site, email="nspub@test.dev")

        resp = await client.get(
            "/visit", headers={"host": f"ns-pub.{_platform_domain()}"},
        )
        html = resp.text
        assert "Hours not set" in html
        assert "Address not set" in html
        assert "Contact details not set" in html
        assert "Add your" not in html


# ---------------------------------------------------------------------------
# Public regression: view-model refactor must not change public output
# ---------------------------------------------------------------------------

class TestPublicRegression:

    async def test_public_home_renders(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(
            db_session, slug="reg-home", tagline="Fresh Pasta",
        )
        await make_owner(db_session, site, email="reghome@test.dev")

        resp = await client.get(
            "/", headers={"host": f"reg-home.{_platform_domain()}"},
        )
        assert resp.status_code == 200
        assert "Fresh Pasta" in resp.text
        assert "sample-badge" not in resp.text

    async def test_public_menu_renders(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="reg-menu")
        await make_owner(db_session, site, email="regmenu@test.dev")

        resp = await client.get(
            "/menu", headers={"host": f"reg-menu.{_platform_domain()}"},
        )
        assert resp.status_code == 200
        assert "Sample Menu" not in resp.text

    async def test_public_empty_home_no_sample(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Public page for empty site shows NO sample content."""
        site = await make_site(db_session, slug="reg-empty")
        await make_owner(db_session, site, email="regempty@test.dev")

        resp = await client.get(
            "/", headers={"host": f"reg-empty.{_platform_domain()}"},
        )
        assert resp.status_code == 200
        assert "sample-badge" not in resp.text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _platform_domain():
    from app.core.config import settings
    return settings.PLATFORM_BASE_DOMAIN
