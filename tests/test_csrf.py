"""CSRF protection tests — token presence, validity, and session binding."""

import uuid

from app.auth.context import AuthContext
from app.core.csrf import generate_csrf_token
from tests.conftest import csrf_token_for, make_owner, make_site


class TestCsrf:
    async def _login(self, client, email, password):
        resp = await client.post(
            "/admin/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        return resp.cookies["session"]

    async def test_post_without_csrf_token_returns_403(self, db_session, client):
        """An authenticated POST with no csrf_token field is rejected."""
        site = await make_site(db_session, slug="csrf1", name="CSRF One")
        await make_owner(db_session, site, email="c1@test.dev", password="pass")

        cookie = await self._login(client, "c1@test.dev", "pass")

        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "Hacked"},
            cookies={"session": cookie},
        )
        assert resp.status_code == 403

        # Verify the CSRF-specific header is present
        assert resp.headers.get("x-csrf-fail") == "1"

        # Site unchanged
        await db_session.refresh(site)
        assert site.restaurant_name == "CSRF One"

    async def test_post_with_valid_token_succeeds(self, db_session, client):
        """An authenticated POST with a valid session-bound token is accepted."""
        site = await make_site(db_session, slug="csrf2", name="CSRF Two")
        owner = await make_owner(db_session, site, email="c2@test.dev", password="pass")

        cookie = await self._login(client, "c2@test.dev", "pass")
        token = csrf_token_for(owner)

        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "CSRF Updated", "csrf_token": token},
            cookies={"session": cookie},
        )
        assert resp.status_code == 200
        assert "Details saved" in resp.text

        await db_session.refresh(site)
        assert site.restaurant_name == "CSRF Updated"

    async def test_token_from_different_session_returns_403(self, db_session, client):
        """A token bound to user B must not work for user A's session.

        This proves the session binding is doing the work, not just token presence.
        """
        site_a = await make_site(db_session, slug="csrf3a", name="CSRF A")
        site_b = await make_site(db_session, slug="csrf3b", name="CSRF B")
        owner_a = await make_owner(db_session, site_a, email="ca@test.dev", password="pass")
        owner_b = await make_owner(db_session, site_b, email="cb@test.dev", password="pass")

        cookie_a = await self._login(client, "ca@test.dev", "pass")
        token_b = csrf_token_for(owner_b)  # token from B's session

        # Use A's session cookie but B's CSRF token
        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "Cross-session", "csrf_token": token_b},
            cookies={"session": cookie_a},
        )
        assert resp.status_code == 403
        assert resp.headers.get("x-csrf-fail") == "1"

        # Neither site was modified
        await db_session.refresh(site_a)
        await db_session.refresh(site_b)
        assert site_a.restaurant_name == "CSRF A"
        assert site_b.restaurant_name == "CSRF B"

    async def test_logout_without_csrf_token_returns_403(self, db_session, client):
        """Logout is also CSRF-protected."""
        site = await make_site(db_session, slug="csrf4", name="CSRF Four")
        await make_owner(db_session, site, email="c4@test.dev", password="pass")

        cookie = await self._login(client, "c4@test.dev", "pass")

        resp = await client.post(
            "/admin/logout",
            cookies={"session": cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 403
