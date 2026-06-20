"""Site coordinator — owns the commit boundary for site writes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.site import Site
from app.schemas.site import SiteDetailsForm
from app.services import site_service


async def update_site_details(
    db: AsyncSession,
    auth_ctx: AuthContext,
    form: SiteDetailsForm,
) -> Site:
    """Validate and apply site detail edits, then commit.

    The service resolves the target site from auth_ctx.scoped_site_id only —
    no site_id is accepted from the caller.
    """
    site = await site_service.update_site_details(db, auth_ctx, form)
    await db.commit()
    return site


async def set_template(
    db: AsyncSession, auth_ctx: AuthContext, template: str
) -> Site:
    site = await site_service.set_template(db, auth_ctx, template)
    await db.commit()
    return site
