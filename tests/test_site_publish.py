"""Tests for site-level publish / go-live gate.

Covers:
  - Unpublished site → coming-soon page (name only, no sample/placeholder leakage)
  - Published site → normal public render
  - Admin preview bypasses the publish gate
  - can_publish: eligibility from resolver (mode-independent)
  - POST publish / unpublish (scoping, CSRF, eligibility)
  - make_site default is_published=True (regression guard)
"""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.resolver import resolve_site_view
from app.models.photo import Photo
from app.models.site_image_role import SiteImageRole
from app.services.site_service import can_publish
from tests.conftest import (
    csrf_token_for,
    make_menu,
    make_owner,
    make_site,
)


# ---------------------------------------------------------------------------
# can_publish (pure unit tests — no DB)
# ---------------------------------------------------------------------------

class TestCanPublish:

    def _make_view(self, *, menu_status="sample", hero_source="empty"):
        """Build a minimal SiteView-like dict for can_publish."""
        return {
            "menu": SimpleNamespace(status=menu_status),
            "home": SimpleNamespace(
                status="sample",
                fields={"hero": SimpleNamespace(source=hero_source)},
            ),
            "our_story": SimpleNamespace(status="sample"),
            "visit": SimpleNamespace(status="partial"),
            "gallery": SimpleNamespace(status="sample"),
        }

    def test_not_eligible_when_empty(self):
        eligible, reasons = can_publish(self._make_view())
        assert not eligible
        assert "Add your menu" in reasons
        assert "Add a hero photo" in reasons

    def test_not_eligible_menu_only(self):
        eligible, reasons = can_publish(
            self._make_view(menu_status="yours", hero_source="empty")
        )
        assert not eligible
        assert "Add a hero photo" in reasons
        assert "Add your menu" not in reasons

    def test_not_eligible_hero_only(self):
        eligible, reasons = can_publish(
            self._make_view(menu_status="sample", hero_source="real")
        )
        assert not eligible
        assert "Add your menu" in reasons
        assert "Add a hero photo" not in reasons

    def test_eligible_when_menu_and_hero(self):
        eligible, reasons = can_publish(
            self._make_view(menu_status="yours", hero_source="real")
        )
        assert eligible
        assert reasons == []

    def test_mode_independent(self):
        """can_publish keys on status/source, which are mode-independent."""
        site = SimpleNamespace(
            restaurant_name="Test", tagline=None, address_street=None,
            phone=None, email=None, regular_hours=[], content_blocks=[],
            menus=[SimpleNamespace(name="Food")],
        )
        photo = SimpleNamespace(s3_key="test.jpg", alt_text="", width=800, height=600)
        role_images = {"feature_images": [photo]}
        _url = lambda key: f"https://cdn/{key}"

        view_public = resolve_site_view(site=site, role_images=role_images, mode="public", storage_url=_url)
        view_preview = resolve_site_view(site=site, role_images=role_images, mode="preview", storage_url=_url)

        result_pub = can_publish(view_public)
        result_prev = can_publish(view_preview)
        assert result_pub == result_prev


