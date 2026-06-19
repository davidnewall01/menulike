"""Single source of application configuration.

All config flows through the `settings` singleton below. Read from the
environment (and a local `.env` for dev); Railway injects these per-environment
in staging/production.
"""

import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder JWT secret shipped for local dev. If this value is still in
# place when ENVIRONMENT=production, we refuse to boot (see guard below).
DEV_JWT_SENTINEL = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres connection. A plain postgresql:// URL is fine — session.py rewrites
    # it to the asyncpg driver for the app engine; alembic strips it to sync.
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/menulike"

    # Subdomain base for {slug}.<domain> tenant resolution (wired up in a later phase).
    PLATFORM_BASE_DOMAIN: str = "menulike.app"

    # Auth signing secret. Overridden per-environment; the dev default trips the
    # production guard below.
    JWT_SECRET_KEY: str = DEV_JWT_SENTINEL

    # S3 media storage. AWS creds + bucket are required for photo uploads but
    # NOT for boot — the app runs fine without them for all non-photo work.
    # A clear error fires at use-time if unconfigured (see storage.py).
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "ap-southeast-2"
    S3_PUBLIC_BASE_URL: str = ""

    # Emit SQL to logs when true.
    DB_ECHO: bool = False

    # "development" | "production". Only "production" arms the fail-closed guard.
    ENVIRONMENT: str = "development"


settings = Settings()


# Fail closed: never run production on the shared dev secret.
if settings.ENVIRONMENT == "production" and settings.JWT_SECRET_KEY == DEV_JWT_SENTINEL:
    print(
        "FATAL: JWT_SECRET_KEY is still the dev default while ENVIRONMENT=production. "
        "Set a real secret before deploying.",
        file=sys.stderr,
    )
    sys.exit(1)
