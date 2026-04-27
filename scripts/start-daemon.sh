#!/usr/bin/env bash
#
# start-daemon.sh - Start all OctoAgent development services in daemon mode
#
# This script starts OctoAgent services in the background without keeping
# the terminal connection. Logs are written to separate files.
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

NGINX_CONFIG_TEMPLATE="$REPO_ROOT/docker/nginx/nginx.local.conf.template"
NGINX_CONFIG_RENDERED="$REPO_ROOT/tmp/nginx.local.conf"

DEV_MODE=true
for arg in "$@"; do
    case "$arg" in
        --dev) DEV_MODE=true ;;
        --prod) DEV_MODE=false ;;
        *) echo "Unknown argument: $arg"; echo "Usage: $0 [--dev|--prod]"; exit 1 ;;
    esac
done

mkdir -p "$REPO_ROOT/tmp"
mkdir -p "$REPO_ROOT/tmp/nginx/client_body" \
         "$REPO_ROOT/tmp/nginx/proxy" \
         "$REPO_ROOT/tmp/nginx/fastcgi" \
         "$REPO_ROOT/tmp/nginx/uwsgi" \
         "$REPO_ROOT/tmp/nginx/scgi"
python3 "$REPO_ROOT/scripts/render_nginx_config.py" \
    "$NGINX_CONFIG_TEMPLATE" \
    "$NGINX_CONFIG_RENDERED"

kill_port_owners() {
    local port="$1"

    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" 2>/dev/null || true
        return
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
        return
    fi

    if command -v ss >/dev/null 2>&1; then
        ss -ltnp "( sport = :$port )" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            | xargs -r kill -9 2>/dev/null || true
    fi
}

# ── Stop existing services ────────────────────────────────────────────────────

echo "Stopping existing services if any..."
pkill -f "langgraph dev" 2>/dev/null || true
pkill -f "langgraph_cli dev" 2>/dev/null || true
pkill -f "python -m langgraph_cli" 2>/dev/null || true
pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next start" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
nginx -c "$NGINX_CONFIG_RENDERED" -p "$REPO_ROOT" -s quit 2>/dev/null || true
sleep 1
pkill -9 nginx 2>/dev/null || true
kill_port_owners "$LANGGRAPH_PORT"
kill_port_owners "$GATEWAY_PORT"
kill_port_owners "$FRONTEND_PORT"
kill_port_owners "$NGINX_PORT"
./scripts/cleanup-containers.sh octoagent-sandbox 2>/dev/null || true
sleep 1

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo " Starting OctoAgent in Daemon Mode (DEV)"
else
    echo " Starting OctoAgent in Daemon Mode (PROD)"
fi
echo "=========================================="
echo ""

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

# ── Cleanup on failure ───────────────────────────────────────────────────────

cleanup_on_failure() {
    echo "Failed to start services, cleaning up..."
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "langgraph_cli dev" 2>/dev/null || true
    pkill -f "python -m langgraph_cli" 2>/dev/null || true
    pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    nginx -c "$NGINX_CONFIG_RENDERED" -p "$REPO_ROOT" -s quit 2>/dev/null || true
    sleep 1
    pkill -9 nginx 2>/dev/null || true
    kill_port_owners "$LANGGRAPH_PORT"
    kill_port_owners "$GATEWAY_PORT"
    kill_port_owners "$FRONTEND_PORT"
    kill_port_owners "$NGINX_PORT"
    echo "✓ Cleanup complete"
}

trap cleanup_on_failure INT TERM

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
    cleanup_on_failure
    exit 1
}

# ── Python runner detection ───────────────────────────────────────────────────
if [ -f backend/.venv/bin/python ]; then
    LANGGRAPH_RUN=".venv/bin/python -m langgraph_cli"
    PY_RUN=".venv/bin/python -m"
elif [ -f backend/.venv/Scripts/python.exe ]; then
    LANGGRAPH_RUN=".venv/Scripts/python.exe -m langgraph_cli"
    PY_RUN=".venv/Scripts/python.exe -m"
elif command -v uv >/dev/null 2>&1; then
    LANGGRAPH_RUN="uv run langgraph"
    PY_RUN="uv run"
else
    echo "✗ Neither backend venv nor uv found. Run 'make install' first."
    exit 1
fi

if $DEV_MODE; then
    FRONTEND_CMD="pnpm exec next dev --turbo --hostname 127.0.0.1 --port $FRONTEND_PORT"
    LANGGRAPH_EXTRA_FLAGS=""
else
    FRONTEND_CMD="env BETTER_AUTH_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(16))') pnpm exec next start --hostname 127.0.0.1 --port $FRONTEND_PORT"
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    echo "Rebuilding frontend production assets..."
    (
        cd frontend
        python3 - <<'PY'
from pathlib import Path
import shutil

build_dir = Path('.next')
if build_dir.exists():
    shutil.rmtree(build_dir, ignore_errors=False)
PY
        pnpm exec next build
    )
    echo "✓ Frontend production assets rebuilt"
