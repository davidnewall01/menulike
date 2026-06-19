"""Image-role assignments — scoped to the owner's site (admin) or by site_id (public)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth.context import AuthContext
from app.models.photo import Photo
from app.models.site_image_role import ALLOWED_ROLES, SiteImageRole
from app.services.exceptions import InvalidRole, NoSiteInScope, PhotoNotFound
from app.services import photo_service


# ---------------------------------------------------------------------------
# Admin reads (scoped via auth_ctx)
# ---------------------------------------------------------------------------

async def list_roles(
    db: AsyncSession, auth_ctx: AuthContext
) -> list[SiteImageRole]:
    """All role assignments for the owner's site, with photos eager-loaded."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()

    result = await db.execute(
        select(SiteImageRole)
        .options(joinedload(SiteImageRole.photo))
        .where(SiteImageRole.site_id == auth_ctx.scoped_site_id)
        .order_by(SiteImageRole.role, SiteImageRole.position)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Admin writes (flush only — coordinator commits)
# ---------------------------------------------------------------------------

async def assign(
    db: AsyncSession, auth_ctx: AuthContext,
    role: str, photo_id: uuid.UUID,
) -> SiteImageRole:
    """Assign a photo to a role. Single-assign: replaces any existing row for that role.

    Validates:
      - role is in ALLOWED_ROLES
      - photo belongs to the scoped site (via get_owner_photo IDOR gate)
    """
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    if role not in ALLOWED_ROLES:
        raise InvalidRole(f"Unknown role '{role}'. Allowed: {sorted(ALLOWED_ROLES)}")

    # IDOR gate: photo must belong to the owner's site
    await photo_service.get_owner_photo(db, auth_ctx, photo_id)

    # Single-assign: delete existing row(s) for this role on this site
    await db.execute(
        delete(SiteImageRole).where(
            SiteImageRole.site_id == auth_ctx.scoped_site_id,
            SiteImageRole.role == role,
        )
    )

    assignment = SiteImageRole(
        site_id=auth_ctx.scoped_site_id,
        role=role,
        photo_id=photo_id,
        position=0,
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def clear(
    db: AsyncSession, auth_ctx: AuthContext, role: str
) -> None:
    """Remove all assignments for a role on the owner's site."""
    if auth_ctx.scoped_site_id is None:
        raise NoSiteInScope()
    if role not in ALLOWED_ROLES:
        raise InvalidRole(f"Unknown role '{role}'. Allowed: {sorted(ALLOWED_ROLES)}")

    await db.execute(
        delete(SiteImageRole).where(
            SiteImageRole.site_id == auth_ctx.scoped_site_id,
            SiteImageRole.role == role,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Public loader (by site_id — tenant already trusted via Host)
# ---------------------------------------------------------------------------

async def load_role_images(
    db: AsyncSession, site_id: uuid.UUID
) -> dict[str, list[Photo]]:
    """Load all role assignments for a site, returning {role: [Photo, ...]}.

    Public-only loader: site_id comes from the already-trusted tenant resolution.
    Do NOT use this on the admin side — admin ops must go through auth_ctx paths.
    """
    result = await db.execute(
        select(SiteImageRole)
        .options(joinedload(SiteImageRole.photo))
        .where(SiteImageRole.site_id == site_id)
        .order_by(SiteImageRole.role, SiteImageRole.position)
    )
    roles: dict[str, list[Photo]] = {}
    for assignment in result.scalars().all():
        roles.setdefault(assignment.role, []).append(assignment.photo)
    return roles
