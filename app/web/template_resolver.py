"""Template resolver — maps site.template to file paths with safe fallback.

Convention: site.template is a folder name under public/ (for page layouts)
and public/themes/ (for tokens + CSS). If the named template's directory
doesn't exist, fall back to the default rather than 500'ing.
"""

from pathlib import Path

DEFAULT_TEMPLATE = "linen"

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
