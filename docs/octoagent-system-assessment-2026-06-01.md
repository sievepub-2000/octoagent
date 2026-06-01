# OctoAgent System Assessment - 2026-06-01

## Verification Snapshot

Environment checked on 2号机 `192.168.110.2`.

- Branch: `main`
- WebUI entry: `http://127.0.0.1:19800/` returns HTTP 307 into `/workspace/chats/...`
- Agent backend: `langgraph_cli dev` on `127.0.0.1:19804`
- Gateway: `uvicorn src.gateway.app:app` on `127.0.0.1:19802`
- Disk: root filesystem 1.9T total, 168G used, 1.6T available
- Memory: 121Gi total, 89Gi used, 32Gi available, swap essentially unused

Validation commands:

```bash
cd /home/sieve-pub/public-workspace/octoagent/backend
.venv/bin/python -m pytest tests/agents/test_skill_evolution_trace.py -W error::DeprecationWarning
.venv/bin/python -m pytest tests/agents -W error::DeprecationWarning
```

Results:

- `tests/agents/test_skill_evolution_trace.py`: 11 passed, no warning
- `tests/agents`: 168 passed, no warning

## Warning Fix

The previous 3 warning lines came from one deprecated timestamp path being triggered several times during `test_skill_evolution_trace.py`:

- `datetime.datetime.utcnow()` inside Pydantic model defaults
- non-timezone-aware `last_used` updates in the skill evolution registry

Fixed files:

- `backend/src/storage/skill_evolution/types.py`
- `backend/src/storage/skill_evolution/registry.py`

The fix uses timezone-aware UTC timestamps via `datetime.now(UTC)`.

## Current Architecture Assessment

### Agent Runtime

The agent runtime is now much stronger than the earlier state:

- Dialogue routing separates fast answers, control commands, plan-only requests, current research, tool action, and deep agent tasks.
- `ExecutionModeMiddleware` separates assisted collaboration from goal/autopilot execution.
- `InstructionContractMiddleware` enforces source-first research routing when the task requires web evidence.
- `ContinuationMiddleware` prevents completed tasks from being restarted.
- `TaskStateMiddleware`, `StepReflectionMiddleware`, and `ProgressStallMiddleware` now provide a clearer Execute -> Check -> Decide loop.

Assessment: the core agent loop is entering a stable, testable phase. The biggest remaining risk is not missing middleware, but interaction quality across real multi-turn production traces.

### WebUI

Observed WebUI process memory is modest:

- `next-server`: about 106 MB RSS during this sampling

Recent layout/card fixes have reduced visible regressions. The WebUI is not the main resource bottleneck.

Recommended next WebUI work:

- Keep optimizing only hot routes/components, not broad redesign.
- Add a small Playwright smoke suite for chat layout, right info panel, management cards, and run timeline rendering.
- Track message duplication and continuation UX with deterministic UI tests.

### Resource Profile

Current sampled resource hotspots:

- `langgraph_cli dev`: about 4.2 GB RSS, around 4% CPU at sampling
- `uvicorn` gateway: about 551 MB RSS
- PostgreSQL has one larger checkpointer process and several idle octoagent sessions
- `next-server`: about 106 MB RSS

Assessment: backend runtime, especially LangGraph dev mode, remains the main memory target. WebUI should not be treated as the primary performance problem.

Recommended resource work:

- Investigate replacing or wrapping `langgraph_cli dev --no-reload` with a lighter production runner when available.
- Profile memory growth across long conversations and tool-heavy runs.
- Add process RSS sampling to startup health logs so regressions are visible.

### Tooling and Research

Current strengths:

- Source-first web routing is now enforced for current research.
- Anti-bot fallback through scrapling exists from prior work.
- Tool recovery and progress-stall tests are in place.

Remaining risks:

- Tool-call quality still depends on model compliance after the first repaired call.
- Research closure needs more real-world fixtures, especially paywalled, blocked, multilingual, and partial-source cases.
- Scrapling should be tested in a nightly or operator-triggered integration suite because it depends on external sites.

### Continuation and Goal Execution

Recent fixes improved:

- Completed task stop behavior
- Mode-aware assisted vs autopilot operation
- Reflection after tool batches
- Stall recovery after repeated tools

Remaining risks:

- The system still needs more replay tests from actual problematic conversations.
- The goal/autopilot mode should expose a compact, user-visible status timeline without leaking hidden reasoning.
- Long-running autonomous runs need explicit max strategy attempts, failure taxonomy, and recovery summaries stored in run records.

## Priority Recommendations

### P0 - Stabilize Real Conversation Replays

Build a replay harness for historical chat IDs that already exposed failures:

- repeated execution after completion
- wrong first tool in current research
- missing continuation content after restart
- duplicated user message after workflow interruption

Success condition: each historical failure has a replay test or reduced fixture.

### P1 - Production Runner and Memory Baseline

The largest observed resource consumer is still `langgraph_cli dev`. Create a measured baseline:

- cold start RSS
- idle RSS after 10 minutes
- RSS after one long research run
- RSS after one file-editing run
- RSS after 5 continuation resumes

Then decide whether to tune LangGraph workers, replace dev mode, or isolate heavy run state.

### P1 - UI Smoke Tests

Add browser tests for:

- chat input does not duplicate user messages
- right info panel renders workflow name and run timeline
- collapsed right panel keeps new-chat prompt width aligned with input width
- management cards do not overflow

### P2 - Research Fallback Integration Tests

Add operator-triggered tests for:

- web_fetch success path
- web_fetch anti-bot/blocked path -> scrapling fallback
- source-first search with named domains
- partial evidence final answer with explicit uncertainty

### P2 - Run Record Observability

Persist compact run summaries with:

- execution mode
- goal contract
- tool strategy attempts
- recovered failures
- final status and evidence links

This would make future debugging faster and reduce dependence on manual chat inspection.

## Overall Status

OctoAgent is no longer in a broad architecture-rebuild phase. The recent work has moved the project toward a stable runtime with targeted guards and regression tests. The next phase should be conservative: replay real failures, measure backend resource behavior, and add narrow UI smoke tests. Avoid large rewrites unless a replay or measurement proves a specific boundary is still wrong.
