#!/usr/bin/env bash
# Thin wrapper around the backend-owned contract codegen CLI.

set -euo pipefail

# Stabilise code-generation ordering and text encoding across developer and CI
# environments. The generated contract contains no locale- or time-dependent
# content, so these settings make that invariant explicit.
export LANG=C
export LC_ALL=C
export PYTHONHASHSEED=0
export PYTHONUTF8=1
export TZ=UTC
umask 022

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT/api"
export APP_ENV="${APP_ENV:-dev}"
PYTHONPATH=src python -m api.cli generate-shared-types

# Sync generated types into the web bundle (avoids the pnpm workspace:* dependency on Vercel)
CANONICAL_TYPES="$PROJECT_ROOT/packages/shared-types/src/generated.ts"
WEB_TYPES="$PROJECT_ROOT/web/src/lib/shared-types/generated.ts"
cp "$CANONICAL_TYPES" "$WEB_TYPES"

# The web copy is a byte-for-byte mirror, not an independently formatted
# generated artefact. Fail here if a future sync mechanism violates that
# contract before CI evaluates repository drift.
if ! cmp -s "$CANONICAL_TYPES" "$WEB_TYPES"; then
  echo "Generated shared-type mirror differs from the canonical contract." >&2
  exit 1
fi
