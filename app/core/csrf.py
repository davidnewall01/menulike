"""Stateless, session-bound CSRF tokens.

Each token is an HMAC-SHA256 signature over (user_id, nonce, issued_at),
keyed with JWT_SECRET_KEY. Validation checks the signature, session binding
(user_id must match the current AuthContext), and expiry.

Login CSRF is a known gap, deferred on impact: a forced login drops the
victim into the attacker's tenant, which is confusion, not a data leak.
SameSite=lax does NOT cover this (the cross-site POST still goes through
for a fresh login that sets a cookie). Revisit if the threat model shifts.
"""

import hashlib
import hmac
import os
import time

from app.auth.context import AuthContext
from app.core.config import settings

_CSRF_LIFETIME_SECONDS = 8 * 60 * 60  # 8 hours


def _sign(message: str) -> str:
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def generate_csrf_token(auth_ctx: AuthContext) -> str:
    """Produce a token bound to the current session's user_id."""
    nonce = os.urandom(16).hex()
    issued = str(int(time.time()))
    payload = f"{auth_ctx.user_id}:{nonce}:{issued}"
    sig = _sign(payload)
    return f"{payload}:{sig}"


def validate_csrf_token(token: str | None, auth_ctx: AuthContext) -> bool:
    """Verify signature, session binding, and expiry."""
    if not token:
        return False

    parts = token.split(":")
    if len(parts) != 4:
        return False

    user_id_str, nonce, issued_str, sig = parts

    # Session binding
    if user_id_str != str(auth_ctx.user_id):
        return False

    # Signature
    payload = f"{user_id_str}:{nonce}:{issued_str}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return False

    # Expiry
    try:
        issued = int(issued_str)
    except ValueError:
        return False
    if time.time() - issued > _CSRF_LIFETIME_SECONDS:
        return False

    return True
