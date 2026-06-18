"""Pydantic form models for site editing."""

from pydantic import BaseModel, field_validator


def _empty_to_none(v: str | None) -> str | None:
    """Coerce empty strings from HTML forms to None."""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class SiteDetailsForm(BaseModel):
    """Validates the restaurant-details edit form.

    restaurant_name is required; URLs and email are validated if present;
    everything else is optional.
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
