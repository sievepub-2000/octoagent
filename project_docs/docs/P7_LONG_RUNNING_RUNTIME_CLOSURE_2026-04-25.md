# P7 Long-Running Runtime Closure

> Date: 2026-04-25
> Canonical project root: `/home/sieve-pub/public-workspace/octoagent`
> Branch policy: `main` only

## Summary

P7 closes the first concrete long-running runtime slice. OctoAgent now has an auditable LangGraph thread/run/checkpoint contract ledger, checkpoint prune/copy/delete semantics at the OctoAgent layer, conversation session maintenance and stale-session recovery hooks, expanded doctor metrics for long-running health, worker isolation counters/limits for blocking runtime paths, and a WebUI operator policy governance surface.

This does not replace LangGraph's own remote persistence engine. Instead, it gives OctoAgent a stable operator-auditable contract above LangGraph so workflows can be inspected, pruned, copied, deleted, and monitored consistently while the underlying LangGraph checkpointer is upgraded or swapped.

## Completed Work

### Workflow and LangGraph contract closure

- Added `backend/src/agent_runtime/workflow_contract.py`.
- Records LangGraph thread, run, checkpoint, task, agent, assistant, graph, and query-session mappings.
- LangGraph executions now record local `run_id` lifecycle:
  - `running`
  - `completed`
  - `failed`
  - `timeout`
  - `cancelled`
- Workflow snapshots now include `langgraph_contract`.
- Studio runtime summaries expose LangGraph contract counts.

### Checkpoint prune/copy/delete

Added runtime APIs:

- `GET /api/runtime/langgraph-contract`
- `POST /api/runtime/langgraph-contract/prune`
- `POST /api/runtime/langgraph-contract/copy`
- `DELETE /api/runtime/langgraph-contract/threads/{thread_id}`

The prune API enforces per-thread caps for checkpoints and runs. The soak test created 40 checkpoints, pruned them to 5, and verified the queue and runtime metrics returned to a stable state.

### Conversation cache and stale-session recovery

QueryEngine now has:

- Active turn budget: `OCTO_QUERY_MAX_ACTIVE_TURNS`, default `8`.
- Runtime event budget: `OCTO_QUERY_MAX_RUNTIME_EVENTS`, default `120`.
- Summary budget: `OCTO_QUERY_MAX_SUMMARIES`, default `20`.
- Automatic session budget enforcement after turns and agent executions.
- Maintenance snapshot and maintenance run APIs:
  - `GET /api/query-engine/maintenance`
  - `POST /api/query-engine/maintenance/run`
- Stale-session recovery API:
  - `POST /api/query-engine/sessions/{session_id}/recover`

### Doctor and long-running metrics

Runtime doctor now checks:

- Runtime disk free space and usage percent.
- Worker isolation queue depth.
- LangGraph contract ledger counts.
- Event loop latency.

New health endpoint:

- `GET /api/runtime/long-running-health`

The doctor smoke now validates memory, disk, worker isolation, LangGraph contract, and query maintenance surfaces.

### Blocking worker isolation and concurrency limits

Added `backend/src/runtime_governance.py` with in-process worker isolation pools:

- `model`
- `browser`
- `system`
- `research`
- `tool`

Default limits are configurable through:

- `OCTO_WORKER_LIMIT_MODEL`
- `OCTO_WORKER_LIMIT_BROWSER`
- `OCTO_WORKER_LIMIT_SYSTEM`
- `OCTO_WORKER_LIMIT_RESEARCH`
- `OCTO_WORKER_LIMIT_TOOL`

LangGraph model calls now pass through the model pool. QueryEngine browser, system, and research targets pass through their respective pools.

### Capability operator policy WebUI

Capability operator policy now has:

- WebUI policy state panel.
- Per-capability decision controls:
  - `inherit`
  - `allow`
  - `audit_only`
  - `deny`
- Audit event display.
- Policy export API with SHA-256 signature.
- Policy import API for operator restore/migration.

## Validation

| Area | Result |
| --- | --- |
| Backend compile | Passed |
| Backend ruff | Passed |
| Doctor/API contract smoke | Passed |
| Long-running soak | Passed |
| Frontend lint | Passed |
| Frontend typecheck | Passed |
| Frontend production build | Passed |

Soak result:

- Generated 40 contract checkpoints.
- Pruned 35 checkpoints and 30 runs.
- Final checkpoint count after prune: 5.
- Worker queues returned to zero.
- Query maintenance completed with zero residual sessions in the isolated smoke context.

## Remaining Production Risk

The OctoAgent-side contract is now in place, but the underlying LangGraph remote checkpointer still needs a production-grade implementation or upgrade that natively supports prune/copy/delete. The project should treat the new contract ledger as the operator control plane and the LangGraph checkpointer upgrade as the storage-plane follow-up.

## Next Work

1. Upgrade `langgraph-api` and confirm compatibility with the new contract ledger.
2. Bind the contract ledger to real LangGraph remote checkpoint APIs where available.
3. Add a production service timer for query maintenance and contract pruning.
4. Add WebUI runtime health panels for disk, event-loop latency, checkpoint count, and worker queues.
5. Add multi-hour soak tests with real workflow execution, not only ledger-level simulation.
6. Add alert thresholds for memory pressure, disk pressure, checkpoint growth, and queue growth.
