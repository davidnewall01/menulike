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


class SectionNotFound(Exception):
    """The section_id didn't resolve within the owner's scoped site."""


class SubsectionNotFound(Exception):
    """The subsection_id didn't resolve within the owner's scoped site."""


class ItemNotFound(Exception):
    """The item_id didn't resolve within the owner's scoped site."""


class VariantNotFound(Exception):
    """The variant_id didn't resolve within the owner's scoped site."""


class ReorderMismatch(Exception):
    """The submitted id list is not an exact permutation of the parent's children."""


class PhotoNotFound(Exception):
    """The photo_id didn't resolve within the owner's scoped site."""


class InvalidImage(Exception):
    """The uploaded file is not an allowed image type or exceeds size limits."""


class InvalidRole(Exception):
    """The role key is not in the allowed set."""


class InvalidTemplate(Exception):
    """The template value is not in AVAILABLE_TEMPLATES."""
