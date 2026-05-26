# Section A reference-source classifier (2026-05-26)

Counts hits per category for each remaining Section A endpoint.
Categories: `backend-prod` (backend/src minus tests), `backend-test`, `frontend-real`, `frontend-mock`, `scripts`, `docs`, `config`.

Verdicts:
- `KEEP`        – has backend-prod or frontend-real caller
- `TEST-ONLY`   – only backend/tests reference it (delete route + test)
- `DOC-ONLY`    – only docs mention it (delete route + doc line)
- `MOCK-ONLY`   – only frontend mock route uses it (delete both)
- `SCRIPT-ONLY` – only scripts/ uses it
- `MIXED-DEAD`  – combination of test/doc/mock/script/config only, no live caller
- `ORPHAN`      – no references found anywhere

| Router | Method | Path | Verdict | Refs |
|--------|--------|------|---------|------|
| `agents.py` | GET | `/api/agents/{name}/avatar` | **KEEP** | backend-prod=5;frontend-real=1 |
| `agents.py` | POST | `/api/agents/{name}/avatar` | **KEEP** | backend-prod=5;frontend-real=1 |
| `artifacts.py` | GET | `/api/threads/{thread_id}/artifacts/{path:path}` | **KEEP** | backend-prod=6;frontend-real=2 |
| `auth.py` | GET | `/api/auth/me` | **KEEP** | backend-prod=2 |
| `capabilities.py` | GET | `/api/capabilities/binding-contract` | **KEEP** | backend-prod=2 |
| `capabilities.py` | GET | `/api/capabilities/policies/precheck` | **KEEP** | backend-prod=2 |
| `capabilities.py` | POST | `/api/capabilities/invalidate-cache` | **KEEP** | backend-prod=2 |
| `channels.py` | GET | `/api/channels/{name}/login-status` | **KEEP** | backend-prod=9;frontend-real=3;scripts=3 |
| `channels.py` | POST | `/api/channels/{name}/ingest` | **KEEP** | backend-prod=9;frontend-real=3;scripts=3 |
| `distributed_execution.py` | POST | `/api/execution-nodes/dispatch` | **KEEP** | backend-prod=6 |
| `distributed_execution.py` | POST | `/api/execution-nodes/dispatches/{dispatch_id}/replay` | **KEEP** | backend-prod=4 |
| `distributed_execution.py` | POST | `/api/execution-nodes/dispatches/{dispatch_id}/result` | **KEEP** | backend-prod=4 |
| `distributed_execution.py` | POST | `/api/execution-nodes/worker/dispatch` | **KEEP** | backend-prod=4 |
| `distributed_execution.py` | POST | `/api/execution-nodes/{node_id}/heartbeat` | **KEEP** | backend-prod=13;frontend-real=1;scripts=1 |
| `hooks.py` | GET | `/api/hooks/state` | **KEEP** | backend-prod=2 |
| `hooks.py` | POST | `/api/hooks/emit` | **KEEP** | backend-prod=2 |
| `memory.py` | DELETE | `/api/memory/global/{entry_id}` | **KEEP** | frontend-real=1 |
| `memory.py` | GET | `/api/memory/global` | **KEEP** | frontend-real=1 |
| `memory.py` | GET | `/api/memory/status` | **KEEP** | backend-prod=2 |
| `memory.py` | GET | `/api/memory/system/stats` | **KEEP** | backend-prod=2 |
| `memory.py` | POST | `/api/memory/global` | **KEEP** | frontend-real=1 |
| `memory.py` | PUT | `/api/memory/global/{entry_id}` | **KEEP** | frontend-real=1 |
| `metrics.py` | GET | `/api/metrics/governance` | **KEEP** | backend-prod=3 |
| `metrics.py` | GET | `/api/metrics/memory-health` | **KEEP** | backend-prod=3 |
| `metrics.py` | GET | `/metrics` | **KEEP** | backend-prod=89;frontend-real=3 |
| `metrics.py` | POST | `/api/metrics/increment/{metric_name}` | **KEEP** | backend-prod=3 |
| `model_auth.py` | GET | `/api/model-auth/{provider_id}/oauth/callback` | **KEEP** | backend-prod=2;frontend-real=2 |
| `module_status.py` | GET | `/api/system/modules/status` | **KEEP** | backend-prod=1;docs=1 |
| `multi_tenant.py` | GET | `/api/tenants/export` | **KEEP** | backend-prod=4 |
| `multi_tenant.py` | GET | `/api/tenants/{tenant_id}/limits/agents` | **KEEP** | backend-prod=11;frontend-real=1 |
| `optimization_program.py` | GET | `/api/optimization/metrics` | **KEEP** | backend-prod=2 |
| `optimization_program.py` | GET | `/api/optimization/program` | **KEEP** | backend-prod=4 |
| `optimization_program.py` | GET | `/api/optimization/roadmap` | **KEEP** | backend-prod=2 |
| `optimization_program.py` | GET | `/api/optimization/scorecard` | **KEEP** | backend-prod=2 |
| `query_engine.py` | GET | `/api/query-engine/maintenance` | **KEEP** | backend-prod=4 |
| `query_engine.py` | GET | `/api/query-engine/sessions/{session_id}/replay-context` | **KEEP** | backend-prod=2;frontend-real=1 |
| `query_engine.py` | POST | `/api/query-engine/maintenance/run` | **KEEP** | backend-prod=2 |
| `query_engine.py` | POST | `/api/query-engine/sessions/{session_id}/recover` | **KEEP** | backend-prod=2;frontend-real=1 |
| `query_engine.py` | POST | `/api/query-engine/sessions/{session_id}/summary-quality` | **KEEP** | backend-prod=2;frontend-real=1 |
| `rag_config.py` | POST | `/api/runtime/rag-config/download` | **ORPHAN** |  |
| `runtime.py` | DELETE | `/api/runtime/langgraph-contract/threads/{thread_id}` | **KEEP** | backend-prod=6 |
| `runtime.py` | GET | `/api/runtime/langgraph-contract` | **KEEP** | backend-prod=8 |
| `runtime.py` | GET | `/api/runtime/provider-contracts` | **KEEP** | backend-prod=2 |
| `runtime.py` | POST | `/api/runtime/langgraph-contract/copy` | **KEEP** | backend-prod=4 |
| `runtime.py` | POST | `/api/runtime/langgraph-contract/prune` | **KEEP** | backend-prod=4 |
| `runtime.py` | POST | `/api/runtime/langgraph-contract/threads/{thread_id}/lifecycle` | **KEEP** | backend-prod=6 |
| `self_evolution.py` | GET | `/api/evolution/proposals/{proposal_id}` | **KEEP** | backend-prod=2;frontend-real=1 |
| `skill_evolution.py` | GET | `/api/skill-evolution/metrics/{skill_name}` | **KEEP** | frontend-real=1 |
| `software_interfaces.py` | DELETE | `/api/software-interfaces/connections/{connection_id}` | **KEEP** | frontend-real=1 |
| `software_interfaces.py` | GET | `/api/software-interfaces/{toolkit}/triggers` | **KEEP** | backend-prod=1;frontend-real=1 |
| `software_interfaces.py` | GET | `/api/software-interfaces/{toolkit}/triggers/available` | **KEEP** | backend-prod=1;frontend-real=1 |
| `software_interfaces.py` | POST | `/api/software-interfaces/connections/{connection_id}/sync` | **KEEP** | frontend-real=1 |
| `suggestions.py` | POST | `/api/threads/{thread_id}/suggestions` | **KEEP** | backend-prod=7;frontend-real=2 |
| `system_update.py` | GET | `/api/system/update/auto-config` | **KEEP** | frontend-real=1 |
| `system_update.py` | GET | `/api/system/update/check` | **KEEP** | frontend-real=2 |
| `system_update.py` | GET | `/api/system/version` | **KEEP** | frontend-real=1 |
| `system_update.py` | POST | `/api/system/update/apply` | **KEEP** | frontend-real=1 |
| `system_update.py` | POST | `/api/system/update/auto-config` | **KEEP** | frontend-real=1 |
| `task_workspaces.py` | GET | `/api/task-workspaces/{task_id}/artifacts/{artifact_path:path}` | **KEEP** | backend-prod=15;frontend-real=5;scripts=1 |
| `task_workspaces.py` | POST | `/api/task-workspaces/{task_id}/agents/{agent_id}/handoff` | **KEEP** | backend-prod=15;frontend-real=5;scripts=1 |
| `ws_events.py` | WEBSOCKET | `/ws/events` | **KEEP** | backend-prod=3 |

## Verdict summary

- `KEEP`: 60
- `ORPHAN`: 1
