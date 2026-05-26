# P22 Context, Runtime Config, and Gateway Contract Unification

Date: 2026-05-15

## Scope

This pass unified four previously separate control planes:

- Context budget estimation and trimming
- Session compaction guardrails
- Runtime RAG configuration persistence/application
- Gateway router registration contract validation

The goal was to reduce duplicate heuristics, make startup/runtime behaviour more predictable, and keep the agent platform stable under long-running sessions.

## Deep Module Analysis

### Context Budget

Before this pass, token estimation and message truncation existed independently in the model factory and the session compaction middleware. That made behaviour drift likely: one layer could believe a message set was safe while the next layer had different accounting.

`src.context_budget` is now the shared source of truth for:

- CJK-aware lightweight token estimation
- LangChain/dict message content extraction
- continuation-marker insertion
- per-message truncation
- bounded system-message preservation
- recent-message budget selection

The model factory keeps compatibility wrappers for tests and external callers, but delegates the real logic to the shared module.

### Session Compaction

The middleware still owns agent-specific decisions: coalescing identical tool output, choosing compaction strategy under pressure, injecting runtime checkpoints, and updating runtime state. Low-level estimation/truncation now comes from `src.context_budget`.

The compactor also uses the shared estimator for missing token counts, so compaction summaries and preflight estimates use the same accounting family as the model-call retry path.

### Runtime Config

The RAG config router previously mixed API handling, JSON persistence, environment application, model-cache inspection, and import-time side effects in one file.

`src.runtime_config` now owns:

- runtime config path resolution
- atomic JSON writes
- RAG config schema/defaults
- load/save/apply lifecycle
- embedding/reranker singleton reset
- Hugging Face cache inspection

The router now acts as an API adapter. Gateway startup explicitly applies runtime config, while router import keeps legacy idempotent behaviour for processes that import only the router.

### Gateway Router Contract

Router registration previously included routers directly without a central contract. `src.gateway.router_contract` now builds a typed route contract and validates duplicate method/path combinations before registration.

The real gateway route table currently contains 43 routers and 290 API routes. The validation deliberately blocks duplicate route collisions first; tag normalization is left as a future non-breaking cleanup because one existing root router is historically untagged.

### Runtime Identity and Permissions

During validation, services were accidentally started as `root`, causing runtime plugin registry writes to be root-owned. The repo was repaired back to `sieve-pub:sieve-pub` ownership and services were restarted under `sieve-pub`. Runtime identity now reports uid/euid 1000 and `is_root=false`.

## Validation

- `ruff check .`
- `ruff format . --check`
- `pytest -q`: 136 passed, 1 skipped
- `pnpm typecheck`
- `pnpm build`
- Gateway health: `HTTP 200`
- Runtime identity: `sieve-pub`, non-root
- RAG config endpoint: cache hit for embedding and reranker models
- Models endpoint: Gemini model present
- Router contract: 43 routers, 290 routes

## System Recommendations

1. Move remaining runtime JSON stores behind `src.runtime_config`-style services.
2. Add a non-blocking report for missing router tags, then gradually enforce tags once historical routers are normalized.
3. Route all context-pressure metrics through one telemetry event so frontend, runtime, and model factory display the same pressure state.
4. Add a daemon wrapper or service file that always starts OctoAgent as `sieve-pub` to prevent root-owned runtime artifacts.
5. Consider replacing heuristic token accounting with provider-specific tokenizers only at model-boundary hot paths; keep the shared heuristic for low-resource preflight checks.
