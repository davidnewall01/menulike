"""Tests for Phase 1A: signup, name-your-restaurant, owner-no-site gate."""

import pytest
from httpx import AsyncClient

from app.core.security import encode_session
from tests.conftest import (
    csrf_token_for,
    make_owner,
    make_owner_no_site,
    make_site,
)


# ---------------------------------------------------------------------------
# Slug service (pure + DB)
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        from app.services.slug_service import slugify
        assert slugify("Porto Azzurro") == "porto-azzurro"

    def test_accents(self):
        from app.services.slug_service import slugify
        assert slugify("Mama's Café") == "mama-s-cafe"

    def test_unicode_heavy(self):
        from app.services.slug_service import slugify
        assert slugify("Chez François") == "chez-francois"

    def test_empty_fallback(self):
        from app.services.slug_service import slugify
        assert slugify("") == "restaurant"
        assert slugify("---") == "restaurant"

    def test_leading_trailing_hyphens(self):
        from app.services.slug_service import slugify
        assert slugify("  --Hello World--  ") == "hello-world"

    def test_consecutive_special_chars(self):
        from app.services.slug_service import slugify
        assert slugify("A & B!!! Grill") == "a-b-grill"


@pytest.mark.anyio
class TestGenerateUniqueSlug:
    async def test_no_collision(self, db_session):
        from app.services.slug_service import generate_unique_slug
        slug = await generate_unique_slug(db_session, "Brand New Place")
        assert slug == "brand-new-place"

    async def test_collision_appends_suffix(self, db_session):
        from app.services.slug_service import generate_unique_slug
        await make_site(db_session, slug="porto-azzurro", name="Porto Azzurro")
        slug = await generate_unique_slug(db_session, "Porto Azzurro")
        assert slug == "porto-azzurro-2"

    async def test_double_collision(self, db_session):
        from app.services.slug_service import generate_unique_slug
        await make_site(db_session, slug="test-place", name="Test Place")
        await make_site(db_session, slug="test-place-2", name="Test Place 2")
        slug = await generate_unique_slug(db_session, "Test Place")
        assert slug == "test-place-3"


# ---------------------------------------------------------------------------
# create_site service
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestCreateSiteService:
    async def test_creates_site_and_binds_user(self, db_session):
        from app.auth.context import AuthContext
        from app.services import site_service

        user = await make_owner_no_site(db_session, email="new@test.dev")
        auth = AuthContext(
            user_id=user.user_id, email=user.email,
            role=user.role, site_id=None,
        )
        site = await site_service.create_site(
            db_session, auth, "My Restaurant", "my-restaurant"
        )
        assert site.slug == "my-restaurant"
        assert site.restaurant_name == "My Restaurant"
        assert site.template == "linen"

        # User should now be bound
        from sqlalchemy import select
        from app.models.user import User
        result = await db_session.execute(
            select(User).where(User.user_id == user.user_id)
        )
        refreshed = result.scalar_one()
        assert refreshed.site_id == site.site_id

    async def test_already_has_site_raises(self, db_session):
        from app.auth.context import AuthContext
        from app.services import site_service
        from app.services.exceptions import AlreadyHasSite

        site = await make_site(db_session)
        user = await make_owner(db_session, site, email="has-site@test.dev")
        auth = AuthContext(
            user_id=user.user_id, email=user.email,
            role=user.role, site_id=user.site_id,
        )
        with pytest.raises(AlreadyHasSite):
            await site_service.create_site(
                db_session, auth, "Second Site", "second-site"
            )


