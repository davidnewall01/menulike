#!/usr/bin/env bash
# Kill whatever holds port 8000, then start uvicorn.
# Mac equivalent of scripts/start_service.ps1.
#
# Usage: ./scripts/start_service.sh
set -euo pipefail

PORT=8000

# Run from repo root regardless of where the script is invoked from.
cd "$(dirname "$0")/.."

# Use the project venv if present so uvicorn resolves.
if [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# --- Kill whatever holds $PORT ---------------------------------------------
PIDS=$(lsof -ti "tcp:$PORT" 2>/dev/null || true)
for p in $PIDS; do
    echo "Killing PID $p (holding port $PORT)"
    kill -9 "$p" 2>/dev/null || true
done

# --- Wait until port is actually free (up to 10 seconds) -------------------
for i in $(seq 1 20); do
    if ! lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
        break
    fi
    if [[ "$i" -eq 1 ]]; then
        echo "Waiting for port $PORT to free..."
    fi
    sleep 0.5
done

if lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
    echo "ERROR: port $PORT still occupied after 10s. Try restarting manually." >&2
    exit 1
fi

# --- Start server -----------------------------------------------------------
# --reload picks up Python/template edits without a manual restart (dev only).
python -m uvicorn app.main:app --port "$PORT" --reload
