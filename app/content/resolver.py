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
from datetime import date
from typing import Any, Callable, Literal

from app.content import samples

Source = Literal["real", "sample", "derived", "empty"]
Status = Literal["yours", "partial", "sample"]
RenderMode = Literal["public", "preview"]


@dataclass(frozen=True)
class FieldView:
    """One resolved content field.

    value:  the actual content (real data, sample constant, derived, or None)
    source: "real" | "sample" | "derived" | "empty"

    Invariant: source="sample" if and only if value came from the samples
    module. source="derived" for computed defaults (e.g. SEO meta).
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
    "events": frozenset({"events"}),
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

def _get_default_location(site: Any) -> Any | None:
    """Return the site's first location (by position), or None."""
    locations = getattr(site, "locations", None)
    if locations:
        return locations[0]
    return None


def resolve_site_view(
    *,
    site: Any,
    role_images: dict[str, list],
    mode: RenderMode,
    storage_url: Callable[[str], str],
) -> SiteView:
    """Build a resolved view of all content areas.

    Pure function. Reads only already-loaded attributes — never triggers
    a DB query or lazy load. Deterministic.

    Field values are normalised to uniform shapes so templates never
    branch on source to read — only to mark (sample badge etc.):
      - Images → URL strings (storage_url applied for real, static for sample)
      - Gallery → list of {url, alt_text, width, height}
      - Blocks → list of {heading, body, image_url, image_alt}

    Args:
        site: Site model with eager-loaded menus, locations (with
              regular_hours + hours_exceptions), content_blocks.
        role_images: dict from image_role_service.load_role_images —
                     {role: [Photo, ...]}. Already loaded.
        mode: "public" or "preview".
        storage_url: Callable to resolve an S3 key to a public URL.

    Returns:
        SiteView — dict keyed by area name, each value an AreaView.
    """
    location = _get_default_location(site)
    return {
        "home": _resolve_home(site, role_images, mode, storage_url),
        "our_story": _resolve_our_story(site, mode, storage_url),
        "visit": _resolve_visit(site, location, mode),
        "gallery": _resolve_gallery(role_images, mode, storage_url),
        "menu": _resolve_menu(site, mode),
        "events": _resolve_events(site, mode, storage_url),
        "seo": _resolve_seo(site, location),
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
    storage_url: Callable[[str], str],
) -> AreaView:
    feature_images = role_images.get("feature_images", [])
    logo_images = role_images.get("logo", [])

    fields = {
        # Uniform shape: URL string in both real and sample
        "hero": _resolve_field(
            has_real=len(feature_images) > 0,
            real_value=storage_url(feature_images[0].s3_key) if feature_images else None,
            sample_value=samples.HERO_IMAGE_URL,
            mode=mode,
        ),
        # All feature images as URL list — used by carousel templates.
        # Single-hero templates ignore this; carousel templates read it.
        # NOT status-bearing (hero field covers status).
        "hero_images": _resolve_field(
            has_real=len(feature_images) > 0,
            real_value=[storage_url(p.s3_key) for p in feature_images],
            sample_value=[samples.HERO_IMAGE_URL],
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
        # Uniform shape: URL string
        "logo": _resolve_field(
            has_real=len(logo_images) > 0,
            real_value=storage_url(logo_images[0].s3_key) if logo_images else None,
            sample_value=samples.LOGO_IMAGE_URL,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("home", fields), fields=fields)


def _resolve_our_story(
    site: Any, mode: RenderMode,
    storage_url: Callable[[str], str],
) -> AreaView:
    story_blocks = [
        b for b in site.content_blocks
        if b.page_key == "our_story" and b.is_visible
    ]
    has_blocks = len(story_blocks) > 0

    # Uniform shape: list of {heading, body, image_url, image_alt}
    real_list = [
        {
            "heading": b.heading,
            "body": b.body,
            "image_url": storage_url(b.image.s3_key) if b.image else None,
            "image_alt": (b.image.alt_text or "") if b.image else "",
        }
        for b in story_blocks
    ]
    sample_list = [
        {
            "heading": samples.OUR_STORY_HEADING,
            "body": samples.OUR_STORY_BODY,
            "image_url": None,
            "image_alt": "",
        },
    ]

    fields = {
        "blocks": _resolve_field(
            has_real=has_blocks,
            real_value=real_list,
            sample_value=sample_list,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("our_story", fields), fields=fields)


def _resolve_events(
    site: Any, mode: RenderMode,
    storage_url: Callable[[str], str],
) -> AreaView:
    today = date.today()
    event_blocks = [
        b for b in site.content_blocks
        if b.page_key == "events" and b.is_visible
    ]

    # Split: upcoming (dated, future/today) vs standing specials (undated)
    upcoming = sorted(
        [b for b in event_blocks if b.event_date is not None and b.event_date >= today],
        key=lambda b: b.event_date,
    )
    specials = sorted(
        [b for b in event_blocks if b.event_date is None],
        key=lambda b: b.position,
    )

    has_events = len(upcoming) > 0 or len(specials) > 0

    def _block_dict(b: Any) -> dict:
        return {
            "heading": b.heading,
            "body": b.body,
            "event_date": b.event_date,
            "image_url": storage_url(b.image.s3_key) if b.image else None,
            "image_alt": (b.image.alt_text or "") if b.image else "",
        }

    real_value = {
        "upcoming": [_block_dict(b) for b in upcoming],
        "specials": [_block_dict(b) for b in specials],
    }
    sample_value = {
        "upcoming": [
            {
                "heading": samples.EVENT_UPCOMING_1_HEADING,
                "body": samples.EVENT_UPCOMING_1_BODY,
                "event_date": samples.event_sample_date(3),
                "image_url": None, "image_alt": "",
            },
            {
                "heading": samples.EVENT_UPCOMING_2_HEADING,
                "body": samples.EVENT_UPCOMING_2_BODY,
                "event_date": samples.event_sample_date(10),
                "image_url": None, "image_alt": "",
            },
        ],
        "specials": [
            {
                "heading": samples.EVENT_SPECIAL_1_HEADING,
                "body": samples.EVENT_SPECIAL_1_BODY,
                "event_date": None, "image_url": None, "image_alt": "",
            },
            {
                "heading": samples.EVENT_SPECIAL_2_HEADING,
                "body": samples.EVENT_SPECIAL_2_BODY,
                "event_date": None, "image_url": None, "image_alt": "",
            },
        ],
    }

    fields = {
        "events": _resolve_field(
            has_real=has_events,
            real_value=real_value,
            sample_value=sample_value,
            mode=mode,
        ),
    }
    return AreaView(status=_compute_status("events", fields), fields=fields)


def _clean_social(raw: Any) -> list[dict]:
    """Shape social_links for public render: a list of {platform, url}, dropping
    any entry missing either. Returns [] for None/absent/malformed input."""
    if not raw:
        return []
    out: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        platform = (entry.get("platform") or "").strip()
        url = (entry.get("url") or "").strip()
        if platform and url:
            out.append({"platform": platform, "url": url})
    return out


def _resolve_visit(site: Any, location: Any | None, mode: RenderMode) -> AreaView:
    has_address = bool(location and location.address_street)
    has_hours = bool(location and len(location.regular_hours) > 0)
    has_contact = bool(location and (location.phone or location.email))

    address_value = {
        "street": location.address_street,
        "suburb": location.address_suburb,
        "state": location.address_state,
        "postcode": location.address_postcode,
    } if has_address else None

    contact_value = {
        "phone": location.phone,
        "email": location.email,
    } if location else {"phone": None, "email": None}

    fields = {
        # Name is always real post-signup
        "name": FieldView(value=site.restaurant_name, source="real"),
        # Factual fields: never_sample=True — empty-but-prompting in preview
        "address": _resolve_field(
            has_real=has_address,
            real_value=address_value,
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
        "hours": _resolve_field(
            has_real=has_hours,
            real_value=list(location.regular_hours) if location else [],
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
        "contact": _resolve_field(
            has_real=has_contact,
            real_value=contact_value,
            sample_value=None,
            mode=mode,
            never_sample=True,
        ),
        # Social: never sampled. Direct FieldView so value is ALWAYS a list
        # ([] when empty) — the footer reads .value and expects a list.
        "social": _social_field(location),
    }
    return AreaView(status=_compute_status("visit", fields), fields=fields)


def _social_field(location: Any | None) -> FieldView:
    social = _clean_social(location.social_links if location else None)
    return FieldView(value=social, source="real" if social else "empty")


def _resolve_gallery(
    role_images: dict[str, list], mode: RenderMode,
    storage_url: Callable[[str], str],
) -> AreaView:
    gallery_photos = role_images.get("gallery", [])

    # Uniform shape: list of {url, alt_text, width, height}
    real_list = [
        {
            "url": storage_url(p.s3_key),
            "alt_text": p.alt_text or "",
            "width": p.width,
            "height": p.height,
        }
        for p in gallery_photos
    ]
    sample_list = [
        {"url": u, "alt_text": "", "width": 400, "height": 300}
        for u in samples.GALLERY_IMAGE_URLS
    ]

    fields = {
        "photos": _resolve_field(
            has_real=len(gallery_photos) > 0,
            real_value=real_list,
            sample_value=sample_list,
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


_META_TITLE_MAX = 60


def _derive_meta_title(site: Any, location: Any | None) -> str | None:
    """Derive a meta title from name + suburb. None if too thin."""
    name = site.restaurant_name
    suburb = getattr(location, "address_suburb", None) if location else None
    if suburb:
        candidate = f"{name} — {suburb}"
        if len(candidate) <= _META_TITLE_MAX:
            return candidate
    return name


def _derive_meta_description(site: Any, location: Any | None) -> str | None:
    """Derive a meta description from tagline + suburb.

    Degrade ladder:
      both   → "{tagline}. Located in {suburb}."
      tagline only → "{tagline}"
      suburb only  → "{name} — a restaurant in {suburb}."
      neither      → None (omit — better no description than a bad one)
    """
    tagline = getattr(site, "tagline", None)
    suburb = getattr(location, "address_suburb", None) if location else None
    name = site.restaurant_name

    if tagline and suburb:
        desc = f"{tagline}. Located in {suburb}."
    elif tagline:
        desc = tagline
    elif suburb:
        desc = f"{name} — a restaurant in {suburb}."
    else:
        return None

    return desc[:155] if len(desc) > 155 else desc


def _resolve_seo(site: Any, location: Any | None) -> AreaView:
    """Resolve SEO meta fields with derive-with-override.

    Mode-independent: derived values are always computed (not sample content).
    NOT status-bearing — SEO is not part of the publish gate.
    """
    has_title = bool(site.meta_title)
    has_desc = bool(site.meta_description)

    if has_title:
        title_field = FieldView(value=site.meta_title, source="real")
    else:
        derived = _derive_meta_title(site, location)
        title_field = FieldView(value=derived, source="derived")

    if has_desc:
        desc_field = FieldView(value=site.meta_description, source="real")
    else:
        derived = _derive_meta_description(site, location)
        if derived:
            desc_field = FieldView(value=derived, source="derived")
        else:
            desc_field = FieldView(value=None, source="empty")

    fields = {"meta_title": title_field, "meta_description": desc_field}

    # Status: "yours" if either is overridden, else "sample" (auto-generated).
    # This is cosmetic for the dashboard tile only — not a publish-gate concern.
    if has_title or has_desc:
        status: Status = "yours"
    else:
        status = "sample"

    return AreaView(status=status, fields=fields)
