"""Admin routes — login/logout, dashboard, details, menu/section/subsection/item/variant CRUD."""

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.auth.context import AuthContext
from app.auth.deps import SESSION_COOKIE, require_auth, require_csrf, require_csrf_owner_site, require_owner_site
from app.coordinators import content_block_coordinator, hours_coordinator, hours_exception_coordinator, image_role_coordinator, location_coordinator, menu_coordinator, photo_coordinator, site_coordinator
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import SESSION_LIFETIME, encode_session
from app.db.session import get_db
from app.models.site import Site
from app.schemas.extraction import ExtractedMenu
from app.schemas.menu import ItemForm, MenuForm, SectionForm, SubsectionForm, VariantForm, parse_extras
from app.schemas.site import SiteDetailsForm
from app.services import auth_service, content_block_service, hours_exception_service, hours_service, image_role_service, location_service, menu_extraction_service, menu_service, photo_service, site_service
from app.services.hours_service import HoursRangeNotFound, InvalidHoursLabel
from app.services.location_service import InvalidHoursDisplayMode
from app.services.hours_exception_service import HoursExceptionNotFound, InvalidDateRange
from app.services.storage import public_url as storage_public_url
from app.services.exceptions import (
    CannotDeleteLastLocation,
    ContentBlockNotFound,
    EmptyBlock,
    InvalidImage,
    InvalidRole,
    InvalidTemplate,
    ItemNotFound,
    LocationNotFound,
    MenuNotFound,
    NoSiteInScope,
    PhotoNotFound,
    ReorderMismatch,
    SectionNotFound,
    SiteNotFound,
    SubsectionNotFound,
    VariantNotFound,
)
from app.services.menu_extraction_service import (
    ExtractionFailed,
    ExtractionNotConfigured,
    InvalidPDF,
)
from app.services.storage import StorageNotConfigured
from app.services import template_meta_service
from app.web.template_resolver import get_feature_image_mode, page_path_safe, resolve_template

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
# Current year for footer copyright — evaluated per render, never hardcoded.
# Preview renders crema templates through this env (public.py has its own copy).
templates.env.globals["current_year"] = lambda: date.today().year

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Render helper — bakes csrf_token into every admin template context
# ---------------------------------------------------------------------------

def _render(
    request: Request,
    template: str,
    auth: AuthContext | None = None,
    *,
    status_code: int = 200,
    **context,
) -> Response:
    """Build a TemplateResponse with csrf_token automatically included.

    All admin renders go through this so the token is never forgotten.
    For pre-auth pages (login), pass auth=None and no token is generated.
    """
    ctx: dict = {"request": request, **context}
    if auth is not None:
        ctx["csrf_token"] = generate_csrf_token(auth)
        ctx["_auth"] = auth  # For nav indicator (acting-as, role checks)
    return templates.TemplateResponse(template, ctx, status_code=status_code)


# ---------------------------------------------------------------------------
# Auth (login / logout)
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render(request, "admin/login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Normalise email to match signup behaviour
    email = email.strip().lower()

    user = await auth_service.authenticate_user(db, email, password)

    if user is None:
        return _render(request, "admin/login.html", status_code=401, error="Invalid email or password")

    # Role-based post-login routing
    if user.role == "internal_admin":
        redirect_url = "/admin/"
    elif user.site_id is None:
        redirect_url = "/setup/restaurant"
    else:
        redirect_url = "/admin/"

    token = encode_session(user.user_id)
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
    )
    return response


@router.post("/logout")
async def logout(auth: AuthContext = Depends(require_csrf)):
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return response


# ---------------------------------------------------------------------------
# Concierge: act-as mechanism (admin-only)
# ---------------------------------------------------------------------------

from app.core.security import ACT_AS_COOKIE, ACT_AS_LIFETIME, encode_act_as


