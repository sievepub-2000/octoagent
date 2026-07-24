#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP=${OCTOAGENT_APP_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}
cd "$APP"
export OCTOAGENT_APP_ROOT="${OCTOAGENT_APP_ROOT:-$APP}"
export OCTOAGENT_BACKEND_PATH="${OCTOAGENT_BACKEND_PATH:-$APP/backend}"
if [[ -x "${OCTOAGENT_PYTHON_BIN:-$APP/backend/.venv/bin/python}" ]]; then
  PYTHON_CMD=("${OCTOAGENT_PYTHON_BIN:-$APP/backend/.venv/bin/python}")
else
  PYTHON_CMD=(docker compose exec -T -e PYTHONPATH=/app/backend gateway /app/backend/.venv/bin/python)
fi
export OCTOAGENT_FILESYSTEM_ROOT="${OCTOAGENT_FILESYSTEM_ROOT:-$APP}"
export OCTOAGENT_MCP_TOOLS_DIR="${OCTOAGENT_MCP_TOOLS_DIR:-$APP/runtime/tools/mcp}"
export OCTOAGENT_MCP_FILESYSTEM_BIN="${OCTOAGENT_MCP_FILESYSTEM_BIN:-$OCTOAGENT_MCP_TOOLS_DIR/node_modules/.bin/mcp-server-filesystem}"
export OCTOAGENT_MCP_POSTGRES_BIN="${OCTOAGENT_MCP_POSTGRES_BIN:-$OCTOAGENT_MCP_TOOLS_DIR/node_modules/.bin/mcp-server-postgres}"
export OCTOAGENT_MCP_OPENAPI_BIN="${OCTOAGENT_MCP_OPENAPI_BIN:-$OCTOAGENT_MCP_TOOLS_DIR/node_modules/.bin/openapi-mcp-server}"
export OCTOAGENT_MCP_KUBERNETES_BIN="${OCTOAGENT_MCP_KUBERNETES_BIN:-$OCTOAGENT_MCP_TOOLS_DIR/node_modules/.bin/mcp-server-kubernetes}"
export OCTOAGENT_MCP_DOCKER_BIN="${OCTOAGENT_MCP_DOCKER_BIN:-$OCTOAGENT_MCP_TOOLS_DIR/node_modules/.bin/docker-mcp}"
export OCTOAGENT_GATEWAY_INTERNAL_URL="${OCTOAGENT_GATEWAY_INTERNAL_URL:-http://127.0.0.1:${OCTO_GATEWAY_PORT:-19802}}"
export OCTOAGENT_GATEWAY_HEALTH_URL="${OCTOAGENT_GATEWAY_HEALTH_URL:-$OCTOAGENT_GATEWAY_INTERNAL_URL/health}"
export OCTOAGENT_OPENAPI_SPEC_URL="${OCTOAGENT_OPENAPI_SPEC_URL:-$OCTOAGENT_GATEWAY_INTERNAL_URL/openapi.json}"
export OCTOAGENT_KUBECONFIG_SMOKE="${OCTOAGENT_KUBECONFIG_SMOKE:-$APP/runtime/tools/kubernetes/kubeconfig-smoke.yaml}"
PYTHONPATH="$APP/backend" exec "${PYTHON_CMD[@]}" -m src.tools.mcp.smoke "$@"
