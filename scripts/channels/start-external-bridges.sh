#!/usr/bin/env bash
# Start OctoAgent-owned external communication bridges.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAPCAT_HOME="${OCTO_NAPCAT_HOME:-$REPO_ROOT/runtime/tools/napcat}"
NAPCAT_START="${NAPCAT_START:-$NAPCAT_HOME/start.sh}"
QQ_BRIDGE_SCRIPT="$REPO_ROOT/scripts/channels/qq_bridge.py"
NAPCAT_PID="$REPO_ROOT/runtime/pids/napcat.pid"
QQ_BRIDGE_PID="$REPO_ROOT/runtime/pids/qq_bridge.pid"
QQ_BRIDGE_LOG="$REPO_ROOT/runtime/logs/qq_bridge.log"
PYTHON_BIN="${OCTO_QQ_BRIDGE_PYTHON:-$REPO_ROOT/backend/.venv/bin/python}"
NAPCAT_HEALTH_URL="${NAPCAT_HEALTH_URL:-http://127.0.0.1:19884/get_login_info}"

mkdir -p "$REPO_ROOT/runtime/pids" "$REPO_ROOT/runtime/logs"

if [ -f "$NAPCAT_START" ]; then
    if [ -f "$NAPCAT_PID" ] && kill -0 "$(cat "$NAPCAT_PID")" 2>/dev/null; then
        echo "  NapCatQQ is already running."
    else
        rm -f "$NAPCAT_PID"
        echo "  Starting NapCatQQ from $NAPCAT_HOME..."
        "$NAPCAT_START" || true
    fi
else
    echo "  NapCatQQ is not installed at $NAPCAT_HOME; QQ login will wait until scripts/channels/install-napcat.sh is run."
fi

if [ -f "$QQ_BRIDGE_SCRIPT" ] && [ -x "$PYTHON_BIN" ]; then
    echo "  Starting QQ Bridge..."
    if [ -f "$QQ_BRIDGE_PID" ] && kill -0 "$(cat "$QQ_BRIDGE_PID")" 2>/dev/null; then
        echo "    QQ Bridge is already running."
    else
        export NAPCAT_API_URL="${NAPCAT_API_URL:-http://127.0.0.1:19884}"
        export QQ_BRIDGE_SHARED_SECRET="${QQ_BRIDGE_SHARED_SECRET:-change-me}"
        export OCTO_BASE_URL="${OCTO_BASE_URL:-http://127.0.0.1:19800}"
        nohup "$PYTHON_BIN" "$QQ_BRIDGE_SCRIPT" > "$QQ_BRIDGE_LOG" 2>&1 &
        echo $! > "$QQ_BRIDGE_PID"
    fi
else
    echo "  QQ Bridge script or backend Python is missing; skipped."
fi

if command -v curl >/dev/null 2>&1; then
    curl -fsS -X POST "$NAPCAT_HEALTH_URL" >/dev/null 2>&1 || true
fi
