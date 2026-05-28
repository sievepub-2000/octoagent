#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${1:-$(git describe --tags --always --dirty 2>/dev/null || date +%Y%m%d)}"
OUT_DIR="${OCTOAGENT_PACKAGE_DIR:-$REPO_ROOT/dist}"
mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/octoagent-docker-${VERSION}.tar.gz"

if [ -n "$(git status --short)" ] && [ "${OCTOAGENT_PACKAGE_ALLOW_DIRTY:-0}" != "1" ]; then
    echo "Refusing to package a dirty worktree. Commit first or set OCTOAGENT_PACKAGE_ALLOW_DIRTY=1." >&2
    exit 1
fi

git archive --format=tar --prefix="octoagent/" HEAD | gzip -9 > "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
cat <<MSG
Created Docker source package:
  $ARCHIVE
  $ARCHIVE.sha256

Install from the extracted directory with:
  ./scripts/install-docker.sh --prefix "$(pwd)"
MSG
