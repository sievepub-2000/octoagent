#!/usr/bin/env bash
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


echo "=========================================="
echo "  Checking Required Dependencies"
echo "=========================================="
echo ""

FAILED=0

echo "Checking Node.js..."
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    if [ "$NODE_MAJOR" -ge 22 ]; then
        echo "  ✓ Node.js $NODE_VERSION (>= 22 required)"
    else
        echo "  ✗ Node.js $NODE_VERSION found, but version 22+ is required"
        echo "    Install from: https://nodejs.org/"
        FAILED=1
    fi
else
    echo "  ✗ Node.js not found (version 22+ required)"
    echo "    Install from: https://nodejs.org/"
    FAILED=1
fi

echo ""
echo "Checking pnpm..."
if command -v pnpm >/dev/null 2>&1; then
    PNPM_VERSION=$(pnpm -v)
    echo "  ✓ pnpm $PNPM_VERSION"
else
    echo "  ✗ pnpm not found"
    echo "    Install: npm install -g pnpm"
    echo "    Or visit: https://pnpm.io/installation"
    FAILED=1
fi

echo ""
echo "Checking Python..."
PY_FOUND=0
for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY_VER=$($candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
            echo "  ✓ Python $PY_VER ($(command -v $candidate))"
            PY_FOUND=1
            break
        fi
    fi
done
if [ "$PY_FOUND" -eq 0 ]; then
    echo "  ✗ Python 3.12+ not found"
    echo "    Install from: https://www.python.org/downloads/"
    FAILED=1
fi

echo ""
echo "Checking uv (optional, recommended)..."
if command -v uv >/dev/null 2>&1; then
    UV_VERSION=$(uv --version | awk '{print $2}')
    echo "  ✓ uv $UV_VERSION"
else
    echo "  ⚠ uv not found (will fall back to pip + requirements.txt)"
    echo "    Install for faster setup: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo ""
echo "Checking nginx..."
if command -v nginx >/dev/null 2>&1; then
    NGINX_VERSION=$(nginx -v 2>&1 | awk -F'/' '{print $2}')
    echo "  ✓ nginx $NGINX_VERSION"
else
    echo "  ✗ nginx not found"
    echo "    macOS:   brew install nginx"
    echo "    Ubuntu:  sudo apt install nginx"
    echo "    Or visit: https://nginx.org/en/download.html"
    FAILED=1
fi

echo ""
if [ "$FAILED" -eq 0 ]; then
    echo "=========================================="
    echo "  ✓ All dependencies are installed!"
    echo "=========================================="
    echo ""
    echo "You can now run:"
    echo "  make install  - Install project dependencies"
    echo "  make config   - Generate local config files"
    echo "  make dev      - Start development server"
    echo "  make start    - Start production server"
else
    echo "=========================================="
    echo "  ✗ Some dependencies are missing"
    echo "=========================================="
    echo ""
    echo "Please install the missing tools and run 'make check' again."
    exit 1
fi
