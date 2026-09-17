#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi

echo "=================================================="
echo "🚀 Starting Job Radar Dashboard on http://${HOST}:${PORT}"
echo "=================================================="

exec venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
