#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./sachkhoj.db}"
export CURATED_DATA_DIR="${CURATED_DATA_DIR:-$ROOT/data/curated}"
export UPLOAD_DIR="${UPLOAD_DIR:-$ROOT/backend/uploads}"
export ADMIN_TOKEN="${ADMIN_TOKEN:-dev-admin-token}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
