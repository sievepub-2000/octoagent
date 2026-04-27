#!/usr/bin/env bash
# OctoAgent systemd service script
# Starts the local OctoAgent server stack for both WebUI and Electron desktop shell

export PATH="/snap/bin:/usr/local/bin:/usr/bin:/usr/sbin:$PATH"
cd /home/sieve-pub/public-workspace/octoagent || exit 1

LANGGRAPH_PORT=19884
FRONTEND_PORT=19886
GATEWAY_PORT=19882
NGINX_PORT=19880

mkdir -p logs
PIDS=()

# Portable Python runner: uv preferred, venv fallback
if command -v uv >/dev/null 2>&1; then
    PY_RUN="uv run"
elif [ -f backend/.venv/bin/python3 ]; then
    PY_RUN=".venv/bin/python3 -m"
else
    echo "Neither uv nor backend venv found. Run 'make install' first."
    exit 1
fi

cleanup() {
    echo "Stopping OctoAgent services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "uvicorn src.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    nginx -s stop -p "$(pwd)" -c docker/nginx/nginx.local.conf 2>/dev/null || true
    echo "OctoAgent stopped."
    exit 0
}
trap cleanup SIGTERM SIGINT

(cd backend && $PY_RUN langgraph dev --allow-blocking --no-browser --host 127.0.0.1 --port $LANGGRAPH_PORT > ../logs/langgraph.log 2>&1) &
PIDS+=($!)
(cd backend && $PY_RUN uvicorn src.gateway.app:app --host 127.0.0.1 --port $GATEWAY_PORT > ../logs/gateway.log 2>&1) &
PIDS+=($!)
(cd frontend && pnpm exec next start --hostname 127.0.0.1 --port $FRONTEND_PORT > ../logs/frontend.log 2>&1) &
PIDS+=($!)
nginx -g 'daemon off;' -c "$(pwd)/docker/nginx/nginx.local.conf" -p "$(pwd)" > logs/nginx.log 2>&1 &
PIDS+=($!)

echo "OctoAgent server stack is running at http://localhost:$NGINX_PORT"
wait
