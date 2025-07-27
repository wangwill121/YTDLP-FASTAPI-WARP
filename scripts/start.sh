#!/bin/sh
set -e

echo "[DEBUG] boot script started."
PORT="${PORT:-8000}"
WORKERS=1
echo "[DEBUG] PORT=$PORT"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --log-level info 2>&1
