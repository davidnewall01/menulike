"""Admin routes — login/logout, dashboard, details editing, menu CRUD."""

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
from app.coordinators import menu_coordinator, site_coordinator
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import SESSION_LIFETIME, encode_session
from app.db.session import get_db
from app.schemas.menu import MenuForm
from app.schemas.site import SiteDetailsForm
from app.services import auth_service, menu_service, site_service
from app.services.exceptions import MenuNotFound, NoSiteInScope, SiteNotFound

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
