#!/usr/bin/env bash
# Run OctoAgent daily self-check, environment repair, safe update, and memory record.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

mkdir -p "$REPO_ROOT/runtime/logs" "$REPO_ROOT/workspace/runtime/maintenance"
LOG_FILE="$REPO_ROOT/runtime/logs/daily-self-check.log"

PYTHON_BIN="${OCTO_DAILY_SELF_CHECK_PYTHON:-${OCTOAGENT_PYTHON_BIN:-$REPO_ROOT/backend/.venv/bin/python}}"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "OctoAgent backend venv not found at $PYTHON_BIN" >&2
    exit 1
fi

exec >> "$LOG_FILE" 2>&1

echo "===== OctoAgent daily self-check $(date -Is) ====="
"$PYTHON_BIN" "$REPO_ROOT/backend/scripts/daily_self_check.py" "$@"
