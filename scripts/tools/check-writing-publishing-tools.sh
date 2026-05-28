#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PY_VENV="$REPO_ROOT/runtime/system_tools/writing-python/.venv"
NODE_ROOT="$REPO_ROOT/runtime/tools/writing-node"
BIN_DIR="$REPO_ROOT/runtime/tools/bin"
PLAYWRIGHT_BROWSERS="$REPO_ROOT/runtime/tools/playwright-browsers"

echo "== Python packages =="
"$PY_VENV/bin/python" - <<'PY'
import importlib
for name in ['browser_use','presidio_analyzer','presidio_anonymizer']:
    mod = importlib.import_module(name)
    print(name, 'ok', getattr(mod, '__version__', ''))
PY

echo "== Node/textlint =="
"$NODE_ROOT/node_modules/.bin/textlint" --version

echo "== Vale =="
"$BIN_DIR/vale" --version

echo "== WP-CLI =="
"$BIN_DIR/wp" --info --allow-root | sed -n '1,8p'

echo "== Pandoc =="
pandoc --version | head -1

echo "== Playwright =="
PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS" node -e "const { chromium } = require('./frontend/node_modules/@playwright/test'); (async () => { const browser = await chromium.launch({ headless: true }); await browser.close(); console.log('playwright chromium launch ok'); })()"

echo "writing/publishing toolchain ok"
