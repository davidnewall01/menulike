#!/usr/bin/env bash
# Snapshot the local dev DB to a golden dump (pg_dump custom format).
#
# This captures the full DB — schema + content + alembic version — so it can be
# restored later with scripts/db_restore.sh. It does NOT capture S3 image
# binaries: restored Photo rows point at the same s3_key objects, which must
# still exist in the bucket. Set them up once via the admin UI, then snapshot.
#
# Usage: ./scripts/db_snapshot.sh [-y]
#   -y   skip the overwrite confirmation (for automation)
set -euo pipefail

PG_CONTAINER="menulike-pg"
PG_USER="menulike"
PG_PASSWORD="menulike"
PG_DB="menulike"

cd "$(dirname "$0")/.."
SNAP_DIR="scripts/snapshots"
SNAP="$SNAP_DIR/dev.dump"
mkdir -p "$SNAP_DIR"

ASSUME_YES=0
[[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]] && ASSUME_YES=1

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "Postgres container '$PG_CONTAINER' is not running. Start it (or run reset_dev.sh) first." >&2
    exit 1
fi

# Confirm before clobbering an existing golden snapshot.
if [[ -f "$SNAP" && "$ASSUME_YES" -eq 0 ]]; then
    existing_date=$(date -r "$SNAP" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")
    existing_size=$(du -h "$SNAP" | cut -f1)
    echo "A snapshot already exists: $SNAP ($existing_size, $existing_date)"
    printf "Overwrite it? The current one is kept as dev.dump.prev. [y/N] "
    read -r reply
    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
        echo "Aborted — no snapshot taken."
        exit 0
    fi
fi

# Dump to a temp file first so a failure never corrupts the golden snapshot.
TMP="$SNAP.tmp"
echo "--- Dumping $PG_DB (custom format) ---"
docker exec -e PGPASSWORD="$PG_PASSWORD" "$PG_CONTAINER" \
    pg_dump -U "$PG_USER" -Fc "$PG_DB" > "$TMP"

# Rotate the previous snapshot, then move the new one into place.
[[ -f "$SNAP" ]] && mv "$SNAP" "$SNAP.prev"
mv "$TMP" "$SNAP"

echo "Snapshot written: $SNAP ($(du -h "$SNAP" | cut -f1))"
echo "Restore with: ./scripts/db_restore.sh"
