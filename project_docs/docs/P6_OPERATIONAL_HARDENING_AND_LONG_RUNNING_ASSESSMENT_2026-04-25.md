# P6 Operational Hardening And Long-Running Assessment

> Date: 2026-04-25
> Canonical project root: `/home/sieve-pub/public-workspace/octoagent`
> Branch policy: `main` only

## Executive Summary

This pass closes the next hardening slice after P1-P5. The project now has a clean frontend lint gate, a backend doctor/API contract smoke gate, a first auditable operator policy layer above the capability binding contract, and a smaller task workspace frontend component boundary. The local OctoAgent stack was validated through backend compile, backend lint, doctor/API smoke, frontend lint/typecheck/build, and WebUI smoke.

Sieve host mihomo was also switched to TUN virtual interface mode and enabled as a persistent systemd service. The service is active and exposes the expected TUN interface, but one upstream proxy connectivity check returned a provider timeout, so proxy-provider health should still be monitored separately from local TUN health.

## Completed Engineering Work

### Frontend lint closure

- Cleared the existing frontend lint debt that previously blocked `pnpm lint`.
- Normalized import order, optional chaining, escaped text, React hook dependencies, and unstable function references across workspace pages and task workspace components.
- Current frontend verification:
  - `pnpm lint` passed.
  - `pnpm typecheck` passed.
  - `pnpm build` passed.

### Doctor and API contract smoke

- Expanded `/api/runtime/doctor` so it checks:
  - Capability registry construction.
  - Capability binding contract construction.
  - Channel registry availability.
  - Runtime provider contract availability.
  - Host memory availability.
- Added `backend/scripts/run_system_doctor.py` as the local operator smoke entrypoint.
- Added release precheck coverage for the doctor smoke path.
- Current smoke covers:
  - `/health`
  - `/api/runtime/doctor`
  - `/api/capabilities/registry`
  - `/api/capabilities/binding-contract`
  - `/api/channels/`
  - `/api/models`
  - `/api/task-workspaces`
  - `/api/memory/status`
  - `/api/capabilities/policies`
  - `/api/runtime/provider-contracts`

### Frontend component split

- Extracted task workspace transcript rendering into `task-workspace-agent-transcript.tsx`.
- Extracted inspector primitives into `task-workspace-inspector-primitives.tsx`.
- Extracted shared status tone mapping into `task-workspace-status.ts`.
- Reduced the main task workspace unified card surface while keeping the product behavior unchanged.

### Auditable capability operator policy

- Added `CapabilityPolicyService` under `backend/src/capability_core/policy.py`.
- Added operator policy decisions:
  - `inherit`
  - `allow`
  - `deny`
  - `audit_only`
- Added policy audit records with actor, reason, timestamp, and previous/new decision.
- Extended binding contract items with `operator_policy`.
- Added `operator_policy_denied` blockers when a capability is denied.
- Added API endpoints:
  - `GET /api/capabilities/policies`
  - `PUT /api/capabilities/policies/{capability_id:path}`
- Policy state is local runtime state and is intentionally not tracked in Git:
  - `workspace/runtime/capability_operator_policies.json`

## Validation Matrix

| Area | Command or check | Result |
| --- | --- | --- |
| Backend syntax | `backend/.venv/bin/python -m compileall -q backend/src backend/scripts` | Passed |
| Backend lint | `cd backend && .venv/bin/python -m ruff check src scripts` | Passed |
| Doctor/API contract smoke | `backend/scripts/run_system_doctor.py --skip-git` | Passed |
| Frontend lint | `cd frontend && pnpm lint` | Passed |
| Frontend types | `cd frontend && pnpm typecheck` | Passed |
| Frontend build | `cd frontend && pnpm build` | Passed |
| WebUI smoke | `backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` | Passed |
| Sieve mihomo config | `mihomo -t -d /etc/mihomo -f /etc/mihomo/config.yaml` | Passed |
| Sieve mihomo service | `systemctl is-active mihomo`, `systemctl is-enabled mihomo` | Active, enabled |
| Sieve TUN interface | `ip -brief addr show mihomo` | Present, `198.18.0.1/30` |

## Current Runtime State

The host2 development stack is running behind the local nginx entrypoint:

- nginx public entry: `http://127.0.0.1:19880`
- frontend dev process: `127.0.0.1:19886`
- FastAPI gateway: `127.0.0.1:19882`
- LangGraph runtime: `127.0.0.1:19884`

The WebUI smoke confirmed the primary local user flows:

- Backend health available.
- Frontend route available.
- Model list available.
- Embedded bootstrap model visible.
- Chat input usable in mock mode.
- Continuation route opens.
- Workflow task creation path works.
- Settings and bootstrap sections open.
- Guide generation smoke path works.

## Important Findings

### LangGraph runtime compatibility

The runtime log reports that the installed `langgraph-api` version is behind the currently available line and is already in a critical support window. This is not an immediate local boot failure, but it should be treated as a near-term maintenance item because runtime behavior, checkpoint contracts, and server expectations can drift quickly.

### Checkpointer retention risk

The LangGraph runtime reports missing optional checkpointer methods, including checkpoint pruning. For OctoAgent's long-running conversation and task model, this is the highest-priority sustainability issue: without a reliable prune/copy/delete lifecycle, checkpoint storage can grow without a stable ceiling during long conversations or repeated agent runs.

