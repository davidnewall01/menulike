#!/usr/bin/env bash
# Reset dev (macOS): ensure Postgres (Docker), drop DB, migrate, seed, start server.
# Mac equivalent of scripts/reset_dev.ps1.
#
# Usage: ./scripts/reset_dev.sh
#
# Prereqs (one-time):
#   - Docker running
#   - A Python venv with deps:   python3 -m venv .venv
#                                source .venv/bin/activate
#                                pip install -r requirements.txt
set -euo pipefail

PORT=8000
PG_CONTAINER="menulike-pg"
PG_PORT=5433            # host port -> matches DATABASE_URL in .env (parity with Windows)
PG_USER="menulike"      # matches postgresql://menulike:menulike@localhost:5433/menulike in .env
PG_PASSWORD="menulike"
PG_DB="menulike"

# Run from repo root regardless of where the script is invoked from.
cd "$(dirname "$0")/.."

# Use the project venv if present so alembic/uvicorn resolve.
if [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

dexec() { docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" "$@"; }

# --- Ensure Postgres container ---------------------------------------------
if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running - start Docker Desktop and retry." >&2
    exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    :  # already running
elif docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "--- Starting existing Postgres container '$PG_CONTAINER' ---"
    docker start "$PG_CONTAINER" >/dev/null
else
    echo "--- Creating Postgres container '$PG_CONTAINER' ---"
    docker run -d --name "$PG_CONTAINER" \
        -e POSTGRES_USER="$PG_USER" \
        -e POSTGRES_PASSWORD="$PG_PASSWORD" \
        -e POSTGRES_DB="$PG_DB" \
        -p "$PG_PORT:5432" \
        -v menulike-pgdata:/var/lib/postgresql/data \
        postgres:16 >/dev/null
fi

echo "--- Waiting for Postgres to accept connections ---"
until dexec pg_isready -U "$PG_USER" -q; do
    sleep 1
done

# --- Stop server holding $PORT ---------------------------------------------
PIDS=$(lsof -ti "tcp:$PORT" 2>/dev/null || true)
if [[ -n "$PIDS" ]]; then
    echo "Killing PID(s) $PIDS holding port $PORT"
    # shellcheck disable=SC2086
    kill -9 $PIDS 2>/dev/null || true
    sleep 1
fi

# --- Drop & recreate DB -----------------------------------------------------
echo ""
echo "--- Dropping and recreating database ---"

# Terminate all other connections to the DB first.
dexec psql -U "$PG_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$PG_DB' AND pid <> pg_backend_pid();" >/dev/null

dexec psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS $PG_DB;"
dexec psql -U "$PG_USER" -d postgres -c "CREATE DATABASE $PG_DB;"
echo "Database recreated."

# --- Migrations -------------------------------------------------------------
echo ""
echo "--- Running migrations ---"
python -m alembic upgrade head

# --- Seed -------------------------------------------------------------------
echo ""
echo "--- Seeding Porto Azzurro ---"
python -m scripts.seed_porto_azzurro

echo ""
echo "--- Seeding admin users ---"
python -m scripts.seed_admin_users

# --- Start server -----------------------------------------------------------
echo ""
echo "--- Starting uvicorn on port $PORT ---"
python -m uvicorn app.main:app --port "$PORT"
