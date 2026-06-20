"""Template resolver — maps site.template to file paths with safe fallback.

Convention: site.template is a folder name under public/ (for page layouts)
and public/themes/ (for tokens + CSS). If the named template's directory
doesn't exist, fall back to the default rather than 500'ing.
"""

from pathlib import Path

DEFAULT_TEMPLATE = "linen"

# Curated allowlist — a template isn't "available" just because its folder exists.
# Each entry is (value, display_label). set_template validates against this.
AVAILABLE_TEMPLATES: list[tuple[str, str]] = [
    ("linen", "Linen"),
    ("slate", "Slate"),
    ("olive", "Olive"),
]

# Per-template feature_images mode. "single" = one hero image (replace on assign).
# "carousel" = ordered multi-image list (add/remove/reorder).
FEATURE_IMAGE_MODE: dict[str, str] = {
    "linen": "single",
    "slate": "single",
    "olive": "carousel",
}

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
