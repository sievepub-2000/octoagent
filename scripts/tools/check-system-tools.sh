#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_BIN="$REPO_ROOT/backend/.venv/bin"
MANAGED_BIN="$REPO_ROOT/runtime/tools/bin"
NODE_BIN="$REPO_ROOT/runtime/tools/node_modules/.bin"
printf 'OctoAgent tool policy\n'
printf '  backend venv: %s\n' "$BACKEND_BIN"
printf '  managed bin : %s\n' "$MANAGED_BIN"
printf '  node bin    : %s\n' "$NODE_BIN"
for name in python ruff pytest bandit trivy docker git ssh scp psql sqlite3 node npm npx pnpm; do
  found=""
  for candidate in "$BACKEND_BIN/$name" "$MANAGED_BIN/$name" "$NODE_BIN/$name"; do
    if [ -x "$candidate" ]; then found="$candidate"; break; fi
  done
  if [ -z "$found" ]; then found="$(command -v "$name" 2>/dev/null || true)"; fi
  printf '%-10s %s\n' "$name" "${found:-MISSING}"
done
"$BACKEND_BIN/python" - <<'PY'
import importlib.metadata as md
for name in ("mcp", "langchain-mcp-adapters", "ruff", "pytest", "bandit"):
    try: print(f"{name}={md.version(name)}")
    except md.PackageNotFoundError: print(f"{name}=NOT_INSTALLED")
PY
