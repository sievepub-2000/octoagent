# Runtime Path Migration

OctoAgent runtime data belongs under the canonical workspace root:

`/home/sieve-pub/public-workspace/octoagent/workspace`

Do not use repo-local `.octoagent`, `backend/.octoagent`, or archived roots such as `/home/sieve-pub/codex/octoagent` as active runtime locations.

## Current Layout

- `workspace/default/agents/` stores agent definitions.
- `workspace/default/threads/` stores thread user data, uploads, and outputs.
- `workspace/default/memory.json` stores working memory.
- `workspace/default/global_memory.json` stores user-editable global memory.
- `workspace/runtime/checkpoints.db` stores LangGraph checkpoints.
- `workspace/runtime/system_memory.duckdb` stores backend-managed semantic memory.
- `workspace/env/setup.json` records the selected workspace and key runtime paths.

## Migration Steps

1. Stop services with `make stop`.
2. Copy any wanted files from old runtime roots into the matching `workspace/default` or `workspace/runtime` location.
3. Update local setup state so `workspace_path` points to `/home/sieve-pub/public-workspace/octoagent/workspace`.
4. Ensure `config.yaml` uses `checkpointer.connection_string: runtime/checkpoints.db`.
5. Delete stale `.octoagent` directories only after confirming the copied data is present.
6. Start services with `./scripts/start-daemon.sh`.
7. Verify with `make smoke-real SMOKE_TIMEOUT_SECONDS=60` and `make check-legacy-paths`.

## Recovery

If checkpoint or memory files are corrupted, stop services, move the affected file aside with a timestamped `.bak` suffix, and restart. OctoAgent will recreate the runtime file. Restore only known-good data from backups.

## CI Guard

`scripts/check_legacy_paths.py` fails CI if source-controlled files reintroduce known stale runtime path patterns.
