"""Auth queries for the login flow."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """Verify credentials and return the User, or None on failure."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user
