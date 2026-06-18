"""Auth dependencies for FastAPI routes."""

import uuid

from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.core.security import decode_session
from app.db.session import get_db
from app.models.user import User

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
        role=user.role,
        site_id=user.site_id,
    )


def require_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency alias — makes intent explicit at the route level."""
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
