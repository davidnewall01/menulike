"""Tenant isolation tests — session-scoped admin path.

Proves that an owner scoped to site A can only see site A's data through the
admin dashboard, regardless of query params or other sites existing in the DB.

Full IDOR coverage (owner_A editing B's menu_id -> 403/404) arrives with
Phase 2's id-taking endpoints and belongs here alongside these tests.
"""

import pytest

from tests.conftest import make_owner, make_site


class TestOwnerScopeIsolation:
    """The admin dashboard derives the site from the session, never from
    route params or any external input."""

    async def test_owner_sees_own_site(self, db_session, client):
        site_a = await make_site(db_session, slug="alpha", name="Alpha Ristorante")
        site_b = await make_site(db_session, slug="beta", name="Beta Bistro")
        await make_owner(db_session, site_a, email="a@test.dev", password="pass")

        login = await client.post(
            "/admin/login",
            data={"email": "a@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        cookie = login.cookies["session"]

        resp = await client.get("/admin/", cookies={"session": cookie})
        assert resp.status_code == 200
        assert "Alpha Ristorante" in resp.text
        assert "Beta Bistro" not in resp.text

    async def test_query_param_site_id_is_ignored(self, db_session, client):
        """Passing site_id=<B> as a query param must not change the scoped site."""
        site_a = await make_site(db_session, slug="alpha2", name="Alpha Due")
        site_b = await make_site(db_session, slug="beta2", name="Beta Due")
        await make_owner(db_session, site_a, email="a2@test.dev", password="pass")

        login = await client.post(
            "/admin/login",
            data={"email": "a2@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        cookie = login.cookies["session"]

        # Inject B's site_id as a query param — must be ignored
        resp = await client.get(
            f"/admin/?site_id={site_b.site_id}",
            cookies={"session": cookie},
        )
        assert resp.status_code == 200
        assert "Alpha Due" in resp.text
        assert "Beta Due" not in resp.text

    async def test_two_owners_see_only_their_own_site(self, db_session, client):
        """Two owners in the same DB each see only their own site."""
        site_a = await make_site(db_session, slug="alpha3", name="Alpha Tre")
        site_b = await make_site(db_session, slug="beta3", name="Beta Tre")
        await make_owner(db_session, site_a, email="a3@test.dev", password="pass")
        await make_owner(db_session, site_b, email="b3@test.dev", password="pass")

        # Owner A
        login_a = await client.post(
            "/admin/login",
            data={"email": "a3@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        resp_a = await client.get(
            "/admin/", cookies={"session": login_a.cookies["session"]}
        )
        assert "Alpha Tre" in resp_a.text
        assert "Beta Tre" not in resp_a.text

        # Owner B
        login_b = await client.post(
            "/admin/login",
            data={"email": "b3@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        resp_b = await client.get(
            "/admin/", cookies={"session": login_b.cookies["session"]}
        )
        assert "Beta Tre" in resp_b.text
        assert "Alpha Tre" not in resp_b.text
