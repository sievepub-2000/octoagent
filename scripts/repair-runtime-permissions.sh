#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_USER="${OCTOAGENT_RUNTIME_USER:-sieve-pub}"

if ! id "$RUNTIME_USER" >/dev/null 2>&1; then
    RUNTIME_USER="$(stat -c '%U' "$REPO_ROOT")"
fi
RUNTIME_GROUP="$(id -gn "$RUNTIME_USER")"
SYSTEM_TOOLS_ROOT="$REPO_ROOT/runtime/system_tools"
WORKSPACE_RUNTIME_ROOT="$REPO_ROOT/workspace/runtime"

mkdir -p \
    "$SYSTEM_TOOLS_ROOT/html_to_canvas" \
    "$SYSTEM_TOOLS_ROOT/flipbook" \
    "$WORKSPACE_RUNTIME_ROOT"

chown -R "$RUNTIME_USER:$RUNTIME_GROUP" "$SYSTEM_TOOLS_ROOT"
chmod -R u+rwX,go+rX "$SYSTEM_TOOLS_ROOT"

# Runtime smoke and maintenance commands are sometimes invoked by root.
# Keep top-level runtime state readable/writable by the service owner so a
# diagnostic run cannot break the long-lived sieve-pub gateway process.
find "$WORKSPACE_RUNTIME_ROOT" -maxdepth 1 \
    \( -type f -o -type d \) \
    -exec chown "$RUNTIME_USER:$RUNTIME_GROUP" {} +
find "$WORKSPACE_RUNTIME_ROOT" -maxdepth 1 -type d -exec chmod u+rwx,g+rwX,o+rX {} +
find "$WORKSPACE_RUNTIME_ROOT" -maxdepth 1 -type f -exec chmod u+rw,g+rw,o-rwx {} +

# A few generated repository metadata files are updated by local smoke and
# capability-registry flows. Keep them service-owned even after root-run git
# operations or diagnostics.
for path in "$REPO_ROOT/.gitignore" "$REPO_ROOT/.github/copilot-instructions.md"; do
    if [ -e "$path" ]; then
        chown "$RUNTIME_USER:$RUNTIME_GROUP" "$path"
        chmod u+rw,g+r,o+r "$path"
    fi
done
