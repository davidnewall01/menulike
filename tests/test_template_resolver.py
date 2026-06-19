"""Template resolver tests — default, resolution, fallback."""

from app.web.template_resolver import DEFAULT_TEMPLATE, page_path, resolve_template
from tests.conftest import make_site


class TestResolveTemplate:

    def test_linen_resolves_to_linen(self):
        """Known template 'linen' resolves to itself."""
        assert resolve_template("linen") == "linen"

    def test_unknown_falls_back_to_default(self):
        """An unknown template name falls back to the default."""
        assert resolve_template("nonexistent_template") == DEFAULT_TEMPLATE

    def test_empty_string_falls_back_to_default(self):
        assert resolve_template("") == DEFAULT_TEMPLATE

    def test_none_falls_back_to_default(self):
        assert resolve_template(None) == DEFAULT_TEMPLATE


class TestPagePath:

    def test_linen_home(self):
        assert page_path("linen", "home") == "public/linen/home.html"

    def test_other_template(self):
        """A different template value routes to a different path."""
        assert page_path("dumpling", "home") == "public/dumpling/home.html"


class TestSiteTemplateDefault:

    async def test_new_site_defaults_to_linen(self, db_session):
        """A new site gets template='linen' by default."""
        site = await make_site(db_session, slug="tpl-default")
        assert site.template == "linen"
