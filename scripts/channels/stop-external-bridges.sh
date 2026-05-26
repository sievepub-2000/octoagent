#!/usr/bin/env bash
# Stop OctoAgent-owned external communication bridges.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAPCAT_PID="$REPO_ROOT/runtime/pids/napcat.pid"
QQ_BRIDGE_PID="$REPO_ROOT/runtime/pids/qq_bridge.pid"

stop_pid_file() {
    local pid_file="$1"
    local label="$2"

    if [ ! -f "$pid_file" ]; then
        return 0
    fi

    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "  Stopping $label ($pid)..."
        kill -TERM "$pid" 2>/dev/null || true
        sleep 1
        kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
}

stop_pid_file "$QQ_BRIDGE_PID" "QQ Bridge"
stop_pid_file "$NAPCAT_PID" "NapCatQQ"

pkill -TERM -f "$REPO_ROOT/scripts/channels/qq_bridge.py" 2>/dev/null || true
pkill -TERM -f "$REPO_ROOT/runtime/tools/napcat/opt/QQ/qq" 2>/dev/null || true
sleep 1
pkill -KILL -f "$REPO_ROOT/scripts/channels/qq_bridge.py" 2>/dev/null || true
pkill -KILL -f "$REPO_ROOT/runtime/tools/napcat/opt/QQ/qq" 2>/dev/null || true
