# OctoAgent 项目进度与计划

> Last updated: 2026-04-26

## 当前目标

在保持现有 WebUI 与现有 API 兼容形状的前提下，继续收口运行时真相、operator 产品面、HookCore / CapabilityCore 边界、doctor/API contract smoke，以及长时间任务的上下文、检查点和资源回收闭环。

## 当前已完成

- 运行时真相已经收敛为 Next.js WebUI -> FastAPI gateway -> LangGraph runtime。
- 默认 workflow 生命周期真相已经收敛为 `task_workspaces` 与 `workflow_core` 投影；`/api/studio/*` 不再是默认产品面。
- `distributed_execution`、`monitoring`、`reflection`、`self_evolution` 已在 system settings overview 中获得最小 operator 面板，并直接复用既有 API。
- opt-in live tests 已拆分为独立的 manual/nightly workflow，不再继续污染默认 CI lane。
- 本地端口/入口链已支持 `OCTO_PUBLIC_BASE_URL`，可将统一入口迁移到外部可访问端口，例如 `11980`。
- 活跃文档已经继续压缩，当前状态、下一步、operator 状态和 handoff 文档都已回到“当前真相优先”的写法。
- Frontend lint debt has been cleared, so `pnpm lint` is now a usable hard gate again.
- `/api/runtime/doctor` now validates capability registry, capability binding contract, channels, runtime provider contract, and host memory status.
- `backend/scripts/run_system_doctor.py` now provides a repeatable local doctor/API contract smoke.
- Capability binding contract now has an auditable operator policy layer with `inherit`, `allow`, `deny`, and `audit_only` decisions.
- The oversized task workspace unified card has been partially split into transcript, inspector primitive, and status helper modules.
- Sieve host mihomo has been switched to persistent TUN mode through systemd.
- LangGraph thread/run/checkpoint contract ledger has been added at the OctoAgent runtime boundary.
- Checkpoint prune/copy/delete semantics now exist through `/api/runtime/langgraph-contract/*`.
- QueryEngine now has session maintenance, active-turn compaction budgets, and stale-session recovery.
- Runtime doctor now reports disk, worker queue, LangGraph contract, and event-loop latency checks.
- Blocking model/browser/system/research paths now pass through worker isolation counters and concurrency limits.
- Capability operator policy has a WebUI governance panel with per-capability decisions and audit history.
- The backend environment stack is aligned on `langgraph-api==0.8.1`, `langgraph-runtime-inmem==0.28.0`, OpenTelemetry `1.41.1`, `protobuf==6.33.6`, and `pydantic==2.13.3`.
- Runtime maintenance now starts with the gateway lifespan and exposes status/manual-run APIs.
- Runtime Health now has a WebUI settings page with alerts, worker isolation, LangGraph contract, and maintenance controls.
- `uv.lock` is refreshed and lock verification is bounded with `timeout 600s uv lock --locked`.
- Workflow/LangGraph contract smoke now covers remote thread creation plus pause/resume/cancel/replay/terminate lifecycle audit.
- Long-running soak now records memory, disk, process count, event-loop latency, worker queue, checkpoints, active runs, and final stability.
- Runtime Health alerts now surface through the top status bar and browser notification hook.
- QueryEngine now exposes summary quality evaluation, stale session recovery, and replay context.
- Capability operator policy now has release precheck plus WebUI import/export.
- Multi-tenant now has an operator governance surface with tenant registration, policy application, limit probe, and audit events.
- Multi-tenant registry is now persisted, exported, and bound into workspace/query/capability policy metadata.
- Distributed execution now has real HTTP remote worker dispatch, dispatch history, and live gateway remote-dispatch smoke coverage.
- `make operator-release` is the fixed release command, and CI runs it through the `release-precheck` job.
- QueryEngine replay golden now validates tenant continuity, semantic compaction quality, stale recovery, and replay context.
- Real LangGraph remote lifecycle E2E now creates an actual remote thread/run id, validates remote cancel/replay/delete behavior, and records recoverable terminate errors after cancel.

