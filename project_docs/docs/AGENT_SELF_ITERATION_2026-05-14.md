# Agent Self-Iteration Workflow (2026-05-14)

## Background

Thread `8f85b6de-3bec-4b6d-906d-798498367d76` ran 1,357 tool calls on what was
nominally a simple cleanup-report task. Forensics on the PostgresSaver state
showed three compounding failures:

1. `local_sandbox.execute_command()` returned the ambiguous string
   `"(no output)"` for both "command succeeded, stdout empty" and "command
   failed silently". The LLM had no signal to switch strategy.
2. There was no stall detector. `ToolBudgetMiddleware` only reacted to
   *errors*, so an `exit=0 + empty stdout` loop ran indefinitely.
3. Compaction had to chew through ~1,398 nearly-identical tool messages with
   no de-noising pass first, blowing both tokens and summariser attention.

## The three-layer cadence taxonomy

To make the agent's daily workflow a coherent **Execute → Check →
Continue-or-Correct** loop, three complementary middlewares now run in fixed
order in `backend/src/agents/lead_agent/agent.py`:

| Layer | Middleware | Trigger | Output marker | File |
|---|---|---|---|---|
| Contract | `CriticMiddleware` | `<goal_contract>` violation (every 3 turns) | `<critic_feedback>` | `backend/src/agents/middlewares/critic_middleware.py` |
| **Cadence** | **`StepReflectionMiddleware`** | every 3 completed tool batches per human turn | `<step_review>` | `backend/src/agents/middlewares/step_reflection_middleware.py` |
| Stall | `ProgressStallMiddleware` | duplicate tool calls / redundant outputs | `<self_reflection>` | `backend/src/agents/middlewares/progress_stall_middleware.py` |

The middlewares are stacked after `RuntimeStateMiddleware`/`TaskStateMiddleware`
and **before** `ToolBudgetMiddleware`, so reflection happens before any
budgeted dispatch decision.

## StepReflectionMiddleware

Cadence-based steady-state checkpoint. Fires only when:

- the latest message is a `ToolMessage`,
- the current AI batch is fully resolved (all `tool_call_id`s have matching
  results),
- the number of completed batches since the latest human turn is a multiple
  of `OCTO_STEP_REVIEW_EVERY_N` (default **3**).

Injects a hidden `<step_review>` SystemMessage that forces the **model's next
turn** to begin with a 5-part block:

1. 我刚做了什么 (one line)
2. 观察到的关键事实 (≤ 3 factual bullets, from real tool output)
3. 结果分类：`SUCCESS` / `PARTIAL` / `FAILED`
4. Branch:
   - `SUCCESS` → next concrete step, or finalise if task is already done
   - `PARTIAL` → known vs missing, then the gap-closing step
   - `FAILED` → specific failure mode + 1-line root-cause hypothesis +
     **different** correction (must change params or tool — no same-arg retry)
5. No-retry-without-difference rule

Throttle:
- Window fingerprint = sha1 of last ≤12 tool signatures + outputs. Identical
  window → no re-inject.
- Hard cap `OCTO_STEP_REVIEW_MAX_PER_TURN` (default 8) reviews per human turn.

Tests: `backend/tests/unit/agents/test_step_reflection_middleware.py` — 8/8.

## ProgressStallMiddleware

Reflexion-style stall escape. Triggers when:
- a `(tool_name + args)` signature repeats ≥ `OCTO_PROGRESS_STALL_DUP` (3)
  times in the current human turn, OR
- the last `OCTO_PROGRESS_STALL_WINDOW` (5) tool outputs collapse to ≤k
  variants with the dominant variant occurring ≥
  `OCTO_PROGRESS_STALL_REDUNDANT` (4) times.

Injects `<self_reflection>` forcing (a) evidence summary, (b) unknown list,
(c) explicit finalise-or-switch decision, (d) repeat-ban. Throttled by stable
`kind:hash` prefix; max `OCTO_PROGRESS_STALL_MAX_REFLECTIONS` (3) per turn.

Tests: `backend/tests/unit/agents/test_progress_stall_middleware.py` — 6/6.

## Supporting fixes shipped together

- `backend/src/sandbox/local/local_sandbox.py`: empty-output disambiguation
  — succeeded vs failed-silent are now distinguishable, with an explicit
  "do NOT retry with the same arguments" hint when `exit=0`.
- `backend/src/agents/middlewares/tool_budget_middleware.py`: stable
  duplicate-tool-call dispatch guard via
  `_consecutive_recent_tool_signatures` / `_duplicate_signature_recent_count`,
  gated by `OCTO_TOOL_DUPLICATE_LIMIT` (default 4). The guard runs only when
  no prior error-recovery branch matched, so specific error guidance still
  wins.
- `backend/src/agents/middlewares/session_compaction_middleware.py`:
  Claude-Code / Cursor style `_coalesce_identical_tool_messages` pass before
  `_truncate_oversized_messages`, so the summariser never sees runs of
  duplicate tool output.
- `frontend/src/components/workspace/messages/message-list.tsx`: scroll-up
  auto-expand of the history window (`HISTORY_GROUP_WINDOW=90`) with anchor
  preservation (`scrollTop = beforeTop + (afterHeight - beforeHeight)`).

## Environment knobs

```
OCTO_STEP_REVIEW_EVERY_N=3
OCTO_STEP_REVIEW_MAX_PER_TURN=8
OCTO_PROGRESS_STALL_DUP=3
OCTO_PROGRESS_STALL_WINDOW=5
OCTO_PROGRESS_STALL_REDUNDANT=4
OCTO_PROGRESS_STALL_MAX_REFLECTIONS=3
OCTO_TOOL_DUPLICATE_LIMIT=4
```

## Verification on host 192.168.110.2

- `systemctl is-active octoagent-local.service` → `active`
- `curl /api/langgraph/ok` → `200`
- `curl /` → `307`
- `StepReflectionMiddleware ok every_n=3`; `wired: True`
- Targeted unit tests pass: 8/8 (step_reflection) + 6/6 (progress_stall) +
  19/19 (tool_recovery).

## Mature patterns referenced

- **Reflexion** (Shinn et al. 2023): heuristic stall detector + LLM-time
  self-critique prompt rather than hard abort.
- **Self-Refine**: emit an explicit "decide A (finalise) or B (different
  strategy)" choice, not a vague critique.
- **Claude-Code / Cursor**: collapse identical tool outputs **before** the
  compaction summariser ever sees them; saves both tokens and the
  summariser's attention budget.
- **Slack / VS Code chat**: chunked history virtualisation with
  anchor-preserving scroll.
- **Plan-Reflect-Act** cadence: periodic checkpoint between batches so the
  agent's reasoning is visibly broken into verifiable Execute → Check →
  Continue/Correct cycles.
