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
from app.auth.deps import SESSION_COOKIE, require_auth, require_csrf
from app.coordinators import image_role_coordinator, menu_coordinator, photo_coordinator, site_coordinator
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import SESSION_LIFETIME, encode_session
from app.db.session import get_db
from app.schemas.menu import ItemForm, MenuForm, SectionForm, SubsectionForm, VariantForm
from app.schemas.site import SiteDetailsForm
from app.services import auth_service, image_role_service, menu_service, photo_service, site_service
from app.services.storage import public_url as storage_public_url
from app.services.exceptions import (
    InvalidImage,
    InvalidRole,
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
from app.services.storage import StorageNotConfigured

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
    user = await auth_service.authenticate_user(db, email, password)

    if user is None:
        return _render(request, "admin/login.html", status_code=401, error="Invalid email or password")

    token = encode_session(user.user_id)
    response = RedirectResponse(url="/admin/", status_code=303)
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
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: AuthContext = Depends(require_auth),
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
# Details editing
# ---------------------------------------------------------------------------

@router.get("/details", response_class=HTMLResponse)
async def details_page(
    request: Request,
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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


@router.get("/menu/{menu_id}", response_class=HTMLResponse)
async def menu_canvas(
    request: Request,
    menu_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    subsection_id = form_data.get("subsection_id")
    menu_id = form_data.get("menu_id")

    try:
        form = ItemForm(**dict(form_data))
    except ValidationError:
        return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)

    try:
        await menu_coordinator.create_item(db, auth, uuid.UUID(subsection_id), form)
    except (NoSiteInScope, SubsectionNotFound) as exc:
        _not_found(exc)

    return RedirectResponse(url=f"/admin/menu/{menu_id}", status_code=303)


@router.get("/item/{item_id}", response_class=HTMLResponse)
async def item_display(
    request: Request,
    item_id: uuid.UUID,
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
        item = await menu_coordinator.update_item(db, auth, item_id, form)
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_auth),
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
    auth: AuthContext = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()
    upload = form_data.get("file")

    if not upload or not hasattr(upload, "read"):
        return await _photos_with_error(request, auth, db, "No file selected.")

    file_data = await upload.read()
    filename = getattr(upload, "filename", None)
    content_type = getattr(upload, "content_type", "application/octet-stream")

    try:
        await photo_coordinator.create_photo(db, auth, file_data, filename, content_type)
    except InvalidImage as exc:
        return await _photos_with_error(request, auth, db, str(exc))
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")
    except StorageNotConfigured as exc:
        return await _photos_with_error(request, auth, db, str(exc))

    return RedirectResponse(url="/admin/photos", status_code=303)


@router.post("/photos/{photo_id}/alt", response_class=HTMLResponse)
async def photos_update_alt(
    request: Request,
    photo_id: uuid.UUID,
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
    """Convert list of SiteImageRole into {role_key: assignment}."""
    return {r.role: r for r in roles}


@router.get("/appearance", response_class=HTMLResponse)
async def appearance_page(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if auth.is_internal_admin:
        return _render(
            request, "admin/appearance.html", auth,
            roles={}, is_internal_admin=True, storage_url=None,
        )

    try:
        roles = await image_role_service.list_roles(db, auth)
    except NoSiteInScope:
        raise HTTPException(status_code=400, detail="No site in scope")

    return _render(
        request, "admin/appearance.html", auth,
        roles=_roles_by_key(roles), is_internal_admin=False,
        storage_url=storage_public_url,
    )


@router.get("/appearance/picker", response_class=HTMLResponse)
async def appearance_picker(
    request: Request,
    role: str,
    auth: AuthContext = Depends(require_auth),
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
    )


@router.post("/appearance/assign", response_class=HTMLResponse)
async def appearance_assign(
    request: Request,
    auth: AuthContext = Depends(require_csrf),
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
    auth: AuthContext = Depends(require_csrf),
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
