import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UUID, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.photo import Photo
    from app.models.site import Site

ALLOWED_ROLES = {"feature_images", "gallery", "logo"}


class SiteImageRole(TimestampMixin, Base):
    __tablename__ = "site_image_roles"
    __table_args__ = (
        UniqueConstraint("site_id", "role", "position", name="uq_site_role_position"),
    )

    site_image_role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.photo_id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="image_roles")
    photo: Mapped["Photo"] = relationship()
