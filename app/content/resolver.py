"""Site content resolver — the single source of truth for real vs sample content.

Pure function, no DB access. Reads only pre-loaded attributes from a Site model
and a role_images dict. Deterministic: same inputs produce the same output.

Three consumers (built in later chunks) bind to the types defined here:
  - Public render:  mode="public"  → real content only, samples hidden
  - Preview render: mode="preview" → real content, with samples filling gaps
  - Dashboard tiles: status field  → yours / partial / sample per area

The STATUS of each area is always mode-independent — it reflects what the owner
has actually provided, regardless of whether the caller is public or preview.
Only the VALUE/SOURCE of each field changes by mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.content import samples

Source = Literal["real", "sample", "empty"]
Status = Literal["yours", "partial", "sample"]
RenderMode = Literal["public", "preview"]


@dataclass(frozen=True)
class FieldView:
    """One resolved content field.

    value:  the actual content (real data, sample constant, or None)
    source: "real" | "sample" | "empty"

    Invariant: source="sample" if and only if value came from the samples
    module. These are always set together — never one without the other.
    """
    value: Any
    source: Source


@dataclass(frozen=True)
class AreaView:
    """One content area (e.g. home, menu, gallery).

    status: mode-INDEPENDENT status based on real data presence
    fields: all resolved fields for this area (keyed by field name)
    """
    status: Status
    fields: dict[str, FieldView]


# Type alias — keyed by area name
SiteView = dict[str, AreaView]


# ---------------------------------------------------------------------------
# Status-bearing field sets — explicit per area.
#
# Only these fields count toward an area's status (yours/partial/sample).
# Other fields (e.g. logo in home) are resolved for value/source but do NOT
# affect the status computation. This is structural, not implicit — adding
# a field to an area's resolver without adding it here won't change status.
# ---------------------------------------------------------------------------

_STATUS_FIELDS: dict[str, frozenset[str]] = {
    "home": frozenset({"hero", "tagline"}),
    "our_story": frozenset({"blocks"}),
    "visit": frozenset({"name", "address", "hours", "contact"}),
    "gallery": frozenset({"photos"}),
    "menu": frozenset({"menus"}),
}

# Visit fields that are factual and should NOT show sample data even in
# preview — too-plausible fakes (hours, addresses, phone numbers) could
# mislead owners into thinking they're real. These resolve to empty in
# both modes; only status is computed from real presence.
_NEVER_SAMPLE_FIELDS: frozenset[str] = frozenset({
    "address", "hours", "contact",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_site_view(
    *,
    site: Any,
    role_images: dict[str, list],
    mode: RenderMode,
) -> SiteView:
    """Build a resolved view of all content areas.

    Pure function. Reads only already-loaded attributes — never triggers
    a DB query or lazy load. Deterministic.

    Args:
        site: Site model with eager-loaded menus, regular_hours,
              content_blocks.
        role_images: dict from image_role_service.load_role_images —
                     {role: [Photo, ...]}. Already loaded.
        mode: "public" or "preview".

    Returns:
        SiteView — dict keyed by area name, each value an AreaView.
    """
    return {
        "home": _resolve_home(site, role_images, mode),
        "our_story": _resolve_our_story(site, mode),
        "visit": _resolve_visit(site, mode),
        "gallery": _resolve_gallery(role_images, mode),
        "menu": _resolve_menu(site, mode),
    }


# ---------------------------------------------------------------------------
# Per-area resolvers (private)
# ---------------------------------------------------------------------------

def _resolve_field(
    *,
    has_real: bool,
    real_value: Any,
    sample_value: Any,
    mode: RenderMode,
    never_sample: bool = False,
) -> FieldView:
    """Resolve a single field.

    Guarantees the invariant: source="sample" iff value is from the samples
    module. They are always set together.

    If never_sample is True, the field resolves to empty even in preview
    mode when real data is absent (for factual fields like hours/address).
    """
    if has_real:
        return FieldView(value=real_value, source="real")

    if mode == "preview" and not never_sample:
        return FieldView(value=sample_value, source="sample")

    return FieldView(value=None, source="empty")


def _compute_status(area_key: str, fields: dict[str, FieldView]) -> Status:
    """Compute area status from its status-bearing fields only."""
    status_keys = _STATUS_FIELDS[area_key]
    real_count = sum(
        1 for k in status_keys
        if k in fields and fields[k].source == "real"
    )
    if real_count == len(status_keys):
        return "yours"
    if real_count == 0:
        return "sample"
    return "partial"


def _resolve_home(
    site: Any, role_images: dict[str, list], mode: RenderMode,
) -> AreaView:
    feature_images = role_images.get("feature_images", [])
    logo_images = role_images.get("logo", [])

    fields = {
        "hero": _resolve_field(
            has_real=len(feature_images) > 0,
            real_value=feature_images[0] if feature_images else None,
            sample_value=samples.HERO_IMAGE_URL,
            mode=mode,
        ),
        "tagline": _resolve_field(
            has_real=bool(site.tagline),
            real_value=site.tagline,
            sample_value=samples.TAGLINE,
            mode=mode,
        ),
        # Logo: resolved for value but NOT status-bearing (excluded from
        # _STATUS_FIELDS["home"]). Present/absent does not change home status.
        "logo": _resolve_field(
            has_real=len(logo_images) > 0,
            real_value=logo_images[0] if logo_images else None,
            sample_value=samples.LOGO_IMAGE_URL,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("home", fields), fields=fields)


def _resolve_our_story(site: Any, mode: RenderMode) -> AreaView:
    story_blocks = [
        b for b in site.content_blocks if b.page_key == "our_story"
    ]
    has_blocks = len(story_blocks) > 0

    sample_block = {
        "heading": samples.OUR_STORY_HEADING,
        "body": samples.OUR_STORY_BODY,
    }

    fields = {
        "blocks": _resolve_field(
            has_real=has_blocks,
            real_value=story_blocks,
            sample_value=[sample_block],
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("our_story", fields), fields=fields)


def _resolve_visit(site: Any, mode: RenderMode) -> AreaView:
    has_address = bool(site.address_street)
    has_hours = len(site.regular_hours) > 0
    has_contact = bool(site.phone or site.email)

    fields = {
        # Name is always real post-signup
        "name": FieldView(value=site.restaurant_name, source="real"),
        # Factual fields: never_sample=True — empty-but-prompting in preview
        "address": _resolve_field(
            has_real=has_address,
            real_value=site.address_street,
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
        "hours": _resolve_field(
            has_real=has_hours,
            real_value=list(site.regular_hours),
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
        "contact": _resolve_field(
            has_real=has_contact,
            real_value={"phone": site.phone, "email": site.email},
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
    }
    return AreaView(status=_compute_status("visit", fields), fields=fields)


def _resolve_gallery(
    role_images: dict[str, list], mode: RenderMode,
) -> AreaView:
    gallery_photos = role_images.get("gallery", [])

    fields = {
        "photos": _resolve_field(
            has_real=len(gallery_photos) > 0,
            real_value=gallery_photos,
            sample_value=samples.GALLERY_IMAGE_URLS,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("gallery", fields), fields=fields)


def _resolve_menu(site: Any, mode: RenderMode) -> AreaView:
    has_menus = len(site.menus) > 0

    # Sample menu tree is NOT built here — deferred to the preview chunk.
    # value stays None in sample mode; the preview template will handle
    # rendering a static sample menu partial.
    fields = {
        "menus": _resolve_field(
            has_real=has_menus,
            real_value=list(site.menus),
            sample_value=None,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("menu", fields), fields=fields)
