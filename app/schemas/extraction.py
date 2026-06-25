"""Pydantic models for the menu extraction contract (vision model output)."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedExtra(BaseModel):
    label: str
    price: str | None = None


class ExtractedVariant(BaseModel):
    label: str | None = None
    price: str | None = None


class ExtractedItem(BaseModel):
    name: str
    description: str | None = None
    dietary_tags: list[str] = []
    variants: list[ExtractedVariant] = []
    extras: list[ExtractedExtra] = []


class ExtractedSubsection(BaseModel):
    name: str | None = None
    items: list[ExtractedItem] = []


class ExtractedSection(BaseModel):
    name: str
    note: str | None = None
    subsections: list[ExtractedSubsection] = []


class ExtractedFooterEntry(BaseModel):
    label: str | None = None
    description: str | None = None


class ExtractedFooterBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    block_type: str = Field(default="info", alias="type")
    title: str | None = None
    entries: list[ExtractedFooterEntry] = []


class ExtractedMenu(BaseModel):
    menu_name: str
    sections: list[ExtractedSection] = []
    menu_note: str | None = None
    footer_blocks: list[ExtractedFooterBlock] = []
    ignored: list[str] = []
