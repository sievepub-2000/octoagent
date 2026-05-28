#!/usr/bin/env bash
set -euo pipefail
APP=${OCTOAGENT_APP_ROOT:-/home/sieve-pub/public-workspace/octoagent}
cd "$APP"
export PYTHONPATH="$APP/backend${PYTHONPATH:+:$PYTHONPATH}"
exec "$APP/backend/.venv/bin/python" -m src.tools.mcp.smoke "$@"
