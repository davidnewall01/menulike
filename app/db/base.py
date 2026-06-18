"""Declarative base and shared model mixins (SQLAlchemy 2.0 typed style).

PK convention (established here, applied when real models land next):
    No generic `id` lives on Base — that is deliberate. Each model declares its
    own per-entity-named UUID primary key so foreign keys read self-documenting
    (e.g. `menu_id`, `section_id`). The standard shape is:

        import uuid
        from sqlalchemy import UUID
        ...
        menu_id: Mapped[uuid.UUID] = mapped_column(
            UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
        )

A generic `id` on Base would defeat the named-PK pattern, so we don't add one.
"""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Adds DB-managed created_at / updated_at to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
