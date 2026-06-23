"""Unit tests for the site content resolver.

All tests use lightweight fakes (SimpleNamespace) — NO database, proving
the resolver is pure. Tests cover:
  - Per-area status across real/absent permutations
  - Mode-dependent value/source resolution
  - Mode-independence of status
  - Logo not affecting home status (structural invariant)
  - Visit never reaching "sample" status
  - never_sample fields (hours/address/contact) resolving empty in preview
  - Sample-value-and-source-set-together invariant
"""

from types import SimpleNamespace

import pytest

from app.content.resolver import (
    AreaView,
    FieldView,
    SiteView,
    resolve_site_view,
)
from app.content import samples


# ---------------------------------------------------------------------------
# Fake builders
# ---------------------------------------------------------------------------

def make_site(
    *,
    restaurant_name: str = "Test Restaurant",
    tagline: str | None = None,
    address_street: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    regular_hours: list | None = None,
    content_blocks: list | None = None,
    menus: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        restaurant_name=restaurant_name,
        tagline=tagline,
        address_street=address_street,
        phone=phone,
        email=email,
        regular_hours=regular_hours or [],
        content_blocks=content_blocks or [],
        menus=menus or [],
    )


def make_role_images(
    *,
    feature_images: list | None = None,
    gallery: list | None = None,
    logo: list | None = None,
) -> dict[str, list]:
    d: dict[str, list] = {}
    if feature_images is not None:
        d["feature_images"] = feature_images
    if gallery is not None:
        d["gallery"] = gallery
    if logo is not None:
        d["logo"] = logo
    return d


def make_photo(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        s3_key=kwargs.get("s3_key", "photos/test.jpg"),
        alt_text=kwargs.get("alt_text", ""),
    )


def make_block(page_key: str = "our_story", **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        page_key=page_key,
        heading=kwargs.get("heading", "Heading"),
        body=kwargs.get("body", "Body text"),
        image_photo_id=None,
        image=None,
    )


def make_hours_range(day: int = 0) -> SimpleNamespace:
    return SimpleNamespace(day_of_week=day)


def make_menu(name: str = "Food") -> SimpleNamespace:
    return SimpleNamespace(name=name, sections=[])


# ---------------------------------------------------------------------------
# HOME area
# ---------------------------------------------------------------------------

