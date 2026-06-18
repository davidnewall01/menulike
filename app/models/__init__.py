"""Model package.

Alembic imports this package so every model is registered on
`Base.metadata` before migrations run.
"""

from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
from app.models.site import Site
from app.models.user import User

__all__ = [
    "Menu",
    "MenuItem",
    "MenuItemVariant",
    "Section",
    "Site",
    "Subsection",
    "User",
]
