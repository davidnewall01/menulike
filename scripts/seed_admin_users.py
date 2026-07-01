"""Seed admin users for local development.

Idempotent: deletes existing users by email before inserting fresh.
Refuses to run unless ENVIRONMENT=development.

Usage:
    python -m scripts.seed_admin_users
"""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

if settings.ENVIRONMENT != "development":
    print(f"FATAL: seed scripts are dev-only (ENVIRONMENT={settings.ENVIRONMENT})")
    sys.exit(1)

USERS = [
    {
        "email": "admin@menulike.dev",
        "password": "admin123",
        "role": "internal_admin",
        "site_slug": None,
    },
    {
        "email": "owner@portoazzurro.dev",
        "password": "owner123",
        "role": "owner",
        "site_slug": "portoazzurro",
    },
    {
        "email": "owner@kin.dev",
        "password": "owner123",
        "role": "owner",
        "site_slug": "kin",
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        for spec in USERS:
            # Delete existing user if present
            result = await session.execute(
                select(User).where(User.email == spec["email"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                await session.delete(existing)
                await session.flush()
                print(f"Deleted existing user: {spec['email']}")

            # Resolve site_id for owners
            site_id = None
            if spec["site_slug"]:
                result = await session.execute(
                    select(Site).where(Site.slug == spec["site_slug"])
                )
                site = result.scalar_one_or_none()
                if site is None:
                    print(
                        f"ERROR: Site '{spec['site_slug']}' not found. "
                        f"Run seed_porto_azzurro first."
                    )
                    return
                site_id = site.site_id

            # Validate role against the enum
            try:
                UserRole(spec["role"])
            except ValueError:
                print(f"ERROR: Invalid role '{spec['role']}'. Must be one of {[r.value for r in UserRole]}")
                return

            user = User(
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                role=spec["role"],
                site_id=site_id,
            )
            session.add(user)
            await session.flush()
            print(
                f"Created user: {spec['email']} "
                f"(role={spec['role']}, site_id={site_id})"
            )

        await session.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
