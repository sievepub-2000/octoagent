#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${OCTOAGENT_REPO_URL:-https://github.com/sievepub-2000/octoagent.git}"
BRANCH="${OCTOAGENT_BRANCH:-main}"
MODE="local"
PREFIX="${OCTOAGENT_HOME:-}"
RUN_USER="${OCTOAGENT_USER:-$(id -un)}"
YES="0"
START_AFTER="0"
SKIP_SYSTEM_PACKAGES="0"
SKIP_BOOTSTRAP="0"
DEFAULT_MODEL="${OCTOAGENT_DEFAULT_MODEL:-}"
BIN_DIR="${OCTOAGENT_BIN_DIR:-/usr/local/bin}"

# === Phase 5 (2026-05-26): macOS support ===
detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)  echo "linux" ;;
        *)      echo "unknown" ;;
    esac
}

OS_KIND="$(detect_os)"

ensure_macos_deps() {
    if [ "$OS_KIND" != "macos" ]; then
        return 0
    fi
    if ! command -v brew >/dev/null 2>&1; then
        echo "macOS install requires Homebrew. Install from https://brew.sh and re-run." >&2
        exit 2
    fi
    local missing=()
    for pkg in git python@3.12 pnpm node@22 nginx postgresql@16; do
        if ! brew list --formula "$pkg" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Installing missing Homebrew packages: ${missing[*]}"
        brew install "${missing[@]}"
    fi
    # systemd is Linux-only; on macOS we use launchd via plist (Phase 5 scope:
    # documented; full plist generation is Phase 5.5 deferred).
    if [ "$MODE" = "service" ]; then
        echo "macOS detected with --mode service. systemd is Linux-only." >&2
        echo "Recommended: --mode local; then run \`octoagent start\` manually," >&2
        echo "or write a launchd plist (see docs/macos-launchd.md, TBD)." >&2
    fi
}
# === end Phase 5 additions ===


