#!/bin/bash
# Starts the REZOLV API (:8787) and the web app (:5173) for the demo.
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"
python3 backend/run.py &
API=$!
trap "kill $API 2>/dev/null" EXIT
cd frontend
[ -d node_modules ] || npm install --no-audit --no-fund
npm run dev -- --host 127.0.0.1 --port 5173
