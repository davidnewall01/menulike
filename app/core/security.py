"""Password hashing and session-token encoding/decoding."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

_ALGORITHM = "HS256"
SESSION_LIFETIME = timedelta(days=7)


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def encode_session(user_id: uuid.UUID) -> str:
    """Create a signed JWT containing the user_id claim with expiry."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + SESSION_LIFETIME,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_session(token: str) -> uuid.UUID | None:
    """Decode a session token, returning the user_id or None on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        return uuid.UUID(sub)
    except (JWTError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Act-as scope (admin concierge) — separate signed token, short-lived.
#
# This is a SEPARATE cookie from the login session. The login session carries
# the admin's identity (user_id, 7-day TTL). The act-as cookie carries ONLY
# the target site_id with a short TTL (~1 hour). When it expires the admin
# drops back to no-scope cleanly — the login session is unaffected.
#
# The act-as cookie is ONLY read for internal_admin users. Owner sessions
# NEVER read it — branch on role FIRST in AuthContext.scoped_site_id.
# ---------------------------------------------------------------------------

ACT_AS_LIFETIME = timedelta(hours=1)
ACT_AS_COOKIE = "act_as"


def encode_act_as(site_id: uuid.UUID) -> str:
    """Create a signed, short-lived JWT carrying the target site_id."""
    payload = {
        "site_id": str(site_id),
        "exp": datetime.now(timezone.utc) + ACT_AS_LIFETIME,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_act_as(token: str) -> uuid.UUID | None:
    """Decode an act-as token, returning the site_id or None on failure/expiry."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
        site_id_str = payload.get("site_id")
        if site_id_str is None:
            return None
        return uuid.UUID(site_id_str)
    except (JWTError, ValueError):
        return None
