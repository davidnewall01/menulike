"""Domain exceptions raised by services.

Routes/coordinators translate these to HTTP status codes.
Services never raise HTTPException directly.
"""


class SiteNotFound(Exception):
    """The scoped site_id resolved to no row — fail closed."""


class NoSiteInScope(Exception):
    """The auth context has no scoped site (e.g. internal_admin)."""


class MenuNotFound(Exception):
    """The menu_id didn't resolve within the owner's scoped site."""
