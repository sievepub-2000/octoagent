#!/usr/bin/env bash
#
# start.sh - Start all OctoAgent development services
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

source "$REPO_ROOT/scripts/port-layout.sh"

# Use the repository-owned setup snapshot so local services do not
# drift to stale user-level setup_state.json from another checkout.
export OCTO_AGENT_SETUP_STATE_FILE="${OCTO_AGENT_SETUP_STATE_FILE:-$REPO_ROOT/workspace/env/setup.json}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
REPO_OWNER_HOME="$(getent passwd "$(stat -c %U "$REPO_ROOT" 2>/dev/null)" | cut -d: -f6)"
if [ -n "$REPO_OWNER_HOME" ] && [ -d "$REPO_OWNER_HOME/.cache/huggingface" ]; then
    export HF_HOME="${HF_HOME:-$REPO_OWNER_HOME/.cache/huggingface}"
fi

# Keep HTTP(S) proxy support, but drop ALL_PROXY because several model clients
# used by OctoAgent reject SOCKS-style proxy values in local deployments.
export ALL_PROXY=""
if $DEV_MODE && [ -z "${OCTO_SMTP_HOST:-}" ]; then
    # Local/dev installs without SMTP still need a usable registration flow.
    # The auth page displays this code only when the backend opts in here.
    export OCTO_AUTH_DEV_EXPOSE_CODES="${OCTO_AUTH_DEV_EXPOSE_CODES:-1}"
fi

NGINX_CONFIG_TEMPLATE="$REPO_ROOT/docker/nginx/nginx.local.conf.template"
NGINX_CONFIG_RENDERED="$REPO_ROOT/tmp/nginx.local.conf"

# ── Argument parsing ─────────────────────────────────────────────────────────

DEV_MODE=true
for arg in "$@"; do
    case "$arg" in
        --dev)  DEV_MODE=true ;;
        --prod) DEV_MODE=false ;;
        *) echo "Unknown argument: $arg"; echo "Usage: $0 [--dev|--prod]"; exit 1 ;;
    esac
done

mkdir -p "$REPO_ROOT/tmp"
python3 "$REPO_ROOT/scripts/render_nginx_config.py" \
    "$NGINX_CONFIG_TEMPLATE" \
    "$NGINX_CONFIG_RENDERED"

if $DEV_MODE; then
    FRONTEND_CMD="pnpm exec next dev --turbo --hostname 127.0.0.1 --port $FRONTEND_PORT"
else
    FRONTEND_CMD="env BETTER_AUTH_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(16))') pnpm exec next start --hostname 127.0.0.1 --port $FRONTEND_PORT"
fi

# ── Stop existing services ────────────────────────────────────────────────────

echo "Stopping existing services if any..."
pkill -f "langgraph dev" 2>/dev/null || true
pkill -f "langgraph_cli dev" 2>/dev/null || true
pkill -f "python -m langgraph_cli" 2>/dev/null || true
pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
nginx -c "$NGINX_CONFIG_RENDERED" -p "$REPO_ROOT" -s quit 2>/dev/null || true
sleep 1
pkill -9 nginx 2>/dev/null || true
killall -9 nginx 2>/dev/null || true
./scripts/cleanup-containers.sh octoagent-sandbox 2>/dev/null || true
sleep 1

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  Starting OctoAgent Development Server"
echo "=========================================="
echo ""
if $DEV_MODE; then
    echo "  Mode: DEV  (hot-reload enabled)"
    echo "  Tip:  run \`make start\` in production mode"
else
    echo "  Mode: PROD (hot-reload disabled)"
    echo "  Tip:  run \`make dev\` to start in development mode"
fi
echo ""
echo "Services starting up..."
echo "  → Backend: LangGraph + Gateway"
echo "  → Frontend: Next.js"
echo "  → Nginx: Reverse Proxy"
echo ""

if ! $DEV_MODE; then
    echo "Rebuilding frontend production assets..."
    (
        cd frontend
        rm -rf .next
        pnpm run build
    )
    echo "✓ Frontend production assets rebuilt"
    echo ""
fi

# ── Python runner detection ───────────────────────────────────────────────────
# Prefer the repository-owned backend venv to avoid host-level uv/lockfile drift.
if [ -f backend/.venv/bin/python ]; then
    LANGGRAPH_CMD=".venv/bin/python -m langgraph_cli"
    PY_RUN="backend/.venv/bin/python -m"
    PY_RUN_BACKEND=".venv/bin/python -m"
elif [ -f backend/.venv/Scripts/python.exe ]; then
    LANGGRAPH_CMD=".venv/Scripts/python.exe -m langgraph_cli"
    PY_RUN="backend/.venv/Scripts/python.exe -m"
    PY_RUN_BACKEND=".venv/Scripts/python.exe -m"
elif command -v uv >/dev/null 2>&1; then
    LANGGRAPH_CMD="uv run langgraph"
    PY_RUN="uv run"
    PY_RUN_BACKEND="uv run"
else
    echo "✗ Neither uv nor a backend venv found."
    echo "  Run 'make install' or './scripts/bootstrap.sh' first."
    exit 1
fi

# ── Config check ─────────────────────────────────────────────────────────────

