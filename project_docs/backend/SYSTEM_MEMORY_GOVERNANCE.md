# System Memory Governance

## Scope

`SystemRAGStore` is the backend-owned semantic memory layer for system-generated operational context.

It is not the same as:

- user-editable global memory in `.octoagent/global_memory.json`
- per-thread conversational memory extracted by the standard memory pipeline
- task-local runtime state stored in task workspace metadata

System memory exists to retain backend-generated summaries, skill-evolution signals, and operational observations that should be searchable across sessions without becoming user-editable prompt state.

## Allowed Namespaces

Current intended namespaces are:

- `conversation_summary`
- `skill_evolution`
- `system_insight`

New namespaces should only be added when they represent stable system-owned categories with a clear producer, retrieval audience, and retention reason.

## Write Boundary

System memory is write-restricted.

- Backend services may write entries through `SystemRAGStore.add()` or `add_batch()`.
- Gateway only exposes read-only system-memory endpoints.
- Frontend and operators must not directly mutate DuckDB rows through UI flows.
- User prompts, uploaded files, and arbitrary external payloads must not be written straight into system memory without an explicit summarization or governance layer.

This boundary exists so system memory remains a curated backend artifact instead of turning into an ungoverned shadow prompt store.

## Retrieval Boundary

Read-only endpoints:

- `GET /api/memory/system/stats`
- `POST /api/memory/system/search`
- `GET /api/memory/system/list`

Retrieval rules:

- Prefer namespace-filtered queries for operator tooling and diagnostics.
- Use semantic search for discovery, not as an implicit authorization bypass.
- Treat results as operational context, not as canonical source-of-truth replacing task workspaces, checkpoints, or audit logs.
- UI/API consumers should surface namespace and metadata so operators can judge provenance.
- The backend now enforces a namespace allowlist and clamps search/list result windows before queries hit DuckDB.
- `GET /api/memory/system/stats` now exposes governance telemetry for operators: read-only status, allowed namespaces, max search top-k, and max list limit.

## Retention Policy

System memory is intentionally durable, but not unbounded.

- Retain high-signal summaries and operational insights.
- Avoid bulk insertion of raw transcripts or duplicate tool output.
- Prefer summarized entries over verbose copies of runtime logs.
- When retention pressure appears, prune by namespace policy and duplication rate rather than deleting recent data indiscriminately.

Recommended future pruning order:

1. Duplicate or near-duplicate `system_insight` entries.
2. Low-value `conversation_summary` entries already superseded by fresher summaries.
3. Stale `skill_evolution` entries that were operationally invalidated.

## System Tool Memory Policy

The Letta-style `tool_policy` memory block is the runtime home for durable system-tool rules. It should include these operator rules:

- Unqualified "system" means the OctoAgent agent system/runtime. Use "operating system", "OS", "host", "machine", or "server" for host operating-system work, and ask a clarification when the distinction changes the action.
- Before installing any tool, package, runtime, or dependency, ask the user for explicit confirmation of the package/tool list, target tool directory, and whether the install changes the host OS or OctoAgent runtime.
- Install tool-owned dependencies and artifacts under `runtime/system_tools/<tool_name>/`; only modify shared runtime environments such as `backend/.venv` after explicit user confirmation that the OctoAgent runtime itself should change.
- After installation, run a real verification command and update `project_docs/TOOLS_CATALOG.md` or the owning tool documentation with path and usage notes.

Because `workspace/default/memory.json` is runtime state and intentionally ignored by Git, durable repository truth for this policy lives in this governance document and `project_docs/TOOLS_CATALOG.md`; operators may mirror it into the active `tool_policy` memory block at runtime.

## Operational Guardrails

Operators should treat `.octoagent/system_memory.duckdb` as managed runtime data.

- Back up the DuckDB file before manual repair or schema work.
- Do not edit the database in place while the gateway is actively writing.
- If embedding configuration changes materially, validate search quality before trusting old vectors.
- If the file is corrupted, restore from backup or rebuild from approved producers rather than patching rows ad hoc.

## Governance Requirements

Any new producer that writes into system memory must define:

- producer name and owning module
- namespace used
- write trigger and cadence
- expected retrieval consumers
- retention expectation
- failure mode if embeddings or DuckDB are unavailable

Fail closed guidance:

- If the store cannot initialize, the system should degrade gracefully and continue without claiming system-memory coverage.
- If semantic search fails, callers should surface the failure instead of silently pretending no memories exist.

## Non-Goals

System memory should not become:

- a user-controlled long-term prompt editor
- a replacement for structured audit logs
- a generic file archive
- a hidden persistence layer for router-local state

## Current Gaps

The current implementation now enforces namespace allowlists for writers and query callers, and exposes governance limits through the stats endpoint. Remaining follow-on work should include:

- explicit retention tooling or scheduled compaction
- operator-safe export/import workflow
- health checks covering DuckDB availability and embedding backend drift
- a richer frontend/operator panel for system-memory visibility beyond the read-only API surface