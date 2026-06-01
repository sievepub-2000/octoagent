#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_PY="$REPO_ROOT/backend/.venv/bin/python"
TOOLS_DIR="$REPO_ROOT/runtime/tools"
BIN_DIR="$TOOLS_DIR/bin"
mkdir -p "$BIN_DIR" "$TOOLS_DIR/npm-cache"
export NPM_CONFIG_CACHE="$TOOLS_DIR/npm-cache"
install_python_security() {
  "$BACKEND_PY" -m pip install 'bandit==1.9.4'
  "$BACKEND_PY" - <<'PY'
import importlib.metadata as md
assert md.version('mcp') >= '1.25.0'
print('python-security-ok')
PY
}
install_trivy() {
  arch="$(uname -m)"
  case "$arch" in
    aarch64|arm64) asset_arch="ARM64" ;;
    x86_64|amd64) asset_arch="64bit" ;;
    *) echo "unsupported architecture for managed trivy: $arch" >&2; exit 1 ;;
  esac
  version="${TRIVY_VERSION:-0.70.0}"
  work="$TOOLS_DIR/trivy-$version"
  mkdir -p "$work"
  url="https://github.com/aquasecurity/trivy/releases/download/v${version}/trivy_${version}_Linux-${asset_arch}.tar.gz"
  curl -fL --retry 3 --connect-timeout 20 --max-time 240 -o "$work/trivy.tar.gz" "$url"
  tar -xzf "$work/trivy.tar.gz" -C "$work" trivy
  chmod +x "$work/trivy"
  ln -sfn "$work/trivy" "$BIN_DIR/trivy"
  "$BIN_DIR/trivy" --version
}
case "${1:-all}" in
  all) install_python_security; install_trivy ;;
  python-security) install_python_security ;;
  trivy) install_trivy ;;
  *) echo "Usage: $0 [all|python-security|trivy]" >&2; exit 2 ;;
esac
