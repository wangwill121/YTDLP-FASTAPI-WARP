#!/bin/bash
# Exit on error
set -e

# Canary log - a simple message to confirm the script is running
echo "[DEBUG] boot script started."

# Hardcode variables for the Railway environment
PORT=${PORT:-8000}
WORKERS=1

echo "[DEBUG] PORT=${PORT}"
echo "[DEBUG] WORKERS=${WORKERS}"
echo "[DEBUG] Launching Uvicorn..."

# Execute the application, redirecting stderr to stdout to capture all logs
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level info 2>&1
