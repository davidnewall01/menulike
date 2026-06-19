import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Numeric, String, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.menu import Menu
    from app.models.photo import Photo
    from app.models.site_image_role import SiteImageRole


class Site(TimestampMixin, Base):
    __tablename__ = "site"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    restaurant_name: Mapped[str] = mapped_column(String, nullable=False)
    template: Mapped[str] = mapped_column(
        String, nullable=False, server_default="linen"
    )
    tagline: Mapped[str | None] = mapped_column(String, nullable=True)
    hero_heading: Mapped[str | None] = mapped_column(String, nullable=True)
    hero_subheading: Mapped[str | None] = mapped_column(String, nullable=True)
    about_story: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Address
    address_street: Mapped[str | None] = mapped_column(String, nullable=True)
    address_suburb: Mapped[str | None] = mapped_column(String, nullable=True)
    address_state: Mapped[str | None] = mapped_column(String, nullable=True)
    address_postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    address_country: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )

    # Contact / CTAs
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_url: Mapped[str | None] = mapped_column(String, nullable=True)
    order_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # SEO
    meta_title: Mapped[str | None] = mapped_column(String, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Design config (JSONB)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Relationships
    menus: Mapped[list["Menu"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Menu.position",
    )
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    image_roles: Mapped[list["SiteImageRole"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
