"""Admin routes — login/logout, dashboard, and details editing."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.deps import SESSION_COOKIE, require_auth
from app.coordinators import site_coordinator
from app.core.config import settings
from app.core.security import SESSION_LIFETIME, encode_session, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.site import SiteDetailsForm
from app.services import site_service

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth (login / logout)
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401,
        )

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
async def logout():
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
    site = await site_service.get_owner_site(db, auth)

    result = await db.execute(select(User).where(User.user_id == auth.user_id))
    user = result.scalar_one()

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "email": user.email,
            "role": auth.role,
            "site_name": site.restaurant_name if site else None,
            "is_internal_admin": auth.is_internal_admin,
        },
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
    site = await site_service.get_owner_site(db, auth)
    return templates.TemplateResponse(
        "admin/details.html",
        {"request": request, "site": site},
    )


@router.post("/details", response_class=HTMLResponse)
async def details_save(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    form_data = await request.form()

    try:
        form = SiteDetailsForm(**dict(form_data))
    except ValidationError as exc:
        site = await site_service.get_owner_site(db, auth)
        errors = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return templates.TemplateResponse(
            "admin/_details_form.html",
            {"request": request, "site": site, "errors": errors, "saved": False},
        )

    site = await site_coordinator.update_site_details(db, auth, form)

    return templates.TemplateResponse(
        "admin/_details_form.html",
        {"request": request, "site": site, "saved": True, "errors": None},
    )
