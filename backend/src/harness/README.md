# Harness — agent-run lifecycle hygiene & extensibility

Minimum-viable runtime harness for octoagent. Phase-2 adds declarative hooks,
wall-clock + max-turns budget, and a Postgres-backed run journal that
structurally eliminates the ghost-run class of bugs.

## Layout

| Module | Purpose |
|---|---|
| `lifecycle.py` | `OrphanRunSweeper`: age-based and (opt-in) heartbeat-based cancel of stale LangGraph runs. |
| `hooks.py` | `HookEvent` enum, `HookRegistry`, `HookExecutor`, `HookContext`, `HookResult`. Decorator `@hook(event)`. |
| `hook_middleware.py` | `HookDispatchMiddleware` (single AgentMiddleware that fires all registered hooks at `before_model` / `after_model`) + `install_default_hooks()` migrating Critic / StepReflection / ProgressStall into the hook surface. |
| `budget.py` | `BudgetMiddleware` — terminates a run when `max_turns` or `max_wallclock_sec` is exceeded. |
| `run_journal.py` | Postgres-backed run journal (opt-in via `OCTO_HARNESS_RUN_JOURNAL=1`). Records run lifecycle + heartbeats; sweeper consults it for stale-heartbeat detection; `mark_orphans_on_startup` flips every still-running row on boot. |

## Env knobs

| Var | Default | Effect |
|---|---|---|
| `OCTO_LANGGRAPH_BASE_URL` | `http://localhost:19884` | LangGraph HTTP API endpoint |
| `OCTO_HARNESS_MAX_RUN_AGE_MIN` | `10` | Age-based sweeper threshold |
| `OCTO_HARNESS_SWEEP_INTERVAL_SEC` | `60` | Sweeper cadence |
| `OCTO_HARNESS_MAX_TURNS` | `60` | Budget: model-call ceiling per user turn |
| `OCTO_HARNESS_MAX_WALLCLOCK_SEC` | `900` | Budget: wall-clock ceiling per user turn |
| `OCTO_HARNESS_BUDGET_ENABLED` | `1` | Set to `0` to disable `BudgetMiddleware` |
| `OCTO_HARNESS_RUN_JOURNAL` | `0` | Set to `1` to enable Postgres run journal |
| `OCTO_HARNESS_RUN_JOURNAL_DSN` | (auto) | Override Postgres DSN; falls back to checkpointer DSN |
| `OCTO_HARNESS_RUN_HEARTBEAT_STALE_SEC` | `120` | Heartbeat-based sweep threshold |

## Why no `langgraph-runtime-postgres`

The official Postgres-backed queue (`langgraph-runtime-postgres`) is shipped
under Elastic-2.0 with the LangGraph Platform commercial bundle and is **not
available on PyPI as OSS**. We instead keep the `langgraph-runtime-inmem`
process-local scheduler (it's fine when the *process* is alive) and pair it
with:

1. **Postgres checkpointer** (`langgraph-checkpoint-postgres`, already wired
   in `config.yaml`) — state survives restarts.
2. **Persistent run journal** in the same Postgres DB — *the* signal that
   a run is alive (heartbeat) survives restarts.
3. **Startup sweep** + **periodic age/heartbeat sweep** — kills ghost runs
   before any user request lands on them.

Outcome: ghost-runs are eliminated as a *user-visible* failure mode. If/when
LangChain ships the Postgres runtime as OSS we can revisit.

## Wiring

* `backend/src/gateway/lifecycle.py` runs:
  ```python
  init_run_journal()
  mark_orphans_on_startup()
  await sweep_orphaned_runs_once()
  start_orphan_run_sweeper_task(app)
  ```
* `backend/src/agents/lead_agent/agent.py` runs `install_default_hooks()`
  during the agent build and appends a single `HookDispatchMiddleware()` in
  place of the three legacy middlewares.

## Roadmap

* Tool-level hooks (`ON_TOOL_START` / `ON_TOOL_END`) wired through the
  agent's tool-call interceptor (currently only the `AFTER_MODEL` surface
  is bridged).
* Heartbeat emission inside `HookDispatchMiddleware` once the agent run-id
  is exposed in `Runtime` (LangChain 1.0.x API).
* Replace inmem runtime queue with a vendored OSS Postgres queue once
  upstream lands.
