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
  "$BACKEND_PY" -m pip uninstall -y semgrep >/dev/null 2>&1 || true
  "$BACKEND_PY" - <<'PY'
import importlib.metadata as md
assert md.version('mcp') >= '1.25.0'
try:
    md.version('semgrep')
except md.PackageNotFoundError:
    pass
else:
    raise SystemExit('semgrep must not be installed in backend/.venv')
print('python-security-ok')
PY
}
install_trivy() {
  arch="$(uname -m)"
  install_semgrep() {
  # Semgrep pins mcp==1.23.3 and older click; installing it into backend/.venv
  # would downgrade mcp (1.25.0) and break OctoAgent MCP. Install it in an
  # isolated pipx venv and expose a managed symlink so _which("semgrep")
  # resolves it without polluting backend/.venv.
  if ! command -v pipx >/dev/null 2>&1; then
    echo "pipx is required for isolated semgrep (apt-get install -y pipx)" >&2
    exit 1
  fi
  pipx install --force semgrep
  sg="${PIPX_HOME:-$HOME/.local/share/pipx}/venvs/semgrep/bin/semgrep"
  if [ ! -x "$sg" ]; then sg="$HOME/.local/share/pipx/venvs/semgrep/bin/semgrep"; fi
  ln -sfn "$sg" "$BIN_DIR/semgrep"
  "$BIN_DIR/semgrep" --version
}
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
  all) install_python_security; install_trivy; install_semgrep ;;
  python-security) install_python_security ;;
  trivy) install_trivy ;;
  semgrep) install_semgrep ;;
  *) echo "Usage: $0 [all|python-security|trivy|semgrep]" >&2; exit 2 ;;
esac