if ! { \
        [ -n "$OCTO_AGENT_CONFIG_PATH" ] && [ -f "$OCTO_AGENT_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "✗ No OctoAgent config file found."
    echo "  Checked these locations:"
    echo "    - $OCTO_AGENT_CONFIG_PATH (when OCTO_AGENT_CONFIG_PATH is set)"
    echo "    - backend/config.yaml"
    echo "    - ./config.yaml"
    echo ""
    echo "  Run 'make config' from the repo root to generate ./config.yaml, then set required model API keys in .env or your config file."
    exit 1
fi

# ── Cleanup trap ─────────────────────────────────────────────────────────────

cleanup() {
    trap - INT TERM
    echo ""
    echo "Shutting down services..."
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "langgraph_cli dev" 2>/dev/null || true
    pkill -f "python -m langgraph_cli" 2>/dev/null || true
    pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    # Kill nginx using the captured PID first (most reliable),
    # then fall back to pkill/killall for any stray nginx workers.
    if [ -n "${NGINX_PID:-}" ] && kill -0 "$NGINX_PID" 2>/dev/null; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$NGINX_PID" 2>/dev/null || true
    fi
    pkill -9 nginx 2>/dev/null || true
    killall -9 nginx 2>/dev/null || true
    echo "Cleaning up sandbox containers..."
    ./scripts/cleanup-containers.sh octoagent-sandbox 2>/dev/null || true
    echo "✓ All services stopped"
    exit 0
}
trap cleanup INT TERM

assert_process_alive() {
    local pid="$1"
    local service="$2"
    local logfile="$3"
    if kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    echo "✗ $service launcher exited before the service was ready."
    if [ -f "$logfile" ]; then
        echo "  Last log output from $logfile:"
        tail -60 "$logfile"
    fi
    cleanup
}

# ── Start services ────────────────────────────────────────────────────────────

mkdir -p logs

if $DEV_MODE; then
    LANGGRAPH_EXTRA_FLAGS=""
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env'"
else
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS=""
fi

echo "Starting LangGraph server..."
(cd backend && NO_COLOR=1 $LANGGRAPH_CMD dev --no-browser --allow-blocking --host 127.0.0.1 --port $LANGGRAPH_PORT $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1) &
LANGGRAPH_PID=$!
./scripts/wait-for-port.sh $LANGGRAPH_PORT 60 "LangGraph" || {
    echo "  See logs/langgraph.log for details"
    tail -20 logs/langgraph.log
    cleanup
}
assert_process_alive "$LANGGRAPH_PID" "LangGraph" "logs/langgraph.log"
echo "✓ LangGraph server started on localhost:$LANGGRAPH_PORT"

echo "Starting Gateway API..."
(cd backend && $PY_RUN_BACKEND uvicorn src.gateway.app:app --host 127.0.0.1 --port $GATEWAY_PORT $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1) &
GATEWAY_PID=$!
./scripts/wait-for-port.sh $GATEWAY_PORT 30 "Gateway API" || {
    echo "✗ Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    echo ""
    echo "Likely configuration errors:"
    grep -E "Failed to load configuration|Environment variable .* not found|config\.yaml.*not found" logs/gateway.log | tail -5 || true
    cleanup
}
assert_process_alive "$GATEWAY_PID" "Gateway API" "logs/gateway.log"
echo "✓ Gateway API started on localhost:$GATEWAY_PORT"

echo "Starting Frontend..."
(cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1) &
FRONTEND_PID=$!
./scripts/wait-for-port.sh $FRONTEND_PORT 120 "Frontend" || {
    echo "  See logs/frontend.log for details"
    tail -20 logs/frontend.log
    cleanup
}
assert_process_alive "$FRONTEND_PID" "Frontend" "logs/frontend.log"
echo "✓ Frontend started on localhost:$FRONTEND_PORT"

echo "Starting Nginx reverse proxy..."
nginx -g 'daemon off;' -c "$NGINX_CONFIG_RENDERED" -p "$REPO_ROOT" > logs/nginx.log 2>&1 &
NGINX_PID=$!
./scripts/wait-for-port.sh $NGINX_PORT 10 "Nginx" || {
    echo "  See logs/nginx.log for details"
    tail -10 logs/nginx.log
    cleanup
}
assert_process_alive "$NGINX_PID" "Nginx" "logs/nginx.log"
echo "✓ Nginx started on localhost:$NGINX_PORT"

# ── Ready ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo "  ✓ OctoAgent development server is running!"
else
    echo "  ✓ OctoAgent production server is running!"
fi
echo "=========================================="
echo ""
echo "  🌐 Application: http://localhost:$NGINX_PORT"
echo "  📡 API Gateway: http://localhost:$NGINX_PORT/api/*"
echo "  🤖 LangGraph:   http://localhost:$NGINX_PORT/api/langgraph/*"
echo ""
echo "  📋 Logs:"
echo "     - LangGraph: logs/langgraph.log"
echo "     - Gateway:   logs/gateway.log"
echo "     - Frontend:  logs/frontend.log"
echo "     - Nginx:     logs/nginx.log"
echo ""
echo "Press Ctrl+C to stop all services"

wait
