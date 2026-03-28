#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
cd backend
uv sync --extra dev
uv run pyinstaller --onefile --name agentpm-api --paths src entrypoint.py
TARGET_TRIPLE=$(rustc --print host-tuple)
mkdir -p ../apps/desktop/src-tauri/binaries
cp dist/agentpm-api ../apps/desktop/src-tauri/binaries/agentpm-api-${TARGET_TRIPLE}
