"""Details editing tests — write stack isolation and scoping."""

import pytest

from tests.conftest import csrf_token_for, make_owner, make_site


class TestDetailsEditing:
    """Owner edits their site's details via the write stack;
    a second site in the DB is never touched."""

    async def _login(self, client, email, password):
        resp = await client.post(
            "/admin/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        return resp.cookies["session"]

    async def test_owner_edits_own_site_only(self, db_session, client):
        site_a = await make_site(db_session, slug="alpha", name="Alpha Original")
        site_b = await make_site(db_session, slug="beta", name="Beta Original")
        owner = await make_owner(db_session, site_a, email="a@test.dev", password="pass")

        cookie = await self._login(client, "a@test.dev", "pass")
        token = csrf_token_for(owner)

        # Edit site A's details
        resp = await client.post(
            "/admin/details",
            data={
                "restaurant_name": "Alpha Updated",
                "phone": "0400 000 000",
                "csrf_token": token,
            },
            cookies={"session": cookie},
        )
        assert resp.status_code == 200
        assert "Details saved" in resp.text

        # Refresh both sites from the DB
        await db_session.refresh(site_a)
        await db_session.refresh(site_b)

        # Site A was updated
        assert site_a.restaurant_name == "Alpha Updated"
        assert site_a.phone == "0400 000 000"

        # Site B is untouched
        assert site_b.restaurant_name == "Beta Original"

    async def test_no_site_id_accepted_from_form(self, db_session, client):
        """Even if a site_id field is injected into the form, it's ignored —
        the target is always auth_ctx.scoped_site_id."""
        site_a = await make_site(db_session, slug="alpha2", name="Alpha Due")
        site_b = await make_site(db_session, slug="beta2", name="Beta Due")
        owner = await make_owner(db_session, site_a, email="a2@test.dev", password="pass")

        cookie = await self._login(client, "a2@test.dev", "pass")
        token = csrf_token_for(owner)

        # Inject site_b's id in the form data
        resp = await client.post(
            "/admin/details",
            data={
                "restaurant_name": "Alpha Edited",
                "site_id": str(site_b.site_id),
                "csrf_token": token,
            },
            cookies={"session": cookie},
        )
        assert resp.status_code == 200

        await db_session.refresh(site_a)
        await db_session.refresh(site_b)

        # A was edited, B untouched
        assert site_a.restaurant_name == "Alpha Edited"
        assert site_b.restaurant_name == "Beta Due"

    async def test_get_details_shows_current_values(self, db_session, client):
        site = await make_site(
            db_session, slug="preload", name="Preloaded",
            phone="1234",
        )
        await make_owner(db_session, site, email="p@test.dev", password="pass")

        cookie = await self._login(client, "p@test.dev", "pass")

        resp = await client.get("/admin/details", cookies={"session": cookie})
        assert resp.status_code == 200
        assert 'value="Preloaded"' in resp.text
        assert 'value="1234"' in resp.text

    async def test_empty_optional_fields_become_none(self, db_session, client):
        site = await make_site(
            db_session, slug="blanks", name="Blanks",
            phone="9999",
        )
        owner = await make_owner(db_session, site, email="b@test.dev", password="pass")

        cookie = await self._login(client, "b@test.dev", "pass")
        token = csrf_token_for(owner)

        # Submit with empty optional fields
        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "Blanks", "phone": "", "csrf_token": token},
            cookies={"session": cookie},
        )
        assert resp.status_code == 200

        await db_session.refresh(site)
        assert site.phone is None

    async def test_empty_restaurant_name_rejected(self, db_session, client):
        """Empty or whitespace-only restaurant_name must trigger a validation
        error and must NOT persist to the DB."""
        site = await make_site(db_session, slug="valfail", name="ValFail")
        owner = await make_owner(db_session, site, email="v@test.dev", password="pass")

        cookie = await self._login(client, "v@test.dev", "pass")
        token = csrf_token_for(owner)

        # Empty string
        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "", "csrf_token": token},
            cookies={"session": cookie},
        )
        assert resp.status_code == 200
        assert "Restaurant name is required" in resp.text
        assert "Details saved" not in resp.text

        # Whitespace only
        resp = await client.post(
            "/admin/details",
            data={"restaurant_name": "   ", "csrf_token": token},
            cookies={"session": cookie},
        )
        assert resp.status_code == 200
        assert "Restaurant name is required" in resp.text
        assert "Details saved" not in resp.text

        # Verify original name is untouched
        await db_session.refresh(site)
        assert site.restaurant_name == "ValFail"

