import uuid
from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, SmallInteger, Time, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.site import Site


class RegularHours(TimestampMixin, Base):
    __tablename__ = "regular_hours"

    regular_hours_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(
        SmallInteger, nullable=False
    )  # 0=Mon .. 6=Sun
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="regular_hours")
