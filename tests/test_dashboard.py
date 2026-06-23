"""Tests for the tiled owner dashboard (Chunk 3).

Covers:
  - Tile statuses from resolver for empty/full sites
  - Publish bar: enabled/disabled by eligibility
  - Progress bar: counts only "yours"
  - Tile links to CRUD pages
  - Internal admin gets separate (non-tiled) dashboard
  - Published vs unpublished header state
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.site_image_role import SiteImageRole
from tests.conftest import (
    csrf_token_for,
    make_menu,
    make_owner,
    make_site,
)


async def _login(client, email, password="testpass"):
    resp = await client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return dict(resp.cookies)


async def _get_dashboard(client, cookies):
    return await client.get("/admin/", cookies=cookies, follow_redirects=False)


# ---------------------------------------------------------------------------
# Empty site — all tiles sample, publish disabled
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestEmptySiteDashboard:

    async def test_all_tiles_sample_for_new_site(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="empty-dash", is_published=False)
        await make_owner(db_session, site, email="empty@test.dev")
        cookies = await _login(client, "empty@test.dev")

        resp = await _get_dashboard(client, cookies)
        assert resp.status_code == 200
        html = resp.text

        # Core tiles show "Still sample"
        assert "Still sample" in html
        # Publish bar disabled with reasons
        assert "Publish site" in html
        assert "Add your menu" in html
        assert "Add a hero photo" in html

    async def test_progress_zero_for_new_site(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Brand-new site: 0 of 5 made yours (Visit is partial, doesn't count)."""
        site = await make_site(db_session, slug="prog-zero", is_published=False)
        await make_owner(db_session, site, email="prog0@test.dev")
        cookies = await _login(client, "prog0@test.dev")

        resp = await _get_dashboard(client, cookies)
        assert "0 of 5 made yours" in resp.text

    async def test_not_published_header(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="notpub", is_published=False)
        await make_owner(db_session, site, email="notpub@test.dev")
        cookies = await _login(client, "notpub@test.dev")

        resp = await _get_dashboard(client, cookies)
        assert "Not published yet" in resp.text


# ---------------------------------------------------------------------------
# Site with menu + hero — publish enabled
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestEligibleSiteDashboard:

    async def _setup(self, db_session, client):
        site = await make_site(db_session, slug="elig-dash", is_published=False)
        user = await make_owner(db_session, site, email="elig@test.dev")

        await make_menu(db_session, site, name="Food")

        photo = Photo(
            site_id=site.site_id, s3_key="photos/hero.jpg",
            content_type="image/jpeg",
        )
        db_session.add(photo)
        await db_session.flush()
        role = SiteImageRole(
            site_id=site.site_id, role="feature_images",
            photo_id=photo.photo_id, position=0,
        )
        db_session.add(role)
        await db_session.flush()

        cookies = await _login(client, "elig@test.dev")
        return site, user, cookies

    async def test_menu_tile_yours(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        _, _, cookies = await self._setup(db_session, client)
        resp = await _get_dashboard(client, cookies)
        html = resp.text
        # Menu should show "Yours"
        assert "Edit your menu" in html

    async def test_publish_bar_enabled(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        _, _, cookies = await self._setup(db_session, client)
        resp = await _get_dashboard(client, cookies)
        html = resp.text
        # Publish button should be enabled (not disabled)
        assert 'class="pbtn enabled"' in html
        assert "Add your menu" not in html
        assert "Add a hero photo" not in html


# ---------------------------------------------------------------------------
# Published site
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPublishedSiteDashboard:

    async def test_published_header_and_take_offline(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        site = await make_site(db_session, slug="pub-dash", is_published=True)
        await make_owner(db_session, site, email="pub@test.dev")
        cookies = await _login(client, "pub@test.dev")

        resp = await _get_dashboard(client, cookies)
        html = resp.text
        assert "Your site is live" in html
        assert "Take offline" in html
        assert "/admin/unpublish" in html


# ---------------------------------------------------------------------------
# Tile links
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestTileLinks:

    async def test_all_tile_links_present(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """All five tile CTA links point to real CRUD pages."""
        site = await make_site(db_session, slug="links")
        await make_owner(db_session, site, email="links@test.dev")
        cookies = await _login(client, "links@test.dev")

        resp = await _get_dashboard(client, cookies)
        html = resp.text

        assert '/admin/menu"' in html
        assert '/admin/appearance"' in html
        assert '/admin/our-story"' in html
        assert '/admin/hours"' in html
        assert '/admin/gallery"' in html

    async def test_tile_links_resolve(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Each tile link actually resolves to a real page (200)."""
        site = await make_site(db_session, slug="resolve")
        await make_owner(db_session, site, email="resolve@test.dev")
        cookies = await _login(client, "resolve@test.dev")

        for path in ["/admin/menu", "/admin/appearance", "/admin/our-story",
                     "/admin/hours", "/admin/gallery"]:
            resp = await client.get(path, cookies=cookies, follow_redirects=False)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"


# ---------------------------------------------------------------------------
# Internal admin — untouched
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestInternalAdminDashboard:

    async def test_internal_admin_gets_simple_dashboard(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Internal admin sees the old simple card, not tiles."""
        from app.core.security import hash_password
        from app.models.user import User

        admin_user = User(
            email="admin@test.dev",
            password_hash=hash_password("testpass"),
            role="internal_admin",
            site_id=None,
        )
        db_session.add(admin_user)
        await db_session.flush()

        cookies = await _login(client, "admin@test.dev")
        resp = await _get_dashboard(client, cookies)
        assert resp.status_code == 200
        html = resp.text
        # Should show old admin card, not tiles
        assert "Internal admin" in html
        assert "tile-grid" not in html


# ---------------------------------------------------------------------------
# Preview link
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestPreviewLink:

    async def test_preview_link(
        self, client: AsyncClient, db_session: AsyncSession,
    ):
        """Preview link says 'Preview your site' and links to /admin/preview."""
        site = await make_site(db_session, slug="prev-link")
        await make_owner(db_session, site, email="prev@test.dev")
        cookies = await _login(client, "prev@test.dev")

        resp = await _get_dashboard(client, cookies)
        assert "Preview your site" in resp.text
        assert 'href="/admin/preview"' in resp.text