# ---------------------------------------------------------------------------
# Coming-soon gate (integration — DB + HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestComingSoonGate:

    async def test_unpublished_site_shows_coming_soon(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Unpublished site → 200 coming-soon with restaurant name only."""
        site = await make_site(
            db_session, slug="unpub", name="Porto Test", is_published=False,
        )
        resp = await client.get("/", headers={"host": "unpub.menulike.local"})
        assert resp.status_code == 200
        assert "Porto Test" in resp.text
        assert "Opening soon" in resp.text
        # No sample/placeholder leakage
        assert "No menus available" not in resp.text
        assert "Hours not set" not in resp.text
        assert "SAMPLE" not in resp.text

    async def test_unpublished_all_public_routes_gated(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """All public routes return coming-soon for an unpublished site."""
        await make_site(db_session, slug="gated", is_published=False)
        for path in ["/", "/menu", "/gallery", "/our-story", "/visit"]:
            resp = await client.get(path, headers={"host": "gated.menulike.local"})
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
            assert "Opening soon" in resp.text, f"{path} missing coming-soon"

    async def test_published_site_renders_normally(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Published site → normal public render (not coming-soon)."""
        await make_site(db_session, slug="live", is_published=True)
        resp = await client.get("/", headers={"host": "live.menulike.local"})
        assert resp.status_code == 200
        assert "Opening soon" not in resp.text

    async def test_unknown_site_still_404(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Non-existent slug → 404 (not coming-soon)."""
        resp = await client.get("/", headers={"host": "nonexistent.menulike.local"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin preview bypasses gate
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPreviewBypassesGate:

    async def test_preview_works_for_unpublished_site(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Owner can preview their unpublished site — gate does NOT catch preview."""
        site = await make_site(
            db_session, slug="prev", name="Preview Test", is_published=False,
        )
        user = await make_owner(db_session, site, email="preview@test.dev")

        # Login
        resp = await client.post(
            "/admin/login",
            data={"email": "preview@test.dev", "password": "testpass"},
            follow_redirects=False,
        )
        cookies = dict(resp.cookies)

        # Preview menu — should work (authenticated, not Host-resolved)
        resp = await client.get(
            "/admin/preview/menu",
            cookies=cookies,
            follow_redirects=False,
        )
        # 200 = rendered; NOT coming-soon
        assert resp.status_code == 200
        assert "Opening soon" not in resp.text


# ---------------------------------------------------------------------------
# Publish / Unpublish endpoints
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPublishEndpoints:

    async def _setup_eligible_site(self, db_session, client):
        """Create a site with menu + hero (eligible to publish)."""
        site = await make_site(
            db_session, slug="pubtest", is_published=False,
        )
        user = await make_owner(db_session, site, email="pub@test.dev")

        # Add a menu (makes menu status = "yours")
        await make_menu(db_session, site, name="Food")

        # Add a hero photo (makes home.hero = real)
        photo = Photo(
            site_id=site.site_id,
            s3_key="photos/hero.jpg",
            content_type="image/jpeg",
        )
        db_session.add(photo)
        await db_session.flush()

        role = SiteImageRole(
            site_id=site.site_id,
            role="feature_images",
            photo_id=photo.photo_id,
            position=0,
        )
        db_session.add(role)
        await db_session.flush()

        # Login
        resp = await client.post(
            "/admin/login",
            data={"email": "pub@test.dev", "password": "testpass"},
            follow_redirects=False,
        )
        cookies = dict(resp.cookies)
        csrf = csrf_token_for(user)

        return site, user, cookies, csrf

    async def test_publish_eligible_site(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site, user, cookies, csrf = await self._setup_eligible_site(
            db_session, client,
        )

        resp = await client.post(
            "/admin/publish",
            data={"csrf_token": csrf},
            cookies=cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Site should now be published
        await db_session.refresh(site)
        assert site.is_published is True

    async def test_publish_blocked_when_ineligible(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Site with no menu/hero → publish redirects but stays unpublished."""
        site = await make_site(
            db_session, slug="inelig", is_published=False,
        )
        user = await make_owner(db_session, site, email="inelig@test.dev")

        resp = await client.post(
            "/admin/login",
            data={"email": "inelig@test.dev", "password": "testpass"},
            follow_redirects=False,
        )
        cookies = dict(resp.cookies)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/admin/publish",
            data={"csrf_token": csrf},
            cookies=cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(site)
        assert site.is_published is False

    async def test_unpublish(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(
            db_session, slug="unpubtest", is_published=True,
        )
        user = await make_owner(db_session, site, email="unpub@test.dev")

        resp = await client.post(
            "/admin/login",
            data={"email": "unpub@test.dev", "password": "testpass"},
            follow_redirects=False,
        )
        cookies = dict(resp.cookies)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/admin/unpublish",
            data={"csrf_token": csrf},
            cookies=cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(site)
        assert site.is_published is False

    async def test_publish_requires_csrf(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="csrftest", is_published=False)
        user = await make_owner(db_session, site, email="csrf@test.dev")

        resp = await client.post(
            "/admin/login",
            data={"email": "csrf@test.dev", "password": "testpass"},
            follow_redirects=False,
        )
        cookies = dict(resp.cookies)

        # POST without CSRF token
        resp = await client.post(
            "/admin/publish",
            cookies=cookies,
            follow_redirects=False,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Regression: make_site defaults to published
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestMakeSiteDefault:

    async def test_make_site_defaults_published(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """make_site() creates a published site by default (regression guard)."""
        site = await make_site(db_session, slug="default-pub")
        assert site.is_published is True

        # Should render normally, not coming-soon
        resp = await client.get("/", headers={"host": "default-pub.menulike.local"})
        assert "Opening soon" not in resp.text
