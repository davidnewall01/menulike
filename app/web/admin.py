"""Admin routes — login/logout and a protected stub dashboard."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.deps import SESSION_COOKIE, require_auth
from app.core.config import settings
from app.core.security import SESSION_LIFETIME, encode_session, verify_password
from app.db.session import get_db
from app.models.site import Site
from app.models.user import User

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


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


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    site_name = None
    if auth.scoped_site_id:
        result = await db.execute(
            select(Site).where(Site.site_id == auth.scoped_site_id)
        )
        site = result.scalar_one_or_none()
        if site:
            site_name = site.restaurant_name

    # Load the user email for display
    result = await db.execute(select(User).where(User.user_id == auth.user_id))
    user = result.scalar_one()

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "email": user.email,
            "role": auth.role,
            "site_name": site_name,
            "is_internal_admin": auth.is_internal_admin,
        },
    )
