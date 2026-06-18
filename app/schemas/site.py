"""Pydantic form models for site editing."""

from urllib.parse import urlparse

from pydantic import BaseModel, field_validator


_ALLOWED_URL_SCHEMES = {"http", "https", ""}


def _empty_to_none(v: str | None) -> str | None:
    """Coerce empty strings from HTML forms to None."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def _validate_url_scheme(v: str | None) -> str | None:
    """Reject URLs with schemes other than http/https."""
    if v is None:
        return v
    scheme = urlparse(v).scheme.lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"URL scheme '{scheme}' is not allowed; use http or https")
    return v


class SiteDetailsForm(BaseModel):
    """Validates the restaurant-details edit form.

    restaurant_name is required and must be non-empty after stripping.
    URLs must use http/https if a scheme is present. Everything else optional.
    """

    restaurant_name: str
    tagline: str | None = None
    hero_heading: str | None = None
    hero_subheading: str | None = None
    about_story: str | None = None
    address_street: str | None = None
    address_suburb: str | None = None
    address_state: str | None = None
    address_postcode: str | None = None
    address_country: str | None = None
    phone: str | None = None
    email: str | None = None
    booking_url: str | None = None
    order_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None

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

    @field_validator("booking_url", "order_url")
    @classmethod
    def url_scheme_check(cls, v: str | None) -> str | None:
        return _validate_url_scheme(v)
