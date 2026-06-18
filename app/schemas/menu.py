"""Pydantic form models for menu editing."""

from pydantic import BaseModel, field_validator


class MenuForm(BaseModel):
    """Validates the menu create/edit form.

    name is required and must be non-empty after stripping.
    description and availability_note are optional (empty -> None).
    """

    name: str
    description: str | None = None
    availability_note: str | None = None

    @field_validator("description", "availability_note", mode="before")
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
