# OctoAgent Runtime/UI/Workflow Optimization Report

Date: 2026-05-29

## Completed Scope

### WebUI resource usage

- Kept the chat-first route light by leaving the workflow/runtime inspector closed by default.
- Deferred inspector loading until the panel is opened and the browser is idle.
- Deferred `/api/runtime/capabilities` polling until the inspector is actually visible.
- Preserved auto-open behavior when a thread already has artifacts or workflow state.

Expected effect: the default chat surface avoids loading workflow inspector code, runtime capability data, and inspector-side memoized state unless the user needs that surface.

### Streaming output

- Added a unified frontend run-event contract:
  - `queued`
  - `planning`
  - `tool_call`
  - `tool_result`
  - `workflow`
  - `subagent`
  - `answer_delta`
  - `artifact`
  - `done`
  - `error`
- Added a run-event normalizer for backend custom events.
- Updated the streaming indicator to show the current run phase instead of only bouncing dots.
- Converted LangChain tool start/end events and existing subagent events into the same run-event timeline.
- Kept existing 33ms message throttling and windowed message rendering intact.

Expected effect: the WebUI can now show a stable execution phase before the first assistant token and during long tool/subagent work.

### Workflow and subagent integration

- Added default lead-agent workflow runtime tools:
  - `workflow_start`
  - `workflow_status`
  - `spawn_subagent`
  - `checkpoint`
- `workflow_start` creates a first-class WorkPlan envelope for complex tasks.
- `spawn_subagent` attaches a subagent dispatch to a WorkPlan and returns a payload ready for the existing `task` execution adapter.
- `checkpoint` emits workflow timeline updates.
- `workflow_status` projects current thread workflow/subagent state.
- Existing `task` subagent execution now emits unified `run_event` updates in addition to the legacy task events.

Expected effect: workflows and subagents are no longer only a WebUI/studio side surface. The lead agent now has default callable runtime verbs for creating, tracking, delegating, and checkpointing WorkPlans while still reusing the proven subagent runtime.

## Validation

- `backend/.venv/bin/python -m py_compile ...`
- `frontend: pnpm exec tsc --noEmit`
- `frontend: pnpm exec next build`
- Tool catalog smoke: confirmed `workflow_start`, `workflow_status`, `spawn_subagent`, `checkpoint`, and `task` are present in the default tool set.
- Restarted `octoagent-local.service`.
- WebUI entrypoint: `http://127.0.0.1:19800/workspace` returns OK.
- `backend/scripts/run_webui_smoke.py --mock` passed.
- `backend/scripts/run_system_doctor.py --json --skip-git` passed.

## Current Runtime Observations

- WebUI process memory remains relatively small compared with backend runtime processes.
- `next-server` is no longer forced to load the workflow inspector for a plain chat unless panel state requires it.
- `langgraph_cli dev` remains the largest OctoAgent-owned CPU/RSS hotspot; model/task latency tuning remains intentionally out of scope for this pass.
- The new workflow runtime tools are a first-stage runtime seam, not a full replacement for the existing studio workflow engine.

## Residual Risks

- The WorkPlan envelope is currently tool/event driven. It does not yet persist as a dedicated backend `RunGraph` table.
- `spawn_subagent` prepares the dispatch and relies on the lead agent to call `task` next. This is deliberate for auditability, but a later runtime adapter can make this automatic.
- The WebUI timeline currently shows the latest run phase in the streaming indicator. A richer collapsible run timeline should reuse the same `RunEvent` contract.
- The workflow/studio task workspace state and LangGraph thread state are still separate persistence surfaces. They are now bridged by default tools and events, but not fully merged.

## Recommended Next Steps

1. Persist `RunEvent` and WorkPlan state into thread runtime state or a dedicated `RunGraph` store.
2. Add a compact run timeline panel that groups tool calls, subagents, artifacts, and checkpoints.
3. Add a deterministic backend workflow adapter that can execute `spawn_subagent -> task` without relying on the model to chain the calls.
4. Promote `/workspace` to a project/workflow cockpit only after WorkPlan persistence and replay are stable.
5. Resume model/task latency work separately with TTFT, tokens/sec, prompt token, graph-step, and tool-latency instrumentation.
