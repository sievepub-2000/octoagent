# OctoAgent Stable Period Optimization Plan

Date: 2026-05-29
Status: Phase 1 approved for implementation

## Stable-period posture

OctoAgent should now optimize through small, reversible modules rather than broad architecture replacement. The existing lead agent, LangGraph runtime, WebUI, workflow tools, and subagent entry points remain the system core. The next improvements should add clearer control, routing, event, memory, and observability interfaces around that core.

## Current assessment

The highest-impact issue is not only model quality. User intent, UI control commands, planning-only requests, tool execution, workflow execution, and deep analysis are currently too easy to merge into the same broad execution path. This can cause the agent to run tools when the user asked for a plan, continue stale context when the newest turn should control the session, or route simple commands such as `/new` through ordinary model reasoning.

PilotDeck is useful as product reference, especially its WorkSpace, white-box memory, smart routing, multi-channel command pattern, and always-on work model. OctoAgent should borrow those product ideas selectively while keeping the current runtime stable.

## Phase 1: conversation intent and control

Priority: P0

Goal: make conversation control deterministic before normal agent execution.

Scope:

- Add explicit routing for control commands such as `/new`, `开启新对话`, `暂停`, `停止`, `继续`, `状态`, and `resume`.
- Add explicit routing for planning-only or confirmation-gated turns such as `先给方案`, `等我确认`, `不要执行`, `只评估`, and `先分析`.
- Keep the backend as the authoritative router. The frontend may provide a hint, but server classification decides the final route.
- Avoid hidden client contracts dominating the model prompt for plan-only or control turns.
- Add regression coverage for Chinese and mixed Chinese/English commands.

Expected behavior:

- `/new` and equivalent text are treated as control commands, not workspace actions.
- "先给方案，等我确认后再执行" is treated as plan-only, with no tool pre-plan and no tool attachment by default.
- Bare continuation commands are control commands first; actual resume/tool execution should happen only when runtime state explicitly requires it.
- Frontend and backend route labels stay aligned.

## Later phases

### Phase 2: run timeline and streaming

Persist normalized run events and expose a clearer timeline for queued, planning, tool call, tool result, answer delta, artifact, done, and error states.

### Phase 3: workflow and subagent hardening

Keep the existing workflow tools, then add WorkPlan snapshots, parent run identifiers, child result writeback, and resource-aware parallelism limits.

### Phase 4: WebUI resource trimming

Lazy-load workflow, agents, settings, Markdown, highlighter, charts, and heavy editor modules. Cache models, tools, and runtime capability payloads.

### Phase 5: white-box memory and workspace profiles

Make memory visible and editable. Store user preferences such as "stable-period changes should be small" and "provide a plan before executing" as explicit, inspectable memory. Add project workspace profiles for files, browser sessions, terminals, tokens, cleanup policy, and risk boundaries.

### Phase 6: multi-channel control consistency

Unify `/new`, `/stop`, `/status`, `/resume`, and related control commands across WebUI, QQ, Telegram, Discord, and any future channels.

## Guardrails

- Prefer additive modules and small adapter changes.
- Keep compatibility with existing LangGraph and WebUI APIs.
- Feature behavior should be covered by tests before service rollout.
- Do not change the main workspace entry until runtime state and conversation control are stable.
