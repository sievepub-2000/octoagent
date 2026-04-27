# P11 Release Hardening And Management Smoke - 2026-04-27

## Task List Added

- Centralize Gateway operator/worker permission helpers so router-level checks share one path.
- Improve WebUI follow-up stability while the first response is still streaming.
- Keep the current Next.js UI and optimize in place; do not start a Vue rewrite before launch.
- Add a low-privilege background generic maintenance agent for runtime/query cleanup and long-term memory hygiene primitives.
- Add authenticated management-menu and configuration API smoke coverage.
- Keep 2h/8h/24h soak as the final long-running gate and preserve reports.

## Completed Changes

### Gateway Security

- Added `backend/src/gateway/security.py`.
- Updated multi-tenant and distributed-execution routers to use the shared operator/worker guard helpers.
- Kept development compatibility: production still becomes strict when `OCTO_OPERATOR_TOKEN` and `OCTO_EXECUTION_WORKER_TOKEN` are configured.

### WebUI Follow-Up Stability

- Updated the existing Next.js input flow instead of adding new UI surfaces.
- If the user submits a follow-up while the current response is streaming, the follow-up is queued instead of stopping the stream.
- Added a compact visible queued-follow-up indicator so the action is observable.
- Updated WebUI smoke to verify the follow-up through UI first and then through authoritative thread state when virtualization/stream timing hides the text.

### Generic Maintenance Agent

- Added `backend/src/generic_agent/` as a low-privilege silent maintenance scheduler.
- It runs existing runtime maintenance and query-engine maintenance jobs; it does not call external models, push code, or mutate operator config.
- Wired it into Gateway lifespan and exposed status through `/api/metrics/memory-health`.
- Environment controls: `OCTO_GENERIC_AGENT_ENABLED`, `OCTO_GENERIC_AGENT_INTERVAL_SECONDS`, `OCTO_GENERIC_AGENT_STARTUP_DELAY_SECONDS`.

### Memory/Soak Hardening

- Fixed long-soak validation so concurrent 2h/8h/24h runs do not fail each other by checking global checkpoint counts.
- Short soak passed with active runs settled, worker queue settled, and no alerts.

### Management Smoke

- Added `backend/scripts/run_management_menu_smoke.py`.
- The smoke creates a real local auth user, logs in through `/api/auth/login`, sets session/tenant context in the browser, opens management/config routes, and checks core config APIs.
- Covered routes include auth, chat, agents, workflows, tasks, models, MCP, plugins, skills, tools, channels, memory, evolution, and settings sections.
- Covered APIs include auth, models, bootstrap, MCP, plugins, skills, tools, channels, memory stats, skill evolution, memory health, tenants, and execution nodes.

## Validation Results

- Backend compile: passed.
- Ruff: passed.
- Frontend typecheck: passed.
- Management menu/API smoke: passed.
- WebUI smoke: passed; `multi_turn_message_sent=true`, with follow-up confirmed from authoritative thread state.
- Short long-running soak: passed.
- System doctor: passes once the working tree is committed; pre-commit failure is only `git-sync` due local pending changes.
- Generic agent status: running through `/api/metrics/memory-health`, `last_error=null`.

## Current Module Assessment

- Frontend/WebUI: release candidate. The main flow, auth page, management/config pages, and follow-up submission path are tested. Remaining work after launch should be richer Playwright coverage for failure states and long streaming sessions.
- Gateway API: healthy with 38 registered router groups and 41 router files. Permission checks are now more centralized, but the large router surface still deserves a future middleware pass.
- LangGraph Runtime: healthy enough for release candidate. Stale run cleanup and short soak pass; final 8h/24h reports remain the long-running release gate.
- Models/Embedding: SentenceTransformerBackend remains active with 384 dimensions.
- Memory/Query: maintenance is available, and the generic agent now runs it silently. Continue tracking memory plateau under real long conversations.
- Distributed Execution: worker/lease/callback/replay remain in place; set `OCTO_EXECUTION_WORKER_TOKEN` in production.
- Multi Tenant: auth-bound tenant context works; set `OCTO_OPERATOR_TOKEN` in production.
- Operator Governance: audit redaction/signing is unified; set `OCTO_OPERATOR_AUDIT_SECRET` in production.
- Skills/Tools Hub: smoke remains good. Keep generated capability index files CI-owned.
- Docs/DevOps: module count is now 45; router count remains 38 registered groups and 41 router files.

## Deferred Integration Recommendations

| Item | Recommendation | Value | Decision |
| --- | --- | ---: | --- |
| Vue3 rewrite | Defer | 2/5 | Keep optimizing current Next.js. A rewrite is not worth launch risk. |
| Deep memory optimization | Continue | 5/5 | Add memory-budget CI gates and long-conversation regression profiles after final soak. |
| xray-core proxy | Defer | 2/5 | Only integrate if egress routing/proxy policy becomes product-critical. |
| Generic agent | Implemented as pilot | 4/5 | Low-privilege local maintenance agent is live; no external GitHub agent code pulled. |
| public-apis/browser wing/superpowers/agent ui/openrelay/agent browser | Selective later | 3/5 | Keep out of launch unless a specific workflow requires one. |
