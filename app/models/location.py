"""Location entity — address + hours + contact per venue.

Location is deliberately content-free — address/hours/contact (including
social handles, a contact channel) ONLY.
Never add menu or other content (design doc §6b bright line).
A site has MANY locations (multi-venue); each location carries its own
address, opening hours, and contact details. Different menu = a future
separate Site under a Brand (Feature B), not another location.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.hours_exception import HoursException
    from app.models.regular_hours import RegularHours
    from app.models.site import Site


class Location(TimestampMixin, Base):
    __tablename__ = "location"

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    address_street: Mapped[str | None] = mapped_column(String, nullable=True)
    address_suburb: Mapped[str | None] = mapped_column(String, nullable=True)
    address_state: Mapped[str | None] = mapped_column(String, nullable=True)
    address_postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Contact channel: list of {"platform": str, "url": str}. Normalisation
    # happens at the form layer; the resolver shapes it for public render.
    social_links: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    position: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    # How opening hours render publicly: "detailed" (every day listed) or
    # "summary" (grouped by service period / collapsed day-runs).
    hours_display_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="detailed", server_default="detailed"
    )

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="locations")
    regular_hours: Mapped[list["RegularHours"]] = relationship(
        back_populates="location",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RegularHours.day_of_week, RegularHours.open_time",
    )
    hours_exceptions: Mapped[list["HoursException"]] = relationship(
        back_populates="location",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HoursException.start_date",
    )