Required follow-up:

- Implement or adopt a checkpointer that supports thread/run pruning.
- Define per-thread retention policy.
- Add operator-visible checkpoint metrics.
- Add soak tests that verify checkpoint count and storage size stabilize after pruning.

### Blocking runtime work risk

The LangGraph runtime warns that blocking code is allowed on the shared loop. Long-running browser, tool, workflow, or model calls should not monopolize the shared event loop.

Required follow-up:

- Move blocking tool calls into isolated worker pools or background jobs.
- Enable isolated background job loops for production-style runtime.
- Add latency and queue-depth alarms to the doctor output.

### Frontend continuation route edge

During live WebUI smoke, the route was usable, but the frontend log emitted a TanStack Query warning for a thread-state query returning `undefined`. This should be converted to a stable `null` or typed empty state so long-running continuation flows do not accumulate noisy client-side errors.

### Sieve mihomo TUN mode

Local mihomo TUN mode is configured and active:

- Config backup: `/etc/mihomo/config.yaml.bak-20260425183759`
- Service: active and enabled.
- TUN device: `mihomo`
- TUN address: `198.18.0.1/30`

One external proxy test through the local mixed proxy returned an upstream timeout from the selected provider. That result does not invalidate the local TUN setup, but it means provider node health still needs separate monitoring and failover validation.

## Full Project Assessment

OctoAgent has moved from prototype-shaped integration toward a credible operator system. The strongest parts are now the unified runtime shape, the task workspace projection, capability registry/binding contract visibility, and a repeatable local validation lane. The repository is much healthier than before P0-P5 because the canonical path, branch policy, frontend build, and backend smoke checks are now explicit and repeatable.

The main risk is no longer simple bootability. The main risk is long-duration correctness: workflow state retention, memory growth, context continuation, provider retries, checkpoint lifecycle, and resource isolation. These are the areas that decide whether OctoAgent can run multi-hour or multi-day work without gradually consuming disk, RAM, event-loop capacity, or operator attention.

Module status:

- WebUI: usable and passing lint/type/build. The task workspace UI still has large surfaces, but the split started in this pass gives a safer path for deeper decomposition.
- Gateway API: stable enough for local smoke and operator-facing contract checks. More contract tests are needed for error envelopes and long-running workflow transitions.
- CapabilityCore: substantially improved. Binding is now inspectable and can be overridden by operator policy.
- WorkflowCore/task workspaces: functional, but should become the single audited projection of LangGraph run state.
- LangGraph provider: usable but needs version upgrade, checkpointer contract completion, and retention governance.
- Memory layer: cleanup exists, but needs measurable budgets, pressure feedback, and context compaction policy tied to conversation continuation.
- Monitoring/doctor: now useful as a local operator tool, but should evolve into a continuous health surface with thresholds, historical samples, and remediation hints.
- Deployment/runtime: service ownership and local stack start are workable; runtime directories must stay owned by `sieve-pub` to avoid dev-server permission failures.

## Next Work Plan

### P7: LangGraph workflow contract closure

1. Define one canonical mapping between OctoAgent task workspace IDs, LangGraph thread IDs, run IDs, and checkpoint namespaces.
2. Add contract tests for create, run, pause, resume, cancel, retry, terminate, and replay.
3. Implement checkpoint prune/copy/delete support or switch to a checkpointer implementation that supports it.
4. Add task-workspace projection tests that assert the frontend sees stable status, events, artifacts, and errors.
5. Upgrade `langgraph-api` after compatibility verification.

### P8: Conversation cache and context continuation

1. Define a per-thread context budget with hard and soft token/memory limits.
2. Add summarization/compaction checkpoints at controlled intervals.
3. Store continuation metadata separately from transient chat render state.
4. Ensure frontend queries return typed empty states instead of `undefined`.
5. Add recovery tests for stale thread, missing checkpoint, partial artifact, and restarted runtime cases.

### P9: Resource stabilization for long-running work

1. Add runtime memory, checkpoint count, queue depth, and event-loop latency to doctor output.
2. Add periodic cleanup for stale artifacts, stale checkpoints, temporary uploads, and orphaned task workspaces.
3. Add worker isolation for blocking browser/tool/model calls.
4. Add concurrency limits per provider, per workflow, and per operator.
5. Run soak tests that verify memory, disk, and process counts return to a stable band after repeated long tasks.

### P10: Operator governance and policy UI

1. Expose capability operator policies in WebUI.
2. Add policy export/import and signed audit history.
3. Add policy diff review before applying high-impact deny/allow changes.
4. Tie policy decisions to workflow execution logs so blocked capability use is auditable.
5. Add release precheck gates for dangerous policy regressions.

### P11: Production readiness

1. Replace development Next.js serving with a production build in the service path.
2. Move secrets and host-specific runtime state out of operator-visible Git surfaces.
3. Add backup/restore procedures for workflow state, memory state, and policy state.
4. Add service-level monitors for nginx, gateway, frontend, LangGraph, and mihomo provider health.
5. Document rollback paths for LangGraph runtime upgrades and mihomo config changes.
