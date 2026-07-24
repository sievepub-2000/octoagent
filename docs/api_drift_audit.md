# Backend↔Frontend API drift audit (v2, prefix-aware)

- Backend routes scanned: **276**
- Frontend `/api/...` literal URLs (unique): **192**
- Backend routes covered by a frontend URL: **214**
- Frontend URLs matched to a backend route:   **192**

Matching: backend `{var}` segments treated as `[^/]+`; frontend `${expr}` likewise.
Caveat: this still misses HTTP calls assembled from non-literal base URLs (e.g. `fetch(url)` where `url` is built elsewhere), so section A must still be cross-checked.

## A. Backend routes with no frontend reference (62)

### `agents.py` (2)

- `GET    /api/agents/{name}/avatar`
- `POST   /api/agents/{name}/avatar`

### `artifacts.py` (2)

- `DELETE /api/threads/{thread_id}/artifacts/{path:path}`
- `GET    /api/threads/{thread_id}/artifacts/{path:path}`

### `auth.py` (1)

- `GET    /api/auth/me`

### `capabilities.py` (3)

- `GET    /api/capabilities/binding-contract`
- `GET    /api/capabilities/policies/precheck`
- `POST   /api/capabilities/invalidate-cache`

### `channels.py` (2)

- `GET    /api/channels/{name}/login-status`
- `POST   /api/channels/{name}/ingest`

### `distributed_execution.py` (5)

- `POST   /api/execution-nodes/dispatch`
- `POST   /api/execution-nodes/dispatches/{dispatch_id}/replay`
- `POST   /api/execution-nodes/dispatches/{dispatch_id}/result`
- `POST   /api/execution-nodes/worker/dispatch`
- `POST   /api/execution-nodes/{node_id}/heartbeat`

### `hooks.py` (2)

- `GET    /api/hooks/state`
- `POST   /api/hooks/emit`

### `memory.py` (6)

- `DELETE /api/memory/global/{entry_id}`
- `GET    /api/memory/global`
- `GET    /api/memory/status`
- `GET    /api/memory/system/stats`
- `POST   /api/memory/global`
- `PUT    /api/memory/global/{entry_id}`

### `metrics.py` (4)

- `GET    /api/metrics/governance`
- `GET    /api/metrics/memory-health`
- `GET    /metrics`
- `POST   /api/metrics/increment/{metric_name}`

### `model_auth.py` (1)

- `GET    /api/model-auth/{provider_id}/oauth/callback`

### `module_status.py` (1)

- `GET    /api/system/modules/status`

### `multi_tenant.py` (2)

- `GET    /api/tenants/export`
- `GET    /api/tenants/{tenant_id}/limits/agents`

### `optimization_program.py` (4)

- `GET    /api/optimization/metrics`
- `GET    /api/optimization/program`
- `GET    /api/optimization/roadmap`
- `GET    /api/optimization/scorecard`

### `query_engine.py` (5)

- `GET    /api/query-engine/maintenance`
- `GET    /api/query-engine/sessions/{session_id}/replay-context`
- `POST   /api/query-engine/maintenance/run`
- `POST   /api/query-engine/sessions/{session_id}/recover`
- `POST   /api/query-engine/sessions/{session_id}/summary-quality`

### `rag_config.py` (1)

- `POST   /api/runtime/rag-config/download`

### `runtime.py` (6)

- `DELETE /api/runtime/langgraph-contract/threads/{thread_id}`
- `GET    /api/runtime/langgraph-contract`
- `GET    /api/runtime/provider-contracts`
- `POST   /api/runtime/langgraph-contract/copy`
- `POST   /api/runtime/langgraph-contract/prune`
- `POST   /api/runtime/langgraph-contract/threads/{thread_id}/lifecycle`

### `self_evolution.py` (1)

- `GET    /api/evolution/proposals/{proposal_id}`

### `skill_evolution.py` (1)

- `GET    /api/skill-evolution/metrics/{skill_name}`

### `software_interfaces.py` (4)

- `DELETE /api/software-interfaces/connections/{connection_id}`
- `GET    /api/software-interfaces/{toolkit}/triggers`
- `GET    /api/software-interfaces/{toolkit}/triggers/available`
- `POST   /api/software-interfaces/connections/{connection_id}/sync`

### `suggestions.py` (1)

- `POST   /api/threads/{thread_id}/suggestions`

### `system_update.py` (5)

