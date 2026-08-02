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
PYTHONPATH="$APP/backend" exec "${PYTHON_CMD[@]}" -m src.tools.mcp.smoke "$@"
