#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

INSTALL_HOST_DEPS="${OCTOAGENT_INSTALL_HOST_DEPS:-0}"
PY_VENV="$REPO_ROOT/runtime/system_tools/writing-python/.venv"
NODE_ROOT="$REPO_ROOT/runtime/tools/writing-node"
BIN_DIR="$REPO_ROOT/runtime/tools/bin"
GO_ROOT="$REPO_ROOT/runtime/tools/go"
PLAYWRIGHT_BROWSERS="$REPO_ROOT/runtime/tools/playwright-browsers"

mkdir -p "$BIN_DIR" "$NODE_ROOT" "$GO_ROOT" "$PLAYWRIGHT_BROWSERS" "$REPO_ROOT/runtime/tools/npm-cache"

if [ "$INSTALL_HOST_DEPS" = "1" ]; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y php-cli pandoc
  fi
fi

python3 -m venv "$PY_VENV"
"$PY_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$PY_VENV/bin/python" -m pip install browser-use==0.12.9 presidio-analyzer==2.2.362 presidio-anonymizer==2.2.362

cd "$NODE_ROOT"
if [ ! -f package.json ]; then
  npm init -y >/dev/null
fi
npm install textlint@15.7.1 textlint-rule-preset-ja-technical-writing textlint-rule-preset-ja-spacing textlint-rule-write-good
cat > .textlintrc.json <<'JSON'
{
  "rules": {
    "preset-ja-technical-writing": false,
    "preset-ja-spacing": false,
    "write-good": {
      "passive": true,
      "so": true,
      "thereIs": true,
      "weasel": true
    }
  }
}
JSON
cd "$REPO_ROOT"

if [ -d "$REPO_ROOT/frontend/node_modules/@playwright/test" ]; then
  PLAYWRIGHT_BROWSERS_PATH="$PLAYWRIGHT_BROWSERS" npx --prefix "$REPO_ROOT/frontend" playwright install chromium
fi

if [ ! -x "$BIN_DIR/vale" ]; then
  if command -v go >/dev/null 2>&1; then
    GOBIN="$BIN_DIR" GOPATH="$GO_ROOT" GOPROXY="${GOPROXY:-https://goproxy.cn,direct}" GOSUMDB="${GOSUMDB:-sum.golang.google.cn}" go install github.com/errata-ai/vale/v3/cmd/vale@latest || true
  fi
fi
if [ ! -x "$BIN_DIR/vale" ]; then
  tmp="$(mktemp -d)"
  for asset_version in 3.14.2 3.12.0 3.11.2 3.9.6; do
    url="https://github.com/errata-ai/vale/releases/download/v${asset_version}/vale_${asset_version}_Linux_arm64.tar.gz"
    if curl -fsSL "$url" -o "$tmp/vale.tar.gz"; then
      tar -xzf "$tmp/vale.tar.gz" -C "$tmp"
      install -m 0755 "$tmp/vale" "$BIN_DIR/vale"
      break
    fi
  done
  rm -rf "$tmp"
fi
if [ ! -x "$BIN_DIR/vale" ]; then
  echo "Vale was not installed automatically. Install vale into $BIN_DIR/vale from https://github.com/errata-ai/vale/releases." >&2
fi

if [ ! -x "$BIN_DIR/wp" ]; then
  curl -fsSL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o "$BIN_DIR/wp"
  chmod +x "$BIN_DIR/wp"
fi

"$PY_VENV/bin/python" - <<'PY'
import importlib
for name in ['browser_use','presidio_analyzer','presidio_anonymizer']:
    importlib.import_module(name)
print('python writing packages ok')
PY
"$NODE_ROOT/node_modules/.bin/textlint" --version
command -v pandoc >/dev/null 2>&1 && pandoc --version | head -1 || true
[ -x "$BIN_DIR/vale" ] && "$BIN_DIR/vale" --version || true
[ -x "$BIN_DIR/wp" ] && "$BIN_DIR/wp" --info --allow-root | sed -n '1,8p' || true
