# Agent S System-Level Self Execution

## Short Answer

No. This repository does **not** currently implement Agent-S-style system-level self execution as a first-class runtime.

What exists today:

- sandbox command execution
- browser automation capability signaling
- thread-local file workspaces
- workflow contracts and runtime guardrails

What does **not** exist today:

- desktop/window introspection loop
- native GUI action planner
- cursor / keyboard / window-control runtime
- screenshot-grounded desktop control executor
- verified OS-level action policy layer

## Current Code Reality

### Present

- sandbox execution:
  `backend/src/sandbox/*`
- browser automation capability surface:
  `backend/src/config/integrations_config.py`
  `backend/src/gateway/routers/integrations.py`
- runtime guardrails:
  `backend/src/gateway/routers/runtime.py`
  `backend/src/system_guard/*`

### Missing

- desktop-control provider abstraction
- system-execution action schema
- perception loop for screen state
- explicit approval model for OS-level actions
- replay/audit log for desktop actions

## New Capability Signal

The integrations capability surface now exposes `system_execution`.

Current default state is effectively:

- `enabled = false`
- `engine = none`
- no desktop control
- no window introspection
- no file-open handoff runtime

This is deliberate. The code now says clearly that the feature is absent instead of leaving it ambiguous.

## How To Implement It Correctly

Do not bolt desktop control directly into the lead agent prompt.

Implement it as a dedicated runtime stack:

1. **System execution provider layer**
   Add `backend/src/system_execution/` with an abstract provider interface.
   Providers:
   - local desktop provider
   - remote desktop provider
   - hybrid browser+desktop provider

2. **Perception contract**
   Standardize:
   - screenshot capture
   - active window metadata
   - UI tree / OCR output
   - cursor position
   - focused application identity

3. **Action contract**
   Standardize actions such as:
   - click
   - type
   - hotkey
   - drag
   - scroll
   - launch app
   - focus window
   - open file
   - wait for selector / text / OCR match

4. **Guardrail layer**
   Every action path needs:
   - allowlist / denylist targets
   - destructive-action classification
   - explicit approval boundaries
   - replayable audit trail

5. **Planner/executor split**
   Brain Core or the lead agent should output a **system execution contract**.
   A dedicated executor should perform the action loop.
   Do not let the planner directly own mouse/keyboard side effects.

6. **Frontend/operator control**
   The workspace should show:
   - active desktop session
   - current screen snapshot
   - pending risky actions
   - pause / stop / approve controls
   - action history

## Recommended Repository Shape

Suggested additions:

- `backend/src/system_execution/contracts.py`
- `backend/src/system_execution/providers/base.py`
- `backend/src/system_execution/providers/local_desktop.py`
- `backend/src/system_execution/service.py`
- `backend/src/gateway/routers/system_execution.py`
- `frontend/src/core/system-execution/*`
- `frontend/src/components/workspace/system-execution/*`

## Integration With Brain Core

Brain Core should not become the desktop driver.

Brain Core should only produce:

- readiness
- risk classification
- required approvals
- suggested workflow/runtime mode
- execution contract for the system executor

The system executor should own the actual OS-level loop.