## Current Verification

- Backend: `backend/.venv/bin/python -m compileall -q backend/src backend/scripts` passed.
- Backend: `cd backend && .venv/bin/python -m ruff check src scripts` passed.
- Backend: `backend/scripts/run_system_doctor.py --skip-git` passed.
- Backend: `backend/.venv/bin/python -m pip check` passed.
- Frontend: `pnpm lint` passed.
- Frontend: `pnpm typecheck` passed.
- Frontend: `pnpm build` passed.
- WebUI: `backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed.
- Long-running soak: `backend/scripts/run_long_running_soak.py --iterations 40 --json` passed.
- Workflow/LangGraph contract smoke: `backend/scripts/run_workflow_langgraph_contract_smoke.py --json` passed.
- Release precheck: `backend/scripts/run_release_precheck.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed.
- Operator release: `make operator-release` passed with 12/12 steps, including tenant persistence, distributed dispatch, QueryEngine replay golden, bounded soak, backend lint/compile, uv lock, frontend lint/build, and system doctor.
- Distributed remote dispatch: `backend/scripts/run_distributed_dispatch_smoke.py --gateway-url http://127.0.0.1:19880 --json` passed against the live gateway.
- LangGraph real remote lifecycle: `backend/scripts/run_langgraph_remote_lifecycle_e2e.py --base-url http://127.0.0.1:19884 --allow-cancel-recovery --json` passed with a real remote run id.

## 当前仍在收口的点

- HookCore 仍需继续从“已接线”推进到更明确的事件所有权边界。
- CapabilityCore 已完成 active caller 收敛，并已具备可审计 operator policy 基线；下一步是做 WebUI 策略治理面、导入导出和策略变更审计。
- `multi_tenant` 已具备持久 registry 与 tenant metadata binding；下一步是统一 auth binding、operator role、租户级数据/资源 enforcement 和审计导出签名。
- `distributed_execution` 已具备 gateway/worker HTTP dispatch；下一步是独立 worker daemon、节点 token、容量租约、故障转移 replay 和治理 UI。
- `monitoring`、`reflection`、`self_evolution` 虽已有最小 WebUI 面，但仍缺导出、审计或更深治理能力。

## 下一步计划

1. 继续保持 task-workspace lifecycle 和 public runtime projection 作为唯一默认 workflow 真相。
2. 运行真实 2h、8h、24h soak，并将报告保存到 `workspace/runtime/soak_reports/`。
3. 将 remote worker 从 gateway self-dispatch 推进到独立 daemon，补节点权限、容量治理和结果回传重试。
4. 接入 operator role、危险操作二次确认、secret redaction 和不可抵赖审计。
5. 继续精修 Runtime Health、tenant、distributed、policy 前端治理面，减少重复状态展示。
6. 建立生产部署、backup/restore、migration、observability dashboard 和回归矩阵。
7. 继续维持每个代码切片后的 lint + typecheck + build + doctor smoke + operator release 验证闭环。

## P0 Closure - 2026-04-25

P0 is closed for the current main branch. The stale LangGraph thread submit failure is handled as a recoverable missing-thread condition, tracked tests and duplicate historical documents were removed, and repository validation now relies on compile/typecheck/build/smoke checks. See `P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md` for the full closure record.

## P1-P5 Closure - 2026-04-25

P1-P5 is closed for the current delivery pass. The repository roadmap formally defines P1-P3 and does not define named P4/P5 phases, so P4 is treated as release governance and repository sync, while P5 is treated as full code assessment and next-plan closure.

Implemented closure items:

- CapabilityCore now includes channel capabilities in the unified registry.
- `/api/capabilities/binding-contract` now exposes normalized bindable targets, dispatch contracts, blockers, and audit metadata.
- Task-workspace frontend query keys are centralized in `frontend/src/core/task-workspaces/query-keys.ts`.
- Backend compile, capability contract construction, frontend typecheck, and frontend production build passed.

