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

from app.auth.context import AuthContext
from app.core.config import settings
from app.core.csrf import generate_csrf_token
from app.core.security import hash_password
from app.db.session import _to_async_url, get_db
from app.main import app
from app.models.menu import Menu, MenuItem, MenuItemVariant, Section, Subsection
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


async def make_owner_no_site(
    db_session: AsyncSession,
    email: str | None = None,
    password: str = "testpass",
) -> User:
    """Insert an owner user with NO site (the signup state)."""
    user = User(
        email=email or f"owner-{uuid.uuid4().hex[:8]}@test.dev",
        password_hash=hash_password(password),
        role="owner",
        site_id=None,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def make_menu(
    db_session: AsyncSession,
    site: Site,
    name: str = "Test Menu",
    position: int = 10,
    **overrides,
) -> Menu:
    """Insert a menu into the test transaction."""
    fields = dict(
        site_id=site.site_id,
        name=name,
        position=position,
    )
    fields.update(overrides)
    menu = Menu(**fields)
    db_session.add(menu)
    await db_session.flush()
    return menu


async def make_section(
    db_session: AsyncSession,
    menu: Menu,
    name: str = "Test Section",
    position: int = 10,
) -> Section:
    section = Section(
        menu_id=menu.menu_id,
        name=name,
        position=position,
    )
    db_session.add(section)
    await db_session.flush()
    return section


async def make_subsection(
    db_session: AsyncSession,
    section: Section,
    name: str | None = None,
    position: int = 10,
) -> Subsection:
    subsection = Subsection(
        section_id=section.section_id,
        name=name,
        position=position,
    )
    db_session.add(subsection)
    await db_session.flush()
    return subsection


async def make_item(
    db_session: AsyncSession,
    subsection: Subsection,
    name: str = "Test Item",
    position: int = 10,
    **overrides,
) -> MenuItem:
    fields = dict(
        subsection_id=subsection.subsection_id,
        name=name,
        position=position,
        dietary_tags=[],
        featured=False,
    )
    fields.update(overrides)
    item = MenuItem(**fields)
    db_session.add(item)
    await db_session.flush()
    return item


async def make_variant(
    db_session: AsyncSession,
    item: MenuItem,
    price: str = "10.00",
    label: str | None = None,
    position: int = 10,
) -> MenuItemVariant:
    from decimal import Decimal
    variant = MenuItemVariant(
        menu_item_id=item.menu_item_id,
        label=label,
        price=Decimal(price),
        position=position,
    )
    db_session.add(variant)
    await db_session.flush()
    return variant


def csrf_token_for(user: User) -> str:
    """Generate a valid CSRF token bound to the given user's identity."""
    ctx = AuthContext(
        user_id=user.user_id,
        email=user.email,
        role=user.role,
        site_id=user.site_id,
    )
    return generate_csrf_token(ctx)
