"""Auth flow tests — login, session cookie, protected routes, logout."""

import pytest

from tests.conftest import csrf_token_for, make_owner, make_site


class TestLogin:
    async def test_bad_creds_returns_401(self, db_session, client):
        site = await make_site(db_session)
        await make_owner(db_session, site, email="o@test.dev", password="correct")

        resp = await client.post(
            "/admin/login",
            data={"email": "o@test.dev", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert "session" not in resp.cookies

    async def test_good_creds_redirects_with_cookie(self, db_session, client):
        site = await make_site(db_session)
        await make_owner(db_session, site, email="o@test.dev", password="correct")

        resp = await client.post(
            "/admin/login",
            data={"email": "o@test.dev", "password": "correct"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/"
        assert "session" in resp.cookies

        # Verify cookie flags
        cookie_header = resp.headers["set-cookie"]
        assert "httponly" in cookie_header.lower()
        assert "samesite=lax" in cookie_header.lower()
        assert "max-age=604800" in cookie_header.lower()


class TestProtectedRoute:
    async def test_no_cookie_returns_401(self, client):
        resp = await client.get("/admin/")
        assert resp.status_code == 401

    async def test_with_cookie_returns_200_scoped(self, db_session, client):
        site = await make_site(db_session, slug="mysite", name="My Restaurant")
        await make_owner(db_session, site, email="o@test.dev", password="pass")

        # Login to get cookie
        login_resp = await client.post(
            "/admin/login",
            data={"email": "o@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        cookie = login_resp.cookies["session"]

        # Access dashboard with cookie
        resp = await client.get("/admin/", cookies={"session": cookie})
        assert resp.status_code == 200
        assert "My Restaurant" in resp.text
        assert "o@test.dev" in resp.text
        assert "owner" in resp.text

    async def test_tampered_cookie_returns_401(self, client):
        resp = await client.get("/admin/", cookies={"session": "garbage.token.here"})
        assert resp.status_code == 401

    async def test_garbage_cookie_returns_401(self, client):
        resp = await client.get("/admin/", cookies={"session": "not-even-a-jwt"})
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_clears_cookie(self, db_session, client):
        site = await make_site(db_session)
        owner = await make_owner(db_session, site, email="o@test.dev", password="pass")

        # Login
        login_resp = await client.post(
            "/admin/login",
            data={"email": "o@test.dev", "password": "pass"},
            follow_redirects=False,
        )
        cookie = login_resp.cookies["session"]
        token = csrf_token_for(owner)

        # Logout
        resp = await client.post(
            "/admin/logout",
            data={"csrf_token": token},
            cookies={"session": cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/login"

        # Cookie cleared (max-age=0)
        set_cookie = resp.headers["set-cookie"]
        assert "max-age=0" in set_cookie.lower()
