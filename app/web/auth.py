"""Auth routes — signup, setup (restaurant naming).

These live on the apex domain (no tenant context, no resolve_tenant).
Standalone templates — never inherit the admin base that assumes a site.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.deps import SESSION_COOKIE, require_auth, require_csrf
from app.coordinators import site_coordinator
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import SESSION_LIFETIME, encode_session, hash_password
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.exceptions import AlreadyHasSite, DuplicateEmail

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(tags=["auth"])

MIN_PASSWORD_LENGTH = 8


# ---------------------------------------------------------------------------
# Sign-up
# ---------------------------------------------------------------------------

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})


@router.post("/signup")
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Normalise email: strip whitespace, lowercase
    email = email.strip().lower()

    errors: list[str] = []
    if not email:
        errors.append("Email is required.")
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != password_confirm:
        errors.append("Passwords do not match.")

    if errors:
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "errors": errors, "email": email},
            status_code=400,
        )

    # Check duplicate email
    from sqlalchemy import select
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        return templates.TemplateResponse(
            "auth/signup.html",
            {
                "request": request,
                "errors": ["Looks like you already have an account."],
                "show_login_link": True,
                "email": email,
            },
            status_code=409,
        )

    # Create owner with no site
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole.owner.value,
        site_id=None,
    )
    db.add(user)
    await db.commit()

    # Issue session cookie — same logic as the login route
    token = encode_session(user.user_id)
    response = RedirectResponse(url="/setup/restaurant", status_code=303)
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


# ---------------------------------------------------------------------------
# Setup — name your restaurant
# ---------------------------------------------------------------------------

@router.get("/setup/restaurant", response_class=HTMLResponse)
async def setup_restaurant_page(
    request: Request,
    auth: AuthContext = Depends(require_auth),
):
    # Already has a site — skip to workspace
    if auth.site_id is not None:
        return RedirectResponse(url="/admin/", status_code=303)

    return templates.TemplateResponse(
        "auth/setup_restaurant.html",
        {
            "request": request,
            "csrf_token": generate_csrf_token(auth),
            "base_domain": settings.PLATFORM_BASE_DOMAIN,
        },
    )


@router.post("/setup/restaurant")
async def setup_restaurant_submit(
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    restaurant_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Already has a site — don't create a second one
    if auth.site_id is not None:
        return RedirectResponse(url="/admin/", status_code=303)

    restaurant_name = restaurant_name.strip()
    if not restaurant_name:
        return templates.TemplateResponse(
            "auth/setup_restaurant.html",
            {
                "request": request,
                "csrf_token": generate_csrf_token(auth),
                "base_domain": settings.PLATFORM_BASE_DOMAIN,
                "errors": ["Restaurant name is required."],
            },
            status_code=400,
        )

    site = await site_coordinator.create_site(db, auth, restaurant_name)

    # The auth context is frozen (site_id=None still). The session cookie
    # already contains the user_id, and on the next request get_auth_context
    # will reload the user row (which now has site_id set). No need to
    # re-issue the cookie.
    return RedirectResponse(url="/admin/", status_code=303)
