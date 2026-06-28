"""Template metadata queries — DB-backed, replaces the old TEMPLATE_CATALOG dict."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.template_meta import TemplateMeta


async def get_template_meta(
    db: AsyncSession, template_key: str,
) -> TemplateMeta | None:
    """Return the metadata for a single template, or None if unknown."""
    result = await db.execute(
        select(TemplateMeta)
        .options(selectinload(TemplateMeta.tags))
        .where(TemplateMeta.template_key == template_key)
    )
    return result.scalar_one_or_none()


async def list_templates(db: AsyncSession) -> list[TemplateMeta]:
    """Return all template metadata rows, ordered by display_name."""
    result = await db.execute(
        select(TemplateMeta)
        .options(selectinload(TemplateMeta.tags))
        .order_by(TemplateMeta.display_name)
    )
    return list(result.scalars().all())


async def available_template_choices(
    db: AsyncSession,
) -> list[tuple[str, str]]:
    """Return (key, display_name) tuples for template selectors."""
    result = await db.execute(
        select(TemplateMeta.template_key, TemplateMeta.display_name)
        .order_by(TemplateMeta.display_name)
    )
    return [(row.template_key, row.display_name) for row in result.all()]


async def get_available_keys(db: AsyncSession) -> set[str]:
    """Return the set of valid template keys (for validation)."""
    result = await db.execute(select(TemplateMeta.template_key))
    return {row[0] for row in result.all()}
