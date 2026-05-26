# Hermes/Warp Agent Hardening Notes

## Reference Systems

- Hermes Agent: centralized `AIAgent` loop, explicit tool dispatch, iteration budgets, provider fallback, context compression, session persistence, and memory flush before compression.
- Warp: agent-mode workflows with specs, reusable skills, permission profiles, plan-oriented task execution, and repository-checked guidance.
- OpenAI Agents SDK: agent loop, handoffs, sessions, guardrails, and tracing as first-class primitives.
- LangGraph: durable execution, checkpoints, interrupts, and resumable state graphs.

## Production Patterns Adopted

### 1. Instruction Contract Before Action

OctoAgent now classifies the latest instruction into a stable execution contract before model execution. The contract records:

- intent: identity, current research, code task, system operation, or general
- evidence requirements: tool-backed research, required domains, minimum source URL count
- risk requirements: confirmation and guardrail labels for destructive, privileged, or remote-publish actions
- runtime identity requirements for "what model are you" style prompts

This mirrors Hermes' centralized loop responsibilities and Warp's spec-first/permission-first approach, but keeps the implementation local and lightweight.

### 2. Tool-Backed Research Gate

Current or time-sensitive research prompts now require source evidence. Requests such as "x.com 前十大新闻" must produce enough concrete content-page URLs instead of passing with one generic fallback result.

### 3. Runtime Identity Discipline

Identity prompts are separated from general chat and research. The hidden contract tells the model to distinguish OctoAgent as the platform from the active runtime model, and to use runtime telemetry when available.

### 4. Long Task Stability

Existing OctoAgent mechanisms already match the core Hermes/Warp patterns:

- `TodoMiddleware`: active task list survives context loss through reminder injection.
- `SessionCompactionMiddleware`: oversized tool results are truncated before model calls.
- `MemoryMiddleware`: final user/assistant exchanges are stored through the memory queue and SimpleMem bridge.
- `RuntimeStateMiddleware`: primary model, active model, fallback chain, memory guard, continuation, and fallback events are persisted into thread runtime state.
- `SkillEvolutionMiddleware`: execution traces can feed task learning and skill evolution.

The new instruction contract layer gives these systems a clearer trigger surface.

## Remaining Hardening Work

1. Convert substantial release work into Warp-style checked-in specs under `project_docs/` before implementation.
2. Extend the browser E2E suite from the deterministic reliability contract into a full backend-backed conversation smoke once the staging LangGraph endpoint is stable.

## 2026-04-30 Hardening Update

- Runtime state now preserves the detected instruction contract, skill evolution hints, memory-write status, context pressure, compaction trigger, and final run record so UI telemetry and logs can explain why a run used tools, fallback, memory, or approval.
- Session compaction now follows Hermes-style defaults: preflight compression at 50% of the context window and aggressive gateway pressure handling at 85%.
- Each completed agent pass can emit a compact run record that joins instruction contract, active model, tool use, todo counts, memory write status, fallback chain, and final evaluation.
- High-risk system CLI operations now pass through a Harness/Warp-style governance decision with signed audit details and blocking when confirmation is missing.
- Skill evolution output now feeds forward into later planning/tool selection through hidden planning hints sourced from evolved skill history.
- Browser regression coverage now includes model identity consistency, x.com/news source-count behavior, multi-turn continuation, long-task interruption/resume, and critical console-error detection.

## 2026-04-30 Release-Gate Follow-Up

- The ad hoc 24h soak process was stopped on request. Long soak artifacts are treated as runtime output and should remain outside Git.
- Optional dependency tests now skip cleanly when `langgraph-checkpoint-sqlite` or `llama_cpp` extras are not installed, so full pytest collection can complete in lean development environments.
- A staging-only browser smoke is available with `OCTO_RUN_STAGING_SMOKE=1 PLAYWRIGHT_BASE_URL=<staging-url> pnpm --dir frontend smoke:staging-chat`; it exercises the real LangGraph chat route.
- Run records are now appended to `workspace/runtime/run_records.jsonl` and exposed through `GET /api/runtime/run-records` for operator observability.
- The right-side inspector keeps the main chat clear while showing one compact Run trust row for audited, review, or approval-waiting runs.
- For release promotion, prefer a short bounded soak smoke during normal development and schedule real 2h/8h/24h soak outside the repo workspace as CI artifacts or external runtime logs.

## 2026-04-30 Test Source Removal Follow-Up

- Source test files and `tests/` directories were removed by operator request.
- CI no longer references deleted test directories. The required gates are repository hygiene, backend lint/compile, frontend lint/typecheck/build, bounded runtime soak smoke, and release precheck.
- Runtime run records are visible in Runtime Health as a compact operator summary.
- Remaining release gaps are tracked in `project_docs/PROJECT_COMPLETION_GAP_ANALYSIS_2026-04-30.md`.