# ---------------------------------------------------------------------------
# Signup route
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSignup:
    async def test_get_signup_page(self, client: AsyncClient):
        resp = await client.get("/signup")
        assert resp.status_code == 200
        assert "Create your restaurant" in resp.text

    async def test_successful_signup(self, client: AsyncClient):
        resp = await client.post("/signup", data={
            "email": "new-owner@example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/setup/restaurant"
        assert "session" in resp.cookies

    async def test_duplicate_email(self, client: AsyncClient, db_session):
        site = await make_site(db_session, slug="existing")
        await make_owner(db_session, site, email="taken@test.dev", password="testpass")
        await db_session.flush()

        resp = await client.post("/signup", data={
            "email": "taken@test.dev",
            "password": "securepass123",
            "password_confirm": "securepass123",
        })
        assert resp.status_code == 409
        assert "already have an account" in resp.text
        assert "Log in instead" in resp.text

    async def test_duplicate_email_case_insensitive(self, client: AsyncClient, db_session):
        """Signup A@x.com then a@x.com -> caught as duplicate."""
        # First signup
        resp = await client.post("/signup", data={
            "email": "CaseTest@Example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }, follow_redirects=False)
        assert resp.status_code == 303

        # Second signup with different case
        resp2 = await client.post("/signup", data={
            "email": "casetest@example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        })
        assert resp2.status_code == 409
        assert "already have an account" in resp2.text

    async def test_password_too_short(self, client: AsyncClient):
        resp = await client.post("/signup", data={
            "email": "short@test.dev",
            "password": "abc",
            "password_confirm": "abc",
        })
        assert resp.status_code == 400
        assert "at least 8 characters" in resp.text

    async def test_password_mismatch(self, client: AsyncClient):
        resp = await client.post("/signup", data={
            "email": "mismatch@test.dev",
            "password": "securepass123",
            "password_confirm": "differentpass",
        })
        assert resp.status_code == 400
        assert "do not match" in resp.text


# ---------------------------------------------------------------------------
# Name-your-restaurant (setup)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestSetupRestaurant:
    async def test_unauthenticated_redirects_to_login(self, client: AsyncClient):
        resp = await client.get(
            "/setup/restaurant",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/admin/login" in resp.headers["location"]

    async def test_owner_with_site_redirects_to_dashboard(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="has-site")
        user = await make_owner(db_session, site, email="has-site@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get(
            "/setup/restaurant",
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/"

    async def test_renders_form_for_owner_no_site(
        self, client: AsyncClient, db_session
    ):
        user = await make_owner_no_site(db_session, email="nosite@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get(
            "/setup/restaurant",
            cookies={"session": token},
        )
        assert resp.status_code == 200
        assert "restaurant called" in resp.text.lower()

    async def test_creates_site_and_redirects(
        self, client: AsyncClient, db_session
    ):
        user = await make_owner_no_site(db_session, email="creator@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/restaurant",
            data={"restaurant_name": "Porto Azzurro Test", "csrf_token": csrf},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/"

        # Verify slug was created
        from sqlalchemy import select
        from app.models.site import Site
        result = await db_session.execute(
            select(Site).where(Site.slug == "porto-azzurro-test")
        )
        site = result.scalar_one()
        assert site.restaurant_name == "Porto Azzurro Test"

    async def test_slug_collision_gets_suffix(
        self, client: AsyncClient, db_session
    ):
        await make_site(db_session, slug="porto-azzurro-test", name="Existing")
        user = await make_owner_no_site(db_session, email="collision@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/restaurant",
            data={"restaurant_name": "Porto Azzurro Test", "csrf_token": csrf},
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        from sqlalchemy import select
        from app.models.site import Site
        result = await db_session.execute(
            select(Site).where(Site.slug == "porto-azzurro-test-2")
        )
        assert result.scalar_one() is not None

    async def test_empty_name_rejected(
        self, client: AsyncClient, db_session
    ):
        user = await make_owner_no_site(db_session, email="empty@test.dev")
        token = encode_session(user.user_id)
        csrf = csrf_token_for(user)

        resp = await client.post(
            "/setup/restaurant",
            data={"restaurant_name": "   ", "csrf_token": csrf},
            cookies={"session": token},
        )
        assert resp.status_code == 400
        assert "required" in resp.text.lower()


# ---------------------------------------------------------------------------
# Owner-no-site gate
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestOwnerNoSiteGate:
    async def test_owner_no_site_redirected_to_setup(
        self, client: AsyncClient, db_session
    ):
        """An owner with no site hitting /admin/ is redirected to setup."""
        user = await make_owner_no_site(db_session, email="gate@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get(
            "/admin/",
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/setup/restaurant"

    async def test_internal_admin_not_caught_by_gate(
        self, client: AsyncClient, db_session
    ):
        """internal_admin has site_id=None too — must NOT be redirected."""
        from app.core.security import hash_password
        from app.models.user import User
        admin = User(
            email=f"admin-gate-{__import__('uuid').uuid4().hex[:8]}@menulike.dev",
            password_hash=hash_password("adminpass"),
            role="internal_admin",
            site_id=None,
        )
        db_session.add(admin)
        await db_session.flush()
        token = encode_session(admin.user_id)

        resp = await client.get(
            "/admin/",
            cookies={"session": token},
            follow_redirects=False,
        )
        # Should get 200 (dashboard), NOT 303 redirect
        assert resp.status_code == 200

    async def test_owner_with_site_reaches_dashboard(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="gated")
        user = await make_owner(db_session, site, email="gated@test.dev")
        token = encode_session(user.user_id)

        resp = await client.get(
            "/admin/",
            cookies={"session": token},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "gated" in resp.text.lower() or "Test Restaurant" in resp.text


# ---------------------------------------------------------------------------
# Role-based login routing
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestLoginRouting:
    async def test_owner_with_site_lands_on_dashboard(
        self, client: AsyncClient, db_session
    ):
        site = await make_site(db_session, slug="login-test")
        await make_owner(db_session, site, email="login@test.dev", password="testpass")

        resp = await client.post("/admin/login", data={
            "email": "login@test.dev",
            "password": "testpass",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/"

    async def test_owner_no_site_lands_on_setup(
        self, client: AsyncClient, db_session
    ):
        await make_owner_no_site(
            db_session, email="nosite-login@test.dev", password="testpass"
        )

        resp = await client.post("/admin/login", data={
            "email": "nosite-login@test.dev",
            "password": "testpass",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/setup/restaurant"

    async def test_internal_admin_lands_on_admin(
        self, client: AsyncClient, db_session
    ):
        from app.core.security import hash_password
        from app.models.user import User
        admin = User(
            email="admin-login@menulike.dev",
            password_hash=hash_password("adminpass"),
            role="internal_admin",
            site_id=None,
        )
        db_session.add(admin)
        await db_session.flush()

        resp = await client.post("/admin/login", data={
            "email": "admin-login@menulike.dev",
            "password": "adminpass",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/admin/"


# ---------------------------------------------------------------------------
# Auth templates render without tenant contamination
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestAuthTemplatesNoTenant:
    async def test_signup_no_tenant_needed(self, client: AsyncClient):
        """GET /signup on apex — no resolve_tenant, no site in context."""
        resp = await client.get("/signup")
        assert resp.status_code == 200
        assert "menulike" in resp.text

    async def test_setup_no_tenant_needed(
        self, client: AsyncClient, db_session
    ):
        """GET /setup/restaurant — behind auth, but no tenant resolution."""
        user = await make_owner_no_site(db_session, email="tpl@test.dev")
        token = encode_session(user.user_id)
        resp = await client.get(
            "/setup/restaurant",
            cookies={"session": token},
        )
        assert resp.status_code == 200
        # Must NOT contain any 500/error indicators
        assert "Internal Server Error" not in resp.text
