# Runtime Hygiene Implementation Plan

**Goal:** Prevent legacy OctoAgent runtime paths from re-entering the repository and verify the Web UI with real user-like browser actions.

**Architecture:** Add a repository-level hygiene scanner, wire it into CI and release precheck, expand backend path tests, and make the browser smoke test fail on chat or console regressions.

**Tasks:**

- Add `scripts/check_legacy_paths.py` and run it from CI, Makefile, and release precheck.
- Expand backend path tests for checkpointer, setup snapshots, memory, and system memory defaults.
- Strengthen `backend/scripts/run_webui_smoke.py` so chat submit and follow-up failures fail the process.
- Run backend lint/tests, frontend typecheck/build-facing checks, and real browser smoke against `http://127.0.0.1:19880`.
- Commit, push `main`, fetch `origin/main`, and verify local `HEAD` equals remote `origin/main`.
