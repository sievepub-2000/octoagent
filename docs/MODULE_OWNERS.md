# OctoAgent Module Ownership Map

Status: **canonical** as of 2026-05-27.
Supersedes the "Phase 7 semantic dedup deferred" follow-up noted in
[`CHANGELOG.md`](../CHANGELOG.md) under the 2026-05-26 entry.

## Why this document exists

After the 2026-05-26 topology freeze (48 → 11 top-level domains under
`backend/src/`), reviewers asked whether the four `agents/*` subdomains
were a *physical* split of one responsibility or whether each truly owns
a distinct concern. This document closes that question: each subdomain
has a unique, non-overlapping role, and the apparent overlap is a
naming artifact (every domain happens to have a `contracts.py`, a
`service.py`, etc.). The boundaries below are enforced by the
[`.importlinter`](../.importlinter) contracts and by
[`scripts/check_topology_freeze.py`](../scripts/check_topology_freeze.py).

## The four `agents/*` subdomains

| Subdomain | Owns | Public surface |
| --- | --- | --- |
| `agents.core` | Session lifecycle, role definitions, instruction contracts, run records, termination policies. **Stateless.** | `AgentCoreService`, `get_agent_core_service` |
| `agents.runtime` | The provider abstraction over how an agent is *executed* (LangGraph in-process vs remote). Builds providers, marshals execution snapshots. **Stateful at the manager level.** | `AgentRuntimeManager`, `AgentExecutionRequest/Result`, `AgentRuntimeProvider*`, `LangGraphWorkflowContractService` |
| `agents.lead_agent` | The product-level lead agent — the kernel and graph builder that actually executes user turns (Hermes-class durable-execution semantics, OctoAgent-native). Consumes `core` + `runtime`. | `make_lead_agent`, `OctoLeadAgentKernel`, `LeadAgentKernelContract` |
| `agents.generic` | Low-privilege silent maintenance agent (runtime ledger cleanup, query-session compaction). **No external model calls.** | `GenericMaintenanceAgent`, `GenericAgentStatus` |

## Dependency direction (top → bottom)

```
agents.lead_agent  ──►  agents.runtime  ──►  agents.core
                                              ▲
agents.generic ──────────────────────────────┘
        (maintenance only — never reaches into lead_agent)
```

Reverse edges (e.g. `agents.core → agents.lead_agent`) are forbidden;
they would create a runtime-builds-product cycle.

## Why we are NOT physically merging them

A single `agents/` module would re-couple the four lifecycles:

* `lead_agent` is the largest and most product-coupled file set; it
  pulls LangGraph wiring, prompt building, and tool registration.
* `generic` is the smallest and runs in a background thread on a 30
  minute cadence — it is explicitly **forbidden** from importing
  `lead_agent` (would expose the maintenance loop to model providers).
* `runtime` is the only subdomain that imports `langgraph_remote` and
  the in-process LangGraph runtime; merging it into `core` would force
  every consumer of session/role primitives to pull LangGraph
  transitively.
* `core` is the cheapest to import (no LangGraph, no LangChain). Tests
  rely on this: `tests/governance/test_about_integrity.py` imports
  `agents.core.instruction_contracts` without dragging the runtime.

The cost of a merge (loss of selective importability + cycle risk)
outweighs the benefit (one fewer directory).

## Boundary enforcement

* `.importlinter` contracts lock the **inbound** edges of every
  top-level domain (`utils`, `community`, `models`, `governance`,
  `harness`) against the product layer.
* `scripts/check_topology_freeze.py` locks the `backend/src/` directory
  shape — any new top-level package fails CI.
* This document is the **canonical** answer to "are these duplicates?".
  Future contributors who think they see duplication should first read
  the public surfaces above, then open an RFC if they still want a
  merge.

## Open follow-ups

* `agents.runtime` and `agents.core` could expose a single re-export
  module (`agents.public`) for downstream consumers that want a stable
  one-line import. This is convenience-only and explicitly NOT a merge.
* The `lead_agent` builder remains heavy; a Phase 8 refactor will split
  the graph-construction code from the kernel runtime methods. Tracked
  separately.
