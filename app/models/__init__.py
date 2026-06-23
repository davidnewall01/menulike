"""Model package.

Alembic imports this package so every model is registered on
`Base.metadata` before migrations run.
"""

from app.models.content_block import ContentBlock
from app.models.hours_exception import HoursException
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.photo import Photo
from app.models.regular_hours import RegularHours
from app.models.site import Site
from app.models.site_image_role import SiteImageRole
from app.models.user import User

__all__ = [
    "ContentBlock",
    "HoursException",
    "Menu",
    "MenuItem",
    "MenuItemVariant",
    "Photo",
    "RegularHours",
    "Section",
    "Site",
    "SiteImageRole",
    "Subsection",
    "User",
]