class TestHomeArea:

    def test_sample_when_no_hero_no_tagline(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["home"].status == "sample"

    def test_partial_when_hero_only(self):
        view = resolve_site_view(
            site=make_site(),
            role_images=make_role_images(feature_images=[make_photo()]),
            mode="public",
        )
        assert view["home"].status == "partial"

    def test_partial_when_tagline_only(self):
        view = resolve_site_view(
            site=make_site(tagline="Fresh food"),
            role_images={},
            mode="public",
        )
        assert view["home"].status == "partial"

    def test_yours_when_hero_and_tagline(self):
        view = resolve_site_view(
            site=make_site(tagline="Fresh food"),
            role_images=make_role_images(feature_images=[make_photo()]),
            mode="public",
        )
        assert view["home"].status == "yours"

    def test_logo_does_not_affect_status_absent(self):
        """Logo is not status-bearing — its presence/absence must not change status."""
        site = make_site(tagline="Fresh food")
        # Without logo
        view_no_logo = resolve_site_view(
            site=site, role_images=make_role_images(feature_images=[make_photo()]),
            mode="public",
        )
        # With logo
        view_with_logo = resolve_site_view(
            site=site,
            role_images=make_role_images(
                feature_images=[make_photo()], logo=[make_photo()],
            ),
            mode="public",
        )
        assert view_no_logo["home"].status == view_with_logo["home"].status == "yours"

    def test_logo_does_not_affect_status_when_empty(self):
        """Logo present when hero+tagline absent → still sample, not partial."""
        view = resolve_site_view(
            site=make_site(),
            role_images=make_role_images(logo=[make_photo()]),
            mode="public",
        )
        assert view["home"].status == "sample"

    def test_logo_value_resolved_in_preview(self):
        """Logo value IS resolved (for rendering) even though not status-bearing."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        logo = view["home"].fields["logo"]
        assert logo.source == "sample"
        assert logo.value == samples.LOGO_IMAGE_URL


# ---------------------------------------------------------------------------
# OUR STORY area
# ---------------------------------------------------------------------------

class TestOurStoryArea:

    def test_sample_when_no_blocks(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["our_story"].status == "sample"

    def test_yours_when_blocks_exist(self):
        view = resolve_site_view(
            site=make_site(content_blocks=[make_block()]),
            role_images={},
            mode="public",
        )
        assert view["our_story"].status == "yours"

    def test_ignores_blocks_with_different_page_key(self):
        view = resolve_site_view(
            site=make_site(content_blocks=[make_block(page_key="about")]),
            role_images={},
            mode="public",
        )
        assert view["our_story"].status == "sample"


# ---------------------------------------------------------------------------
# VISIT area
# ---------------------------------------------------------------------------

class TestVisitArea:

    def test_never_sample(self):
        """Visit is never 'sample' — name is always real post-signup."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["visit"].status == "partial"
        assert view["visit"].status != "sample"

    def test_partial_when_only_name(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["visit"].status == "partial"

    def test_yours_when_all_present(self):
        view = resolve_site_view(
            site=make_site(
                address_street="1 Main St",
                phone="555-1234",
                regular_hours=[make_hours_range()],
            ),
            role_images={},
            mode="public",
        )
        assert view["visit"].status == "yours"

    def test_partial_when_some_present(self):
        view = resolve_site_view(
            site=make_site(address_street="1 Main St"),
            role_images={},
            mode="public",
        )
        assert view["visit"].status == "partial"

    def test_hours_empty_in_preview_when_absent(self):
        """Hours are never-sample: even in preview, absent hours resolve empty."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        hours = view["visit"].fields["hours"]
        assert hours.source == "empty"
        assert hours.value is None

    def test_address_empty_in_preview_when_absent(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        address = view["visit"].fields["address"]
        assert address.source == "empty"
        assert address.value is None

    def test_contact_empty_in_preview_when_absent(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        contact = view["visit"].fields["contact"]
        assert contact.source == "empty"
        assert contact.value is None

    def test_real_hours_returned_when_present(self):
        hrs = [make_hours_range(0), make_hours_range(1)]
        view = resolve_site_view(
            site=make_site(regular_hours=hrs), role_images={}, mode="public",
        )
        assert view["visit"].fields["hours"].source == "real"
        assert len(view["visit"].fields["hours"].value) == 2


# ---------------------------------------------------------------------------
# GALLERY area
# ---------------------------------------------------------------------------

class TestGalleryArea:

    def test_sample_when_no_photos(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["gallery"].status == "sample"

    def test_yours_when_photos_exist(self):
        view = resolve_site_view(
            site=make_site(),
            role_images=make_role_images(gallery=[make_photo(), make_photo()]),
            mode="public",
        )
        assert view["gallery"].status == "yours"


# ---------------------------------------------------------------------------
# MENU area
# ---------------------------------------------------------------------------

class TestMenuArea:

    def test_sample_when_no_menus(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert view["menu"].status == "sample"

    def test_yours_when_menus_exist(self):
        view = resolve_site_view(
            site=make_site(menus=[make_menu()]),
            role_images={},
            mode="public",
        )
        assert view["menu"].status == "yours"

    def test_menu_sample_value_is_none(self):
        """Sample menu tree is deferred — value is None even in preview."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        menus = view["menu"].fields["menus"]
        assert menus.source == "sample"
        assert menus.value is None


# ---------------------------------------------------------------------------
# MODE-DEPENDENT VALUE/SOURCE
# ---------------------------------------------------------------------------

class TestModeResolution:

    def test_real_data_same_in_both_modes(self):
        """Real data → source="real" in both public and preview."""
        site = make_site(tagline="Real tagline")
        for mode in ("public", "preview"):
            view = resolve_site_view(site=site, role_images={}, mode=mode)
            tagline = view["home"].fields["tagline"]
            assert tagline.source == "real"
            assert tagline.value == "Real tagline"

    def test_absent_public_gives_empty(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        tagline = view["home"].fields["tagline"]
        assert tagline.source == "empty"
        assert tagline.value is None

    def test_absent_preview_gives_sample(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        tagline = view["home"].fields["tagline"]
        assert tagline.source == "sample"
        assert tagline.value == samples.TAGLINE

    def test_preview_hero_sample_is_url(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        hero = view["home"].fields["hero"]
        assert hero.source == "sample"
        assert hero.value == samples.HERO_IMAGE_URL

    def test_preview_gallery_sample_urls(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        photos = view["gallery"].fields["photos"]
        assert photos.source == "sample"
        assert photos.value == samples.GALLERY_IMAGE_URLS

    def test_preview_our_story_sample_block(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        blocks = view["our_story"].fields["blocks"]
        assert blocks.source == "sample"
        assert len(blocks.value) == 1
        assert blocks.value[0]["heading"] == samples.OUR_STORY_HEADING


# ---------------------------------------------------------------------------
# STATUS IS MODE-INDEPENDENT
# ---------------------------------------------------------------------------

class TestStatusModeIndependence:

    @pytest.mark.parametrize("mode", ["public", "preview"])
    def test_empty_site_same_status_both_modes(self, mode):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode=mode,
        )
        assert view["home"].status == "sample"
        assert view["our_story"].status == "sample"
        assert view["visit"].status == "partial"  # name always real
        assert view["gallery"].status == "sample"
        assert view["menu"].status == "sample"

    @pytest.mark.parametrize("mode", ["public", "preview"])
    def test_full_site_same_status_both_modes(self, mode):
        site = make_site(
            tagline="Fresh food",
            address_street="1 Main St",
            phone="555-1234",
            regular_hours=[make_hours_range()],
            content_blocks=[make_block()],
            menus=[make_menu()],
        )
        role_images = make_role_images(
            feature_images=[make_photo()],
            gallery=[make_photo()],
        )
        view = resolve_site_view(site=site, role_images=role_images, mode=mode)
        assert view["home"].status == "yours"
        assert view["our_story"].status == "yours"
        assert view["visit"].status == "yours"
        assert view["gallery"].status == "yours"
        assert view["menu"].status == "yours"


# ---------------------------------------------------------------------------
# SAMPLE-VALUE-AND-SOURCE INVARIANT
# ---------------------------------------------------------------------------

class TestSampleInvariant:
    """source="sample" iff value came from the samples module."""

    def test_no_untagged_sample_values(self):
        """Every field with source="sample" has a non-None value from samples.

        Exception: menu.menus is deliberately None (sample tree deferred to
        preview chunk) — tested separately in test_menu_sample_is_special_case.
        """
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        for area_key, area in view.items():
            for field_key, field in area.fields.items():
                if field.source == "sample" and (area_key, field_key) != ("menu", "menus"):
                    assert field.value is not None, (
                        f"{area_key}.{field_key}: source='sample' but value is None"
                    )

    def test_no_sample_source_with_none_value_public(self):
        """In public mode, absent fields are empty (not sample)."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        for area_key, area in view.items():
            for field_key, field in area.fields.items():
                if field.value is None:
                    assert field.source != "sample", (
                        f"{area_key}.{field_key}: value is None but source='sample'"
                    )

    def test_menu_sample_is_special_case(self):
        """Menu sample has value=None (deferred) but still source='sample'."""
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="preview",
        )
        menus = view["menu"].fields["menus"]
        # This is the one deliberate exception: sample menu tree is deferred,
        # so value is None but source is "sample" to signal the area is sampled.
        assert menus.source == "sample"
        assert menus.value is None


# ---------------------------------------------------------------------------
# ALL AREA KEYS PRESENT
# ---------------------------------------------------------------------------

class TestStructure:

    def test_all_areas_present(self):
        view = resolve_site_view(
            site=make_site(), role_images={}, mode="public",
        )
        assert set(view.keys()) == {"home", "our_story", "visit", "gallery", "menu"}

    def test_field_view_is_frozen(self):
        fv = FieldView(value="x", source="real")
        with pytest.raises(AttributeError):
            fv.value = "y"  # type: ignore[misc]

    def test_area_view_is_frozen(self):
        av = AreaView(status="yours", fields={})
        with pytest.raises(AttributeError):
            av.status = "sample"  # type: ignore[misc]
