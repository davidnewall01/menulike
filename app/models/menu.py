import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.site import Site


class Menu(TimestampMixin, Base):
    __tablename__ = "menus"

    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability_note: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="menus")
    sections: Mapped[list["Section"]] = relationship(
        back_populates="menu",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Section.position",
    )


class Section(TimestampMixin, Base):
    __tablename__ = "sections"

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menus.menu_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    menu: Mapped["Menu"] = relationship(back_populates="sections")
    subsections: Mapped[list["Subsection"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Subsection.position",
    )


class Subsection(TimestampMixin, Base):
    __tablename__ = "subsections"

    subsection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.section_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    section: Mapped["Section"] = relationship(back_populates="subsections")
    items: Mapped[list["MenuItem"]] = relationship(
        back_populates="subsection",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MenuItem.position",
    )


class MenuItem(TimestampMixin, Base):
    __tablename__ = "menu_items"

    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subsection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subsections.subsection_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dietary_tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    subsection: Mapped["Subsection"] = relationship(back_populates="items")
    variants: Mapped[list["MenuItemVariant"]] = relationship(
        back_populates="menu_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MenuItemVariant.position",
    )


class MenuItemVariant(TimestampMixin, Base):
    __tablename__ = "menu_item_variants"

    menu_item_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    menu_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_items.menu_item_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    menu_item: Mapped["MenuItem"] = relationship(back_populates="variants")
