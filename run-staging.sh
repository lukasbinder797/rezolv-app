#!/usr/bin/env bash
# Start the REZOLV Staging Environment (isolated DB on port 8788 + Vite preview on 5174).
set -euo pipefail
cd "$(dirname "$0")"

export REZOLV_ENV=staging
export REZOLV_PORT="${REZOLV_PORT:-8788}"
export REZOLV_DATA_DIR="$(pwd)/backend/data_staging"
export REZOLV_BACKUP_DIR="$(pwd)/backend/backups_staging"
export REZOLV_ORIGINS="http://localhost:5174,http://127.0.0.1:5174,https://staging.rezolv.ro"
export VITE_API_URL="http://localhost:${REZOLV_PORT}"

mkdir -p "$REZOLV_DATA_DIR" "$REZOLV_BACKUP_DIR"

PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

trap 'kill 0 2>/dev/null || true' EXIT
echo "[STAGING] Starting REZOLV API on http://127.0.0.1:${REZOLV_PORT} (env=staging)..."
"$PYTHON_BIN" backend/run.py &
cd frontend && npx vite --port 5174 --host 127.0.0.1
