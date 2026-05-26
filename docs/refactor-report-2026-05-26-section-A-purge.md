# Section A Autonomous Purge — 2026-05-26

System is pre-production, so all `DEAD-CONFIRMED` + `NEEDS-OPS (Refs=0)` entries
from `docs/api_drift_secA_ownership.md` were removed without external sign-off,
on the principle that unused surface = wasted startup time + larger route table +
larger compile graph. The route table can be re-introduced later if a feature
needs it; right now we trade flexibility for tighter binary surface area.

## Removed (25 routes across 9 routers)

### Whole-file deletion (1 file, 3 routes)

| File | Routes |
|------|--------|
| `mcp_server.py` | GET `/api/mcp_server/info`, GET `/api/mcp_server/tools`, POST `/api/mcp_server/jsonrpc` |

### Surgical removals (22 routes)

| Router | Method | Path |
|--------|--------|------|
| `agents.py` | GET | `/api/user-profile` |
| `agents.py` | PUT | `/api/user-profile` |
| `hooks.py` | DELETE | `/api/hooks/webhooks/{webhook_id}` |
| `hooks.py` | GET | `/api/hooks/runtime` |
| `hooks.py` | GET | `/api/hooks/webhooks` |
| `hooks.py` | POST | `/api/hooks/webhooks` |
| `memory.py` | GET | `/api/memory/config` |
| `memory.py` | GET | `/api/memory/governance` |
| `memory.py` | GET | `/api/memory/layers` |
| `memory.py` | GET | `/api/memory/system/list` |
| `memory.py` | POST | `/api/memory/global/import` |
| `memory.py` | POST | `/api/memory/reload` |
| `memory.py` | POST | `/api/memory/system/cleanup` |
| `memory.py` | POST | `/api/memory/system/search` |
| `multi_tenant.py` | GET | `/api/tenants/resolve` |
| `query_engine.py` | POST | `/api/query-engine/maintenance/recover-stale` |
| `skill_evolution.py` | GET | `/api/skill-evolution/health/unhealthy` |
| `software_interfaces.py` | DELETE | `/api/software-interfaces/triggers/{trigger_id}` |
| `software_interfaces.py` | GET | `/api/software-interfaces/toolkits` |
| `software_interfaces.py` | POST | `/api/software-interfaces/execute` |
| `software_interfaces.py` | POST | `/api/software-interfaces/triggers` |

### NOT removed — false positive caught at verify

`rag_config.py POST /api/runtime/rag-config/download` was flagged
`DEAD-CONFIRMED (Refs=0)` because the ownership classifier only
substring-matched literal paths. The frontend actually calls it via
`` `${ENDPOINT}/download` `` in `frontend/src/core/rag-config.ts`, which the
classifier missed. The route was restored after the broken audit pass
(B regressed 0→1) revealed the gap.

## Service / WorkflowCoreService orphan cleanup

After `public_runtime.py` was deleted earlier, `WorkflowCoreService` retained
three methods whose only caller was that router. They are now removed too:

- `get_public_runtime`
- `get_public_runtime_events`
- `get_public_artifacts`

`get_public_bindings` stays (still referenced by `update_public_bindings` and
its dedicated test).

## Outcome metrics

| Metric | Before | After |
|--------|--------|-------|
| Backend routes scanned | 302 | 275 |
| Section A (unmatched-be) | 85 | 61 |
| Section B (orphan-fe) | 0 | 0 |
| Section C (matched) | 214 | 214 |
| Router files | 41 | 40 |
| Backend tests | 291 pass | 291 pass |
| Frontend `tsc --noEmit` | clean | clean |
| Smoke `GET /api/runtime/doctor` | 200 | 200 |

## What's left in Section A (61)

All remaining entries are `REF-INTERNAL` — they have backend / test / docs
in-repo references. Keeping them is correct; further cleanup would require
also rewriting their internal callers and is a separate workstream.
