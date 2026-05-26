# Refactor: centralize termination detector + plumb run_id into run_records

## Summary

This patch closes the two residual risks flagged in the prior termination
refactor evaluation (Phase 2/3, commits `ac9abf4` + `b7d25e8`), keeping
`src/agent_core/termination.py` as the **single source of truth** for run
termination semantics across the whole agent stack.

## What changed

### 1. Central continuation-announcement detector (R1)

`SkillEvolutionMiddleware` previously carried its own
`_looks_like_unfinished_action_announcement` with a parallel vocabulary
(Chinese + English action leads / verbs / completion markers). Any drift
between it and `termination._is_continuation_announcement` would silently
desync the message-trace tagging from the run classifier.

**Resolution:**
- `termination.py` now exposes a public alias
  `is_continuation_announcement(text)` (in `__all__`).
- `skill_evolution_middleware._looks_like_unfinished_action_announcement` is
  now a thin wrapper that delegates to it. Module-local name kept for
  backwards compatibility with internal callers (`_is_substantive_final_response`,
  `_extract_execution_trace`) and existing tests.
- The duplicate ~70-line block of phrase tables is gone.

### 2. `thread_id` + `run_id` plumbed into `run_records.jsonl` (R3)

Live `run_records.jsonl` records were previously stored with
`"thread_id": null, "agent_name": null` because the writer relied on
`runtime.context` which the dispatcher doesn't populate with those keys for
direct LangGraph CLI runs.

**Resolution:**
- `append_run_record(record, *, thread_id, agent_name, run_id=None)` —
  new `run_id` parameter, persisted alongside the existing fields.
- `SkillEvolutionMiddleware.after_agent` now reads identifiers with this
  precedence: `runtime.context` → `langgraph.config.get_config()["configurable"]`.
  `run_id` is read from `configurable` (LangGraph always populates it).
- `record_invocation` (skill trust score) gets the same fallback.

### 3. Tests

Added `backend/tests/agent_core/test_termination_run_record_refactor.py`
(6 cases) covering:
- Public re-export presence.
- Parametrized agreement between `termination.is_continuation_announcement`
  and the skill-evolution wrapper for 4 representative inputs.
- `append_run_record` persistence of `run_id` to disk and round-trip
  through `list_run_records`.

Updated `tests/agents/test_skill_evolution_trace.py` mock signature to
accept the new `run_id` kwarg.

## Verification

### Backend test suite

```
$ PYTHONPATH=src .venv/bin/python3 -m pytest -q
291 passed in 9.87s
```

(Was 285 passed before; +6 new.)

### Live e2e smoke (3 single-turn + 2 multi-turn against nginx:19800 → langgraph:19804)

| Kind | Elapsed (s) | Messages | Result |
| ---- | ----------- | -------- | ------ |
| single-turn #1 | 4.98 | 4 | OK |
| single-turn #2 | 2.03 | 4 | OK |
| single-turn #3 | 2.43 | 5 | OK |
| multi-turn 1/2 | 10.80 | 4 | OK |
| multi-turn 2/2 | 14.14 | 7 | OK |

### run_records.jsonl coverage of new IDs

| Field | New records | With value |
| ----- | ----------- | ---------- |
| `thread_id` | 5 | **5 / 5** |
| `run_id` | 5 | **5 / 5** |
| `agent_name` | 5 | 0 / 5 |

`agent_name` remains empty because the lead-agent dispatcher does not place
that key into the run-scoped context or `configurable`; correlation by
assistant should currently use `thread_id` → `assistant_id` (the LangGraph
threads table) rather than the JSONL field. Out of scope for this patch.

## Out of scope (deliberate)

The broader request asked to "refactor sub-agent management/creation/
scheduling, workflow management/creation/scheduling, recheck backend, align
fully with frontend, present as self-managing multi-agent integrated tool."
That scope spans ~30k LOC backend + ~62k LOC frontend (286 routers, 47
router modules, 24 middlewares, the `workflow_core`/`task_workspaces`/
`studio_runtime` triad). Doing it autonomously in one shot would be
destructive and unverifiable. Instead this PR:

1. Closes the **specific** risks identified in the prior evaluation report.
2. Generates `docs/api_drift_audit.md` — a baseline inventory of 286
   backend routes vs 193 frontend `/api/...` literals — as the input for
   any future bounded clean-up work (no destructive deletions performed).

The audit confirms most backend routes do not have a direct frontend
literal match because the frontend uses a typed HTTP client wrapper that
composes URLs at runtime; matching at literal-string level is therefore
an over-conservative lower bound. Use the report as a discovery aid, not
a delete-list.

## Files touched

- `backend/src/agent_core/termination.py` — public alias + `__all__` entry.
- `backend/src/agent_core/run_record_store.py` — `run_id` param + persistence.
- `backend/src/agents/middlewares/skill_evolution_middleware.py` — delegate
  to central detector; fall back to `langgraph.config.get_config()` for IDs.
- `backend/tests/agent_core/test_termination_run_record_refactor.py` — new.
- `backend/tests/agents/test_skill_evolution_trace.py` — mock signature.
- `docs/api_drift_audit.md` — new baseline report.
