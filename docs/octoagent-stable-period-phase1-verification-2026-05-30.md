# OctoAgent Stable Period Phase 1 Verification

Date: 2026-05-30
Status: implemented and verified

## Scope

This phase keeps the stable-period rule: no broad architecture replacement. The work focuses on conversation control, interruption recovery, right-panel timeline behavior, WebUI resource checks, and tool-loop quality gates.

## Completed changes

- Conversation control and planning-only routing are now handled before ordinary agent execution, including Chinese `/new`, stop, continue, status, and plan-first requests.
- Runtime run events and WorkPlan snapshots are persisted and shown in the right inspector instead of above the chat stream.
- The right inspector lazy-loads workflow, runtime, timeline, console, and artifact modules so opening a chat does not eagerly hydrate heavy panels.
- Markdown/message rendering now throttles live stream updates and limits loading state to the active assistant message.
- Interrupted or compacted runs preserve the latest real user goal instead of drifting back to stale historical tasks.
- Malformed orphan `<function=...>` tool calls are normalized into executable tool calls.
- Repeated web-research closure guards now activate final-answer mode. Once enough evidence is collected and further web calls are being skipped, the next model turn receives final-only guidance and web tools are withheld for that call.
- The new-chat welcome card is constrained to the same `max-w-5xl` width as the input box when the right sidebar is collapsed.
- Run timeline now has an explicit empty/loading state instead of disappearing when no events have been recorded yet.

## Verification commands

Backend regression checks:

```bash
cd backend
.venv/bin/python -m pytest tests/agents/test_tool_recovery_middleware.py tests/agents/test_progress_stall_middleware.py tests/agents/test_task_state_middleware.py
```

Frontend checks:

```bash
cd frontend
pnpm exec tsc --noEmit
pnpm exec next build
```

WebUI resource and layout smoke:

```bash
node scripts/webui_resource_smoke.cjs http://127.0.0.1:19800 /workspace/chats/new
node scripts/webui_resource_smoke.cjs http://127.0.0.1:19800 /workspace/chats/18e5bf3b-9729-4351-aa37-ab7af4081561
```

The smoke script records DOM size, navigation timing, optional JS heap, relevant process RSS lines, console/page/request errors, and the welcome-card versus input-box width assertion.

## Remaining stable-period backlog

- Continue reducing first-open inspector cost by moving rarely used settings and workflow editor details behind explicit user actions.
- Add a saved run-event replay view so a restarted service can replay the most recent timeline without depending on live SSE state.
- Extend the WebUI smoke script with a mobile viewport once the desktop path stays quiet for several releases.
- Add a small operator dashboard for browser/X11/tmp cleanup health so resource leaks are visible before they affect the agent.
