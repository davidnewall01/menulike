#!/usr/bin/env bash
# Restore the local dev DB from the golden snapshot, then apply newer migrations.
#
# Flow: drop DB -> recreate empty -> pg_restore the snapshot (schema + content
# at the snapshot's migration version) -> alembic upgrade head (applies any
# migrations added since the snapshot was taken).
#
# S3 note: restored Photo rows reference s3_key objects that must still exist in
# the bucket. This does not touch S3.
#
# Usage: ./scripts/db_restore.sh [-y]
#   -y   skip the destructive-action confirmation (for automation)
set -euo pipefail

PG_CONTAINER="menulike-pg"
PG_USER="menulike"
PG_PASSWORD="menulike"
PG_DB="menulike"

cd "$(dirname "$0")/.."
SNAP="scripts/snapshots/dev.dump"

ASSUME_YES=0
[[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]] && ASSUME_YES=1

# Use the project venv so alembic resolves.
if [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "Postgres container '$PG_CONTAINER' is not running. Start it (or run reset_dev.sh) first." >&2
    exit 1
fi
if [[ ! -f "$SNAP" ]]; then
    echo "No snapshot found at $SNAP. Take one first: ./scripts/db_snapshot.sh" >&2
    exit 1
fi

if [[ "$ASSUME_YES" -eq 0 ]]; then
    snap_date=$(date -r "$SNAP" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")
    echo "This will DROP the local '$PG_DB' database and restore from:"
    echo "    $SNAP ($snap_date)"
    printf "Continue? [y/N] "
    read -r reply
    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
        echo "Aborted — database unchanged."
        exit 0
    fi
fi

dexec() { docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" "$@"; }

echo "--- Dropping and recreating database ---"
dexec psql -U "$PG_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PG_DB' AND pid<>pg_backend_pid();" >/dev/null
dexec psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS $PG_DB;"
dexec psql -U "$PG_USER" -d postgres -c "CREATE DATABASE $PG_DB;"

echo "--- Restoring snapshot ---"
docker exec -i -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" \
    pg_restore -U "$PG_USER" -d "$PG_DB" --no-owner --no-privileges < "$SNAP"

echo "--- Applying any newer migrations ---"
python -m alembic upgrade head

echo "Restore complete."
