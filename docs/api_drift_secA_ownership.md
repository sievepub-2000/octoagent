# Section A — per-router operations ownership classification

Generated against `docs/api_drift_audit.md` after dead-route pruning
(commits 1512c37, e449d1b, 210a1c2).

**Legend**:
- `DEAD-CONFIRMED`  – no in-repo reference outside the router file (safe to remove pending ops sign-off)
- `REF-INTERNAL`    – referenced from backend/tests/docs (kept by other internal code)
- `NEEDS-OPS`       – admin / operator surface; requires PM/ops confirmation before removal

| Router | Endpoint | Refs | Disposition |
|--------|----------|------|-------------|
| `agents.py` | `GET    /api/agents/{name}/avatar` | 3 | REF-INTERNAL |
| `agents.py` | `GET    /api/user-profile` | 0 | DEAD-CONFIRMED |
| `agents.py` | `POST   /api/agents/{name}/avatar` | 3 | REF-INTERNAL |
| `agents.py` | `PUT    /api/user-profile` | 0 | DEAD-CONFIRMED |
| `artifacts.py` | `GET    /api/threads/{thread_id}/artifacts/{path:path}` | 6 | REF-INTERNAL |
| `auth.py` | `GET    /api/auth/me` | 1 | REF-INTERNAL |
| `capabilities.py` | `GET    /api/capabilities/binding-contract` | 1 | REF-INTERNAL |
| `capabilities.py` | `GET    /api/capabilities/policies/precheck` | 1 | REF-INTERNAL |
| `capabilities.py` | `POST   /api/capabilities/invalidate-cache` | 1 | REF-INTERNAL |
| `channels.py` | `GET    /api/channels/{name}/login-status` | 9 | REF-INTERNAL |
| `channels.py` | `POST   /api/channels/{name}/ingest` | 9 | REF-INTERNAL |
| `distributed_execution.py` | `POST   /api/execution-nodes/dispatch` | 3 | REF-INTERNAL |
| `distributed_execution.py` | `POST   /api/execution-nodes/dispatches/{dispatch_id}/replay` | 2 | REF-INTERNAL |
| `distributed_execution.py` | `POST   /api/execution-nodes/dispatches/{dispatch_id}/result` | 2 | REF-INTERNAL |
| `distributed_execution.py` | `POST   /api/execution-nodes/worker/dispatch` | 2 | REF-INTERNAL |
| `distributed_execution.py` | `POST   /api/execution-nodes/{node_id}/heartbeat` | 7 | REF-INTERNAL |
| `hooks.py` | `DELETE /api/hooks/webhooks/{webhook_id}` | 0 | NEEDS-OPS |
| `hooks.py` | `GET    /api/hooks/runtime` | 0 | NEEDS-OPS |
| `hooks.py` | `GET    /api/hooks/state` | 1 | REF-INTERNAL |
| `hooks.py` | `GET    /api/hooks/webhooks` | 0 | NEEDS-OPS |
| `hooks.py` | `POST   /api/hooks/emit` | 1 | REF-INTERNAL |
| `hooks.py` | `POST   /api/hooks/webhooks` | 0 | NEEDS-OPS |
| `mcp_server.py` | `GET    /api/mcp_server/info` | 0 | NEEDS-OPS |
| `mcp_server.py` | `GET    /api/mcp_server/tools` | 0 | NEEDS-OPS |
| `mcp_server.py` | `POST   /api/mcp_server/jsonrpc` | 0 | NEEDS-OPS |
| `memory.py` | `DELETE /api/memory/global/{entry_id}` | 1 | REF-INTERNAL |
| `memory.py` | `GET    /api/memory/config` | 0 | NEEDS-OPS |
| `memory.py` | `GET    /api/memory/global` | 1 | REF-INTERNAL |
| `memory.py` | `GET    /api/memory/governance` | 0 | NEEDS-OPS |
| `memory.py` | `GET    /api/memory/layers` | 0 | NEEDS-OPS |
| `memory.py` | `GET    /api/memory/status` | 1 | REF-INTERNAL |
| `memory.py` | `GET    /api/memory/system/list` | 0 | NEEDS-OPS |
| `memory.py` | `GET    /api/memory/system/stats` | 1 | REF-INTERNAL |
| `memory.py` | `POST   /api/memory/global` | 1 | REF-INTERNAL |
| `memory.py` | `POST   /api/memory/global/import` | 0 | NEEDS-OPS |
| `memory.py` | `POST   /api/memory/reload` | 0 | NEEDS-OPS |
| `memory.py` | `POST   /api/memory/system/cleanup` | 0 | NEEDS-OPS |
| `memory.py` | `POST   /api/memory/system/search` | 0 | NEEDS-OPS |
| `memory.py` | `PUT    /api/memory/global/{entry_id}` | 1 | REF-INTERNAL |
| `metrics.py` | `GET    /api/metrics/governance` | 1 | REF-INTERNAL |
| `metrics.py` | `GET    /api/metrics/memory-health` | 1 | REF-INTERNAL |
| `metrics.py` | `GET    /metrics` | 14 | REF-INTERNAL |
| `metrics.py` | `POST   /api/metrics/increment/{metric_name}` | 1 | REF-INTERNAL |
| `model_auth.py` | `GET    /api/model-auth/{provider_id}/oauth/callback` | 3 | REF-INTERNAL |
| `module_status.py` | `GET    /api/system/modules/status` | 1 | REF-INTERNAL |
| `multi_tenant.py` | `GET    /api/tenants/export` | 2 | REF-INTERNAL |
| `multi_tenant.py` | `GET    /api/tenants/resolve` | 0 | NEEDS-OPS |
| `multi_tenant.py` | `GET    /api/tenants/{tenant_id}/limits/agents` | 6 | REF-INTERNAL |
| `optimization_program.py` | `GET    /api/optimization/metrics` | 1 | REF-INTERNAL |
| `optimization_program.py` | `GET    /api/optimization/program` | 2 | REF-INTERNAL |
| `optimization_program.py` | `GET    /api/optimization/roadmap` | 1 | REF-INTERNAL |
| `optimization_program.py` | `GET    /api/optimization/scorecard` | 1 | REF-INTERNAL |
| `query_engine.py` | `GET    /api/query-engine/maintenance` | 2 | REF-INTERNAL |
| `query_engine.py` | `GET    /api/query-engine/sessions/{session_id}/replay-context` | 2 | REF-INTERNAL |
| `query_engine.py` | `POST   /api/query-engine/maintenance/recover-stale` | 0 | NEEDS-OPS |
| `query_engine.py` | `POST   /api/query-engine/maintenance/run` | 1 | REF-INTERNAL |
| `query_engine.py` | `POST   /api/query-engine/sessions/{session_id}/recover` | 2 | REF-INTERNAL |
| `query_engine.py` | `POST   /api/query-engine/sessions/{session_id}/summary-quality` | 2 | REF-INTERNAL |
| `rag_config.py` | `POST   /api/runtime/rag-config/download` | 0 | DEAD-CONFIRMED |
| `runtime.py` | `DELETE /api/runtime/langgraph-contract/threads/{thread_id}` | 3 | REF-INTERNAL |
| `runtime.py` | `GET    /api/runtime/langgraph-contract` | 4 | REF-INTERNAL |
| `runtime.py` | `GET    /api/runtime/provider-contracts` | 1 | REF-INTERNAL |
| `runtime.py` | `POST   /api/runtime/langgraph-contract/copy` | 2 | REF-INTERNAL |
| `runtime.py` | `POST   /api/runtime/langgraph-contract/prune` | 2 | REF-INTERNAL |
| `runtime.py` | `POST   /api/runtime/langgraph-contract/threads/{thread_id}/lifecycle` | 3 | REF-INTERNAL |
| `self_evolution.py` | `GET    /api/evolution/proposals/{proposal_id}` | 2 | REF-INTERNAL |
| `skill_evolution.py` | `GET    /api/skill-evolution/health/unhealthy` | 0 | NEEDS-OPS |
| `skill_evolution.py` | `GET    /api/skill-evolution/metrics/{skill_name}` | 1 | REF-INTERNAL |
| `software_interfaces.py` | `DELETE /api/software-interfaces/connections/{connection_id}` | 1 | REF-INTERNAL |
| `software_interfaces.py` | `DELETE /api/software-interfaces/triggers/{trigger_id}` | 0 | NEEDS-OPS |
| `software_interfaces.py` | `GET    /api/software-interfaces/toolkits` | 0 | NEEDS-OPS |
| `software_interfaces.py` | `GET    /api/software-interfaces/{toolkit}/triggers` | 1 | REF-INTERNAL |
| `software_interfaces.py` | `GET    /api/software-interfaces/{toolkit}/triggers/available` | 1 | REF-INTERNAL |
| `software_interfaces.py` | `POST   /api/software-interfaces/connections/{connection_id}/sync` | 1 | REF-INTERNAL |
| `software_interfaces.py` | `POST   /api/software-interfaces/execute` | 0 | NEEDS-OPS |
| `software_interfaces.py` | `POST   /api/software-interfaces/triggers` | 0 | NEEDS-OPS |
| `suggestions.py` | `POST   /api/threads/{thread_id}/suggestions` | 7 | REF-INTERNAL |
| `system_update.py` | `GET    /api/system/update/auto-config` | 1 | REF-INTERNAL |
| `system_update.py` | `GET    /api/system/update/check` | 2 | REF-INTERNAL |
| `system_update.py` | `GET    /api/system/version` | 1 | REF-INTERNAL |
| `system_update.py` | `POST   /api/system/update/apply` | 1 | REF-INTERNAL |
| `system_update.py` | `POST   /api/system/update/auto-config` | 1 | REF-INTERNAL |
| `task_workspaces.py` | `GET    /api/task-workspaces/{task_id}/artifacts/{artifact_path:path}` | 12 | REF-INTERNAL |
| `task_workspaces.py` | `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/handoff` | 12 | REF-INTERNAL |
| `ws_events.py` | `WEBSOCKET /ws/events` | 1 | REF-INTERNAL |
