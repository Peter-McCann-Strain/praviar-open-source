#!/usr/bin/env bash
# Thin wrapper around the API dev CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

usage() {
  echo "Usage: APP_ENV=dev DATABASE_URL=<dev-db-url> $0" >&2
  echo "   or: APP_ENV=dev $0 <dev-db-url>" >&2
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$#" -gt 1 ]]; then
  usage
  exit 2
fi

if [[ "${APP_ENV:-}" != "dev" ]]; then
  echo "ERROR: APP_ENV=dev is required for scripts/seed-db.sh." >&2
  exit 2
fi

if [[ "$#" -eq 1 ]]; then
  export DATABASE_URL="$1"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: provide an explicit dev database target via DATABASE_URL or argv." >&2
  usage
  exit 2
fi

cd "$PROJECT_ROOT/api"
python -m alembic upgrade head
PYTHONPATH=src python -m api.cli seed-dev-db
