"""Admin routes — login/logout, dashboard, details, menu/section/subsection/item/variant CRUD."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.auth.context import AuthContext
from app.auth.deps import SESSION_COOKIE, require_auth, require_csrf, require_csrf_owner_site, require_owner_site
from app.coordinators import content_block_coordinator, hours_coordinator, hours_exception_coordinator, image_role_coordinator, menu_coordinator, photo_coordinator, site_coordinator
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import SESSION_LIFETIME, encode_session
from app.db.session import get_db
from app.schemas.menu import ItemForm, MenuForm, SectionForm, SubsectionForm, VariantForm, parse_extras
from app.schemas.site import SiteDetailsForm
from app.services import auth_service, content_block_service, hours_exception_service, hours_service, image_role_service, menu_extraction_service, menu_service, photo_service, site_service
from app.services.hours_service import HoursRangeNotFound
from app.services.hours_exception_service import HoursExceptionNotFound, InvalidDateRange
from app.services.storage import public_url as storage_public_url
from app.services.exceptions import (
    ContentBlockNotFound,
    EmptyBlock,
    InvalidImage,
    InvalidRole,
    InvalidTemplate,
    ItemNotFound,
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
from app.web.template_resolver import AVAILABLE_TEMPLATES, FEATURE_IMAGE_MODE

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

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
# Preview (draft-inclusive, real Linen template)
# ---------------------------------------------------------------------------

@router.get("/preview/menu", response_class=HTMLResponse)
async def preview_menu(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    """Render the owner's menu (including drafts) through the real Linen template.

    Authenticated, owner-scoped. Draft stays out of the public subdomain.
    """
    site = await site_service.get_owner_site_with_drafts(db, auth)
    return templates.TemplateResponse(
        "public/linen/menu.html",
        {
            "request": request,
            "site": site,
            "render_mode": "preview",
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
    try:
        site = await site_service.get_owner_site(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    return _render(
        request, "admin/dashboard.html", auth,
        email=auth.email,
        role=auth.role,
        site_name=site.restaurant_name if site else None,
        is_internal_admin=auth.is_internal_admin,
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
    site_view = resolve_site_view(site=site, role_images=role_images, mode="public")

    eligible, _reasons = site_service.can_publish(site_view)
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

@router.get("/menu", response_class=HTMLResponse)
async def menu_list(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin:
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

    return _render(request, "admin/menu_canvas.html", auth, menu=menu)


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

        return _render(
            request, "admin/_menu_edit_form.html", auth,
            menu=None, deleted=True, saved=False, errors=None,
        )

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
        await menu_coordinator.create_item(db, auth, uuid.UUID(subsection_id), form, extras=extras)
    except (NoSiteInScope, SubsectionNotFound) as exc:
        _not_found(exc)

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


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

    return _render(request, "admin/_item_row.html", auth, item=item, menu_id=menu_id)


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
    return _render(request, "admin/_item_row.html", auth, item=item, menu_id=menu_id)


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

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


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
    except (NoSiteInScope, SectionNotFound) as exc:
        _not_found(exc)

    return _render(
        request, "admin/_section_edit_form.html", auth,
        section=section, menu_id=menu_id,
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

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


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
    if auth.is_internal_admin:
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


def _appearance_context(site, roles, auth):
    """Build the shared context dict for the appearance page."""
    mode = FEATURE_IMAGE_MODE.get(site.template, "single")
    by_key = _roles_by_key(roles)
    by_key_list = _roles_list_by_key(roles)
    return dict(
        roles=by_key,
        is_internal_admin=False,
        storage_url=storage_public_url,
        available_templates=AVAILABLE_TEMPLATES,
        current_template=site.template,
        feature_image_mode=mode,
        feature_images_list=by_key_list.get("feature_images", []),
    )


@router.get("/appearance", response_class=HTMLResponse)
async def appearance_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin:
        return _render(
            request, "admin/appearance.html", auth,
            roles={}, is_internal_admin=True, storage_url=None,
            available_templates=AVAILABLE_TEMPLATES, current_template=None,
            feature_image_mode="single", feature_images_list=[],
        )

    try:
        site = await site_service.get_owner_site(db, auth)
    except SiteNotFound:
        raise HTTPException(status_code=400, detail="Scoped site not found")

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/appearance.html", auth,
        **_appearance_context(site, roles, auth),
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

    return _render(
        request, "admin/_appearance_picker.html", auth,
        photos=photos, role=role, storage_url=storage_public_url,
        picker_mode=mode,
        add_url="/admin/appearance/feature-images/add",
        add_target="#slot-feature_images",
        cancel_url="/admin/appearance",
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
    if auth.is_internal_admin:
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
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    return _render(
        request, "admin/_block_list.html", auth,
        blocks=blocks, storage_url=storage_public_url,
    )


@router.get("/our-story", response_class=HTMLResponse)
async def our_story_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin:
        return _render(
            request, "admin/our_story.html", auth,
            blocks=[], is_internal_admin=True, storage_url=None,
        )

    try:
        blocks = await content_block_service.list_blocks(db, auth, PAGE_KEY)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/our_story.html", auth,
        blocks=blocks, is_internal_admin=False,
        storage_url=storage_public_url,
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

    try:
        await content_block_coordinator.create_block(db, auth, PAGE_KEY, heading, body)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Block must have a heading or body")

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
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")

    return _render(
        request, "admin/_block_edit.html", auth,
        block=block,
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

    try:
        await content_block_coordinator.update_block(db, auth, block_id, heading, body)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except ContentBlockNotFound:
        raise HTTPException(status_code=404, detail="Block not found")
    except EmptyBlock:
        raise HTTPException(status_code=400, detail="Block must have a heading, body, or image")

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
# Hours
# ---------------------------------------------------------------------------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hours_by_day(hours_list):
    """Group hours into {day_of_week: [RegularHours, ...]}."""
    out: dict[int, list] = {d: [] for d in range(7)}
    for h in hours_list:
        out[h.day_of_week].append(h)
    return out


@router.get("/hours", response_class=HTMLResponse)
async def hours_page(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin:
        return _render(
            request, "admin/hours.html", auth,
            hours_by_day={}, day_names=DAY_NAMES, is_internal_admin=True,
            exceptions=[],
        )

    try:
        hours = await hours_service.list_hours(db, auth)
        exceptions = await hours_exception_service.list_exceptions(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/hours.html", auth,
        hours_by_day=_hours_by_day(hours), day_names=DAY_NAMES,
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

    try:
        await hours_coordinator.add_range(db, auth, day, open_time, close_time)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return await _render_hours_day(request, auth, db, day)


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

    try:
        await hours_coordinator.update_range(db, auth, range_id, open_time, close_time)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except HoursRangeNotFound:
        raise HTTPException(status_code=404, detail="Range not found")

    return await _render_hours_day(request, auth, db, day)


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

    return await _render_hours_day(request, auth, db, day)


async def _render_hours_day(request, auth, db, day):
    """Re-render a single day's hours partial after a mutation."""
    try:
        hours = await hours_service.list_hours(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    day_hours = [h for h in hours if h.day_of_week == day]
    return _render(
        request, "admin/_hours_day.html", auth,
        day=day, day_name=DAY_NAMES[day], ranges=day_hours,
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

