"""Template metadata — one row per template look (linen/slate/olive).

Admin-editable via the template catalog editor. Separate from
feature_image_mode (which stays in code — render behaviour, not
marketing metadata).
"""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Join table (no ORM model — accessed via relationship)
template_tag = Table(
    "template_tag",
    Base.metadata,
    Column(
        "template_key",
        String,
        ForeignKey("template_meta.template_key", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tag_vocabulary.tag_id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class TemplateMeta(Base):
    __tablename__ = "template_meta"

    template_key: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    descriptor: Mapped[str] = mapped_column(Text, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tags: Mapped[list["TagVocabulary"]] = relationship(
        secondary=template_tag,
        back_populates="templates",
        lazy="selectin",
    )


class TagVocabulary(Base):
    __tablename__ = "tag_vocabulary"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    value: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    templates: Mapped[list["TemplateMeta"]] = relationship(
        secondary=template_tag,
        back_populates="tags",
        lazy="selectin",
    )
