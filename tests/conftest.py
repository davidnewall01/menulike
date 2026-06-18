"""Test fixtures — rollback-per-test against the dev DB.

One connection, one transaction per test. The app's get_db is overridden to
yield the same session the factories write through, so endpoints see fixture
data without a real commit. Everything rolls back at the end of each test.

A test-local engine with NullPool avoids "Future attached to a different loop"
issues with the module-level engine in session.py.
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import _to_async_url, get_db
from app.main import app
from app.models.site import Site
from app.models.user import User


# ---------------------------------------------------------------------------
# Test-local engine (NullPool, one per session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _test_engine():
    engine = create_async_engine(
        _to_async_url(settings.DATABASE_URL),
        poolclass=pool.NullPool,
    )
    yield engine


# ---------------------------------------------------------------------------
# Per-test rollback session
# ---------------------------------------------------------------------------

@pytest.fixture()
async def db_session(_test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session bound to a transaction that rolls back after the test."""
    conn = await _test_engine.connect()
    txn = await conn.begin()

    session = AsyncSession(
        bind=conn,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    yield session

    await session.close()
    await txn.rollback()
    await conn.close()


# ---------------------------------------------------------------------------
# App client with get_db override
# ---------------------------------------------------------------------------

@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the app with the test session override."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Data factories
# ---------------------------------------------------------------------------

async def make_site(
    db_session: AsyncSession,
    slug: str = "testsite",
    name: str = "Test Restaurant",
    **overrides,
) -> Site:
    """Insert a site into the test transaction."""
    fields = dict(
        slug=slug,
        restaurant_name=name,
        settings={},
    )
    fields.update(overrides)
    site = Site(**fields)
    db_session.add(site)
    await db_session.flush()
    return site


async def make_owner(
    db_session: AsyncSession,
    site: Site,
    email: str | None = None,
    password: str = "testpass",
) -> User:
    """Insert an owner user scoped to the given site."""
    user = User(
        email=email or f"owner-{uuid.uuid4().hex[:8]}@test.dev",
        password_hash=hash_password(password),
        role="owner",
        site_id=site.site_id,
    )
    db_session.add(user)
    await db_session.flush()
    return user
