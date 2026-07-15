#!/usr/bin/env bash
# Deprecated alias retained for operators; delegates to the canonical policy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/workspace_cleanup.sh" "$@"
