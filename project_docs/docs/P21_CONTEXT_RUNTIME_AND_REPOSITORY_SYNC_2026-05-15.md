# P21 Context, Runtime, And Repository Sync Report

**Date**: 2026-05-15
**Host**: 2号机 `192.168.110.2`
**Project root**: `/home/sieve-pub/public-workspace/octoagent`

## Executive Summary

This pass stabilised OctoAgent's long-context agent loop, runtime identity,
local provider configuration, repository hygiene, and Python style baseline.
The main failure mode was a long historical LangGraph thread accumulating
runtime-injected system messages until the local model returned repeated
context-window `400` errors.  The runtime now trims system context within a
bounded budget, retries context errors with a hard safety cap, and keeps
future long sessions from preserving every generated checkpoint message.

The working tree was also normalised with Ruff/PEP8 formatting across backend
Python code. Runtime JSON state is ignored rather than committed, while source,
tests, UI integration files, and documentation remain part of the repository
sync.

## Key Repairs

- Bounded model context trimming in `src.models.factory`, including runtime
  system-message budgeting and a hard retry cap.
- Repaired POSIX runtime identity resolution so daemon processes with UID 1000
  resolve to `sieve-pub` and `/home/sieve-pub`, even when sudo leaves root-like
  environment variables behind.
- Repaired runtime permission targeting so writable paths are normalised to the
  actual runtime UID/GID instead of stale `SUDO_UID/SUDO_GID` values.
- Added a Jina compatibility package for SSRF-safe redirect handling expected
  by the community client tests.
- Added fallback Agency templates so `agency-ui-designer` remains available
  even when the optional Agency template bundle is missing.
- Added Postgres checkpointer maintenance hooks for cancelled-run cleanup and
  `keep_latest` pruning.
- Made the custom checkpointer import path lighter by deferring full app-config
  import until saver construction.
- Configured the Google API key in the ignored local `.env`; the secret is not
  committed.
- Ignored local runtime state under `backend/runtime/` and
  `workspace/self_evolution/`.
- Cleared the backend Ruff debt: 88 reported issues are now 0.

## Current Architecture Reading

The active product path remains:

`Next.js WebUI -> FastAPI gateway -> LangGraph runtime -> Postgres checkpointer`

The strongest seams are now:

- `models.factory`: provider selection, fallback, context safety, and provider
  error normalisation.
- `runtime_identity` plus `runtime_permissions`: host ownership and portable
  runtime-root semantics.
- `agents.checkpointer.async_provider`: persistence adapter construction and
  LangGraph maintenance capabilities.
- `gateway.routers.*`: HTTP contract layer over runtime modules.
- `task_workspaces` and `workflow_core`: workflow truth and projections.

The next high-value deepening opportunities are:

- Consolidate model-context budgeting and session-compaction budgeting into a
  single context budget module.
- Move runtime settings JSON (`backend/runtime/rag_config.json`) behind a
  repository-independent data-root abstraction.
- Split the gateway router registry into product groups with a generated
  contract snapshot to prevent accidental route drift.
- Reduce import-time side effects in config/model modules so daemon startup
  does less provider/cache work before the service is ready.

## Verification

- `cd backend && . .venv/bin/activate && ruff check .`
- `cd backend && . .venv/bin/activate && ruff format . --check`
- `cd backend && . .venv/bin/activate && pytest`
- `cd frontend && pnpm typecheck`

Known non-fatal runtime notes:

- `GOOGLE_API_KEY` is configured locally only.
- `workspace/default/agents/*/SOUL.md` deletions are kept as the current local
  repository truth for sync.
- Runtime state remains on disk but is ignored and excluded from git history.