- `GET    /api/system/update/auto-config`
- `GET    /api/system/update/check`
- `GET    /api/system/version`
- `POST   /api/system/update/apply`
- `POST   /api/system/update/auto-config`

### `task_workspaces.py` (2)

- `GET    /api/task-workspaces/{task_id}/artifacts/{artifact_path:path}`
- `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/handoff`

### `ws_events.py` (1)

- `WEBSOCKET /ws/events`

## B. Frontend URLs not matching any backend route (0)


## C. Matched pairs (214)

- `DELETE /api/agents/{name}` ← `agents.py`
- `GET    /api/agent-templates` ← `agents.py`
- `GET    /api/agent-templates/{skill_name}/{template_id}` ← `agents.py`
- `GET    /api/agents` ← `agents.py`
- `GET    /api/agents/check` ← `agents.py`
- `GET    /api/agents/{name}` ← `agents.py`
- `POST   /api/agents` ← `agents.py`
- `PUT    /api/agents/{name}` ← `agents.py`
- `PUT    /api/agents/{name}/conversations/{thread_id}` ← `agents.py`
- `POST   /api/auth/device-login` ← `auth.py`
- `POST   /api/auth/device/verify` ← `auth.py`
- `POST   /api/auth/device/verify/start` ← `auth.py`
- `POST   /api/auth/login` ← `auth.py`
- `POST   /api/auth/register/start` ← `auth.py`
- `POST   /api/auth/register/verify` ← `auth.py`
- `GET    /api/bootstrap/status` ← `bootstrap.py`
- `POST   /api/bootstrap/guide` ← `bootstrap.py`
- `POST   /api/bootstrap/install` ← `bootstrap.py`
- `POST   /api/brain/plan` ← `brain.py`
- `GET    /api/browser-runtime/capabilities` ← `browser_runtime.py`
- `GET    /api/browser-runtime/providers` ← `browser_runtime.py`
- `GET    /api/browser-runtime/sessions` ← `browser_runtime.py`
- `GET    /api/browser-runtime/sessions/{session_id}` ← `browser_runtime.py`
- `POST   /api/browser-runtime/sessions` ← `browser_runtime.py`
- `POST   /api/browser-runtime/sessions/{session_id}/execute-next` ← `browser_runtime.py`
- `POST   /api/browser-runtime/sessions/{session_id}/recover` ← `browser_runtime.py`
- `POST   /api/browser-runtime/sessions/{session_id}/status` ← `browser_runtime.py`
- `GET    /api/capabilities/audit` ← `capabilities.py`
- `GET    /api/capabilities/compat/preview` ← `capabilities.py`
- `GET    /api/capabilities/inventory` ← `capabilities.py`
- `GET    /api/capabilities/policies` ← `capabilities.py`
- `GET    /api/capabilities/policies/export` ← `capabilities.py`
- `GET    /api/capabilities/registry` ← `capabilities.py`
- `GET    /api/capabilities/runtime-state` ← `capabilities.py`
- `GET    /api/capabilities/{category}` ← `capabilities.py`
- `POST   /api/capabilities/migrate` ← `capabilities.py`
- `POST   /api/capabilities/policies/import` ← `capabilities.py`
- `PUT    /api/capabilities/compat/settings` ← `capabilities.py`
- `PUT    /api/capabilities/policies/{capability_id:path}` ← `capabilities.py`
- `PUT    /api/capabilities/registry/{capability_id:path}` ← `capabilities.py`
- `DELETE /api/channels/{name}/config` ← `channels.py`
- `GET    /api/channels/` ← `channels.py`
- `GET    /api/channels/{name}/identity` ← `channels.py`
- `GET    /api/channels/{name}/qrcode` ← `channels.py`
- `POST   /api/channels/{name}/logout` ← `channels.py`
- `POST   /api/channels/{name}/restart` ← `channels.py`
- `PUT    /api/channels/{name}/config` ← `channels.py`
- `PUT    /api/channels/{name}/enabled` ← `channels.py`
- `DELETE /api/execution-nodes/{node_id}` ← `distributed_execution.py`
- `GET    /api/execution-nodes/history/dispatches` ← `distributed_execution.py`
- `GET    /api/execution-nodes/{node_id}` ← `distributed_execution.py`
- `POST   /api/execution-nodes/route` ← `distributed_execution.py`
- `GET    /api/hooks` ← `hooks.py`
- `PUT    /api/hooks/{hook_name}` ← `hooks.py`
- `DELETE /api/mcp/servers/{name}` ← `mcp.py`
- `GET    /api/mcp/config` ← `mcp.py`
- `POST   /api/mcp/servers` ← `mcp.py`
- `PUT    /api/mcp/config` ← `mcp.py`
- `GET    /api/memory` ← `memory.py`
- `GET    /api/memory/schema-status` ← `memory.py`
- `DELETE /api/metrics/{metric_name}` ← `metrics.py`
- `GET    /api/metrics/json` ← `metrics.py`
- `GET    /api/model-auth/status` ← `model_auth.py`
- `GET    /api/model-auth/templates` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/authorize` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/logout` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/oauth/complete` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/oauth/confirm` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/oauth/models` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/oauth/start` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/sync-model` ← `model_auth.py`
- `POST   /api/model-auth/{provider_id}/test` ← `model_auth.py`
- `DELETE /api/models/{model_name}` ← `models.py`
- `GET    /api/fallback-pool/status` ← `models.py`
- `GET    /api/models` ← `models.py`
- `GET    /api/models/{model_name}` ← `models.py`
- `POST   /api/models` ← `models.py`
- `PUT    /api/models/{model_name}` ← `models.py`
- `DELETE /api/tenants/{tenant_id}` ← `multi_tenant.py`
- `GET    /api/tenants/governance` ← `multi_tenant.py`
- `GET    /api/tenants/{tenant_id}` ← `multi_tenant.py`
- `GET    /api/tenants/{tenant_id}/limits/workspaces` ← `multi_tenant.py`
- `PUT    /api/tenants/{tenant_id}/policy` ← `multi_tenant.py`
- `GET    /api/observation/tasks/{task_id}/timeline` ← `observation.py`
- `GET    /api/observation/tool-trace` ← `observation.py`
- `GET    /api/orchestration/capabilities` ← `orchestration.py`
- `GET    /api/orchestration/graphs/seed` ← `orchestration.py`
- `GET    /api/orchestration/prompt-stacks` ← `orchestration.py`
- `DELETE /api/plugins/{plugin_id}` ← `plugins.py`
- `GET    /api/plugins/capabilities` ← `plugins.py`
- `GET    /api/plugins/manifests` ← `plugins.py`
- `GET    /api/plugins/registry` ← `plugins.py`
- `POST   /api/plugins/install` ← `plugins.py`
- `POST   /api/plugins/recommendations` ← `plugins.py`
- `POST   /api/plugins/{plugin_id}/disable` ← `plugins.py`
- `POST   /api/plugins/{plugin_id}/enable` ← `plugins.py`
- `GET    /api/query-engine/capabilities` ← `query_engine.py`
- `GET    /api/query-engine/sessions` ← `query_engine.py`
- `GET    /api/query-engine/sessions/{session_id}` ← `query_engine.py`
- `POST   /api/query-engine/plan-operation` ← `query_engine.py`
- `POST   /api/query-engine/sessions/{session_id}/compact` ← `query_engine.py`
- `POST   /api/query-engine/sessions/{session_id}/execute` ← `query_engine.py`
- `POST   /api/query-engine/sessions/{session_id}/refresh-profile` ← `query_engine.py`
- `POST   /api/query-engine/sessions/{session_id}/turns` ← `query_engine.py`
- `GET    /api/reflection/export` ← `reflection.py`
- `GET    /api/reflection/insights` ← `reflection.py`
- `GET    /api/reflection/observations` ← `reflection.py`
- `GET    /api/reflection/summary` ← `reflection.py`
- `POST   /api/reflection/insights/derive` ← `reflection.py`
- `POST   /api/reflection/observations` ← `reflection.py`
- `GET    /api/research-runtime/capabilities` ← `research_runtime.py`
- `GET    /api/research-runtime/experiments` ← `research_runtime.py`
- `GET    /api/research-runtime/experiments/{experiment_id}` ← `research_runtime.py`
- `GET    /api/research-runtime/experiments/{experiment_id}/trials` ← `research_runtime.py`
- `GET    /api/research-runtime/programs` ← `research_runtime.py`
- `POST   /api/research-runtime/experiments` ← `research_runtime.py`
- `POST   /api/research-runtime/experiments/{experiment_id}/run` ← `research_runtime.py`
- `GET    /api/runtime/capabilities` ← `runtime.py`
- `GET    /api/runtime/doctor` ← `runtime.py`
- `GET    /api/runtime/long-running-health` ← `runtime.py`
- `GET    /api/runtime/maintenance/status` ← `runtime.py`
- `GET    /api/runtime/provider-health` ← `runtime.py`
- `GET    /api/runtime/run-records` ← `runtime.py`
- `GET    /api/runtime/system-guard/export` ← `runtime.py`
- `GET    /api/runtime/system-guard/status` ← `runtime.py`
- `POST   /api/runtime/maintenance/run` ← `runtime.py`
- `POST   /api/runtime/system-guard/repair` ← `runtime.py`
- `GET    /api/runtime/profile` ← `runtime_profile.py`
- `GET    /api/evolution/audit` ← `self_evolution.py`
- `GET    /api/evolution/export` ← `self_evolution.py`
- `GET    /api/evolution/proposals` ← `self_evolution.py`
- `POST   /api/evolution/proposals` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/approve` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/promote` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/reject` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/rollback` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/shadow-run` ← `self_evolution.py`
- `POST   /api/evolution/proposals/{proposal_id}/validate` ← `self_evolution.py`
- `GET    /api/setup/status` ← `setup.py`
- `POST   /api/setup/apply` ← `setup.py`
- `POST   /api/setup/browse-directory` ← `setup.py`
- `POST   /api/setup/create-directory` ← `setup.py`
- `POST   /api/setup/validate-workspace` ← `setup.py`
- `GET    /api/skill-evolution/config` ← `skill_evolution.py`
- `GET    /api/skill-evolution/health` ← `skill_evolution.py`
- `GET    /api/skill-evolution/metrics` ← `skill_evolution.py`
- `GET    /api/skill-evolution/records` ← `skill_evolution.py`
- `GET    /api/skill-evolution/skills` ← `skill_evolution.py`
- `GET    /api/skill-evolution/skills/{skill_name}/versions` ← `skill_evolution.py`
- `GET    /api/skill-evolution/trust-scores` ← `skill_evolution.py`
- `POST   /api/skill-evolution/skills/{skill_name}/register` ← `skill_evolution.py`
- `PUT    /api/skill-evolution/config` ← `skill_evolution.py`
- `DELETE /api/skills/{skill_name}` ← `skills.py`
- `GET    /api/skills` ← `skills.py`
- `GET    /api/skills/{skill_name}` ← `skills.py`
- `POST   /api/skills` ← `skills.py`
- `POST   /api/skills/install` ← `skills.py`
- `POST   /api/skills/install/agency-agents` ← `skills.py`
- `PUT    /api/skills/{skill_name}` ← `skills.py`
- `GET    /api/software-interfaces/catalog` ← `software_interfaces.py`
- `GET    /api/software-interfaces/connections` ← `software_interfaces.py`
- `GET    /api/software-interfaces/status` ← `software_interfaces.py`
- `GET    /api/software-interfaces/{toolkit}/scopes` ← `software_interfaces.py`
- `GET    /api/software-interfaces/{toolkit}/tools` ← `software_interfaces.py`
- `POST   /api/software-interfaces/{toolkit}/authorize` ← `software_interfaces.py`
- `POST   /api/software-interfaces/{toolkit}/logout` ← `software_interfaces.py`
- `PUT    /api/software-interfaces/{toolkit}/scopes` ← `software_interfaces.py`
- `DELETE /api/task-workspaces/{task_id}` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/agents` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/agents/{agent_id}/messages` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/artifacts` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/builder-actions/history` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/builder-actions/preview` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/cards` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/checkpoints` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/result` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/run-log` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/studio-runtime` ← `task_workspaces.py`
- `GET    /api/task-workspaces/{task_id}/studio-runtime/events` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/messages` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/pause` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/resume` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/agents/{agent_id}/terminate` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/builder-actions/apply` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/builder-actions/apply-batch` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/checkpoints` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/compile` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/pause` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/resume` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/run` ← `task_workspaces.py`
- `POST   /api/task-workspaces/{task_id}/terminate` ← `task_workspaces.py`
- `PUT    /api/task-workspaces/{task_id}` ← `task_workspaces.py`
- `PUT    /api/task-workspaces/{task_id}/cards` ← `task_workspaces.py`
- `GET    /api/tools/desktop-control/status` ← `tools_registry.py`
- `GET    /api/tools/registry` ← `tools_registry.py`
- `DELETE /api/threads/{thread_id}/uploads/{filename}` ← `uploads.py`
- `GET    /api/threads/{thread_id}/uploads/list` ← `uploads.py`
