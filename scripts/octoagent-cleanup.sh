#!/usr/bin/env bash
# Repository cleanup uses the same conservative policy as runtime maintenance.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/workspace_cleanup.sh" "$@"
