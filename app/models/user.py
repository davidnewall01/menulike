import enum
import uuid

from sqlalchemy import ForeignKey, String, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    internal_admin = "internal_admin"
    owner = "owner"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site.site_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
