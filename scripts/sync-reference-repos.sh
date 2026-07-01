#!/usr/bin/env bash
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF_DIR="${ROOT_DIR}/references/_clones"

mkdir -p "${REF_DIR}"

sync_repo() {
  local name="$1"
  local url="$2"
  local target="${REF_DIR}/${name}"

  if [ -d "${target}/.git" ]; then
    echo "Updating ${name}..."
    git -C "${target}" fetch --depth=1 origin
    git -C "${target}" reset --hard origin/HEAD
  else
    echo "Cloning ${name}..."
    git clone --depth=1 "${url}" "${target}"
  fi
}

sync_repo "Claude-Code-Leak" "https://github.com/iamdin/Claude-Code-Leak.git"
sync_repo "claude-code-reverse" "https://github.com/Yuyz0112/claude-code-reverse.git"
sync_repo "claude-code-sourcemap" "https://github.com/ChinaSiro/claude-code-sourcemap.git"
sync_repo "claude-code-source-code" "https://github.com/sanbuphy/claude-code-source-code.git"

echo "Reference repositories are synchronized in ${REF_DIR}"
