"""Unit tests for extract_slug — pure function, no DB."""

import pytest

from app.web.tenancy import extract_slug


class TestExtractSlug:
    """extract_slug(host, base_domain) -> slug | None"""

    def test_subdomain_localhost(self):
        assert extract_slug("portoazzurro.localhost", "localhost") == "portoazzurro"

    def test_subdomain_localhost_with_port(self):
        assert extract_slug("portoazzurro.localhost:8000", "localhost") == "portoazzurro"

    def test_apex_localhost(self):
        assert extract_slug("localhost", "localhost") is None

    def test_apex_localhost_with_port(self):
        assert extract_slug("localhost:8000", "localhost") is None

    def test_unknown_subdomain(self):
        assert extract_slug("nope.localhost", "localhost") == "nope"

    def test_production_base_domain(self):
        assert extract_slug("portoazzurro.menulike.app", "menulike.app") == "portoazzurro"

    def test_production_apex(self):
        assert extract_slug("menulike.app", "menulike.app") is None

    def test_unrelated_host(self):
        assert extract_slug("example.com", "localhost") is None

    def test_empty_host(self):
        assert extract_slug("", "localhost") is None

    def test_dot_only(self):
        assert extract_slug(".localhost", "localhost") is None

    def test_base_with_port_host_without(self):
        assert extract_slug("portoazzurro.localhost", "localhost:8000") == "portoazzurro"
