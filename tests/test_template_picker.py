"""Template picker tests — happy switch, unknown rejected, scoped write."""

import uuid

import pytest

from app.auth.context import AuthContext
from app.services import site_service
from app.services.exceptions import InvalidTemplate, NoSiteInScope
from app.core.security import encode_session
from tests.conftest import csrf_token_for, make_owner, make_site


def _auth(user) -> AuthContext:
    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


class TestSetTemplateService:

    async def test_switch_to_slate(self, db_session):
        site = await make_site(db_session, slug="tpl-switch")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        result = await site_service.set_template(db_session, auth, "slate")
        assert result.template == "slate"

    async def test_switch_back_to_linen(self, db_session):
        site = await make_site(db_session, slug="tpl-back")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        await site_service.set_template(db_session, auth, "slate")
        result = await site_service.set_template(db_session, auth, "linen")
        assert result.template == "linen"

    async def test_unknown_template_rejected(self, db_session):
        site = await make_site(db_session, slug="tpl-bad")
        owner = await make_owner(db_session, site)
        auth = _auth(owner)

        with pytest.raises(InvalidTemplate):
            await site_service.set_template(db_session, auth, "nonexistent")

    async def test_no_scope_raises(self, db_session):
        auth = AuthContext(user_id=uuid.uuid4(), email="a@b.c", role="internal_admin", site_id=None)

        with pytest.raises(NoSiteInScope):
            await site_service.set_template(db_session, auth, "linen")


class TestSetTemplateScoped:

    async def test_switch_only_affects_own_site(self, db_session):
        """Switching site A's template does not change site B's."""
        site_a = await make_site(db_session, slug="tpl-scope-a")
        site_b = await make_site(db_session, slug="tpl-scope-b")
        owner_a = await make_owner(db_session, site_a)
        auth_a = _auth(owner_a)

        await site_service.set_template(db_session, auth_a, "slate")

        await db_session.refresh(site_b)
        assert site_b.template == "linen"


class TestSetTemplateRoute:

    async def test_switch_via_post(self, client, db_session):
        site = await make_site(db_session, slug="tpl-route")
        owner = await make_owner(db_session, site)
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/appearance/template",
            cookies={"session": cookie},
            data={"csrf_token": token, "template": "slate"},
        )
        assert resp.status_code == 303

        await db_session.refresh(site)
        assert site.template == "slate"

    async def test_unknown_template_returns_400(self, client, db_session):
        site = await make_site(db_session, slug="tpl-route-bad")
        owner = await make_owner(db_session, site)
        token = csrf_token_for(owner)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/appearance/template",
            cookies={"session": cookie},
            data={"csrf_token": token, "template": "bogus"},
        )
        assert resp.status_code == 400

    async def test_without_csrf_returns_403(self, client, db_session):
        site = await make_site(db_session, slug="tpl-nocsrf")
        owner = await make_owner(db_session, site)
        cookie = encode_session(owner.user_id)

        resp = await client.post(
            "/admin/appearance/template",
            cookies={"session": cookie},
            data={"template": "slate"},
        )
        assert resp.status_code == 403
