"""Async engine + session factory and the FastAPI `get_db` dependency.

The coordinator layer owns the commit boundary — `get_db` only yields a session
and guarantees it is closed. Services flush; they never commit.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _to_async_url(url: str) -> str:
    """Rewrite a plain postgresql:// URL to the asyncpg driver.

    Leaves an already-qualified driver (e.g. postgresql+asyncpg://) untouched.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


engine = create_async_engine(
    _to_async_url(settings.DATABASE_URL),
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()
