#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
VENV_PYTHON="${BACKEND_DIR}/.venv/bin/python"
VENV_CELERY="${BACKEND_DIR}/.venv/bin/celery"

if [[ ! -x "${VENV_PYTHON}" ]] || [[ ! -x "${VENV_CELERY}" ]]; then
    echo "Error: Virtual environment not found at ${BACKEND_DIR}/.venv." >&2
    echo "Please set up the backend virtual environment first." >&2
    exit 1
fi

echo "Checking required services..."

"${VENV_PYTHON}" - << 'EOF'
import socket
import sys

def check_port(host: str, port: int, name: str) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3.0):
            print(f"  [OK] {name} is reachable on {host}:{port}")
            return True
    except OSError as e:
        print(f"  [FAIL] Cannot connect to {name} on {host}:{port}: {e}", file=sys.stderr)
        return False

ok_pg = check_port("127.0.0.1", 15432, "PostgreSQL")
ok_redis = check_port("127.0.0.1", 16379, "Redis")

if not (ok_pg and ok_redis):
    print("\nEnsure Docker containers are running: docker compose up -d", file=sys.stderr)
    sys.exit(1)
EOF

echo "Starting Celery worker (concurrency=2)..."
cd "${BACKEND_DIR}"
exec "${VENV_CELERY}" -A app.core.celery_app worker --loglevel=info --concurrency=2 "$@"
