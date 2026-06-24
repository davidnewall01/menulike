import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.location import Location
    from app.models.site import Site


class HoursException(TimestampMixin, Base):
    __tablename__ = "hours_exceptions"

    hours_exception_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("location.location_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    special_hours: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # [{open: "HH:MM", close: "HH:MM"}, ...]
    label: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="hours_exceptions")
    location: Mapped["Location | None"] = relationship(back_populates="hours_exceptions")
