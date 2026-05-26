#!/usr/bin/env bash
#
# bootstrap.sh - Set up OctoAgent development environment from scratch
#
# Works on Linux (x86_64 / aarch64), macOS, and WSL.
# Requires: Python 3.12+, Node.js 22+
# Optional: uv (auto-installed if missing), pnpm (auto-installed if missing)
#
# Usage:
#   ./scripts/bootstrap.sh              # full setup (backend + frontend)
#   ./scripts/bootstrap.sh --backend    # backend only
#   ./scripts/bootstrap.sh --frontend   # frontend only

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Argument parsing ─────────────────────────────────────────────────────────

DO_BACKEND=true
DO_FRONTEND=true

for arg in "$@"; do
    case "$arg" in
        --backend)  DO_FRONTEND=false ;;
        --frontend) DO_BACKEND=false ;;
        --help|-h)
            echo "Usage: $0 [--backend|--frontend]"
            echo "  (no flags)    Set up both backend and frontend"
            echo "  --backend     Set up backend only"
            echo "  --frontend    Set up frontend only"
            exit 0
            ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

echo ""
echo "=========================================="
echo "  OctoAgent Bootstrap"
echo "=========================================="
echo ""

# ── Helper functions ─────────────────────────────────────────────────────────

fail() { echo "✗ $*" >&2; exit 1; }

check_python() {
    local py=""
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            local ver
            ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            local major minor
            major=$(echo "$ver" | cut -d. -f1)
            minor=$(echo "$ver" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 12 ]; then
                py="$candidate"
                break
            fi
        fi
    done
    if [ -z "$py" ]; then
        fail "Python 3.12+ is required but not found. Install from https://www.python.org/downloads/"
    fi
    echo "$py"
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        echo "  ✓ uv $(uv --version | awk '{print $2}')"
        return 0
    fi
    echo "  → Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if command -v uv >/dev/null 2>&1; then
        echo "  ✓ uv $(uv --version | awk '{print $2}') installed"
        return 0
    fi
    echo "  ⚠ uv auto-install failed, will fall back to pip"
    return 1
}

ensure_pnpm() {
    if command -v pnpm >/dev/null 2>&1; then
        echo "  ✓ pnpm $(pnpm -v)"
        return 0
    fi
    echo "  → Installing pnpm via corepack..."
    if command -v corepack >/dev/null 2>&1; then
        corepack enable
        corepack prepare pnpm@latest --activate
    elif command -v npm >/dev/null 2>&1; then
        npm install -g pnpm
    else
        fail "Neither corepack nor npm found. Install pnpm: https://pnpm.io/installation"
    fi
    echo "  ✓ pnpm $(pnpm -v) installed"
}

# ── Backend setup ─────────────────────────────────────────────────────────────

setup_backend() {
    echo "── Backend Setup ──────────────────────────"
    echo ""

    local py
    py=$(check_python)
    echo "  ✓ Python: $py ($($py --version 2>&1))"

    cd "$REPO_ROOT/backend"

    # Strategy: try uv first (fast, lockfile-aware), fall back to pip + requirements.txt
    local USE_UV=false
    if ensure_uv 2>/dev/null; then
        USE_UV=true
    fi

    if $USE_UV; then
        echo "  → Installing backend via uv sync..."
        uv sync
        echo "  ✓ Backend dependencies installed via uv"
    else
        echo "  → Setting up Python virtual environment..."
        if [ ! -d .venv ]; then
            "$py" -m venv .venv
            echo "  ✓ Created .venv"
        else
            echo "  ✓ .venv already exists"
        fi

        # Ensure pip is available in the venv
        if [ ! -f .venv/bin/pip ] && [ ! -f .venv/Scripts/pip.exe ]; then
            echo "  → Installing pip into venv..."
            .venv/bin/python3 -m ensurepip --upgrade 2>/dev/null || \
            .venv/bin/python -m ensurepip --upgrade 2>/dev/null || true
        fi

        # Determine the pip executable
        local VENV_PIP=""
        if [ -f .venv/bin/pip ]; then
            VENV_PIP=".venv/bin/pip"
        elif [ -f .venv/Scripts/pip.exe ]; then
            VENV_PIP=".venv/Scripts/pip.exe"
        else
            # Fall back to running pip as module
            VENV_PIP=".venv/bin/python3 -m pip"
        fi

        if [ ! -f requirements.txt ]; then
            fail "requirements.txt not found. Run 'uv export --no-hashes --frozen --no-annotate > requirements.txt' first."
        fi

        echo "  → Installing backend via pip (from requirements.txt)..."
        $VENV_PIP install -r requirements.txt
        # Also install the project itself in editable mode
        $VENV_PIP install -e .
        echo "  ✓ Backend dependencies installed via pip"
    fi

    # Verify critical imports
    local VENV_PYTHON=".venv/bin/python3"
    [ -f "$VENV_PYTHON" ] || VENV_PYTHON=".venv/bin/python"
    [ -f "$VENV_PYTHON" ] || VENV_PYTHON=".venv/Scripts/python.exe"

    echo "  → Verifying critical packages..."
    $VENV_PYTHON -c "
import langchain, langgraph, fastapi, pydantic, duckdb, httpx, uvicorn
print(f'    langchain={langchain.__version__}  langgraph={langgraph.__version__}')
print(f'    fastapi={fastapi.__version__}  pydantic={pydantic.__version__}')
print(f'    duckdb={duckdb.__version__}  httpx={httpx.__version__}')
" || fail "Critical package verification failed"

    echo "  ✓ Backend ready"
    echo ""
    cd "$REPO_ROOT"
}

# ── Frontend setup ────────────────────────────────────────────────────────────

setup_frontend() {
    echo "── Frontend Setup ─────────────────────────"
    echo ""

    if ! command -v node >/dev/null 2>&1; then
        fail "Node.js not found. Install Node.js 22+ from https://nodejs.org/"
    fi

    local NODE_MAJOR
    NODE_MAJOR=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 22 ]; then
        fail "Node.js 22+ required, found $(node -v)"
    fi
    echo "  ✓ Node.js $(node -v)"

    ensure_pnpm

    cd "$REPO_ROOT/frontend"
    echo "  → Installing frontend dependencies via pnpm..."
    pnpm install --frozen-lockfile
    echo "  ✓ Frontend dependencies installed"
    echo ""
    cd "$REPO_ROOT"
}

# ── Config generation ─────────────────────────────────────────────────────────

setup_config() {
    if [ -f config.yaml ] || [ -f config.yml ]; then
        echo "  ✓ config.yaml already exists"
    elif [ -f config.example.yaml ]; then
        echo "  → Generating config.yaml from example..."
        cp config.example.yaml config.yaml
        echo "  ✓ config.yaml created (edit to set API keys)"
    fi

    if [ ! -f .env ] && [ -f .env.example ]; then
        cp .env.example .env
        echo "  ✓ .env created"
    fi
}

# ── Run ───────────────────────────────────────────────────────────────────────

setup_config

if $DO_BACKEND; then
    setup_backend
fi

if $DO_FRONTEND; then
    setup_frontend
fi

echo "=========================================="
echo "  ✓ Bootstrap complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit config.yaml to set your LLM API keys"
echo "  2. Run 'make dev' to start development server"
echo "  3. Open http://localhost:19800 in your browser"
echo ""
