#!/usr/bin/env bash
#
# Stop all OctoAgent local services and free the configured ports.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

source "$REPO_ROOT/scripts/port-layout.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "Usage: $0"
    echo "  Stop all local OctoAgent services and free configured ports."
    exit 0
fi

if [ "$#" -gt 0 ]; then
    echo "Unknown argument: $1"
    echo "Usage: $0"
    exit 1
fi

kill_port_owners() {
    local port="$1"

    if command -v lsof >/dev/null 2>&1; then
        lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -TERM 2>/dev/null || true
        sleep 1
        lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -KILL 2>/dev/null || true
        return
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "( sport = :$port )" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            | xargs -r kill -TERM 2>/dev/null || true
        sleep 1
        ss -ltnp "( sport = :$port )" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            | xargs -r kill -KILL 2>/dev/null || true
    fi

    if command -v fuser >/dev/null 2>&1; then
        timeout 10 fuser -k "${port}/tcp" 2>/dev/null || true
        sleep 1
    fi
}

wait_for_port_free() {
    local port="$1"
    local label="$2"
    for _ in $(seq 1 20); do
        if ! ss -ltn "( sport = :$port )" 2>/dev/null | grep -q ":$port"; then
            return 0
        fi
        kill_port_owners "$port"
        sleep 0.5
    done
    echo "Warning: $label port $port is still occupied after stop attempts." >&2
    ss -ltnp "( sport = :$port )" 2>/dev/null >&2 || true
    return 1
}

stop_by_pattern() {
    local pattern="$1"
    pkill -TERM -f "$pattern" 2>/dev/null || true
}

force_by_pattern() {
    local pattern="$1"
    pkill -KILL -f "$pattern" 2>/dev/null || true
}

echo "Stopping OctoAgent services..."
if [ "${OCTOAGENT_MANAGE_EXTERNAL_BRIDGES:-1}" = "1" ]; then
    "$REPO_ROOT/scripts/channels/stop-external-bridges.sh" 2>/dev/null || true
else
    echo "  Leaving external bridge channels running; managed by dedicated channel services."
fi
stop_by_pattern "langgraph dev"
stop_by_pattern "langgraph_cli dev"
stop_by_pattern "python -m langgraph_cli"
stop_by_pattern "uvicorn src.gateway.app:app"
stop_by_pattern "next dev"
stop_by_pattern "next start"
stop_by_pattern "next-server"
stop_by_pattern "scripts/run_execution_worker.py"
stop_by_pattern "ttyd --interface 127.0.0.1 --port $TTYD_PORT"
if [ -f "$REPO_ROOT/runtime/pids/ttyd.pid" ]; then
    kill -TERM "$(cat "$REPO_ROOT/runtime/pids/ttyd.pid")" 2>/dev/null || true
fi

if [ -f "$REPO_ROOT/tmp/nginx.local.conf" ]; then
    nginx -c "$REPO_ROOT/tmp/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
fi

sleep 1

force_by_pattern "langgraph dev"
force_by_pattern "langgraph_cli dev"
force_by_pattern "python -m langgraph_cli"
force_by_pattern "uvicorn src.gateway.app:app"
force_by_pattern "next dev"
force_by_pattern "next start"
force_by_pattern "next-server"
force_by_pattern "scripts/run_execution_worker.py"
force_by_pattern "ttyd --interface 127.0.0.1 --port $TTYD_PORT"
kill_port_owners "$LANGGRAPH_PORT"
kill_port_owners "$GATEWAY_PORT"
kill_port_owners "$FRONTEND_PORT"
kill_port_owners "$NGINX_PORT"
kill_port_owners "$TTYD_PORT"

wait_for_port_free "$LANGGRAPH_PORT" "LangGraph" || true
wait_for_port_free "$GATEWAY_PORT" "Gateway" || true
wait_for_port_free "$FRONTEND_PORT" "Frontend" || true
wait_for_port_free "$NGINX_PORT" "Nginx" || true
wait_for_port_free "$TTYD_PORT" "ttyd" || true
rm -f "$REPO_ROOT/runtime/pids/ttyd.pid"

# LangGraph's local dev runtime persists its in-memory queue under
# backend/.langgraph_api.  After a crash or forced browser disconnect, stale
# running/pending runs can be replayed on the next boot and block the single
# local worker.  It is transient runtime state, so clear it only after every
# service has stopped and the ports are free.
# Do NOT rm -rf .langgraph_api: that wipes .langgraph_ops.pckl (thread registry).
# Thread history would be lost on every restart. Only purge stale tmp files if any.
find "$REPO_ROOT/backend/.langgraph_api" -maxdepth 1 -name '*.tmp' -delete 2>/dev/null || true

"$REPO_ROOT/scripts/cleanup-containers.sh" octoagent-sandbox 2>/dev/null || true

echo "OctoAgent services stopped."
