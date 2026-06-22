"""Auth dependencies for FastAPI routes."""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.core.csrf import generate_csrf_token, validate_csrf_token
from app.core.security import decode_session
from app.db.session import get_db
from app.models.user import User
from app.services.exceptions import OwnerNeedsSetup

SESSION_COOKIE = "session"


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Read the session cookie, decode, load the user, return AuthContext.

    Returns 401 (or redirects to login for browser requests) on
    missing/invalid cookie or unknown user.
    """
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        _raise_unauth(request)

    user_id = decode_session(token)
    if user_id is None:
        _raise_unauth(request)

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        _raise_unauth(request)

    return AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )


def require_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency alias — makes intent explicit at the route level."""
    return auth


def require_owner_site(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    """Gate: an owner with no site yet must complete setup first.

    Keys on role — internal_admin ALSO has site_id=None but must NOT be
    caught by this gate.  Only owner + no site triggers the redirect.
    Raises OwnerNeedsSetup (handled by an app-level exception handler
    that returns a real RedirectResponse — NOT HTTPException(303), which
    FastAPI renders as JSON).
    """
    if not auth.is_internal_admin and auth.site_id is None:
        raise OwnerNeedsSetup()
    return auth


async def require_csrf(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """Validate the CSRF token on an authenticated state-changing POST.

    Reads csrf_token from the form body. Returns the AuthContext on success;
    raises 403 on missing, invalid, or session-mismatched token.
    """
    form = await request.form()
    token = form.get("csrf_token")
    if not validate_csrf_token(token, auth):
        raise HTTPException(
            status_code=403,
            detail="CSRF validation failed",
            headers={"X-CSRF-Fail": "1"},
        )
    return auth


async def require_csrf_owner_site(
    request: Request,
    auth: AuthContext = Depends(require_owner_site),
) -> AuthContext:
    """CSRF + owner-must-have-site combined dependency for POST routes."""
    form = await request.form()
    token = form.get("csrf_token")
    if not validate_csrf_token(token, auth):
        raise HTTPException(
            status_code=403,
            detail="CSRF validation failed",
            headers={"X-CSRF-Fail": "1"},
        )
    return auth


def _raise_unauth(request: Request):
    """401 for API calls, redirect to login for browser navigation."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/admin/login"},
        )
    raise HTTPException(status_code=401, detail="Not authenticated")
