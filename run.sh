#!/usr/bin/env bash
# Convenience launcher: activates the venv, loads .env if present (same
# file the systemd service in deploy/ reads), and starts the server.
# Usage: ./run.sh [extra uvicorn args, e.g. --port 8001]
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "No .venv found -- run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
fi
source .venv/bin/activate

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

exec python -m uvicorn app.network.server:app --host 0.0.0.0 --port 8000 "$@"