fi

# ── Start services ────────────────────────────────────────────────────────────

mkdir -p logs

# LangChain/OpenAI/MCP clients in this repo reject the SOCKS-style ALL_PROXY
# values present in this environment. Keep HTTP(S) proxy settings intact for
# outbound network access, but drop ALL_PROXY in both common casings.
export ALL_PROXY=""
export all_proxy=""
if $DEV_MODE && [ -z "${OCTO_SMTP_HOST:-}" ]; then
    # Local/dev installs without SMTP still need a usable registration flow.
    # The auth page displays this code only when the backend opts in here.
    export OCTO_AUTH_DEV_EXPOSE_CODES="${OCTO_AUTH_DEV_EXPOSE_CODES:-1}"
fi

echo "Starting LangGraph server..."
nohup setsid sh -c "cd backend && NO_COLOR=1 $LANGGRAPH_RUN dev --no-browser --allow-blocking --host 127.0.0.1 --port $LANGGRAPH_PORT $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1" &
LANGGRAPH_PID=$!
./scripts/wait-for-port.sh $LANGGRAPH_PORT 60 "LangGraph" || {
    echo "✗ LangGraph failed to start. Last log output:"
    tail -60 logs/langgraph.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$LANGGRAPH_PID" "LangGraph" "logs/langgraph.log"
sleep 1
assert_process_alive "$LANGGRAPH_PID" "LangGraph" "logs/langgraph.log"
echo "✓ LangGraph server started on localhost:$LANGGRAPH_PORT"

echo "Starting Gateway API..."
nohup setsid sh -c "cd backend && $PY_RUN uvicorn src.gateway.app:app --host 127.0.0.1 --port $GATEWAY_PORT > ../logs/gateway.log 2>&1" &
GATEWAY_PID=$!
./scripts/wait-for-port.sh $GATEWAY_PORT 30 "Gateway API" || {
    echo "✗ Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$GATEWAY_PID" "Gateway API" "logs/gateway.log"
sleep 1
assert_process_alive "$GATEWAY_PID" "Gateway API" "logs/gateway.log"
echo "✓ Gateway API started on localhost:$GATEWAY_PORT"

echo "Starting Frontend..."
nohup setsid sh -c "cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1" &
FRONTEND_PID=$!
./scripts/wait-for-port.sh $FRONTEND_PORT 120 "Frontend" || {
    echo "✗ Frontend failed to start. Last log output:"
    tail -60 logs/frontend.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$FRONTEND_PID" "Frontend" "logs/frontend.log"
sleep 1
assert_process_alive "$FRONTEND_PID" "Frontend" "logs/frontend.log"
echo "✓ Frontend started on localhost:$FRONTEND_PORT"

echo "Starting Nginx reverse proxy..."
nohup setsid sh -c 'nginx -g "daemon off;" -c "$2" -p "$1" > logs/nginx.log 2>&1' _ "$REPO_ROOT" "$NGINX_CONFIG_RENDERED" &
NGINX_PID=$!
./scripts/wait-for-port.sh $NGINX_PORT 10 "Nginx" || {
    echo "✗ Nginx failed to start. Last log output:"
    tail -60 logs/nginx.log
    cleanup_on_failure
    exit 1
}
assert_process_alive "$NGINX_PID" "Nginx" "logs/nginx.log"
sleep 1
assert_process_alive "$NGINX_PID" "Nginx" "logs/nginx.log"
echo "✓ Nginx started on localhost:$NGINX_PORT"

# ── Ready ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo " OctoAgent is running in daemon mode!"
else
    echo " OctoAgent is running in production daemon mode!"
fi
echo "=========================================="
echo ""
LOCAL_ENTRYPOINT="http://127.0.0.1:$NGINX_PORT"
PUBLIC_ENTRYPOINT="${OCTO_PUBLIC_BASE_URL:-$LOCAL_ENTRYPOINT}"
echo " 🌐 Local entrypoint: $LOCAL_ENTRYPOINT"
if [ "$PUBLIC_ENTRYPOINT" != "$LOCAL_ENTRYPOINT" ]; then
    echo " 🌍 Public entrypoint: $PUBLIC_ENTRYPOINT"
fi
echo " 📡 API Gateway: http://localhost:$NGINX_PORT/api/*"
echo " 🤖 LangGraph: http://localhost:$NGINX_PORT/api/langgraph/*"
echo ""
echo " 📋 Logs:"
echo " - LangGraph: logs/langgraph.log"
echo " - Gateway: logs/gateway.log"
echo " - Frontend: logs/frontend.log"
echo " - Nginx: logs/nginx.log"
echo ""
echo " 🛑 Stop daemon: make stop"
echo ""
