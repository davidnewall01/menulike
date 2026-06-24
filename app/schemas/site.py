"""Pydantic form models for site editing."""

from pydantic import BaseModel, field_validator


def _empty_to_none(v: str | None) -> str | None:
    """Coerce empty strings from HTML forms to None."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class SiteDetailsForm(BaseModel):
    """Validates the restaurant-details edit form.

    restaurant_name is required and must be non-empty after stripping.
    URLs must use http/https if a scheme is present. Everything else optional.
    """

    restaurant_name: str
    address_street: str | None = None
    address_suburb: str | None = None
    address_state: str | None = None
    address_postcode: str | None = None
    phone: str | None = None
    email: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_str_to_none(cls, v, info):
        if info.field_name == "restaurant_name":
            return v
        return _empty_to_none(v)

    @field_validator("restaurant_name")
    @classmethod
    def restaurant_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Restaurant name is required")
        return stripped


class SeoForm(BaseModel):
    """Validates the SEO override form. Both fields optional (empty = revert to derived)."""

    meta_title: str | None = None
    meta_description: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_str_to_none(cls, v, info):
        return _empty_to_none(v)

