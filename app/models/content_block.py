import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, SmallInteger, String, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.photo import Photo
    from app.models.site import Site


class ContentBlock(TimestampMixin, Base):
    __tablename__ = "content_blocks"

    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_key: Mapped[str] = mapped_column(String, nullable=False)
    heading: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.photo_id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # Relationships
    site: Mapped["Site"] = relationship(back_populates="content_blocks")
    image: Mapped["Photo | None"] = relationship(lazy="raise")
