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
