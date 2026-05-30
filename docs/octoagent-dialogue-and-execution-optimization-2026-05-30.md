# OctoAgent Dialogue and Execution Optimization - 2026-05-30

## Scope

This update targets three stability-period problems reported from recent WebUI history:

- Assistant tone was too cold, mechanical, and report-like.
- The agent could restart or repeat already completed work after continuation/resume.
- Current-research tasks could drift into local repository inspection even when the instruction contract required web evidence from a named source.

## Reference Patterns

Prompt style was adjusted after reviewing public agent prompt patterns, especially:

- OpenAI Codex default prompt style: concise, direct, friendly, execution-oriented.
- Kiro-style IDE assistant prompts: human-sounding developer collaboration rather than generic chatbot prose.
- Community agent prompts that emphasize concise operational explanations grounded in actual system state.

The implementation does not copy those prompts. It adapts the principles into OctoAgent's own prompt and middleware layers.

## Implemented Changes

### Execution Mode Contract

`backend/src/agents/middlewares/execution_mode_middleware.py` adds a hidden per-turn contract that separates two behaviors:

- `assisted`: collaborative mode. The agent should keep the user in the loop, ask one crisp question when credentials, approval, business choice, or missing intent blocks correctness, and avoid silently grinding through repeated failures.
- `goal_autopilot`: automatic execution mode. The agent should frame the objective, inspect outcomes, form root-cause hypotheses, switch strategies after failure, and try at least two materially different strategies before confirming failure unless a hard external blocker is proven.

This keeps normal chat from behaving like an unattended robot, while giving goal-style runs a stronger deliberate execution loop.

### Human Collaboration Prompt

`backend/src/agents/lead_agent/prompt.py` now injects a dedicated `<human_collaboration_style>` section into the full lead-agent prompt.

Key rules:

- Respond like a capable teammate, not a form-filling assistant.
- Match the user's language and emotional temperature.
- Keep routine updates short and specific.
- For execution work: inspect, act, verify, then explain.
- After completing a task, stop executing and do not repeat completed work after restart, compaction, or continuation.

The compact dialogue prompt also gained fast dialogue rules for natural short answers and completed-task stop behavior.

### Reflection and Stall Behavior by Mode

`StepReflectionMiddleware` and `ProgressStallMiddleware` now read `runtime.execution_mode`:

- In `assisted` mode, repeated failures or uncertain branches should lead to a concise evidence summary and a single user question when user input is genuinely required.
- In `goal_autopilot` mode, failed or partial tool results require a root-cause hypothesis and a materially different next strategy instead of retrying the same tool/arguments.

This turns the existing reflection system into a mode-aware Execute -> Check -> Decide loop.

### Completed Continuation Stop Guard

`backend/src/agents/middlewares/continuation_middleware.py` now detects a resumed context where:

- `continue_trigger == "continue"`
- persistent task state is `completed`
- there are no pending task steps
- there are no pending or in-progress todos

In that case the middleware returns a concise completion summary instead of sending the model back into the execution loop. This prevents "continue" from re-running a finished task.

### Current Research Tool Repair

`backend/src/agents/middlewares/instruction_contract_middleware.py` now repairs invalid first model actions for current-research turns.

If the instruction contract requires web evidence and the model tries to call a local exploration tool such as `bash`, `read_file`, `grep`, or similar, the middleware replaces that action with a source-first web call:

- explicit URL in the user request -> `web_fetch`
- named domain in the instruction contract -> `web_search` with `site:domain`
- otherwise -> `web_search` using the user's current request text

This directly addresses the observed Bloomberg-history failure mode where the model recognized a current-research contract but started by inspecting local files.

## Verification

Backend regression run on the 2号机 environment:

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
.venv/bin/python -m pytest \
  tests/agents/test_instruction_contract_middleware.py \
  tests/agents/test_continuation_middleware.py \
  tests/agents/test_execution_mode_middleware.py \
  tests/agents/test_step_reflection_middleware.py \
  tests/agents/test_prompt_human_style.py \
  tests/agents/test_task_state_middleware.py \
  tests/agents/test_tool_recovery_middleware.py
```

Result:

- 58 passed

## Remaining Notes

- This is a stability-period optimization, not a large architecture rewrite.
- The tool repair guard intentionally handles only clear current-research misroutes. It does not override valid web/search/scrapling calls.
- The completed continuation answer is intentionally conservative: if any pending step or active todo exists, normal continuation behavior remains active.
- Execution mode detection is conservative: `plan_only`, direct answers, and control commands remain assisted even if a client accidentally sends a thinking flag.
