"""Template resolver — maps site.template to file paths with safe fallback.

Convention: site.template is a folder name under public/ (for page layouts)
and public/themes/ (for tokens + CSS). If the named template's directory
doesn't exist, fall back to the default rather than 500'ing.

Template METADATA (display_name, descriptor, tags) is DB-backed — see
app/models/template_meta.py and app/services/template_meta_service.py.
Only RENDER BEHAVIOUR (feature_image_mode, path resolution) stays here.
"""

from pathlib import Path

DEFAULT_TEMPLATE = "linen"

# ---------------------------------------------------------------------------
# Feature image mode — RENDER BEHAVIOUR, stays in code (developer-curated).
#
# "single" = one hero image (replace on assign).
# "carousel" = ordered multi-image list (add/remove/reorder).
#
# This is NOT marketing metadata — it controls which admin component renders.
# Do NOT move to DB. Changes only when a template's code changes.
# ---------------------------------------------------------------------------

FEATURE_IMAGE_MODE: dict[str, str] = {
    "linen": "single",
    "slate": "single",
    "olive": "carousel",
}


def get_feature_image_mode(template: str) -> str:
    """Return 'single' or 'carousel' for a template (default: single)."""
    return FEATURE_IMAGE_MODE.get(template, "single")


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "public"


def resolve_template(template_name: str) -> str:
    """Return a validated template name, falling back to the default.

    Checks that the template's page directory exists under public/{template}/.
    If not, returns DEFAULT_TEMPLATE.
    """
    if not template_name:
        return DEFAULT_TEMPLATE

    candidate = _TEMPLATES_DIR / template_name
    if candidate.is_dir():
        return template_name

    return DEFAULT_TEMPLATE


def page_path(template: str, page: str) -> str:
    """Jinja2 template path for a page layout.

    e.g. page_path("linen", "home") -> "public/linen/home.html"
    """
    return f"public/{template}/{page}.html"


def page_path_safe(template: str, page: str) -> str:
    """Like page_path, but falls back to DEFAULT_TEMPLATE if the page file
    doesn't exist for this template (e.g. Olive lacks menu.html).

    Prevents Jinja2 TemplateNotFound → 500 on incomplete templates.
    """
    candidate = _TEMPLATES_DIR / template / f"{page}.html"
    if candidate.is_file():
        return f"public/{template}/{page}.html"
    return f"public/{DEFAULT_TEMPLATE}/{page}.html"