Known carryover:

- `pnpm lint` still fails on pre-existing frontend lint debt outside the files changed in this pass.
- Distributed execution, multi-tenant, reflection, monitoring, and self-evolution remain real but not fully product-complete; they need proof, audit, and UI hardening before promotion.

See `P1_P5_COMPLETION_AND_FULL_CODE_ASSESSMENT_REPORT.md` for the full assessment and next plan.

## P6 Operational Hardening - 2026-04-25

P6 is closed for the current delivery pass. It clears frontend lint debt, adds doctor/API contract smoke, partially splits the task workspace frontend surface, promotes capability binding into an auditable operator policy layer, validates the local stack, and switches sieve host mihomo to persistent TUN mode.

Known carryover:

- LangGraph runtime dependency should be upgraded after compatibility testing.
- The checkpointer must support prune/copy/delete semantics to keep long-running conversations sustainable.
- Blocking runtime work should be isolated away from the shared event loop.
- Provider-node health for mihomo should be monitored separately from local TUN service health.

See `P6_OPERATIONAL_HARDENING_AND_LONG_RUNNING_ASSESSMENT_2026-04-25.md` for the full validation record, assessment, and next work plan.

## P7 Long-Running Runtime Closure - 2026-04-25

P7 is closed for the current delivery pass. It adds the OctoAgent-side LangGraph workflow contract ledger, checkpoint prune/copy/delete APIs, query session maintenance and stale-session recovery, long-running doctor metrics, worker isolation counters/limits, capability policy WebUI governance, and a bounded soak test.

Known carryover:

- The new contract ledger is the OctoAgent operator control plane; the underlying LangGraph remote checkpointer still needs native prune/copy/delete support through upgrade or replacement.
- Soak validation currently proves the contract/maintenance layer with bounded simulation. A real multi-hour workflow soak is still required before production promotion.
- Runtime health metrics are available through API/doctor; a dedicated WebUI health panel and alert thresholds should come next.

See `P7_LONG_RUNNING_RUNTIME_CLOSURE_2026-04-25.md` for the full closure record.

## P8 Environment Stack and Runtime Health Closure - 2026-04-25

P8 is closed for the current delivery pass. It aligns the backend environment stack on LangGraph API 0.8.1, LangGraph in-memory runtime 0.28.0, OpenTelemetry 1.41.1, protobuf 6.33.6, and pydantic 2.13.3; starts runtime maintenance from gateway lifespan; adds maintenance APIs; exposes Runtime Health in WebUI settings; extends doctor/API smoke; and validates the stack with backend, frontend, doctor, and soak gates.

Known carryover:

- `uv.lock` still needs a dedicated refresh because the resolver hung during the LangGraph upgrade attempt.
- Real multi-hour workflow soak is still required before production promotion.
- LangGraph pause/resume/cancel/replay/terminate contract smoke should be added against remote threads/runs/checkpoints.

See `P8_ENVIRONMENT_STACK_AND_RUNTIME_HEALTH_CLOSURE_2026-04-25.md` for the full closure record.

## P9 Finalization Roadmap and Governance Closure - 2026-04-26

P9 is closed for the current delivery pass. It refreshes `uv.lock`, adds bounded lock verification, extends workflow/LangGraph lifecycle contract smoke, upgrades long-running soak sampling, connects Runtime Health alerts to the status bar and notification hook, improves QueryEngine recovery/replay/summary quality, adds capability policy release precheck and WebUI import/export, and promotes multi-tenant to an operator governance surface.

Known carryover:

- Real 2h/8h/24h soak reports should be run before production promotion.
- LangGraph remote lifecycle smoke should move from contract-level proof to real run-id cancellation/replay proof.
- Multi-tenant and distributed execution still need persistence, auth, and real enforcement/dispatch.

See `P9_FINALIZATION_ROADMAP_AND_GOVERNANCE_CLOSURE_2026-04-26.md` for the full closure record and final remaining workload estimate.