@router.post("/act-as/clear", response_class=HTMLResponse)
async def act_as_clear(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
):
    """Admin: drop the acting scope, back to no-scope picker."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    response = RedirectResponse(url="/admin/", status_code=303)
    response.delete_cookie(key=ACT_AS_COOKIE, path="/")
    return response


@router.post("/act-as/{site_id}", response_class=HTMLResponse)
async def act_as_site(
    request: Request,
    site_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Admin: scope into a target site for editing. SHORT-LIVED cookie."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    # Validate site exists
    result = await db.execute(
        select(Site).where(Site.site_id == site_id)
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    token = encode_act_as(site_id)
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key=ACT_AS_COOKIE,
        value=token,
        max_age=int(ACT_AS_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/showcase/create", response_class=HTMLResponse)
async def create_showcase(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Admin: create an orphan showcase site."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    name = form_data.get("restaurant_name", "").strip()
    slug = form_data.get("slug", "").strip()
    template = form_data.get("template", "linen").strip()

    if not name or not slug:
        raise HTTPException(status_code=400, detail="Name and slug required")

    # Check slug uniqueness before creating
    existing = await db.execute(select(Site).where(Site.slug == slug))
    if existing.scalar_one_or_none() is not None:
        all_sites = await site_service.list_all_sites(db)
        return _render(
            request, "admin/dashboard_admin.html", auth,
            email=auth.email, role=auth.role, is_internal_admin=True,
            customer_sites=[s for s in all_sites if not s.is_showcase],
            showcase_sites=[s for s in all_sites if s.is_showcase],
            storage_url=storage_public_url,
            available_templates=await template_meta_service.available_template_choices(db),
            showcase_error=f"A site with slug \"{slug}\" already exists. Choose a different slug.",
        )

    from app.services.site_service import create_showcase_site
    await create_showcase_site(db, name, slug, template)
    await db.commit()

    return RedirectResponse(url="/admin/?tab=showcase", status_code=303)


@router.post("/showcase/thumbnail", response_class=HTMLResponse)
async def upload_showcase_thumbnail(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Admin: upload a marketing thumbnail for a showcase site.

    Stores directly to S3 — does NOT go through photo_service (it's a
    marketing screenshot, not a restaurant photo).
    """
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    site_id_str = form_data.get("site_id", "")
    file = form_data.get("file")

    try:
        target_site_id = uuid.UUID(site_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid site_id")

    if not file or not hasattr(file, "read"):
        return RedirectResponse(url="/admin/?tab=showcase", status_code=303)

    file_data = await file.read()
    if len(file_data) == 0:
        return RedirectResponse(url="/admin/?tab=showcase", status_code=303)

    content_type = getattr(file, "content_type", "image/png") or "image/png"

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    ext = ext_map.get(content_type, "png")

    # Validate site exists
    result = await db.execute(select(Site).where(Site.site_id == target_site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    # Upload to S3 (marketing path, not photo library)
    from app.services import storage
    key = f"sites/{target_site_id}/thumbnails/{uuid.uuid4()}.{ext}"
    await storage.upload(file_data, key, content_type)

    site.thumbnail_key = key
    await db.commit()

    # HTMX request (from modal) → return updated modal; normal POST → redirect
    if request.headers.get("HX-Request"):
        return _render(
            request, "admin/_showcase_settings_modal.html", auth,
            site=site, storage_url=storage_public_url,
        )
    return RedirectResponse(url="/admin/?tab=showcase", status_code=303)


@router.post("/showcase/thumbnail/delete", response_class=HTMLResponse)
async def delete_showcase_thumbnail(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Admin: remove the thumbnail from a showcase site."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    site_id_str = form_data.get("site_id", "")
    try:
        target_site_id = uuid.UUID(site_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid site_id")

    result = await db.execute(select(Site).where(Site.site_id == target_site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    if site.thumbnail_key:
        from app.services import storage
        await storage.delete(site.thumbnail_key)
        site.thumbnail_key = None
        await db.commit()

    if request.headers.get("HX-Request"):
        return _render(
            request, "admin/_showcase_settings_modal.html", auth,
            site=site, storage_url=storage_public_url,
        )
    return RedirectResponse(url="/admin/?tab=showcase", status_code=303)


@router.get("/showcase/{site_id}/settings-modal", response_class=HTMLResponse)
async def showcase_settings_modal(
    request: Request,
    site_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Return the showcase settings modal partial (HTMX-loaded)."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    result = await db.execute(select(Site).where(Site.site_id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return _render(
        request, "admin/_showcase_settings_modal.html", auth,
        site=site, storage_url=storage_public_url,
    )


@router.post("/showcase/{site_id}/update", response_class=HTMLResponse)
async def showcase_update(
    request: Request,
    site_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Update showcase metadata (position, published)."""
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    result = await db.execute(select(Site).where(Site.site_id == site_id))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    form_data = await request.form()
    pos_str = form_data.get("showcase_position", "").strip()
    site.showcase_position = int(pos_str) if pos_str else None

    want_published = form_data.get("is_published") == "on"
    if want_published and not site.is_published:
        # Check publish guard (template availability)
        from app.content.resolver import resolve_site_view
        full_site = await site_service.get_site_by_id_public(db, site.site_id)
        if full_site is None:
            full_site = site
        role_images = await image_role_service.load_role_images(db, site.site_id)
        site_view = resolve_site_view(
            site=full_site, role_images=role_images, mode="public",
            storage_url=storage_public_url,
        )
        tpl_meta = await template_meta_service.get_template_meta(db, site.template)
        eligible, reasons = site_service.can_publish(
            site_view, template_available=tpl_meta.is_available if tpl_meta else False,
        )
        if not eligible:
            return _render(
                request, "admin/_showcase_settings_modal.html", auth,
                site=site, storage_url=storage_public_url,
                publish_error="Cannot publish: " + "; ".join(reasons),
            )
    site.is_published = want_published
    await db.commit()

    # HTMX: redirect via header (modal closes, page reloads to showcase tab)
    if request.headers.get("HX-Request"):
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/admin/?tab=showcase"
        return response
    return RedirectResponse(url="/admin/?tab=showcase", status_code=303)


# ---------------------------------------------------------------------------
# Template catalog editor (admin-only, platform-level)
# ---------------------------------------------------------------------------

from app.web.template_resolver import FEATURE_IMAGE_MODE


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    templates_list = await template_meta_service.list_templates(db)
    vocabulary = await template_meta_service.list_vocabulary(db)
    return _render(
        request, "admin/templates.html", auth,
        templates_list=templates_list,
        vocabulary=vocabulary,
        feature_image_modes=FEATURE_IMAGE_MODE,
    )


@router.get("/templates/vocab-modal", response_class=HTMLResponse)
async def vocab_modal(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    vocabulary = await template_meta_service.list_vocabulary(db)
    return _render(request, "admin/_vocab_modal.html", auth, vocabulary=vocabulary)


@router.get("/templates/{template_key}/edit-modal", response_class=HTMLResponse)
async def template_edit_modal(
    request: Request,
    template_key: str,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    tpl = await template_meta_service.get_template_meta(db, template_key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    vocabulary = await template_meta_service.list_vocabulary(db)
    return _render(
        request, "admin/_template_edit_modal.html", auth,
        tpl=tpl, vocabulary=vocabulary,
        feature_image_mode=FEATURE_IMAGE_MODE.get(template_key, "single"),
    )


@router.post("/templates/{template_key}/update", response_class=HTMLResponse)
async def templates_update(
    request: Request,
    template_key: str,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    display_name = form_data.get("display_name", "").strip()
    descriptor = form_data.get("descriptor", "").strip()
    is_available = form_data.get("is_available") == "on"
    tag_ids = [int(v) for v in form_data.getlist("tag_ids") if v.strip()]

    if not display_name or not descriptor:
        raise HTTPException(status_code=400, detail="Name and descriptor required")

    await template_meta_service.update_template(
        db, template_key,
        display_name=display_name, descriptor=descriptor,
        is_available=is_available, tag_ids=tag_ids,
    )
    await db.commit()

    return RedirectResponse(url="/admin/templates", status_code=303)


@router.post("/templates/vocab/add", response_class=HTMLResponse)
async def vocab_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    value = form_data.get("value", "").strip().lower()
    if not value:
        raise HTTPException(status_code=400, detail="Tag value required")

    try:
        await template_meta_service.add_tag(db, value)
        await db.commit()
    except Exception:
        await db.rollback()
        # Likely duplicate
    return RedirectResponse(url="/admin/templates", status_code=303)


@router.post("/templates/vocab/{tag_id}/rename", response_class=HTMLResponse)
async def vocab_rename(
    request: Request,
    tag_id: int,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    form_data = await request.form()
    new_value = form_data.get("value", "").strip().lower()
    if not new_value:
        raise HTTPException(status_code=400, detail="Tag value required")

    await template_meta_service.rename_tag(db, tag_id, new_value)
    await db.commit()
    return RedirectResponse(url="/admin/templates", status_code=303)


@router.post("/templates/vocab/{tag_id}/delete", response_class=HTMLResponse)
async def vocab_delete(
    request: Request,
    tag_id: int,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if not auth.is_internal_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    await template_meta_service.delete_tag(db, tag_id)
    await db.commit()
    return RedirectResponse(url="/admin/templates", status_code=303)


# ---------------------------------------------------------------------------
# Preview (draft-inclusive, real Linen templates, resolver-driven)
# ---------------------------------------------------------------------------

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_PREVIEW_CTX = {
    "render_mode": "preview",
    "nav_prefix": "/admin/preview",
}


async def _load_preview(db: AsyncSession, auth: AuthContext):
    """Load site + role_images for preview. Shared by all preview routes."""
    site = await site_service.get_owner_site_preview(db, auth)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    return site, role_images


@router.get("/preview", response_class=HTMLResponse)
async def preview_home(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's home page (real content + samples for gaps)."""
    from app.content.resolver import resolve_site_view

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    # Build hours context for scroll templates (e.g. Crema) that render
    # the Find Us section inline on the home page.
    from app.web.public import _build_hours_context
    return templates.TemplateResponse(
        page_path_safe(tpl, "home"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            "role_images": role_images,
            **_build_hours_context(site),
            **_PREVIEW_CTX,
        },
    )


@router.get("/preview/menu", response_class=HTMLResponse)
async def preview_menu(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's menu (including drafts)."""
    from app.content.resolver import resolve_site_view

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path_safe(tpl, "menu"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            **_PREVIEW_CTX,
        },
    )


@router.get("/preview/our-story", response_class=HTMLResponse)
async def preview_our_story(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's Our Story page."""
    from app.content.resolver import resolve_site_view

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path_safe(tpl, "our_story"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            **_PREVIEW_CTX,
        },
    )


@router.get("/preview/gallery", response_class=HTMLResponse)
async def preview_gallery(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's gallery."""
    from app.content.resolver import resolve_site_view

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path_safe(tpl, "gallery"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            **_PREVIEW_CTX,
        },
    )


@router.get("/preview/visit", response_class=HTMLResponse)
async def preview_visit(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's Visit page."""
    from app.content.resolver import resolve_site_view
    from app.web.public import _build_hours_context

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path_safe(tpl, "visit"),
        {
            "request": request,
            "site": site,
            "view": view,
            **_build_hours_context(site),
            "storage_url": storage_public_url,
            **_PREVIEW_CTX,
        },
    )


@router.get("/preview/events", response_class=HTMLResponse)
async def preview_events(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Preview the owner's Events / What's On page."""
    from app.content.resolver import resolve_site_view

    site, role_images = await _load_preview(db, auth)
    view = resolve_site_view(
        site=site, role_images=role_images, mode="preview",
        storage_url=storage_public_url,
    )
    tpl = resolve_template(site.template)
    return templates.TemplateResponse(
        page_path_safe(tpl, "events"),
        {
            "request": request,
            "site": site,
            "view": view,
            "storage_url": storage_public_url,
            **_PREVIEW_CTX,
        },
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    # Internal admin with no acting site: show site picker
    if auth.is_internal_admin and auth.scoped_site_id is None:
        all_sites = await site_service.list_all_sites(db)
        customer_sites = [s for s in all_sites if not s.is_showcase]
        showcase_sites = [s for s in all_sites if s.is_showcase]
        return _render(
            request, "admin/dashboard_admin.html", auth,
            email=auth.email,
            role=auth.role,
            is_internal_admin=True,
            customer_sites=customer_sites,
            showcase_sites=showcase_sites,
            storage_url=storage_public_url,
            available_templates=await template_meta_service.available_template_choices(db),
        )

    # Owner OR admin acting-as: tiled dashboard for the scoped site
    from app.content.resolver import resolve_site_view

    try:
        site = await site_service.get_owner_site_full(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    role_images = await image_role_service.load_role_images(db, site.site_id)
    site_view = resolve_site_view(site=site, role_images=role_images, mode="public", storage_url=storage_public_url)
    tpl_meta = await template_meta_service.get_template_meta(db, site.template)
    eligible, reasons = site_service.can_publish(
        site_view, template_available=tpl_meta.is_available if tpl_meta else False,
    )

    # Count areas made "yours" for the progress bar. Exclude events — it's a
    # deferred/optional section, so owners must be able to reach 100% without it.
    progress_areas = [v for k, v in site_view.items() if k != "events"]
    yours_count = sum(1 for area in progress_areas if area.status == "yours")

    # Photo library count for the "Your photos" tile
    photos = await photo_service.list_photos(db, auth)
    photo_count = len(photos)

    return _render(
        request, "admin/dashboard.html", auth,
        site=site,
        site_view=site_view,
        eligible=eligible,
        reasons=reasons,
        yours_count=yours_count,
        total_areas=len(progress_areas),
        photo_count=photo_count,
        platform_domain=settings.PLATFORM_BASE_DOMAIN,
    )


# ---------------------------------------------------------------------------
# Publish / Unpublish
# ---------------------------------------------------------------------------

@router.post("/publish", response_class=HTMLResponse)
async def publish_site(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Set the owner's site to published (go live).

    Checks eligibility via can_publish (reads the resolver — mode-independent).
    If not eligible, redirects back to dashboard (the dashboard will show reasons
    once tiles are built in Chunk 3).
    """
    from app.content.resolver import resolve_site_view

    site = await site_service.get_owner_site_full(db, auth)
    role_images = await image_role_service.load_role_images(db, site.site_id)
    site_view = resolve_site_view(site=site, role_images=role_images, mode="public", storage_url=storage_public_url)

    tpl_meta = await template_meta_service.get_template_meta(db, site.template)
    eligible, _reasons = site_service.can_publish(
        site_view, template_available=tpl_meta.is_available if tpl_meta else False,
    )
    if not eligible:
        return RedirectResponse(url="/admin/", status_code=303)

    await site_coordinator.publish(db, auth)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/unpublish", response_class=HTMLResponse)
async def unpublish_site(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Set the owner's site to unpublished (take offline).

    No eligibility check — an owner can always take their site offline.
    """
    await site_coordinator.unpublish(db, auth)
    return RedirectResponse(url="/admin/", status_code=303)


# ---------------------------------------------------------------------------
# Front page (tagline + hero + logo)
# ---------------------------------------------------------------------------

@router.get("/front-page", response_class=HTMLResponse)
async def front_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        site = await site_service.get_owner_site(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    mode = get_feature_image_mode(site.template)
    by_key = _roles_by_key(roles)
    by_key_list = _roles_list_by_key(roles)

    return _render(
        request, "admin/front_page.html", auth,
        site=site,
        roles=by_key,
        feature_image_mode=mode,
        feature_images_list=by_key_list.get("feature_images", []),
        storage_url=storage_public_url,
        **_IMAGE_ROLE_URLS,
    )


@router.post("/front-page", response_class=HTMLResponse)
async def front_page_save(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    tagline_raw = form_data.get("tagline", "")
    tagline = tagline_raw.strip() or None

    try:
        site = await site_coordinator.update_tagline(db, auth, tagline)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    mode = get_feature_image_mode(site.template)
    by_key = _roles_by_key(roles)
    by_key_list = _roles_list_by_key(roles)

    return _render(
        request, "admin/front_page.html", auth,
        site=site,
        roles=by_key,
        feature_image_mode=mode,
        feature_images_list=by_key_list.get("feature_images", []),
        storage_url=storage_public_url,
        saved=True,
        **_IMAGE_ROLE_URLS,
    )


# ---------------------------------------------------------------------------
# SEO (search listing)
# ---------------------------------------------------------------------------

@router.get("/seo", response_class=HTMLResponse)
async def seo_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from app.content.resolver import resolve_site_view

    try:
        site = await site_service.get_owner_site_full(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(site=site, role_images=role_images, mode="public", storage_url=storage_public_url)

    return _render(
        request, "admin/seo.html", auth,
        site=site, seo=view["seo"],
        platform_domain=settings.PLATFORM_BASE_DOMAIN,
    )


@router.post("/seo", response_class=HTMLResponse)
async def seo_save(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from app.content.resolver import resolve_site_view
    from app.schemas.site import SeoForm

    form_data = await request.form()
    form = SeoForm(**dict(form_data))

    try:
        site = await site_coordinator.update_seo(
            db, auth, form.meta_title, form.meta_description,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    role_images = await image_role_service.load_role_images(db, site.site_id)
    view = resolve_site_view(site=site, role_images=role_images, mode="public", storage_url=storage_public_url)

    return _render(
        request, "admin/seo.html", auth,
        site=site, seo=view["seo"],
        platform_domain=settings.PLATFORM_BASE_DOMAIN,
        saved=True,
    )


# ---------------------------------------------------------------------------
# Details editing
# ---------------------------------------------------------------------------

@router.get("/details", response_class=HTMLResponse)
async def details_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        site = await site_service.get_owner_site(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    return _render(request, "admin/details.html", auth, site=site)


@router.post("/details", response_class=HTMLResponse)
async def details_save(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()

    try:
        form = SiteDetailsForm(**dict(form_data))
    except ValidationError as exc:
        try:
            site = await site_service.get_owner_site(db, auth)
        except SiteNotFound:
            raise HTTPException(status_code=400, detail="Scoped site not found")
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_details_form.html", auth,
            site=site, errors=errors, saved=False,
        )

    try:
        site = await site_coordinator.update_site_details(db, auth, form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    return _render(
        request, "admin/_details_form.html", auth,
        site=site, saved=True, errors=None,
    )


# ---------------------------------------------------------------------------
# Menu CRUD
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Menu add — method chooser + PDF upload flow (shared extract logic)
# ---------------------------------------------------------------------------

@router.get("/menu/add", response_class=HTMLResponse)
async def menu_add(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
):
    """Method chooser: upload PDF (primary) or build by hand (secondary)."""
    return _render(request, "admin/menu_add.html", auth)


@router.post("/menu/upload", response_class=HTMLResponse)
async def menu_upload(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
):
    """Accept a PDF upload, extract via Claude, render summary for confirmation."""
    import json as _json

    form_data = await request.form()
    upload = form_data.get("file")
    display_title = (form_data.get("display_title") or "").strip() or None

    if not upload or not hasattr(upload, "read"):
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["Please select a PDF file."],
            status_code=400,
        )

    content_type = getattr(upload, "content_type", "")
    if content_type != "application/pdf":
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["That doesn't look like a PDF. Please upload a PDF of your menu."],
            status_code=400,
        )

    file_data = await upload.read()

    try:
        extracted = await menu_extraction_service.extract_from_pdf(file_data)
    except menu_extraction_service.ExtractionNotConfigured:
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["Menu reading is temporarily unavailable. Please try again later or build your menu by hand."],
            status_code=503,
        )
    except menu_extraction_service.InvalidPDF as exc:
        return _render(
            request, "admin/menu_add.html", auth,
            errors=[f"We couldn't read that file. {exc} Try another file."],
            status_code=400,
        )
    except menu_extraction_service.ExtractionFailed:
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["We couldn't make sense of that menu. Try a clearer PDF or build your menu by hand."],
            status_code=422,
        )

    dish_count = menu_extraction_service.count_dishes(extracted)
    if len(extracted.sections) == 0 or dish_count == 0:
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["We couldn't find any menu items in that file. Try a different PDF."],
            status_code=422,
        )

    extraction_json = _json.dumps(extracted.model_dump())
    summary = menu_extraction_service.build_summary_context(extracted)
    return _render(
        request, "admin/menu_upload_summary.html", auth,
        extraction_json=extraction_json,
        display_title=display_title or "",
        **summary,
    )


@router.post("/menu/upload/confirm", response_class=HTMLResponse)
async def menu_upload_confirm(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Commit the extracted menu as a new draft, redirect to menu list."""
    import json as _json

    form_data = await request.form()
    raw = form_data.get("extraction_json", "")
    display_title = (form_data.get("display_title") or "").strip() or None

    try:
        data = _json.loads(raw)
        extracted = ExtractedMenu.model_validate(data)
    except Exception:
        return _render(
            request, "admin/menu_add.html", auth,
            errors=["Something went wrong. Please try uploading your menu again."],
            status_code=400,
        )

    try:
        await menu_coordinator.commit_extracted_menu(db, auth, extracted, display_title=display_title)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return RedirectResponse(url="/admin/menu", status_code=303)


# ---------------------------------------------------------------------------
# Menu list + manual create
# ---------------------------------------------------------------------------

@router.get("/menu", response_class=HTMLResponse)
async def menu_list(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/menu_list.html", auth,
            menus=[], is_internal_admin=True,
        )

    try:
        menus = await menu_service.list_owner_menus(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/menu_list.html", auth,
        menus=menus, is_internal_admin=False,
    )


@router.post("/menu", response_class=HTMLResponse)
async def menu_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()

    try:
        form = MenuForm(**dict(form_data))
    except ValidationError as exc:
        try:
            menus = await menu_service.list_owner_menus(db, auth)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        # Re-render the list page with errors (the create form is at the bottom)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/menu_list.html", auth,
            menus=menus, is_internal_admin=False, errors=errors,
        )

    try:
        await menu_coordinator.create_menu(db, auth, form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return RedirectResponse(url="/admin/menu", status_code=303)


@router.post("/menu/reorder")
async def reorder_menus(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    try:
        ordered = _parse_ordered_ids(form_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ids")

    try:
        await menu_coordinator.reorder_menus(db, auth, ordered)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ReorderMismatch:
        raise HTTPException(status_code=400, detail="Id set mismatch")

    return Response(status_code=204)


@router.post("/menu/{menu_id}/publish", response_class=HTMLResponse)
async def menu_publish(
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await menu_coordinator.set_menu_published(db, auth, menu_id, True)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.post("/menu/{menu_id}/unpublish", response_class=HTMLResponse)
async def menu_unpublish(
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await menu_coordinator.set_menu_published(db, auth, menu_id, False)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.get("/menu/{menu_id}", response_class=HTMLResponse)
async def menu_canvas(
    request: Request,
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        menu = await menu_service.get_owner_menu_with_tree(db, auth, menu_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")

    return _render(request, "admin/menu_canvas.html", auth, menu=menu, storage_url=storage_public_url)


@router.post("/menu/{menu_id}", response_class=HTMLResponse)
async def menu_update_or_delete(
    request: Request,
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")

    if action == "delete":
        try:
            await menu_coordinator.delete_menu(db, auth, menu_id)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        except MenuNotFound:
            raise HTTPException(status_code=404, detail="Menu not found")

        return RedirectResponse(url="/admin/menu", status_code=303)

    # update
    try:
        form = MenuForm(**dict(form_data))
    except ValidationError as exc:
        try:
            menu = await menu_service.get_owner_menu(db, auth, menu_id)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        except MenuNotFound:
            raise HTTPException(status_code=404, detail="Menu not found")
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_menu_edit_form.html", auth,
            menu=menu, saved=False, errors=errors, deleted=False,
        )

    try:
        menu = await menu_coordinator.update_menu(db, auth, menu_id, form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")

    return _render(
        request, "admin/_menu_edit_form.html", auth,
        menu=menu, saved=True, errors=None, deleted=False,
    )


# ---------------------------------------------------------------------------
# Case manager
# ---------------------------------------------------------------------------

@router.get("/menu/{menu_id}/case", response_class=HTMLResponse)
async def case_manager_modal(
    request: Request,
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Return the case manager modal with a sample from the menu's real data."""
    try:
        menu = await menu_service.get_owner_menu_with_tree(db, auth, menu_id)
    except (NoSiteInScope, MenuNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Fixed sample — always the same so the preview is clean and predictable
    sample = {
        "section_name": "Pizza",
        "section_description": "Hand built and beautiful",
        "section_note": "Half and half available",
        "subsection_name": "Pizza Bianca",
        "subsection_description": "Rich, creamy sauce",
        "item_name": "Prosciutto Crudo E Rucola",
        "item_description": "Fresh Rocket & Flaky Parmesan",
        "dietary_tags": "VEG",
        "variant_label": "Large",
    }

    from app.utils.case_transform import TRANSFORM_LABELS
    options = list(TRANSFORM_LABELS.items())

    return _render(
        request, "admin/_case_manager.html", auth,
        menu=menu, sample=sample, options=options,
    )


@router.post("/menu/{menu_id}/case", response_class=HTMLResponse)
async def case_manager_apply(
    request: Request,
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Apply case transforms to all text in the menu."""
    form_data = await request.form()

    field_names = [
        "section_name", "section_description", "section_note",
        "subsection_name", "subsection_description",
        "item_name", "item_description", "dietary_tags", "variant_label",
    ]
    kwargs = {}
    for field in field_names:
        val = form_data.get(field, "none")
        if val not in ("none", "title", "sentence", "upper", "lower"):
            val = "none"
        kwargs[field] = val

    try:
        await menu_coordinator.apply_case_transforms(db, auth, menu_id, **kwargs)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


# ---------------------------------------------------------------------------
# Menu entity photo picker (section / subsection / item)
# ---------------------------------------------------------------------------

_PHOTO_ENTITY_LOADERS = {
    "section": ("section_id", menu_service.get_owner_section),
    "subsection": ("subsection_id", menu_service.get_owner_subsection),
    "item": ("menu_item_id", menu_service.get_owner_item),
}


@router.get("/{entity_type}/{entity_id}/photo-picker", response_class=HTMLResponse)
async def photo_picker_modal(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    menu_id: uuid.UUID | None = None,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if entity_type not in _PHOTO_ENTITY_LOADERS:
        raise HTTPException(status_code=400, detail="Invalid entity type")

    pk_attr, loader = _PHOTO_ENTITY_LOADERS[entity_type]
    try:
        entity = await loader(db, auth, entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    photos = await photo_service.list_photos(db, auth)

    return _render(
        request, "admin/_photo_picker.html", auth,
        photos=photos,
        entity_type=entity_type,
        entity_id=entity_id,
        menu_id=menu_id,
        current_photo_id=entity.photo_id,
        storage_url=storage_public_url,
    )


@router.post("/{entity_type}/{entity_id}/photo", response_class=HTMLResponse)
async def photo_set(
    request: Request,
    entity_type: str,
    entity_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if entity_type not in _PHOTO_ENTITY_LOADERS:
        raise HTTPException(status_code=400, detail="Invalid entity type")

    form_data = await request.form()
    photo_id_raw = form_data.get("photo_id", "")
    menu_id = form_data.get("menu_id")

    pk_attr, loader = _PHOTO_ENTITY_LOADERS[entity_type]
    try:
        entity = await loader(db, auth, entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    # Empty string = remove photo
    if photo_id_raw:
        # Validate the photo belongs to the owner's site
        photo = await photo_service.get_owner_photo(db, auth, uuid.UUID(photo_id_raw))
        entity.photo_id = photo.photo_id
    else:
        entity.photo_id = None

    await db.commit()
    db.expire_all()

    # For items, return the re-rendered item row (HTMX swap, no page reload)
    if entity_type == "item":
        item = await menu_service.get_owner_item_with_variants(db, auth, entity_id)
        return _render(
            request, "admin/_item_row.html", auth,
            item=item, menu_id=menu_id, storage_url=storage_public_url,
        )

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


# ---------------------------------------------------------------------------
# Item CRUD
# ---------------------------------------------------------------------------

def _not_found(exc):
    """Map domain not-found exceptions to HTTP status codes."""
    if isinstance(exc, NoSiteInScope):
        raise HTTPException(status_code=400, detail="No site in scope")
    raise HTTPException(status_code=404, detail="Not found")


@router.post("/item", response_class=HTMLResponse)
async def item_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    subsection_id = form_data.get("subsection_id")
    menu_id = form_data.get("menu_id")

    extras = parse_extras(
        form_data.getlist("extras_label"),
        form_data.getlist("extras_price"),
    )

    try:
        form = ItemForm(**dict(form_data))
    except ValidationError:
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        item = await menu_coordinator.create_item(db, auth, uuid.UUID(subsection_id), form, extras=extras)
    except (NoSiteInScope, SubsectionNotFound) as exc:
        _not_found(exc)

    return RedirectResponse(
        url=f"/admin/menu/{menu_id}?expand_item={item.menu_item_id}",
        status_code=303,
    )


@router.get("/item/{item_id}", response_class=HTMLResponse)
async def item_display(
    request: Request,
    item_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
    menu_id: uuid.UUID | None = None,
):
    """Return the item display partial (for cancel-edit swap)."""
    try:
        item = await menu_service.get_owner_item_with_variants(db, auth, item_id)
    except (NoSiteInScope, ItemNotFound) as exc:
        _not_found(exc)

    return _render(request, "admin/_item_row.html", auth, item=item, menu_id=menu_id, storage_url=storage_public_url)


@router.get("/item/{item_id}/edit", response_class=HTMLResponse)
async def item_edit_form(
    request: Request,
    item_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
    menu_id: uuid.UUID | None = None,
):
    """Return the item edit form partial."""
    try:
        item = await menu_service.get_owner_item_with_variants(db, auth, item_id)
    except (NoSiteInScope, ItemNotFound) as exc:
        _not_found(exc)

    return _render(request, "admin/_item_edit_form.html", auth, item=item, menu_id=menu_id)


@router.post("/item/{item_id}", response_class=HTMLResponse)
async def item_update_or_delete(
    request: Request,
    item_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")

    if action == "delete":
        try:
            await menu_coordinator.delete_item(db, auth, item_id)
        except (NoSiteInScope, ItemNotFound) as exc:
            _not_found(exc)
        return Response(status_code=200)

    extras = parse_extras(
        form_data.getlist("extras_label"),
        form_data.getlist("extras_price"),
    )

    try:
        form = ItemForm(**dict(form_data))
    except ValidationError as exc:
        try:
            item = await menu_service.get_owner_item_with_variants(db, auth, item_id)
        except (NoSiteInScope, ItemNotFound) as exc2:
            _not_found(exc2)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_item_edit_form.html", auth,
            item=item, errors=errors,
        )

    try:
        item = await menu_coordinator.update_item(db, auth, item_id, form, extras=extras)
    except (NoSiteInScope, ItemNotFound) as exc:
        _not_found(exc)

    # Reload with variants for the display partial
    item = await menu_service.get_owner_item_with_variants(db, auth, item_id)
    menu_id = form_data.get("menu_id")
    return _render(request, "admin/_item_row.html", auth, item=item, menu_id=menu_id, storage_url=storage_public_url)


# ---------------------------------------------------------------------------
# Variant CRUD
# ---------------------------------------------------------------------------

@router.post("/variant", response_class=HTMLResponse)
async def variant_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    item_id = form_data.get("item_id")
    menu_id = form_data.get("menu_id")

    try:
        form = VariantForm(**dict(form_data))
    except ValidationError:
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        await menu_coordinator.create_variant(db, auth, uuid.UUID(item_id), form)
    except (NoSiteInScope, ItemNotFound) as exc:
        _not_found(exc)

    # Re-render the item row in-place (HTMX swap)
    item = await menu_service.get_owner_item_with_variants(db, auth, uuid.UUID(item_id))
    return _render(request, "admin/_item_row.html", auth, item=item, menu_id=menu_id, storage_url=storage_public_url)


@router.get("/variant/{variant_id}", response_class=HTMLResponse)
async def variant_display(
    request: Request,
    variant_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Return the variant display partial (for cancel-edit swap)."""
    try:
        variant = await menu_service.get_owner_variant(db, auth, variant_id)
    except (NoSiteInScope, VariantNotFound) as exc:
        _not_found(exc)

    return _render(request, "admin/_variant_row.html", auth, variant=variant)


@router.get("/variant/{variant_id}/edit", response_class=HTMLResponse)
async def variant_edit_form(
    request: Request,
    variant_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Return the variant edit form partial."""
    try:
        variant = await menu_service.get_owner_variant(db, auth, variant_id)
    except (NoSiteInScope, VariantNotFound) as exc:
        _not_found(exc)

    return _render(request, "admin/_variant_edit_form.html", auth, variant=variant)


@router.post("/variant/{variant_id}", response_class=HTMLResponse)
async def variant_update_or_delete(
    request: Request,
    variant_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")

    if action == "delete":
        try:
            await menu_coordinator.delete_variant(db, auth, variant_id)
        except (NoSiteInScope, VariantNotFound) as exc:
            _not_found(exc)
        return Response(status_code=200)

    try:
        form = VariantForm(**dict(form_data))
    except ValidationError as exc:
        try:
            variant = await menu_service.get_owner_variant(db, auth, variant_id)
        except (NoSiteInScope, VariantNotFound) as exc2:
            _not_found(exc2)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_variant_edit_form.html", auth,
            variant=variant, errors=errors,
        )

    try:
        variant = await menu_coordinator.update_variant(db, auth, variant_id, form)
    except (NoSiteInScope, VariantNotFound) as exc:
        _not_found(exc)

    return _render(request, "admin/_variant_row.html", auth, variant=variant)


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------

@router.post("/section", response_class=HTMLResponse)
async def section_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    menu_id = form_data.get("menu_id")

    try:
        form = SectionForm(**dict(form_data))
    except ValidationError:
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        await menu_coordinator.create_section(db, auth, uuid.UUID(menu_id), form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


@router.get("/section/{section_id}/edit", response_class=HTMLResponse)
async def section_edit_form(
    request: Request,
    section_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
    menu_id: uuid.UUID | None = None,
):
    try:
        section = await menu_service.get_owner_section(db, auth, section_id)
        menus = await menu_service.list_owner_menus(db, auth)
    except (NoSiteInScope, SectionNotFound) as exc:
        _not_found(exc)

    # Other menus the section could be moved to
    other_menus = [m for m in menus if m.menu_id != menu_id]

    return _render(
        request, "admin/_section_edit_form.html", auth,
        section=section, menu_id=menu_id, other_menus=other_menus,
        storage_url=storage_public_url,
    )


@router.post("/section/{section_id}", response_class=HTMLResponse)
async def section_update_or_delete(
    request: Request,
    section_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")
    menu_id = form_data.get("menu_id")

    if action == "delete":
        try:
            await menu_coordinator.delete_section(db, auth, section_id)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        except SectionNotFound:
            raise HTTPException(status_code=404, detail="Section not found")
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        form = SectionForm(**dict(form_data))
    except ValidationError as exc:
        try:
            section = await menu_service.get_owner_section(db, auth, section_id)
        except (NoSiteInScope, SectionNotFound) as exc2:
            _not_found(exc2)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_section_edit_form.html", auth,
            section=section, menu_id=menu_id, errors=errors,
            storage_url=storage_public_url,
        )

    try:
        section = await menu_coordinator.update_section(db, auth, section_id, form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SectionNotFound:
        raise HTTPException(status_code=404, detail="Section not found")

    return _render(
        request, "admin/_section_header.html", auth,
        section=section, menu_id=menu_id,
    )


@router.post("/section/{section_id}/move", response_class=HTMLResponse)
async def section_move(
    request: Request,
    section_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    target_menu_id_raw = form_data.get("target_menu_id", "")
    source_menu_id = form_data.get("menu_id")

    # "_new" means create a new menu; otherwise it's an existing menu UUID
    if target_menu_id_raw == "_new":
        target_menu_id = None
    else:
        try:
            target_menu_id = uuid.UUID(target_menu_id_raw)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid target menu")

    try:
        section, target_menu = await menu_coordinator.move_section(
            db, auth, section_id, target_menu_id,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except (SectionNotFound, MenuNotFound):
        raise HTTPException(status_code=404, detail="Not found")

    return RedirectResponse(
        url=f"/admin/menu/{source_menu_id}", status_code=303,
    )


# ---------------------------------------------------------------------------
# Footer block CRUD
# ---------------------------------------------------------------------------


def _parse_entries_text(text: str) -> list[dict]:
    """Parse entries from textarea — one per line, 'label | description' or just text."""
    entries = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = line.split("|", 1)
            entries.append({"label": parts[0].strip(), "description": parts[1].strip()})
        else:
            entries.append({"label": None, "description": line})
    return entries


@router.post("/footer-block", response_class=HTMLResponse)
async def footer_block_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    menu_id = form_data.get("menu_id")
    block_type = form_data.get("block_type", "info")
    title = (form_data.get("title") or "").strip() or None
    entries = _parse_entries_text(form_data.get("entries_text", ""))

    try:
        await menu_coordinator.create_footer_block(
            db, auth, uuid.UUID(menu_id), block_type, title, entries,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


@router.get("/footer-block/{block_id}/edit", response_class=HTMLResponse)
async def footer_block_edit_form(
    request: Request,
    block_id: uuid.UUID,
    menu_id: uuid.UUID | None = None,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        block = await menu_service.get_owner_footer_block(db, auth, block_id)
    except (NoSiteInScope, MenuNotFound):
        raise HTTPException(status_code=404, detail="Not found")

    return _render(
        request, "admin/_footer_block_edit.html", auth,
        block=block, menu_id=menu_id,
    )


@router.post("/footer-block/{block_id}", response_class=HTMLResponse)
async def footer_block_update_or_delete(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")
    menu_id = form_data.get("menu_id")

    if action == "delete":
        try:
            await menu_coordinator.delete_footer_block(db, auth, block_id)
        except (NoSiteInScope, MenuNotFound):
            raise HTTPException(status_code=404, detail="Not found")
        return Response(status_code=200)

    block_type = form_data.get("block_type", "info")
    title = (form_data.get("title") or "").strip() or None
    entries = _parse_entries_text(form_data.get("entries_text", ""))

    try:
        block = await menu_coordinator.update_footer_block(
            db, auth, block_id, block_type, title, entries,
        )
    except (NoSiteInScope, MenuNotFound):
        raise HTTPException(status_code=404, detail="Not found")

    return _render(
        request, "admin/_footer_block_row.html", auth,
        block=block, menu_id=menu_id,
    )


# ---------------------------------------------------------------------------
# Subsection CRUD
# ---------------------------------------------------------------------------

@router.post("/subsection", response_class=HTMLResponse)
async def subsection_create(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    menu_id = form_data.get("menu_id")
    section_id = form_data.get("section_id")

    try:
        form = SubsectionForm(**dict(form_data))
    except ValidationError:
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        await menu_coordinator.create_subsection(db, auth, uuid.UUID(section_id), form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SectionNotFound:
        raise HTTPException(status_code=404, detail="Section not found")

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


@router.get("/subsection/{subsection_id}/edit", response_class=HTMLResponse)
async def subsection_edit_form(
    request: Request,
    subsection_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
    menu_id: uuid.UUID | None = None,
):
    try:
        subsection = await menu_service.get_owner_subsection(db, auth, subsection_id)
    except (NoSiteInScope, SubsectionNotFound) as exc:
        _not_found(exc)

    return _render(
        request, "admin/_subsection_edit_form.html", auth,
        subsection=subsection, menu_id=menu_id,
    )


@router.post("/subsection/{subsection_id}", response_class=HTMLResponse)
async def subsection_update_or_delete(
    request: Request,
    subsection_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    action = form_data.get("_action", "update")
    menu_id = form_data.get("menu_id")

    if action == "delete":
        try:
            await menu_coordinator.delete_subsection(db, auth, subsection_id)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        except SubsectionNotFound:
            raise HTTPException(status_code=404, detail="Subsection not found")
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        form = SubsectionForm(**dict(form_data))
    except ValidationError as exc:
        try:
            subsection = await menu_service.get_owner_subsection(db, auth, subsection_id)
        except (NoSiteInScope, SubsectionNotFound) as exc2:
            _not_found(exc2)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return _render(
            request, "admin/_subsection_edit_form.html", auth,
            subsection=subsection, menu_id=menu_id, errors=errors,
        )

    try:
        subsection = await menu_coordinator.update_subsection(db, auth, subsection_id, form)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SubsectionNotFound:
        raise HTTPException(status_code=404, detail="Subsection not found")

    return _render(
        request, "admin/_subsection_header.html", auth,
        subsection=subsection, menu_id=menu_id,
    )


# ---------------------------------------------------------------------------
# Move item
# ---------------------------------------------------------------------------

@router.post("/item/{item_id}/move", response_class=HTMLResponse)
async def item_move(
    request: Request,
    item_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    target_subsection_id = form_data.get("target_subsection_id")
    menu_id = form_data.get("menu_id")

    try:
        await menu_coordinator.move_item(
            db, auth, item_id, uuid.UUID(target_subsection_id)
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except (ItemNotFound, SubsectionNotFound):
        raise HTTPException(status_code=404, detail="Not found")

    # Re-render destination subsection items via out-of-band swap
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload as _sel
    from app.models.menu import MenuItem, Subsection
    target_id = uuid.UUID(target_subsection_id)
    result = await db.execute(
        select(Subsection)
        .where(Subsection.subsection_id == target_id)
        .options(_sel(Subsection.items).selectinload(MenuItem.variants))
    )
    target_sub = result.scalar_one()
    sorted_items = sorted(target_sub.items, key=lambda i: i.position)

    # Render each item row via the template engine
    csrf = generate_csrf_token(auth)
    item_rows = []
    for item in sorted_items:
        rendered = templates.get_template("admin/_item_row.html").render(
            item=item, menu_id=menu_id, csrf_token=csrf,
            storage_url=storage_public_url,
        )
        item_rows.append(rendered)

    # Build the OOB swap for the destination subsection body
    items_html = "\n".join(item_rows)
    # Wrap sortable container + add-item form for the destination
    dest_inner = (
        f'<div data-sortable data-reorder-url="/admin/subsection/{target_id}/reorder-items">'
        f'{items_html}</div>'
        f'<details class="mt-2">'
        f'<summary class="btn btn-outline btn-xs list-none [&::-webkit-details-marker]:hidden">+ Add item</summary>'
        f'<form method="post" action="/admin/item" class="border border-dashed border-base-300 rounded-lg p-3 mt-1 space-y-2">'
        f'<input type="hidden" name="csrf_token" value="{csrf}">'
        f'<input type="hidden" name="subsection_id" value="{target_id}">'
        f'<input type="hidden" name="menu_id" value="{menu_id}">'
        f'<div class="form-control"><input type="text" name="name" required class="input input-bordered input-sm w-full" placeholder="Item name *"></div>'
        f'<div class="form-control"><input type="text" name="description" class="input input-bordered input-sm w-full" placeholder="Description"></div>'
        f'<div class="form-control"><input type="text" name="dietary_tags" class="input input-bordered input-sm w-full" placeholder="Dietary tags (comma-separated)"></div>'
        f'<button type="submit" class="btn btn-primary btn-xs">Add item</button>'
        f'</form></details>'
    )
    dest_oob = f'<div id="subsection-body-{target_id}" class="hidden" hx-swap-oob="true">{dest_inner}</div>'

    # Primary response: replace the moved item with "Moved ✓"
    primary = '<div class="text-xs text-success italic p-2">Moved ✓</div>'

    return Response(
        content=primary + dest_oob,
        headers={"Content-Type": "text/html"},
    )


# ---------------------------------------------------------------------------
# Reorder (within a parent — 204 No Content, no re-render)
# ---------------------------------------------------------------------------

def _parse_ordered_ids(form_data) -> list[uuid.UUID]:
    """Extract ordered ids from form data (repeated 'ordered_ids' field)."""
    raw = form_data.getlist("ordered_ids")
    return [uuid.UUID(i) for i in raw]


@router.post("/menu/{menu_id}/reorder-sections")
async def reorder_sections(
    menu_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    try:
        ordered = _parse_ordered_ids(form_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ids")

    try:
        await menu_coordinator.reorder_sections(db, auth, menu_id, ordered)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except MenuNotFound:
        raise HTTPException(status_code=404, detail="Menu not found")
    except ReorderMismatch:
        raise HTTPException(status_code=400, detail="Id set mismatch")

    return Response(status_code=204)


@router.post("/section/{section_id}/reorder-subsections")
async def reorder_subsections(
    section_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    try:
        ordered = _parse_ordered_ids(form_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ids")

    try:
        await menu_coordinator.reorder_subsections(db, auth, section_id, ordered)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SectionNotFound:
        raise HTTPException(status_code=404, detail="Section not found")
    except ReorderMismatch:
        raise HTTPException(status_code=400, detail="Id set mismatch")

    return Response(status_code=204)


@router.post("/subsection/{subsection_id}/reorder-items")
async def reorder_items(
    subsection_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    try:
        ordered = _parse_ordered_ids(form_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ids")

    try:
        await menu_coordinator.reorder_items(db, auth, subsection_id, ordered)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SubsectionNotFound:
        raise HTTPException(status_code=404, detail="Subsection not found")
    except ReorderMismatch:
        raise HTTPException(status_code=400, detail="Id set mismatch")

    return Response(status_code=204)


@router.post("/item/{item_id}/reorder-variants")
async def reorder_variants(
    item_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    try:
        ordered = _parse_ordered_ids(form_data)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid ids")

    try:
        await menu_coordinator.reorder_variants(db, auth, item_id, ordered)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ItemNotFound:
        raise HTTPException(status_code=404, detail="Item not found")
    except ReorderMismatch:
        raise HTTPException(status_code=400, detail="Id set mismatch")

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

@router.get("/photos", response_class=HTMLResponse)
async def photos_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/photos.html", auth,
            photos=[], is_internal_admin=True, storage_url=None, error=None,
        )

    try:
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/photos.html", auth,
        photos=photos, is_internal_admin=False,
        storage_url=storage_public_url, error=None,
    )


@router.post("/photos", response_class=HTMLResponse)
async def photos_upload(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    uploads = form_data.getlist("file")

    if not uploads or not any(hasattr(u, "read") for u in uploads):
        return await _photos_with_error(request, auth, db, "No file selected.")

    errors = []
    for upload in uploads:
        if not hasattr(upload, "read"):
            continue
        file_data = await upload.read()
        if not file_data:
            continue
        filename = getattr(upload, "filename", None)
        content_type = getattr(upload, "content_type", "application/octet-stream")

        try:
            await photo_coordinator.create_photo(db, auth, file_data, filename, content_type)
        except InvalidImage as exc:
            errors.append(f"{filename}: {exc}")
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="No site in scope")
        except StorageNotConfigured as exc:
            return await _photos_with_error(request, auth, db, str(exc))

    if errors:
        return await _photos_with_error(request, auth, db, "; ".join(errors))

    return RedirectResponse(url="/admin/photos", status_code=303)


@router.post("/photos/{photo_id}/alt", response_class=HTMLResponse)
async def photos_update_alt(
    request: Request,
    photo_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    alt_text = form_data.get("alt_text", "")

    try:
        photo = await photo_coordinator.update_photo_alt(db, auth, photo_id, alt_text)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return _render(
        request, "admin/_photo_tile.html", auth,
        photo=photo, storage_url=storage_public_url, saved=True,
    )


@router.post("/photos/{photo_id}/delete", response_class=HTMLResponse)
async def photos_delete(
    request: Request,
    photo_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await photo_coordinator.delete_photo(db, auth, photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")
    except StorageNotConfigured as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return Response(status_code=200)


async def _photos_with_error(request, auth, db, error_msg):
    """Re-render the photos page with an error message."""
    try:
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        photos = []
    return _render(
        request, "admin/photos.html", auth,
        photos=photos, is_internal_admin=False,
        storage_url=storage_public_url, error=error_msg,
    )


# ---------------------------------------------------------------------------
# Appearance (image role assignments)
# ---------------------------------------------------------------------------

def _roles_by_key(roles):
    """Convert list of SiteImageRole into {role_key: first assignment}.

    list_roles returns ordered by (role, position), so the first seen per role
    is position 0 — matching the public render's [0] index.
    """
    out: dict = {}
    for r in roles:
        if r.role not in out:
            out[r.role] = r
    return out


def _roles_list_by_key(roles):
    """Convert list of SiteImageRole into {role_key: [assignments...]}."""
    out: dict = {}
    for r in roles:
        out.setdefault(r.role, []).append(r)
    return out


# Shared URL constants for the image-role partials (slot/picker/carousel).
# Routes stay at /admin/appearance/; the partials are surface-agnostic.
_IMAGE_ROLE_URLS = dict(
    picker_url="/admin/appearance/picker",
    assign_url="/admin/appearance/assign",
    clear_url="/admin/appearance/clear",
    carousel_add_url="/admin/appearance/feature-images/add",
    carousel_remove_url="/admin/appearance/feature-images/remove",
    carousel_move_url="/admin/appearance/feature-images/move",
)


@router.get("/appearance", response_class=HTMLResponse)
async def appearance_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/appearance.html", auth,
            is_internal_admin=True,
            available_templates=await template_meta_service.available_template_choices(db), current_template=None,
        )

    try:
        site = await site_service.get_owner_site(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    # Owners see only available templates; admins acting-as see all
    if auth.is_internal_admin:
        tpl_choices = await template_meta_service.available_template_choices(db)
    else:
        tpl_choices = await template_meta_service.public_template_choices(db)

    return _render(
        request, "admin/appearance.html", auth,
        is_internal_admin=False,
        available_templates=tpl_choices,
        current_template=site.template,
    )


@router.post("/appearance/template", response_class=HTMLResponse)
async def appearance_set_template(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    template = form_data.get("template", "")

    try:
        await site_coordinator.set_template(db, auth, template)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")
    except InvalidTemplate:
        raise HTTPException(status_code=400, detail="Invalid template")

    return RedirectResponse(url="/admin/appearance", status_code=303)


@router.get("/appearance/picker", response_class=HTMLResponse)
async def appearance_picker(
    request: Request,
    role: str,
    mode: str = "single",
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Return a photo-picker grid partial for the given role."""
    try:
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    # cancel_url comes from the Referer header or defaults to appearance
    referer = request.headers.get("hx-current-url", "/admin/appearance")
    return _render(
        request, "admin/_appearance_picker.html", auth,
        photos=photos, role=role, storage_url=storage_public_url,
        picker_mode=mode,
        assign_url="/admin/appearance/assign",
        add_url="/admin/appearance/feature-images/add",
        add_target="#slot-feature_images",
        cancel_url=referer,
    )


@router.post("/appearance/assign", response_class=HTMLResponse)
async def appearance_assign(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    role = form_data.get("role", "")
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await image_role_coordinator.assign(db, auth, role, photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Re-render the slot partial for this role
    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/_appearance_slot.html", auth,
        role_key=role, assignment=_roles_by_key(roles).get(role),
        storage_url=storage_public_url,
        **_IMAGE_ROLE_URLS,
    )


@router.post("/appearance/clear", response_class=HTMLResponse)
async def appearance_clear(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    role = form_data.get("role", "")

    try:
        await image_role_coordinator.clear(db, auth, role)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")

    return _render(
        request, "admin/_appearance_slot.html", auth,
        role_key=role, assignment=None,
        storage_url=storage_public_url,
        **_IMAGE_ROLE_URLS,
    )


# ---------------------------------------------------------------------------
# Feature images — carousel (multi-image) controls
# ---------------------------------------------------------------------------

async def _render_carousel(request, auth, db):
    """Re-render the carousel partial after a mutation."""
    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    items = _roles_list_by_key(roles).get("feature_images", [])
    return _render(
        request, "admin/_appearance_carousel.html", auth,
        feature_images_list=items, storage_url=storage_public_url,
        **_IMAGE_ROLE_URLS,
    )


@router.post("/appearance/feature-images/add", response_class=HTMLResponse)
async def feature_images_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await image_role_coordinator.add_to_role(db, auth, "feature_images", photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_carousel(request, auth, db)


@router.post("/appearance/feature-images/remove", response_class=HTMLResponse)
async def feature_images_remove(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await image_role_coordinator.remove_from_role(db, auth, "feature_images", photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")

    return await _render_carousel(request, auth, db)


@router.post("/appearance/feature-images/move", response_class=HTMLResponse)
async def feature_images_move(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Move a photo up or down in the carousel order. Server-authoritative."""
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")
    direction = form_data.get("direction", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Invalid direction")

    # Read current order, apply the swap server-side, then reorder
    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    current = [r for r in roles if r.role == "feature_images"]
    ids = [r.photo_id for r in current]

    if photo_id in ids:
        idx = ids.index(photo_id)
        if direction == "up" and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == "down" and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]
        # else: boundary — no-op

        try:
            await image_role_coordinator.reorder_role(db, auth, "feature_images", ids)
        except (NoSiteInScope, InvalidRole):
            raise HTTPException(status_code=400, detail="Reorder failed")

    return await _render_carousel(request, auth, db)


# ---------------------------------------------------------------------------
# Gallery (content — ordered multi-image role)
# ---------------------------------------------------------------------------

async def _render_gallery_manager(request, auth, db):
    """Re-render the gallery manager partial after a mutation."""
    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    items = _roles_list_by_key(roles).get("gallery", [])
    return _render(
        request, "admin/_gallery_manager.html", auth,
        gallery_list=items, storage_url=storage_public_url,
    )


@router.get("/gallery", response_class=HTMLResponse)
async def gallery_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/gallery.html", auth,
            gallery_list=[], is_internal_admin=True, storage_url=None,
        )

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    items = _roles_list_by_key(roles).get("gallery", [])
    return _render(
        request, "admin/gallery.html", auth,
        gallery_list=items, is_internal_admin=False,
        storage_url=storage_public_url,
    )


@router.get("/gallery/picker", response_class=HTMLResponse)
async def gallery_picker(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Photo picker for the gallery role."""
    try:
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/_appearance_picker.html", auth,
        photos=photos, role="gallery", storage_url=storage_public_url,
        picker_mode="carousel",
        add_url="/admin/gallery/add",
        add_target="#gallery-images",
        cancel_url="/admin/gallery",
    )


@router.post("/gallery/add", response_class=HTMLResponse)
async def gallery_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await image_role_coordinator.add_to_role(db, auth, "gallery", photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_gallery_manager(request, auth, db)


@router.post("/gallery/remove", response_class=HTMLResponse)
async def gallery_remove(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await image_role_coordinator.remove_from_role(db, auth, "gallery", photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidRole:
        raise HTTPException(status_code=400, detail="Invalid role")

    return await _render_gallery_manager(request, auth, db)


@router.post("/gallery/move", response_class=HTMLResponse)
async def gallery_move(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Move a photo up or down in the gallery order."""
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")
    direction = form_data.get("direction", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Invalid direction")

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    current = [r for r in roles if r.role == "gallery"]
    ids = [r.photo_id for r in current]

    if photo_id in ids:
        idx = ids.index(photo_id)
        if direction == "up" and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == "down" and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]

        try:
            await image_role_coordinator.reorder_role(db, auth, "gallery", ids)
        except (NoSiteInScope, InvalidRole):
            raise HTTPException(status_code=400, detail="Reorder failed")

    return await _render_gallery_manager(request, auth, db)


# ---------------------------------------------------------------------------
# Our Story (content blocks)
# ---------------------------------------------------------------------------

PAGE_KEY = "our_story"


async def _render_blocks(request, auth, db):
    """Re-render the block list partial after a mutation."""
    try:
        blocks = await content_block_service.list_blocks(db, auth, PAGE_KEY)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    return _render(
        request, "admin/_content_block_list.html", auth,
        blocks=blocks, storage_url=storage_public_url,
        page_url_prefix="/admin/our-story", show_date=False,
        show_visibility=False, photos=photos,
    )


@router.get("/our-story", response_class=HTMLResponse)
async def our_story_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/our_story.html", auth,
            blocks=[], is_internal_admin=True, storage_url=None,
            page_url_prefix="/admin/our-story", show_date=False,
            show_visibility=False, photos=[],
        )

    try:
        blocks = await content_block_service.list_blocks(db, auth, PAGE_KEY)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/our_story.html", auth,
        blocks=blocks, is_internal_admin=False,
        storage_url=storage_public_url,
        page_url_prefix="/admin/our-story", show_date=False,
        show_visibility=False, photos=photos,
    )


@router.post("/our-story/add", response_class=HTMLResponse)
async def our_story_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    heading = form_data.get("heading", "").strip() or None
    body = form_data.get("body", "").strip() or None
    photo_id_str = form_data.get("photo_id", "").strip()

    image_photo_id = None
    if photo_id_str:
        try:
            image_photo_id = uuid.UUID(photo_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await content_block_coordinator.create_block(
            db, auth, PAGE_KEY, heading, body,
            image_photo_id=image_photo_id,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Block must have a heading, body, or image")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_blocks(request, auth, db)


@router.get("/our-story/{block_id}/edit", response_class=HTMLResponse)
async def our_story_edit_form(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        block = await content_block_service._get_owner_block(db, auth, block_id)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return _render(
        request, "admin/_content_block_edit.html", auth,
        block=block, page_url_prefix="/admin/our-story", show_date=False,
        photos=photos, storage_url=storage_public_url,
    )


@router.post("/our-story/{block_id}/update", response_class=HTMLResponse)
async def our_story_update(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    heading = form_data.get("heading", "").strip() or None
    body = form_data.get("body", "").strip() or None
    photo_id_str = form_data.get("photo_id", "")

    from app.services.content_block_service import _SENTINEL
    if photo_id_str is not None:
        photo_id_str = photo_id_str.strip()
        if photo_id_str == "":
            image_photo_id = None
        else:
            try:
                image_photo_id = uuid.UUID(photo_id_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid photo_id")
    else:
        image_photo_id = _SENTINEL

    try:
        await content_block_coordinator.update_block(
            db, auth, block_id, heading, body,
            image_photo_id=image_photo_id,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Block must have a heading, body, or image")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_blocks(request, auth, db)


@router.post("/our-story/{block_id}/delete", response_class=HTMLResponse)
async def our_story_delete(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await content_block_coordinator.delete_block(db, auth, block_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return await _render_blocks(request, auth, db)


@router.get("/our-story/picker/{block_id}", response_class=HTMLResponse)
async def our_story_picker(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Photo picker for a block image — carousel mode, single-select behaviour."""
    try:
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/_appearance_picker.html", auth,
        photos=photos, role="block_image", storage_url=storage_public_url,
        picker_mode="carousel",
        add_url=f"/admin/our-story/{block_id}/set-image",
        add_target="#block-list",
        cancel_url="/admin/our-story",
    )


@router.post("/our-story/{block_id}/set-image", response_class=HTMLResponse)
async def our_story_set_image(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    photo_id_str = form_data.get("photo_id", "")

    try:
        photo_id = uuid.UUID(photo_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await content_block_coordinator.set_block_image(db, auth, block_id, photo_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_blocks(request, auth, db)


@router.post("/our-story/{block_id}/clear-image", response_class=HTMLResponse)
async def our_story_clear_image(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await content_block_coordinator.clear_block_image(db, auth, block_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Cannot remove image — block would be empty")

    return await _render_blocks(request, auth, db)


@router.post("/our-story/move", response_class=HTMLResponse)
async def our_story_move(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    block_id_str = form_data.get("block_id", "")
    direction = form_data.get("direction", "")

    try:
        block_id = uuid.UUID(block_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid block_id")

    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Invalid direction")

    try:
        blocks = await content_block_service.list_blocks(db, auth, PAGE_KEY)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    ids = [b.block_id for b in blocks]

    if block_id in ids:
        idx = ids.index(block_id)
        if direction == "up" and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == "down" and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]

        try:
            await content_block_coordinator.reorder_blocks(db, auth, PAGE_KEY, ids)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="Reorder failed")

    return await _render_blocks(request, auth, db)


# ---------------------------------------------------------------------------
# Events (What's On) — reuses content_block with page_key="events"
# ---------------------------------------------------------------------------

EVENTS_PAGE_KEY = "events"


async def _render_event_blocks(request, auth, db):
    """Re-render the events block list partial after a mutation."""
    from datetime import date as date_type

    try:
        blocks = await content_block_service.list_blocks(db, auth, EVENTS_PAGE_KEY)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    return _render(
        request, "admin/_content_block_list.html", auth,
        blocks=blocks, storage_url=storage_public_url,
        page_url_prefix="/admin/events", show_date=True,
        show_visibility=True, today=date_type.today(), photos=photos,
    )


@router.get("/events", response_class=HTMLResponse)
async def events_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type

    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/events.html", auth,
            blocks=[], is_internal_admin=True, storage_url=None,
            page_url_prefix="/admin/events", show_date=True,
            show_visibility=True, today=date_type.today(), photos=[],
        )

    try:
        blocks = await content_block_service.list_blocks(db, auth, EVENTS_PAGE_KEY)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/events.html", auth,
        blocks=blocks, is_internal_admin=False,
        storage_url=storage_public_url,
        page_url_prefix="/admin/events", show_date=True,
        show_visibility=True, today=date_type.today(), photos=photos,
    )


@router.post("/events/add", response_class=HTMLResponse)
async def events_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type

    form_data = await request.form()
    heading = form_data.get("heading", "").strip() or None
    body = form_data.get("body", "").strip() or None
    date_str = form_data.get("event_date", "").strip()
    photo_id_str = form_data.get("photo_id", "").strip()

    event_date = None
    if date_str:
        try:
            event_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date")

    image_photo_id = None
    if photo_id_str:
        try:
            image_photo_id = uuid.UUID(photo_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid photo_id")

    try:
        await content_block_coordinator.create_block(
            db, auth, EVENTS_PAGE_KEY, heading, body,
            event_date=event_date, image_photo_id=image_photo_id,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Must have at least a heading, description, or image")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_event_blocks(request, auth, db)


@router.get("/events/{block_id}/edit", response_class=HTMLResponse)
async def events_edit_form(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        block = await content_block_service._get_owner_block(db, auth, block_id)
        photos = await photo_service.list_photos(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return _render(
        request, "admin/_content_block_edit.html", auth,
        block=block, page_url_prefix="/admin/events", show_date=True,
        photos=photos, storage_url=storage_public_url,
    )


@router.post("/events/{block_id}/update", response_class=HTMLResponse)
async def events_update(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type

    form_data = await request.form()
    heading = form_data.get("heading", "").strip() or None
    body = form_data.get("body", "").strip() or None
    date_str = form_data.get("event_date", "").strip()
    photo_id_str = form_data.get("photo_id", "")

    event_date = None
    if date_str:
        try:
            event_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date")

    # Determine image: empty string = clear, non-empty = set, missing = don't change
    from app.services.content_block_service import _SENTINEL
    if photo_id_str is not None:
        photo_id_str = photo_id_str.strip()
        if photo_id_str == "":
            image_photo_id = None  # clear
        else:
            try:
                image_photo_id = uuid.UUID(photo_id_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid photo_id")
    else:
        image_photo_id = _SENTINEL

    try:
        await content_block_coordinator.update_block(
            db, auth, block_id, heading, body,
            event_date=event_date, image_photo_id=image_photo_id,
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Must have at least a heading, description, or image")
    except PhotoNotFound:
        raise HTTPException(status_code=404, detail="Photo not found")

    return await _render_event_blocks(request, auth, db)


@router.post("/events/{block_id}/delete", response_class=HTMLResponse)
async def events_delete(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await content_block_coordinator.delete_block(db, auth, block_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return await _render_event_blocks(request, auth, db)


@router.post("/events/move", response_class=HTMLResponse)
async def events_move(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    block_id_str = form_data.get("block_id", "")
    direction = form_data.get("direction", "")

    try:
        block_id = uuid.UUID(block_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid block_id")

    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Invalid direction")

    try:
        blocks = await content_block_service.list_blocks(db, auth, EVENTS_PAGE_KEY)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    # Only reorder among undated (standing specials) — dated sort by date
    undated = [b for b in blocks if b.event_date is None]
    ids = [b.block_id for b in undated]

    if block_id in ids:
        idx = ids.index(block_id)
        if direction == "up" and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == "down" and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]

        # Include dated blocks in the full reorder to preserve their positions
        dated_ids = [b.block_id for b in blocks if b.event_date is not None]
        try:
            await content_block_coordinator.reorder_blocks(db, auth, EVENTS_PAGE_KEY, dated_ids + ids)
        except NoSiteInScope:
            raise HTTPException(status_code=400, detail="Reorder failed")

    return await _render_event_blocks(request, auth, db)


@router.post("/events/{block_id}/toggle-visibility", response_class=HTMLResponse)
async def events_toggle_visibility(
    request: Request,
    block_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await content_block_coordinator.toggle_visibility(db, auth, block_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return await _render_event_blocks(request, auth, db)


# ---------------------------------------------------------------------------
# Hours
# ---------------------------------------------------------------------------


def _hours_by_day(hours_list):
    """Group hours into {day_of_week: [RegularHours, ...]}."""
    out: dict[int, list] = {d: [] for d in range(7)}
    for h in hours_list:
        out[h.day_of_week].append(h)
    return out


# Social platforms shown on the Visit form, in the footer's canonical order:
# (form/storage key, human label).
_SOCIAL_PLATFORMS = [
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
    ("tripadvisor", "TripAdvisor"),
    ("google", "Google"),
    ("x", "X"),
]


def _read_social_links(form_data) -> list[dict]:
    """Build social_links from the seven fixed inputs. Normalisation at write
    time: trim, drop blanks, prepend https:// when no scheme. Canonical order."""
    out: list[dict] = []
    for key, _label in _SOCIAL_PLATFORMS:
        url = form_data.get(f"social_{key}", "").strip()
        if not url:
            continue
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        out.append({"platform": key, "url": url})
    return out


def _social_lookup(location) -> dict:
    """{platform: url} from a Location's social_links, for form pre-fill."""
    return {
        s.get("platform"): s.get("url", "")
        for s in (location.social_links or [])
        if s.get("platform")
    }


@router.get("/visit", response_class=HTMLResponse)
async def visit_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/visit.html", auth,
            locations=[], is_internal_admin=True,
            day_names=_DAY_NAMES,
            google_places_key=settings.GOOGLE_MAPS_API_KEY,
            multi_location_enabled=settings.MULTI_LOCATION_ENABLED,
        )

    try:
        locations = await location_service.list_locations(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    # Auto-create a default location if none exists (single-location product)
    if not locations:
        await location_coordinator.create_location(db, auth)
        locations = await location_service.list_locations(db, auth)

    # Load hours + exceptions per location
    loc_data = []
    for loc in locations:
        hours = await hours_service.list_hours(db, auth, location_id=loc.location_id)
        exceptions = await hours_exception_service.list_exceptions(
            db, auth, location_id=loc.location_id,
        )
        loc_data.append({
            "location": loc,
            "hours_by_day": _hours_by_day(hours),
            "exceptions": exceptions,
            "social_lookup": _social_lookup(loc),
        })

    return _render(
        request, "admin/visit.html", auth,
        locations=loc_data,
        is_internal_admin=False,
        day_names=_DAY_NAMES,
        social_platforms=_SOCIAL_PLATFORMS,
        google_places_key=settings.GOOGLE_MAPS_API_KEY,
        multi_location_enabled=settings.MULTI_LOCATION_ENABLED,
    )


@router.post("/visit", response_class=HTMLResponse)
async def visit_save_location(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Save address + contact for a location."""
    form_data = await request.form()
    location_id_str = form_data.get("location_id", "")

    try:
        location_id = uuid.UUID(location_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid location_id")

    kwargs = {
        "label": form_data.get("label", "").strip() or None,
        "address_street": form_data.get("address_street", "").strip() or None,
        "address_suburb": form_data.get("address_suburb", "").strip() or None,
        "address_state": form_data.get("address_state", "").strip() or None,
        "address_postcode": form_data.get("address_postcode", "").strip() or None,
        "phone": form_data.get("phone", "").strip() or None,
        "email": form_data.get("email", "").strip() or None,
        # Always pass the list (even []) so clearing a field removes it — the
        # service sets social_links conditionally on non-None.
        "social_links": _read_social_links(form_data),
    }

    # Lat/lng from Places autocomplete (coords stored when user selects a suggestion)
    lat_str = form_data.get("latitude", "").strip()
    lng_str = form_data.get("longitude", "").strip()
    if lat_str and lng_str:
        try:
            from decimal import Decimal
            kwargs["latitude"] = Decimal(lat_str)
            kwargs["longitude"] = Decimal(lng_str)
        except Exception:
            pass  # manual entry — no coords, that's fine

    try:
        await location_coordinator.update_location(db, auth, location_id, **kwargs)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except LocationNotFound:
        raise HTTPException(status_code=400, detail="Location not found")

    return RedirectResponse(url="/admin/visit", status_code=303)


@router.post("/visit/add-location", response_class=HTMLResponse)
async def visit_add_location(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Add a new (empty) location. Gated by MULTI_LOCATION_ENABLED."""
    if not settings.MULTI_LOCATION_ENABLED:
        return RedirectResponse(url="/admin/visit", status_code=303)

    form_data = await request.form()
    label = form_data.get("label", "").strip() or None

    try:
        await location_coordinator.create_location(db, auth, label=label)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return RedirectResponse(url="/admin/visit", status_code=303)


@router.post("/visit/remove-location", response_class=HTMLResponse)
async def visit_remove_location(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Remove a location."""
    form_data = await request.form()
    location_id_str = form_data.get("location_id", "")

    try:
        location_id = uuid.UUID(location_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid location_id")

    try:
        await location_coordinator.delete_location(db, auth, location_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except LocationNotFound:
        raise HTTPException(status_code=400, detail="Location not found")
    except CannotDeleteLastLocation:
        raise HTTPException(status_code=400, detail="A site must have at least one location")

    return RedirectResponse(url="/admin/visit", status_code=303)


@router.get("/hours", response_class=HTMLResponse)
async def hours_redirect():
    """Legacy URL — redirect to /admin/visit."""
    return RedirectResponse(url="/admin/visit", status_code=301)


@router.get("/hours-legacy", response_class=HTMLResponse)
async def hours_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Legacy hours page — kept for the hours HTMX partials that still POST to /admin/hours/*."""
    if auth.is_internal_admin and auth.scoped_site_id is None:
        return _render(
            request, "admin/hours.html", auth,
            hours_by_day={}, day_names=_DAY_NAMES, is_internal_admin=True,
            exceptions=[],
        )

    try:
        hours = await hours_service.list_hours(db, auth)
        exceptions = await hours_exception_service.list_exceptions(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/hours.html", auth,
        hours_by_day=_hours_by_day(hours), day_names=_DAY_NAMES,
        is_internal_admin=False, exceptions=exceptions,
    )


@router.post("/hours/add", response_class=HTMLResponse)
async def hours_add_range(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import time as dt_time

    form_data = await request.form()
    try:
        day = int(form_data.get("day_of_week", ""))
        open_time = dt_time.fromisoformat(form_data.get("open_time", ""))
        close_time = dt_time.fromisoformat(form_data.get("close_time", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid time values")

    if day < 0 or day > 6:
        raise HTTPException(status_code=400, detail="Invalid day")

    # Optional location_id for visit-page scoping — fail closed on bad id
    loc_id_str = form_data.get("location_id", "")
    loc_id = None
    if loc_id_str:
        try:
            loc_id = uuid.UUID(loc_id_str)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid location_id")

    label = form_data.get("label") or None

    try:
        await hours_coordinator.add_range(db, auth, day, open_time, close_time, location_id=loc_id, label=label)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except LocationNotFound:
        raise HTTPException(status_code=400, detail="Location not found")
    except InvalidHoursLabel:
        raise HTTPException(status_code=400, detail="Invalid hours label")

    day_target = form_data.get("day_target", None)
    return await _render_hours_day(request, auth, db, day, location_id=loc_id, day_target=day_target)


@router.post("/hours/{range_id}/update", response_class=HTMLResponse)
async def hours_update_range(
    request: Request,
    range_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import time as dt_time

    form_data = await request.form()
    day = int(form_data.get("day_of_week", "0"))

    try:
        open_time = dt_time.fromisoformat(form_data.get("open_time", ""))
        close_time = dt_time.fromisoformat(form_data.get("close_time", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid time values")

    label = form_data.get("label") or None

    try:
        await hours_coordinator.update_range(db, auth, range_id, open_time, close_time, label=label)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except HoursRangeNotFound:
        raise HTTPException(status_code=404, detail="Range not found")
    except InvalidHoursLabel:
        raise HTTPException(status_code=400, detail="Invalid hours label")

    day_target = form_data.get("day_target", None)
    loc_id_str = form_data.get("location_id", "")
    loc_id = uuid.UUID(loc_id_str) if loc_id_str else None
    return await _render_hours_day(request, auth, db, day, location_id=loc_id, day_target=day_target)


@router.post("/hours/{range_id}/delete", response_class=HTMLResponse)
async def hours_delete_range(
    request: Request,
    range_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    day = int(form_data.get("day_of_week", "0"))

    try:
        await hours_coordinator.delete_range(db, auth, range_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except HoursRangeNotFound:
        raise HTTPException(status_code=404, detail="Range not found")

    day_target = form_data.get("day_target", None)
    loc_id_str = form_data.get("location_id", "")
    loc_id = uuid.UUID(loc_id_str) if loc_id_str else None
    return await _render_hours_day(request, auth, db, day, location_id=loc_id, day_target=day_target)


@router.post("/visit/hours-display", response_class=HTMLResponse)
async def hours_display_mode(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Live-save the public hours display mode (detailed | summary) for a location."""
    form_data = await request.form()

    loc_id_str = form_data.get("location_id", "")
    try:
        loc_id = uuid.UUID(loc_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid location_id")

    mode = form_data.get("hours_display_mode", "")
    try:
        await location_coordinator.set_hours_display_mode(db, auth, loc_id, mode)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except LocationNotFound:
        raise HTTPException(status_code=400, detail="Location not found")
    except InvalidHoursDisplayMode:
        raise HTTPException(status_code=400, detail="Invalid display mode")

    return Response(status_code=204)


async def _render_hours_day(request, auth, db, day, location_id=None, day_target=None):
    """Re-render a single day's hours partial after a mutation."""
    try:
        hours = await hours_service.list_hours(db, auth, location_id=location_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    day_hours = [h for h in hours if h.day_of_week == day]

    if day_target and location_id:
        # Visit-page context: use location-scoped partial
        loc = await location_service.get_owner_location(db, auth, location_id)
        return _render(
            request, "admin/_visit_hours_day.html", auth,
            day=day, day_name=_DAY_NAMES[day], ranges=day_hours,
            day_target=day_target, loc=loc,
        )
    return _render(
        request, "admin/_hours_day.html", auth,
        day=day, day_name=_DAY_NAMES[day], ranges=day_hours,
    )


# ---------------------------------------------------------------------------
# Hours exceptions
# ---------------------------------------------------------------------------


def _parse_special_hours(form_data) -> list | None:
    """Parse special_hours ranges from form data. Returns None if closed."""
    opens = form_data.getlist("sh_open")
    closes = form_data.getlist("sh_close")
    if not opens:
        return None
    ranges = []
    for o, c in zip(opens, closes):
        if o and c:
            ranges.append({"open": o, "close": c})
    return ranges or None


@router.post("/hours/exceptions/add", response_class=HTMLResponse)
async def exception_add(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as dt_date

    form_data = await request.form()
    try:
        start = dt_date.fromisoformat(form_data.get("start_date", ""))
        end = dt_date.fromisoformat(form_data.get("end_date", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date values")

    is_closed = form_data.get("is_closed", "on") == "on"
    label = form_data.get("label", "").strip() or None
    special_hours = None if is_closed else _parse_special_hours(form_data)

    try:
        await hours_exception_coordinator.add_exception(
            db, auth, start, end, is_closed, special_hours, label
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except InvalidDateRange:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    return await _render_exceptions_list(request, auth, db)


@router.post("/hours/exceptions/{exc_id}/update", response_class=HTMLResponse)
async def exception_update(
    request: Request,
    exc_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as dt_date

    form_data = await request.form()
    try:
        start = dt_date.fromisoformat(form_data.get("start_date", ""))
        end = dt_date.fromisoformat(form_data.get("end_date", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date values")

    is_closed = form_data.get("is_closed", "on") == "on"
    label = form_data.get("label", "").strip() or None
    special_hours = None if is_closed else _parse_special_hours(form_data)

    try:
        await hours_exception_coordinator.update_exception(
            db, auth, exc_id, start, end, is_closed, special_hours, label
        )
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except HoursExceptionNotFound:
        raise HTTPException(status_code=404, detail="Exception not found")
    except InvalidDateRange:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    return await _render_exceptions_list(request, auth, db)


@router.post("/hours/exceptions/{exc_id}/delete", response_class=HTMLResponse)
async def exception_delete(
    request: Request,
    exc_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    try:
        await hours_exception_coordinator.delete_exception(db, auth, exc_id)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except HoursExceptionNotFound:
        raise HTTPException(status_code=404, detail="Exception not found")

    return await _render_exceptions_list(request, auth, db)


async def _render_exceptions_list(request, auth, db):
    """Re-render the exceptions list partial after a mutation."""
    try:
        exceptions = await hours_exception_service.list_exceptions(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    return _render(
        request, "admin/_hours_exceptions.html", auth,
        exceptions=exceptions,
    )


# ---------------------------------------------------------------------------
# Menu extraction sandbox
# ---------------------------------------------------------------------------

@router.get("/extraction-sandbox", response_class=HTMLResponse)
async def extraction_sandbox_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
):
    return _render(request, "admin/extraction_sandbox.html", auth)


@router.post("/extraction-sandbox", response_class=HTMLResponse)
async def extraction_sandbox_run(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
):
    import json as _json

    form_data = await request.form()
    upload = form_data.get("file")

    if not upload or not hasattr(upload, "read"):
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error="No file selected.",
        )

    content_type = getattr(upload, "content_type", "")
    if content_type != "application/pdf":
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error=f"Expected a PDF file, got: {content_type or 'unknown'}",
        )

    file_data = await upload.read()

    try:
        result = await menu_extraction_service.extract_from_pdf(file_data)
    except ExtractionNotConfigured as exc:
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error=str(exc),
        )
    except InvalidPDF as exc:
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error=str(exc),
        )
    except ExtractionFailed as exc:
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error=str(exc),
            raw_text=exc.raw_text,
        )

    result_json = _json.dumps(result.model_dump(), indent=2)
    result_json_raw = _json.dumps(result.model_dump())
    return _render(
        request, "admin/extraction_sandbox.html", auth,
        result_json=result_json,
        result_json_raw=result_json_raw,
        ignored=result.ignored,
    )


@router.post("/extraction-sandbox/commit", response_class=HTMLResponse)
async def extraction_sandbox_commit(
    request: Request,
    auth: AuthContext = Depends(require_csrf_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Commit extracted JSON as an unpublished draft menu."""
    import json as _json
    from app.schemas.extraction import ExtractedMenu

    form_data = await request.form()
    raw = form_data.get("extraction_json", "")

    try:
        data = _json.loads(raw)
        extracted = ExtractedMenu.model_validate(data)
    except Exception:
        return _render(
            request, "admin/extraction_sandbox.html", auth,
            error="Invalid extraction data — please re-extract.",
        )

    try:
        menu = await menu_coordinator.commit_extracted_menu(db, auth, extracted)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return RedirectResponse(
        url=f"/admin/menu/{menu.menu_id}", status_code=303
    )