SCRIPT_PATH="${BASH_SOURCE[0]:-}"
SCRIPT_DIR=""
if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
    while [ -L "$SCRIPT_PATH" ]; do
        LINK_TARGET="$(readlink "$SCRIPT_PATH")"
        if [[ "$LINK_TARGET" = /* ]]; then
            SCRIPT_PATH="$LINK_TARGET"
        else
            SCRIPT_PATH="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)/$LINK_TARGET"
        fi
    done
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
fi

if [ -z "$PREFIX" ]; then
    if [ -n "$SCRIPT_DIR" ] && [ -d "$SCRIPT_DIR/../.git" ]; then
        PREFIX="$(cd "$SCRIPT_DIR/.." && pwd)"
    else
        PREFIX="$HOME/octoagent"
    fi
fi

usage() {
    cat <<USAGE
Usage: install-octoagent.sh [options]

Options:
  --prefix PATH            Install or use checkout at PATH (default: $PREFIX)
  --repo URL               Git repository URL (default: $REPO_URL)
  --branch NAME            Git branch (default: $BRANCH)
  --user NAME              Runtime user for systemd service (default: $RUN_USER)
  --mode local|service     local installs CLI only; service also installs systemd
  --default-model NAME     Configure workspace/env/setup.json default_model
  --start                  Start OctoAgent after installation
  --yes, -y                Non-interactive approval for system changes
  --skip-system-packages   Do not attempt apt-based OS dependency installation
  --skip-bootstrap         Do not run scripts/bootstrap.sh
  --help, -h               Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="${2:?--prefix requires a path}"; shift 2 ;;
        --repo) REPO_URL="${2:?--repo requires a URL}"; shift 2 ;;
        --branch) BRANCH="${2:?--branch requires a branch}"; shift 2 ;;
        --user) RUN_USER="${2:?--user requires a user}"; shift 2 ;;
        --mode) MODE="${2:?--mode requires local or service}"; shift 2 ;;
        --default-model) DEFAULT_MODEL="${2:?--default-model requires a name}"; shift 2 ;;
        --start) START_AFTER="1"; shift ;;
        --yes|-y) YES="1"; shift ;;
        --skip-system-packages) SKIP_SYSTEM_PACKAGES="1"; shift ;;
        --skip-bootstrap) SKIP_BOOTSTRAP="1"; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

case "$MODE" in
    local|service) ;;
    *) echo "--mode must be local or service" >&2; exit 2 ;;
esac

confirm() {
    local message="$1"
    if [ "$YES" = "1" ]; then
        return 0
    fi
    if [ ! -t 0 ]; then
        echo "$message" >&2
        echo "Refusing non-interactive system change without --yes." >&2
        return 1
    fi
    local answer
    read -r -p "$message [y/N] " answer
    case "$answer" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

sudo_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

has_python312() {
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            "$candidate" - <<'PY' >/dev/null 2>&1 && return 0
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
        fi
    done
    return 1
}

has_node22() {
    command -v node >/dev/null 2>&1 || return 1
    local major
    major="$(node -v | sed 's/^v//' | cut -d. -f1)"
    [ "${major:-0}" -ge 22 ]
}

install_system_packages() {
    if [ "$SKIP_SYSTEM_PACKAGES" = "1" ]; then
        return 0
    fi
    local needs=""
    command -v git >/dev/null 2>&1 || needs="$needs git"
    command -v curl >/dev/null 2>&1 || needs="$needs curl"
    command -v nginx >/dev/null 2>&1 || needs="$needs nginx"
    has_python312 || needs="$needs python3.12"
    has_node22 || needs="$needs nodejs22"
    if [ -z "$needs" ]; then
        return 0
    fi
    echo "Missing or outdated OS dependencies:$needs"
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "Automatic OS package installation currently supports apt-based Linux only." >&2
        echo "Install Python 3.12+, Node.js 22+, nginx, git, curl, and build-essential, then rerun with --skip-system-packages." >&2
        exit 1
    fi
    confirm "Install/upgrade OS packages with apt and NodeSource Node.js 22 when needed?" || exit 1
    sudo_cmd apt-get update
    sudo_cmd apt-get install -y git curl ca-certificates build-essential nginx
    if ! has_python312; then
        sudo_cmd apt-get install -y python3.12 python3.12-venv python3.12-dev || sudo_cmd apt-get install -y python3 python3-venv python3-dev
    fi
    if ! has_node22; then
        nodesource_setup="$(mktemp)"
        curl -fsSL https://deb.nodesource.com/setup_22.x -o "$nodesource_setup"
        sudo_cmd bash "$nodesource_setup"
        rm -f "$nodesource_setup"
        sudo_cmd apt-get install -y nodejs
    fi
    if command -v corepack >/dev/null 2>&1; then
        corepack enable || true
    fi
}

ensure_checkout() {
    mkdir -p "$(dirname "$PREFIX")"
    if [ -d "$PREFIX/.git" ]; then
        cd "$PREFIX"
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        git pull --ff-only origin "$BRANCH"
    elif [ -e "$PREFIX" ] && [ "$(find "$PREFIX" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)" -gt 0 ]; then
        echo "Prefix exists and is not an empty git checkout: $PREFIX" >&2
        exit 1
    else
        git clone --branch "$BRANCH" "$REPO_URL" "$PREFIX"
        cd "$PREFIX"
    fi
}

bootstrap_project() {
    if [ "$SKIP_BOOTSTRAP" = "1" ]; then
        return 0
    fi
    ./scripts/bootstrap.sh
    if [ -x backend/.venv/bin/python ]; then
        backend/.venv/bin/python - <<'PY'
import faiss
import importlib.metadata as md
print("faiss-cpu", md.version("faiss-cpu"), faiss.__file__)
PY
    fi
}

configure_project() {
    mkdir -p workspace/default workspace/env workspace/workflow/taskwork runtime/logs runtime/system_tools tmp
    if [ ! -f .env ] && [ -f .env.example ]; then
        cp .env.example .env
    fi
    if [ ! -f frontend/.env ] && [ -f frontend/.env.example ]; then
        cp frontend/.env.example frontend/.env
    fi
    if [ -n "$DEFAULT_MODEL" ]; then
        ./scripts/octoagent configure --default-model "$DEFAULT_MODEL" --yes
    elif [ -t 0 ] && [ "$YES" != "1" ]; then
        ./scripts/octoagent configure
    else
        ./scripts/octoagent configure --yes
    fi
}

install_cli() {
    chmod +x scripts/octoagent scripts/install-octoagent.sh scripts/start-octoagent.sh
    if [ "$BIN_DIR" = "/usr/local/bin" ]; then
        confirm "Install octoagent CLI symlink to $BIN_DIR/octoagent?" || return 0
        sudo_cmd ln -sf "$PREFIX/scripts/octoagent" "$BIN_DIR/octoagent"
    else
        mkdir -p "$BIN_DIR"
        ln -sf "$PREFIX/scripts/octoagent" "$BIN_DIR/octoagent"
    fi
    echo "octoagent CLI: $BIN_DIR/octoagent"
}

install_service() {
    [ "$MODE" = "service" ] || return 0
    command -v systemctl >/dev/null 2>&1 || { echo "systemctl is required for --mode service" >&2; exit 1; }
    confirm "Install/refresh octoagent-local.service for user $RUN_USER and path $PREFIX?" || exit 1
    local tmp_unit
    tmp_unit="$(mktemp)"
    cat > "$tmp_unit" <<UNIT
[Unit]
Description=OctoAgent Local Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PREFIX
Environment=PATH=/snap/bin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:$PREFIX/scripts
Environment=TMPDIR=$PREFIX/tmp
Environment=OCTOAGENT_PYTHON_BIN=$PREFIX/backend/.venv/bin/python
Environment=OCTO_AGENT_CAPABILITY_SOURCE=$PREFIX
Environment=OCTOAGENT_MANAGED_BY_SYSTEMD=1
Environment=BG_JOB_ISOLATED_LOOPS=true
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$PREFIX/scripts/start-octoagent.sh run
ExecStop=$PREFIX/scripts/start-octoagent.sh stop-runtime
Restart=on-failure
RestartSec=10
KillMode=mixed
TimeoutStartSec=900
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
UNIT
    sudo_cmd install -o root -g root -m 0644 "$tmp_unit" /etc/systemd/system/octoagent-local.service
    rm -f "$tmp_unit"
    sudo_cmd systemctl daemon-reload
    sudo_cmd systemctl enable octoagent-local.service
}

start_project() {
    [ "$START_AFTER" = "1" ] || return 0
    if [ "$MODE" = "service" ]; then
        sudo_cmd systemctl restart octoagent-local.service
        ./scripts/wait-for-port.sh "${OCTO_NGINX_PORT:-19800}" 120 WebUI
    else
        ./scripts/octoagent start
    fi
}

echo "OctoAgent installer"
echo "  prefix: $PREFIX"
echo "  mode:   $MODE"
echo "  user:   $RUN_USER"

install_system_packages
ensure_checkout
bootstrap_project
configure_project
install_cli
install_service
start_project
./scripts/octoagent ports
echo "OctoAgent installation complete. Run: octoagent"
