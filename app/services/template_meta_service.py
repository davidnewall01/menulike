"""Template metadata queries and mutations — DB-backed."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.template_meta import TagVocabulary, TemplateMeta, template_tag


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
    """Return (key, display_name) tuples for ALL templates.

    Used by admin authoring surfaces (create-showcase, appearance picker).
    Admins see and can use ALL templates, including unavailable/in-progress.
    """
    result = await db.execute(
        select(TemplateMeta.template_key, TemplateMeta.display_name)
        .order_by(TemplateMeta.display_name)
    )
    return [(row.template_key, row.display_name) for row in result.all()]


async def public_template_choices(
    db: AsyncSession,
) -> list[tuple[str, str]]:
    """Return (key, display_name) tuples for AVAILABLE templates only.

    For the PUBLIC picker (Pass 3b) — gates which templates are shown to
    prospects. Admin authoring uses available_template_choices() instead.

    PUBLICATION CASCADE GUARD (future): a showcase site should only be
    set is_published=true if its template is_available. Not enforced yet;
    enforce when showcase publishing + the public picker are built.
    """
    result = await db.execute(
        select(TemplateMeta.template_key, TemplateMeta.display_name)
        .where(TemplateMeta.is_available.is_(True))
        .order_by(TemplateMeta.display_name)
    )
    return [(row.template_key, row.display_name) for row in result.all()]


async def get_available_keys(db: AsyncSession) -> set[str]:
    """Return the set of ALL valid template keys (for set_template validation).

    Includes unavailable templates — an existing site on an unavailable
    template must still be able to re-save without breaking.
    """
    result = await db.execute(select(TemplateMeta.template_key))
    return {row[0] for row in result.all()}


# ---------------------------------------------------------------------------
# Template CRUD (admin editor)
# ---------------------------------------------------------------------------

async def update_template(
    db: AsyncSession, template_key: str,
    *, display_name: str, descriptor: str, is_available: bool,
    tag_ids: list[int],
) -> TemplateMeta | None:
    """Update a template's metadata + tags. Flush only."""
    tpl = await get_template_meta(db, template_key)
    if tpl is None:
        return None

    tpl.display_name = display_name
    tpl.descriptor = descriptor
    tpl.is_available = is_available

    # Replace tags: clear existing, add selected
    vocab_result = await db.execute(
        select(TagVocabulary).where(TagVocabulary.tag_id.in_(tag_ids))
    )
    tpl.tags = list(vocab_result.scalars().all())

    await db.flush()
    return tpl


# ---------------------------------------------------------------------------
# Tag vocabulary CRUD
# ---------------------------------------------------------------------------

async def list_vocabulary(db: AsyncSession) -> list[TagVocabulary]:
    """Return all vocabulary tags, ordered by value."""
    result = await db.execute(
        select(TagVocabulary).order_by(TagVocabulary.value)
    )
    return list(result.scalars().all())


async def add_tag(db: AsyncSession, value: str) -> TagVocabulary:
    """Add a new vocabulary tag. Flush only."""
    tag = TagVocabulary(value=value.strip().lower())
    db.add(tag)
    await db.flush()
    return tag


async def rename_tag(db: AsyncSession, tag_id: int, new_value: str) -> TagVocabulary | None:
    """Rename a vocabulary tag. Flush only."""
    result = await db.execute(
        select(TagVocabulary).where(TagVocabulary.tag_id == tag_id)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        return None
    tag.value = new_value.strip().lower()
    await db.flush()
    return tag


async def delete_tag(db: AsyncSession, tag_id: int) -> bool:
    """Delete a vocabulary tag. CASCADE removes template_tag joins. Flush only."""
    result = await db.execute(
        select(TagVocabulary).where(TagVocabulary.tag_id == tag_id)
    )
    tag = result.scalar_one_or_none()
    if tag is None:
        return False
    await db.delete(tag)
    await db.flush()
    return True


async def count_tag_usage(db: AsyncSession, tag_id: int) -> int:
    """Count how many templates use this tag (for delete warnings)."""
    from sqlalchemy import func
    result = await db.execute(
        select(func.count()).select_from(template_tag).where(
            template_tag.c.tag_id == tag_id
        )
    )
    return result.scalar() or 0
