#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
(
  cd backend
  uv sync
  uv run agentpm-server serve --reload
) &
BACKEND_PID=$!
cleanup() {
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cd apps/desktop
npm install
npm run dev
