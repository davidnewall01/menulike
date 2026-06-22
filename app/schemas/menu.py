"""Pydantic form models for menu editing."""

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, field_validator


def parse_extras(labels: list[str], prices: list[str]) -> list[dict]:
    """Pair extras_label[] and extras_price[] lists into a normalised JSONB array.

    Rules:
    - Strip whitespace from both label and price.
    - Drop rows where the label is blank (price-only rows are meaningless).
    - Keep rows where price is blank (e.g. "Seasonal" with no price).
    - Price stored as string (display-only, not arithmetic).
    """
    extras = []
    for label, price in zip(labels, prices):
        label = label.strip()
        if not label:
            continue
        price = price.strip()
        extras.append({"label": label, "price": price or None})
    return extras


class MenuForm(BaseModel):
    """Validates the menu create/edit form.

    name is required and must be non-empty after stripping.
    description and availability_note are optional (empty -> None).
    """

    name: str
    display_title: str | None = None
    description: str | None = None
    availability_note: str | None = None

    @field_validator("display_title", "description", "availability_note", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Menu name is required")
        return stripped


class SectionForm(BaseModel):
    """Validates the section create/edit form."""

    name: str
    description: str | None = None
    note: str | None = None

    @field_validator("description", "note", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Section name is required")
        return stripped


class SubsectionForm(BaseModel):
    """Validates the subsection create/edit form.

    name is OPTIONAL — empty/blank -> None (headingless subsection).
    """

    name: str | None = None
    description: str | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        if isinstance(v, str):
            return v.strip()
        return v


class ItemForm(BaseModel):
    """Validates the item create/edit form.

    dietary_tags arrives as a comma-separated string from the form,
    parsed into a trimmed list. featured is a checkbox (present = true).
    """

    name: str
    description: str | None = None
    dietary_tags: str = ""
    featured: bool = False

    @field_validator("description", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Item name is required")
        return stripped

    @field_validator("featured", mode="before")
    @classmethod
    def checkbox_to_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "on", "1", "yes")
        return bool(v)

    def parsed_dietary_tags(self) -> list[str]:
        """Split the comma-separated dietary_tags string into a clean list."""
        if not self.dietary_tags:
            return []
        return [t.strip() for t in self.dietary_tags.split(",") if t.strip()]


class VariantForm(BaseModel):
    """Validates the variant create/edit form."""

    label: str | None = None
    price: str

    @field_validator("label", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == "":
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator("price")
    @classmethod
    def valid_price(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Price is required")
        try:
            d = Decimal(stripped)
        except InvalidOperation:
            raise ValueError("Price must be a valid number")
        if d < 0:
            raise ValueError("Price must be zero or positive")
        return stripped

    def parsed_price(self) -> Decimal:
        return Decimal(self.price)
