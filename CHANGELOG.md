## 2026-06-01 - Hardening round 4 (idempotent orphan recovery + tolerant health probe)

- `gateway/lifecycle`: the startup orphaned-workspace recovery sweep is now guarded by a process-scoped `IdempotentRunner` (from `storage.workflow.durable_execution`). A repeated or concurrent sweep replays the prior dispatch decision instead of re-invoking `safe_auto_execute_workspace` for the same `task_id`, closing the in-flight recovery race window (recovery scheduled but agent messages not yet persisted). Adds `backend/tests/gateway/test_orphan_recovery_idempotency.py` (at-most-once across two adversarial sweeps).
- `scripts/start-octoagent.sh`: the systemd supervisor health loop now requires `OCTOAGENT_HEALTH_MAX_FAILURES` (default 3) *consecutive* `/api/models` probe failures before exiting for a restart, and bounds every probe with `curl --max-time 5` (startup `wait_ready` likewise). A single transient probe flap no longer bounces the whole stack (langgraph + gateway + frontend + QQ bridge).
- docs: corrected `docs/MODULE_OWNERS.md` lead-agent kernel reference from the deprecated `HermesLeadAgentKernel` to `OctoLeadAgentKernel`.
- Version: backend `2026.6.1.post1`, frontend `20260601.2`. `make lint` clean; orphan-recovery + durable-execution suites pass (6 tests); service restarted cleanly with entry `/api/models` 200 and langgraph `/ok` 200.

## 2026-06-01 - Hardening round 3 (kernel rename + DuckDB single-writer default-on + durable execution + robustness CI)

- Renamed the internal default lead-agent kernel from `HermesLeadAgentKernel` to `OctoLeadAgentKernel` (and the `_DEFAULT_HERMES_LIFECYCLE_STATES` helper, `name`/`lifecycle_model` from `hermes_compatible` to `octo_native`) so OctoAgent's own self-naming no longer borrows the competitor brand. Scope was deliberate: external/competitor references (`competitor="Hermes Agent Solution Template"`, optimization scorecard baselines, the `hermes-gemini-3.1-pro` external model card, third-party `nousresearch-hermes-3-llama`) are KEPT verbatim because they name real external systems, not OctoAgent internals.
- Promoted DuckDB single-writer convergence from opt-in to **default ON**: `OCTOAGENT_DUCKDB_SERIALIZE` now defaults to `1` (advisory readers-writer file lock via `connect_duckdb_with_retry()`), with `=0` as the explicit opt-out. The launcher (`scripts/start-octoagent.sh`) exports the default so the running service inherits it. This closes the previously-deferred "single-writer refactor" high-risk item — system-memory writes on the shared `octoagent_rag.duckdb` are now serialized across the gateway and LangGraph worker instead of relying on retry-only contention handling. Updated `tests/storage/test_duckdb_serialize.py` to assert the new default (sidecar `.rwlock` created by default; retry-only only when explicitly disabled).
- Absorbed Temporal-style durability *ideas* (not the framework) as a dependency-free `backend/src/storage/workflow/durable_execution.py` layer: `IdempotentRunner` (at-most-once activities with deterministic replay), `Saga` (ordered steps with explicit reverse-order compensation), `ReplayJournal` (append-only auditable record), and `make_idempotency_key`. Pure stdlib, inside the storage architecture boundary, re-exported from `storage.workflow`. 5 unit tests.
- Sealed conversation robustness against the "model-bypass" anti-pattern with deterministic CI tests (`backend/tests/agents/test_conversation_robustness.py`): asserts `current_snapshot` (weather/real-time) turns never short-circuit the model for 5 cities + a non-weather turn, that the `control_command`/arithmetic fast paths are preserved, and that `ConversationIntegrityMiddleware` collapses degenerate repeated output. Wired a new self-contained pytest step into the `backend` CI job (`test_duckdb_serialize` + `test_durable_execution` + `test_conversation_robustness`).
- Live flash verification (port 19804, `mode=flash`): 大阪/北海道/冰岛/济南/北京 each returned distinct, city-specific weather and the non-weather turn self-identified as OctoAgent; `max_repeat=1` on every answer (no parroting, no degenerate repetition). Service rebooted cleanly with the renamed kernel and serialize-on default; `make lint` clean, 23 storage/agents regression tests pass.

## 2026-06-01 - Stability remediation round 2 (persistence health + DuckDB writer safety + HITL parallel de-dup)

- Shared a single `connect_duckdb_with_retry()` helper from `backend/src/storage/rag/unified_store.py` and routed both `UnifiedRAGStore._connect()` and the previously-unprotected `SystemRAGStore._connect()` through it, so system-memory writes (`SimpleMemBridge store.add`) on the shared `octoagent_rag.duckdb` are no longer silently dropped under cross-process lock contention (P1-1 follow-up / item C safe step).
- Surfaced LangGraph checkpoint persistence health in the gateway: `/health` now includes a cached (30s TTL, 2s connect timeout, never-raising, off-event-loop) Postgres checkpoint summary, plus a dedicated `/health/persistence` route. Verified live: `{"backend":"postgres","ok":true,"checkpoints":31043,"threads":78}`.
- Added an instance-level same-pass parallel de-dup guard to the dangerous-tool confirmation middleware: when one node fans out several dangerous tool calls sharing the same in-memory `messages` list, only the first handler emits the confirmation prompt; siblings halt silently. Keyed on list identity within a 3s window, fail-open, and fail-safe toward NOT executing the tool (P1-2 follow-up). 2 regression tests added; 172 agent tests pass.
- Verified the Postgres `acopy_thread` fast path end-to-end at the API level: `POST /threads/<id>/copy` copied a 2713-checkpoint thread 1:1 (2713 checkpoints + 1409 blobs + 3768 writes) in 0.59s, then cleaned up via `DELETE /threads/<id>` (204).
- Confirmed the `request_timeout: 300` change closed the timeout cascade: post-restart langgraph/gateway logs show 0 orphan cancels, 0 timeouts, 0 SSE drops (startup sweep `runs_cancelled: 0`).


## 2026-06-01 - Stability remediation phase 2 (checkpointer acopy_thread + HITL confirmation de-dup)

- Implemented `acopy_thread` on the custom async Postgres checkpointer (`backend/src/agents/checkpointer/async_provider.py`) so `POST /threads/<id>/copy` no longer falls back to the slow generic per-checkpoint copy path; verified against live Postgres (2,713 checkpoints copied 1:1) and the `missing acopy_thread` warning is gone after restart. This corrects the earlier assumption that LangGraph state was non-persistent — the custom Postgres checkpointer has been active all along (30k+ checkpoints persisted via `backend/langgraph.json` + `checkpointer.type: postgres`).
- Added safe, fail-open de-duplication of repeated dangerous-tool confirmation prompts in `backend/src/agents/middlewares/dangerous_tool_confirmation_middleware.py`: a re-emission is suppressed only while an identical-signature confirmation is already the most recent bot output with no human reply since, never across threads or for a different tool. Added 2 regression tests; `tests/agents` 170 passed.
- Documented the corrected P0-1 finding and a DuckDB single-writer convergence design in `docs/octoagent-stability-remediation-2026-06-01.md`.

## 2026-06-01 - Stability remediation (local model timeout + DuckDB lock retry)

- Raised the local `qwen3.6-35b-a3b-q8-mm-prod` model card `request_timeout` from 120s to 300s in the runtime config to stop the timeout -> free-model fallback -> orphan-run -> SSE-drop cascade on long agent generations (P0-2/P0-3/P1-3).
- Added exponential-backoff retry on DuckDB file-lock contention in `UnifiedRAGStore._connect()` so RAG/memory reads and writes are no longer silently dropped when the gateway and LangGraph worker briefly contend for the single-writer lock (P1-1).
- Documented deferred high-risk items (LangGraph persistence migration, DuckDB single-writer refactor) in `docs/octoagent-stability-remediation-2026-06-01.md`.

## 2026-05-28 - Writing and publishing workflow tools (`2026.5.28.post4`)

- Added a managed writing/publishing toolchain wrapper for browser-use, Playwright, WP-CLI, Presidio, Pandoc, textlint, Vale, project storage, drafting, review, human approval, publishing, and publication audit flows.
- Added a reproducible installer for writing/publishing tool dependencies under `runtime/system_tools` and `runtime/tools`.

## 2026-05-28 - OpenRouter attribution and usage tracking

- Added backend-wide OpenRouter attribution headers (`HTTP-Referer`, `X-Title`) for chat model requests and provider model probes.
- Enabled OpenRouter usage accounting opt-in by default with `usage.include=true` on OpenRouter chat requests.

## 2026-05-28 - Cross-platform Docker packaging

- Added the packaged Docker Compose profile for Linux, Windows, and macOS with nginx, frontend, gateway, LangGraph, PostgreSQL, and Redis services.
- Added production backend/frontend Dockerfiles, Linux/macOS and Windows one-command Docker installers, and a Docker source packaging script.
- Made MCP server commands portable through environment variables and installed filesystem/postgres MCP packages into `runtime/tools/mcp`.
- Added English Docker deployment documentation and a Japanese project/install/use guide.

## 2026-05-28 - System tools, MCP cleanup, and runtime hardening

## 2026-05-28 - MCP smoke tests, manifests, and SaaS eval loop

- Added unified MCP smoke tests covering schema, startup, list_tools, minimal calls, registry display, and failure degradation.
- Installed and enabled Redis/OpenAPI/Kubernetes/Docker MCP packages under `runtime/tools/mcp`, plus local HTTP API and Docker Compose MCP inspectors.
- Added machine-readable builtin tool manifest fields for parameters, permission scope, timeout, artifacts, risk, and failure modes.
- Enhanced the Tools Hub to show tool status, failure reasons, risk badges, parameters, timeouts, and artifact hints.
- Upgraded `awesome_selfhosted` to a runtime-updatable SaaS catalog with tags, ratings, deployment complexity, and task templates.
- Added OctoAgent eval suites and specialist subagent templates for planner/coder/operator/reviewer/teacher.


### Changes
- Restored LangGraph startup by aligning PostgreSQL checkpointer dependencies: `langgraph-checkpoint==4.1.1`, `langgraph-checkpoint-postgres==3.1.0`, `psycopg[binary]==3.3.4`, and `psycopg-pool==3.3.1`.
- Added and registered specialized Docker, SSH, Git, database, security, test, `awesome_selfhosted`, and `octo_doctor` tools; capability discovery now lists system-scoped tools while preserving permission metadata.
- Enabled the usable MCP servers (`filesystem`, `postgres`) and removed unavailable MCP entries (`camofox-controlled-browser`, `github`, `peekaboo-vision`).
- Kept `semgrep_scan` absent because current Semgrep releases conflict with the MCP dependency set; use `static_security_scan`, `bandit_scan`, and `trivy_scan` instead.
- Started and enabled Docker/containerd so Docker tools are actually usable on this host.
- Set all OctoAgent model-card temperatures and the local Qwen llama.cpp launcher temperature to `0.85`.
- Documented the operational policy in `docs/system-tools-and-mcp-hardening-2026-05-28.md`.

### Verification
- `octoagent-local.service` active; gateway `/health`, LangGraph `/docs`, and WebUI `/workspace/chats/new` all return HTTP 200.
- Registry reports 91 built-in tools and 2/2 configured MCP servers enabled.
- System-mode tool load returns 104 tools, including 13 MCP tools.
- Representative tool smokes passed: `git_status`, `db_connect_check`, `docker_status`, `awesome_selfhosted`, and `octo_doctor`.
- `backend/.venv/bin/python -m pip check` reports no broken requirements.
- Only the backend virtualenv remains under the project tree.

## 2026-05-27 — Decommission 192.168.110.3 model card; system default now localhost:8000

### Changes
- `runtime/config/config.yaml`: removed model card `qwen3.6-35b-a3b-mxfp4` (was pointing to
  `http://192.168.110.3:8000/v1`); 3号机 has been reimaged so the upstream is gone.
- Elevated `qwen3.6-35b-a3b-q8-mm-prod` (local 2号机 llama.cpp at `http://localhost:8000/v1`)
  to system default by setting `priority: 100`, ahead of all other models. The factory's
  `_select_default_model_name()` is priority-driven, so this becomes the picked default
  whenever no user override exists in setup_state.
- Local deployment `~/.config/octoagent/setup_state.json` also explicitly sets
  `default_model: qwen3.6-35b-a3b-q8-mm-prod` (not committed; user-scoped).

### Verification
- `/api/models` reports 33 entries with zero `mxfp4` references.
- `/api/agents` still reports 57 preset agents.
- `http://127.0.0.1:8000/v1/models` confirms the local llama.cpp server is serving
  `qwen3.6-35b-a3b-q8-mm-prod`.

## 2026-05-27 (Preset agents restored + ask_user_question pause loop fix)

### `_system_agents_root()` path resolution

`backend/src/runtime/config/agents_config.py:_system_agents_root()` previously
computed the repository root via `Path(__file__).resolve().parents[3]`, but the
file lives at `backend/src/runtime/config/agents_config.py`, so that index
resolved to the `backend/` directory and the `.github/agents/` lookup always
missed. The `Path.cwd()` fallback never compensated because the systemd
unit runs uvicorn with `cwd=backend/`. Net effect: `list_system_agents()`
returned an empty list at runtime, `/api/agents` responded with an empty
array, and the WebUI **Preset Agents** gallery at `/workspace/agents`
showed zero entries even though 56+ `.agent.md` files were checked into
`.github/agents/`.

Fix: bump to `parents[4]` (still guarding for short paths) and keep
`Path.cwd()` plus the legacy `parents[3]` hop as additional candidates so
any future relocation continues to discover the directory. After the
restart `/api/agents` returns 57 preset agents.

Touch points:

- `backend/src/runtime/config/agents_config.py` — `_system_agents_root()`
  rewritten with correct anchor + multi-candidate fallback list.

### `ask_user_question` no longer enters an infinite confirmation loop

The lead-agent tool catalog exposes two clarification entry points:
the canonical `ask_clarification` (defined in
`backend/src/tools/builtins/clarification_tool.py`) and a legacy
`ask_user_question` re-export shipped via
`backend/src/tools/builtins/openharness_compat_tools.py:667-674`.

`ClarificationMiddleware` only intercepted the canonical name. The
legacy tool was a no-op stub that returned the plain string
`"User clarification required: <q>"`. Several smaller open-weight
models (e.g. free-tier qwen3-next, gpt-oss-20b) preferred the shorter
name; the model received the stub's text as a tool result, decided the
clarification had not been answered, and immediately re-called the tool —
the `ToolBudgetMiddleware` duplicate hard-stop only fires for byte-for-byte
identical calls, so any small wording variation kept the loop alive
until the runtime recursion limit was hit. The frontend layer at
`frontend/src/core/threads/hooks.ts` then auto-resumed on
`GraphRecursionError`, which made the loop appear permanent to the user.

Fix: `ClarificationMiddleware` now intercepts both `ask_clarification`
and `ask_user_question`. The legacy single-arg
`ask_user_question(question=...)` payload is normalized through a new
`_normalize_clarification_args()` helper into the richer
`ask_clarification` argument shape (with `clarification_type` defaulted
to `"missing_info"`), then routed through the existing
`Command(goto=END)` interrupt path. The resulting `ToolMessage` keeps
`name="ask_clarification"`, so the frontend's existing
`message-group.tsx:402` renderer surfaces it without any UI change.

Touch points:

- `backend/src/agents/middlewares/clarification_middleware.py` — added
  `_CLARIFICATION_TOOL_NAMES`, `_normalize_clarification_args()`, and
  extended `wrap_tool_call` / `awrap_tool_call` to accept both tool names.

Verification:

- `python -c "from src.runtime.config.agents_config import list_system_agents; print(len(list_system_agents()))"` → `57`.
- `curl http://127.0.0.1:19800/api/agents | jq '.agents | length'` → `57`.
- `pytest backend/tests` middleware/config selectors still pass (no regression).
- `ruff check` clean on both modified files.
- WebUI `/workspace/agents` returns HTTP 200 with preset cards rendered.

## 2026-05-27 (Japan + Korea provider cards; start-daemon config detection fix)

### Provider templates — Japan + Korea closed-source models

Eight new closed-source provider cards added to the WebUI **Models** page
(`/workspace/config/models`), inserted **between Google and the existing
GLM card** so the first four cards (Claude, ChatGPT, Grok, Gemini) keep
their position unchanged.

| Order | provider_id | Vendor | Notes |
| --- | --- | --- | --- |
|  5 | `plamo`   | Preferred Networks PLaMo Prime  | OpenAI-compatible, sign up at platform.preferredai.jp |
|  6 | `tsuzumi` | NTT tsuzumi 2                    | Enterprise contract; replace `default_base_url` with Azure MaaS / NTT Communications endpoint |
|  7 | `cotomi`  | NEC cotomi                       | Enterprise-only; endpoint is provisioned per contract |
|  8 | `takane`  | Fujitsu Takane (Kozuchi)         | Sold via Fujitsu Kozuchi platform |
|  9 | `clovax`  | NAVER HyperCLOVA X (CLOVA Studio)| OpenAI-compatible (`/v1/openai`); requires NCP sub-account API key |
| 10 | `exaone`  | LG AI Research EXAONE 3.5        | Hosted via FriendliAI dedicated endpoints |
| 11 | `solar`   | Upstage Solar Pro / Mini         | Native OpenAI-compatible API at `api.upstage.ai/v1` |
| 12 | `ax`      | SK Telecom A.X 4.0               | Enterprise; replace endpoint per subscription |

Existing `glm`, `minimax`, `qwen`, `deepseek` cards shift to positions
13–16 (display order only — their IDs and env-var names are unchanged).

All eight templates pass the model-auth invariants exercised by
`backend/tests/governance/test_model_auth_secret_handling.py`:
unique `OCTOAGENT_MODEL_AUTH_<NAME>` env vars, frozen dataclasses, no
OAuth client secrets in `to_public_dict()`, no filesystem I/O on
import. Verified end-to-end via
`GET /api/model-auth/templates` returning all 16 templates in the
expected order.

Touch points:

- `backend/src/governance/model_auth/service.py` — eight new
  `ProviderTemplate` entries inserted between `"google"` and `"glm"`.

### scripts/start-daemon.sh — recover config-path autodetection

The 2026-05-27 review-hardening commit relocated the active config
file from `<repo>/config.yaml` to `<repo>/runtime/config/config.yaml`,
but the shell pre-flight in `scripts/start-daemon.sh` was not updated
to match. On hosts without `OCTO_AGENT_CONFIG_PATH` exported by the
systemd unit, the service refused to start with
`"✗ No OctoAgent config file found."`.

`scripts/start-daemon.sh` now mirrors the resolver order used by
`backend/src/runtime/config/app_config.py:resolve_app_config_path`:

1. `$OCTO_AGENT_CONFIG_PATH` (if set and the file exists).
2. `$REPO_ROOT/runtime/config/config.yaml` (preferred since 2026-05-27).
3. `$REPO_ROOT/backend/config.yaml` (back-compat).
4. `$REPO_ROOT/config.yaml` (back-compat).

When a file is found via steps 2–4 the script **exports**
`OCTO_AGENT_CONFIG_PATH` so every spawned Python process resolves the
same file even when its working directory differs.

Touch points:

- `scripts/start-daemon.sh` — config-detection cascade rewritten.

Operational note: the temporary systemd drop-in
`/etc/systemd/system/octoagent-local.service.d/10-config-path.conf`
that papered over this regression has been removed; the service now
boots cleanly with the patched script alone.

---
## 2026-05-27 (review hardening: tests, config relocation, docs, license FAQ)

### Summary

Closes the seven follow-up items from the 2026-05-27 project evaluation
(score 4.1/5). Surgical changes only — no behavioural drift on any
existing code path. The single commit chain on `main` (a single squash
from 2026-05-26) is preserved; from this point forward `main` keeps
the full commit history per [`CONTRIBUTING.md`](CONTRIBUTING.md) §7.

### Test coverage added

Six new pytest modules lock high-value invariants that previously had
no regression coverage. All six pass under the existing
`backend/.venv/bin/pytest` baseline and add no new dependencies.

| Module | What it locks |
| --- | --- |
| `backend/tests/governance/test_model_auth_secret_handling.py` | `ProviderTemplate` immutability, `OCTOAGENT_MODEL_AUTH_*` env-var namespace, OAuth client-secret omission from public projection, env-var uniqueness, no filesystem side-effects at import. |
| `backend/tests/governance/test_multi_tenant_isolation.py` | Default-tenant seeding, registry payload versioning, register/deregister idempotency, per-tenant workspace + agent limits, signed audit events, cross-registry isolation. |
| `backend/tests/sandbox/test_system_execution_guard.py` | Safe commands allowed, dangerous commands blocked without operator approval, operator-attested approval path, immutable decision dataclass, signed audit event shape, tuple guardrails. |
| `backend/tests/rag/test_retrieval_precision.py` | BM25 ranking precision on synthetic corpus, ASCII + CJK tokenizer behaviour, `top_k` cap, empty-corpus and empty-query edge cases. |
| `backend/tests/memory/test_memory_governance.py` | Long-term and permanent namespace tier disjointness, canonical metadata keys, permanent retention policy, `is_memory_expired` and `resolve_memory_expiry` edge cases, provenance recording. |
| `backend/tests/harness/test_research_closure_policy.py` | The 2026-05-27 hotfix invariant: research-closure short-circuit only triggers on `status == "must_finalize"`, and the `execution_review` + `step_reflection` middlewares agree on that signal. |

### Configuration relocation

The active configuration file moves from `config.yaml` (repo root) to
**`runtime/config/config.yaml`** so the runtime tree is the single
home for installation-local state. `runtime/config/` was already used
for `model_auth.env` and other secrets; aligning `config.yaml` removes
the last loose root-level secret file.

- `backend/src/runtime/config/app_config.py` —
  `resolve_app_config_path()` now prefers `runtime/config/config.yaml`,
  falls back to `Path.cwd().parent/runtime/config/config.yaml`, and
  only then to the legacy `config.yaml` paths (back-compat).
- `Makefile` — `make config` writes to `runtime/config/config.yaml`
  with mode `0600`. `setup-sandbox` reads from either location.
- `.github/workflows/ci.yml` and `.github/workflows/live-validations.yml`
  — both write the CI / live secret to the new location.
- `.gitignore` — adds `runtime/config/*.yaml` next to the existing
  `runtime/config/*.env` entry.
- The existing config file on this installation was moved with
  `mv config.yaml runtime/config/config.yaml` (mode preserved).

### Push policy (no-squash)

`CONTRIBUTING.md` §7 now documents that `main` keeps full commit
history. The GitHub merge-button policy is **"Create a merge commit"**
or **"Rebase and merge"**; never **"Squash and merge"**. Local cleanup
via `git rebase -i` before push is still encouraged.

### Documentation

- New `docs/INDEX.md` — single entry point that explains the role of
  `docs/` (operator-facing) vs `project_docs/` (contributor-facing).
  Both trees remain separate; the index is the unification surface.
- New `docs/MODULE_OWNERS.md` — closes the "Phase 7 deferred: semantic
  dedup" follow-up from the 2026-05-26 entry **analytically**: after a
  full re-read of `agents.core`, `agents.runtime`, `agents.lead_agent`,
  and `agents.generic`, the subdomains own distinct lifecycles and
  must not be merged. The doc captures the ownership map and the
  reasons against a physical merge so future contributors can find
  the decision.
- New `docs/COMMERCIAL_LICENSE_FAQ.md` — explicit, plain-English
  statement of the commercial licensing model: **free only for
  personal non-commercial use, bona-fide academic research, and ≤30-day
  internal evaluation**. Every other use (SaaS, internal enterprise,
  embedding, OEM, redistribution) requires a paid license from
  `zillafan80@gmail.com`. SSPL §13 is referenced as the source of
  truth; the FAQ is non-binding interpretation.
- `README.md` — adds top-of-file pointers to the License FAQ, the
  docs index, and the module ownership map.
- `CONTRIBUTING.md` — adds §7 (Push policy) and §8 (Configuration
  file location).

### Files added (10)

- `backend/tests/governance/test_model_auth_secret_handling.py`
- `backend/tests/governance/test_multi_tenant_isolation.py`
- `backend/tests/sandbox/test_system_execution_guard.py`
- `backend/tests/rag/test_retrieval_precision.py`
- `backend/tests/memory/test_memory_governance.py`
- `backend/tests/harness/test_research_closure_policy.py`
- `docs/INDEX.md`
- `docs/MODULE_OWNERS.md`
- `docs/COMMERCIAL_LICENSE_FAQ.md`
- (new git-tracked: `runtime/config/` directory contents are gitignored)

### Files modified (7)

- `backend/src/runtime/config/app_config.py`
- `Makefile`
- `.github/workflows/ci.yml`
- `.github/workflows/live-validations.yml`
- `.gitignore`
- `CONTRIBUTING.md`
- `README.md`

### Filesystem changes

- `config.yaml` (previously git-tracked at the repo root) is removed
  from git: its content is operator-local state, not source code. The
  local file was moved to `runtime/config/config.yaml` with mode
  `0600` preserved. `runtime/config/*.yaml` is gitignored going
  forward, so future operator edits never reach `main` again.
- Operators on existing clones should run
  `mkdir -p runtime/config && git mv config.yaml runtime/config/config.yaml`
  on next pull (or accept the deletion and re-create the runtime file
  from `config.example.yaml`).
- This commit does NOT rewrite prior history; any secrets that may
  have previously reached `main` should be rotated separately.

### Verification

- `cd backend && .venv/bin/pytest tests/governance/test_model_auth_secret_handling.py tests/governance/test_multi_tenant_isolation.py tests/sandbox/test_system_execution_guard.py tests/rag/test_retrieval_precision.py tests/memory/test_memory_governance.py tests/harness/test_research_closure_policy.py -v` — see the post-deploy log in `runtime/logs/` for the run.
- `cd backend && .venv/bin/ruff check tests/` — clean on the new files.
- `cd backend && .venv/bin/python scripts/check_topology_freeze.py` — clean (no domain shape change).

### Non-goals (intentionally NOT done)

- **No physical merge** of the four `agents/*` subdomains. The
  `docs/MODULE_OWNERS.md` analysis records why a merge would harm
  selective importability and re-couple the maintenance loop into the
  product runtime. The 2026-05-26 "deferred semantic dedup" item is
  considered **closed**: no real duplication exists.
- **No deletion** of either `docs/` or `project_docs/`. The two trees
  serve different audiences; `docs/INDEX.md` unifies discovery
  without forcing a relocation.
- **No change** to the SSPL v1 / commercial dual-license framework
  itself. The FAQ only clarifies enforcement intent.

---

## 2026-05-26 (phase 7: remaining 6 domain pilots — full topology consolidation)

### Summary

Completed pilots 7.2 through 7.8 atop the interfaces pilot (`9fce489`).
`backend/src/` top-level directory count went **48 -> 11**:
`agents, community, gateway, governance, harness, interfaces, models,
runtime, storage, tools, utils`. ~70K LoC reorganized via `git mv` +
regex codemod. Pytest baseline preserved end-to-end: 314 -> 314.

### Commit chain

| # | SHA | Pilot | Moves |
| --- | --- | --- | --- |
| 7.2 | `78c5072` | governance | model_auth, multi_tenant, operator, users |
| 7.3 | `382e247` | harness | dispatcher, evaluation, hook_core->hooks, orchestration->exec, reflection |
| 7.4 | `efcb103` | runtime | config, bootstrap, system_guard + 8 top-level `.py` folded |
| 7.5 | `7a79772` | tools | sandbox, browser_runtime->sandbox/browser, system_execution, builtins, registry, mcp, plugins, software_interfaces |
| 7.6 | `1004a7f` | gateway | channels, channel_sdk, monitoring, observability (with lazy `__getattr__` rewrite of `gateway/__init__.py`) |
| 7.7 | `5f8084a` + `3939c65` | storage | brain, rag, query_engine->query, task_workspaces, workflow_core->workflow, skills, skill_evolution, self_evolution, optimization_program->optimization, session_compaction |
| 7.8 | `5e115ee` | agents | subagents, generic_agent->generic, agent_core->core, agent_runtime->runtime |

### Critical side-effects encountered

- **gateway/__init__.py made lazy** (pilot 7.6, commit `1004a7f`): rewrote
  to PEP-562 `__getattr__` returning `app`, `create_app`, `GatewayConfig`,
  `get_gateway_config` on demand. Without this, importing
  `src.gateway.observability` from `src.tools.builtins.codex_cli_tool`
  triggered a full `src.gateway.app -> router_registry -> tools.registry`
  load while `src.tools` itself was still initialising.

- **Three `parents[N]` path-chain off-by-one bugs** caught post-codemod:
    - `storage/skills/loader.py` `parents[3] -> [4]` (extra-skill-roots
      from `.agents/skills/*` silently failed to load until fix).
    - `storage/self_evolution/dynamic_tools.py` `parents[2] -> [3]`
      (module-level `_DYNAMIC_ROOT.mkdir` recreated a stray
      `backend/src/src/tools/builtins/dynamic/` tree every pytest run;
      committed in `5f8084a`, removed and fixed in `3939c65`).
    - `agents/subagents/catalog.py` `parents[3] -> [4]` (fixed in
      pilot 7.8).

- **Config-file scan coverage** (pilot 7.5): regex codemod had to be
  extended to scan repo-root `config.yaml` + `config.example.yaml` for
  `use: src.X:Y` tool-catalog strings — initial pass missed 12 substitutions
  and 5 tests broke until fixed in-pilot.

### Topology freeze final state

`scripts/check_topology_freeze.py` FROZEN_DIRS now holds exactly 11 entries
matching the 8-domain MODULE_OWNERS.md target (plus `community`/`models`/`utils`
shared layers). FROZEN_FILES limited to `__init__.py`.
`topology freeze: OK (matches 2026-05-26 snapshot)` enforced by CI workflow
`.github/workflows/topology-freeze.yml`.

### Deferred to follow-ups

- Semantic deduplication between `agents/core/`, `agents/runtime/`, and
  the rest of `src/agents/` (pilot 7.8 was physical move only).
- `import-linter`/`tach` boundary enforcement layered on top of the freeze.
- `make release-readiness` full pass.

---

## 2026-05-26 (phase 7: interfaces-domain pilot — physical merge)

### Summary

First physical execution of the topology consolidation roadmap from
`project_docs/docs/MODULE_OWNERS.md` §3.8. Eight previously top-level
`backend/src/` items merged into a single new `interfaces/` domain — the
smallest-blast-radius pilot. No functional changes; all imports rewritten
atomically; pytest baseline preserved (314 passed → 314 passed).

### Moves (`git mv`, history preserved)

| Old path | New path |
| --- | --- |
| `backend/src/client.py` | `backend/src/interfaces/embedded/client.py` |
| `backend/src/client_agent.py` | `backend/src/interfaces/embedded/agent.py` |
| `backend/src/client_streaming.py` | `backend/src/interfaces/embedded/streaming.py` |
| `backend/src/python_sdk/` | `backend/src/interfaces/python_sdk/` |
| `backend/src/interface_layer/` | `backend/src/interfaces/contracts/` |
| `backend/src/studio_runtime/` | `backend/src/interfaces/studio/` |
| `backend/src/research_runtime/` | `backend/src/interfaces/research/` |
| `backend/src/distributed_execution/` | `backend/src/interfaces/distributed/` |

### Codemod

- Repo-wide regex rewrite across `backend/**.py` + `scripts/**.py` (also
  `*.yaml`/`*.json`/`*.toml`/`*.md`): 13 files / 24 substitutions.
- Order-sensitive rules: `src.client_agent` and `src.client_streaming` rewritten
  **before** `src.client` to avoid prefix collision (regex uses negative
  look-ahead `(?=[\s.,)\]])` for `src.client`).
- Relative imports inside the moved packages (`from .contracts import …`,
  `from .service import …`) unchanged — `git mv` of a package preserves
  relative semantics.
- Public surface: `backend/src/interfaces/__init__.py` (lazy / docstring-only)
  + `backend/src/interfaces/embedded/__init__.py` (re-exports
  `ClientAgentBuilder`, `ClientStreamSerializer`).

### Topology freeze allow-list

`scripts/check_topology_freeze.py`:

- `FROZEN_DIRS`: removed 5 (`distributed_execution`, `interface_layer`,
  `python_sdk`, `research_runtime`, `studio_runtime`); added 1
  (`interfaces`). Net top-level dir count 52 → 48.
- `FROZEN_FILES`: removed 3 (`client.py`, `client_agent.py`,
  `client_streaming.py`).
- `python3 scripts/check_topology_freeze.py` → "topology freeze: OK
  (matches 2026-05-26 snapshot)".

### Verification

- `backend/.venv/bin/pytest -q` → **314 passed in 10.56s** (= prior baseline).
- Smoke import of `interfaces.embedded.{client,agent,streaming}`,
  `interfaces.python_sdk`, `interfaces.studio.service`,
  `interfaces.research.service`, `interfaces.distributed`,
  `gateway.lifecycle` → all resolve cleanly.
- Residual `src.<old_name>` grep across `backend/` + `scripts/`: **zero
  matches** (only stale references remain in `docs/backend_orphan_verdicts.json`
  and `docs/backend_unreachable_modules.json`, both non-executable audit
  artefacts to be regenerated on next audit run).

### Notes / non-goals

- Naming oddity preserved per MODULE_OWNERS spec: `interfaces/contracts/`
  contains an inner `contracts.py` (the original `interface_layer/contracts.py`).
  Not collapsed.
- Pre-existing circular import hazard between `interfaces.contracts.service`
  and `query_engine` surfaces only when `contracts.service` is the first thing
  imported in isolation; normal import order (and the full test suite) is
  unaffected. Tracked separately as a refactor candidate.
- Remaining 6 domains (`runtime`, `agent`, `tooling`, `governance`,
  `evaluation`, `storage`) still scheduled for sequential pilots; the
  `interfaces` move demonstrates the atomic codemod + freeze-list pattern
  to be reused.

---

## 2026-05-26 (phase 6.1-6.5: distributed dispatcher — implementation)

### Summary
Implemented the full distributed dispatcher stack designed in the
phase-6 RFC (`d7c2e7a`). All new code is **env-flag gated and default
OFF**; the existing single-node behaviour is unchanged. With
`OCTO_DISPATCHER_ENABLED=1` set and a Postgres `DATABASE_URL` (or
`OCTO_DISPATCHER_DSN`) available the gateway now performs Postgres-
backed leader election, durable job dispatch and graceful drain.

### New module: `backend/src/harness/dispatcher/`
- `schema.py` — DDL for `octo_dispatch_queue` + `octo_dispatch_workers`,
  shared lazy `AsyncConnectionPool`, env helpers, stable per-process
  `worker_id` (`host:pid:uuid8`).
- `workers.py` — `register_worker`, `heartbeat`, `mark_draining`,
  `list_workers`, `reap_stale_workers`, `HeartbeatLoop` (5 s default).
- `leader.py` — Session-scoped `pg_try_advisory_lock(0x6F63746F, 1)`
  leader election with held connection, leader role recorded in
  workers table, `LeaderLoop` (5 s poll).
- `queue.py` — `enqueue_dispatch` (idempotent ON CONFLICT DO NOTHING +
  best-effort `NOTIFY octo_dispatch_<kind>`), `claim_dispatch` (CTE
  with `FOR UPDATE SKIP LOCKED`), `ack_dispatch`, `nack_dispatch`
  (exponential backoff `2^attempts` capped at 300 s,
  `finished_state='failed'` after `max_attempts`), `dispatch_queue_stats`.
- `bus_backend.py` — Optional `PostgresInboundBus(MessageBus)` activated
  by `OCTO_DISPATCH_BACKEND=postgres`; in-memory fast path preserved
  alongside durable journaling.
- `dispatch.py` — `DispatchLoop` (leader-only); per-tick drains up to
  50 jobs, reaps stale workers ≈60 s; pluggable `register_handler(kind, fn)`.
- `drain.py` — `drain_self(timeout_sec)` marks self draining and polls
  in-flight count until 0 or deadline; safe no-op when dispatcher off.
- `lifespan.py` — `init_dispatcher`, `start_dispatcher_task`,
  `stop_dispatcher_task` composing Heartbeat + Leader + Dispatch loops
  on `app.state`.

### Wired
- `backend/src/gateway/lifecycle.py` — `gateway_lifespan` now awaits
  `start_dispatcher_task(app)` after the OOM guard and
  `stop_dispatcher_task(app)` before shutting down the OOM guard.
- `backend/src/gateway/routers/runtime.py` — added introspection
  endpoints:
  - `GET /api/runtime/workers` → `{ "workers": [...] }`
  - `GET /api/runtime/dispatch` → queue stats (`enabled`, `by_state`,
    `by_kind`, `in_flight`, optional `available`)
  - `GET /api/runtime/leader` → `{worker_id, is_leader, since}`
- `scripts/octoagent` — new `drain` verb runs `drain_self()` for
  graceful rolling-restart workflows (`octoagent drain`).

### Tests
- `backend/tests/harness/test_dispatcher.py` — 15 no-DB tests
  exercising every public API in the disabled / DSN-unresolvable path
  (default OFF).
- Full suite: **314 passed** (was 299) on `192.168.110.2`.

### Enablement
1. `export DATABASE_URL=postgresql://...` (or `OCTO_DISPATCHER_DSN`).
2. `export OCTO_DISPATCHER_ENABLED=1`.
3. (Optional) `export OCTO_DISPATCH_BACKEND=postgres` to durably journal
   inbound channel traffic.
4. Restart gateway. Schema is auto-installed
   (`CREATE TABLE IF NOT EXISTS`). Health: `GET /api/runtime/leader`.

### Operational notes
- Leader election uses a *session-scoped* advisory lock — connection
  loss automatically releases the lock and a follower will take over
  within `leader_poll_interval_sec` (5 s default).
- Backoff curve: 1, 2, 4, 8, 16, 32, 64, 128, 256, 300, 300 … (capped).
- `octoagent drain` runs to completion (default `drain_timeout_sec=600`)
  and exits 0 with `{"drained": true|false, "remaining": N, "enabled": …}`.
- Existing single-node deployments need *no change*; nothing in the
  unflagged path touches Postgres.

## 2026-05-26 (phase 6 RFC: distributed dispatcher design)

### Design RFC (no runtime change)
- `project_docs/docs/PHASE6_DISTRIBUTED_DISPATCHER_RFC.md`: design RFC
  for the Phase 6 distributed dispatcher. Locks in the architectural
  choice **before** any code lands.
  - Goals: durable inbound queue, worker registry with heartbeats,
    leader election, at-least-once dispatch with idempotency,
    drain + graceful rolling restart.
  - Non-goals: geo-distributed deployment, replacing LangGraph in-process
    workers, replacing Postgres, new external API surface.
  - **Decision**: Postgres-native (Option A) — `SELECT ... FOR UPDATE
    SKIP LOCKED` for queue claim, `LISTEN`/`NOTIFY` for wake-ups,
    `pg_try_advisory_lock` for leader election. Zero new operational
    surface (Postgres is already system-of-record for checkpointer +
    `run_journal`). Compared against Redis Streams (Option B) and NATS
    JetStream (Option C); both rejected on operational-surface cost.
  - 5-stage rollout plan (6.1 schema + registry → 6.2 leader election →
    6.3 durable inbound queue → 6.4 dispatch + retries → 6.5 drain +
    rolling restart). Each stage is independently shippable.
  - Acceptance criteria for "Phase 6 done" are documented in §9.

### Next-session slice
- Stage 6.1 implementation: add `octo_dispatch_queue`,
  `octo_dispatch_workers`, and `octo_dispatch_leader_lock` tables
  behind `backend/src/runtime/dispatcher/schema.py`; register every
  process with 5 s heartbeats; expose `/api/runtime/workers` as a
  read-only observability endpoint. No behaviour change.

## 2026-05-26 (follow-up: bug fix + endpoint tests + git cleanup)

### Backend bug fixes
- `backend/src/gateway/routers/runtime.py`: tool-trace + effective-config
  `repo_root` resolution previously fell through to `Path.cwd()` because
  `app_config.repo_root` doesn't exist as an attribute on `AppConfig`. When
  the gateway was launched from `backend/` cwd, the tool-trace `source_file`
  pointed at `backend/workspace/...` (file_exists:false) and the
  effective-config `paths.repo_root` reported the wrong path. Replaced with
  module-level `_resolve_repo_root()` anchored on
  `Path(__file__).resolve().parents[4]` (verified by checking the resolved
  path contains both `backend/` and `frontend/` subdirs).

### Backend tests (Phase 3 partial)
- New `backend/tests/gateway/test_runtime_endpoints.py` — 9 tests covering:
  - effective-config envelope shape (required keys, types).
  - effective-config repo_root regression guard (must contain both
    `backend/` and `frontend/`).
  - secret masking: `OCTOAGENT_FAKE_API_KEY` / `TOKEN` / `PASSWORD` masked
    as `xxx***yy (len=N)`; non-secret keys passed through; short secrets
    (≤6 chars) fully redacted to `***`.
  - tool-trace envelope shape + `source_file` regression guard
    (no `backend/workspace/` substring).
  - tool-trace `limit` clamping (0 and >2000 both accepted).
- Full suite: **299 passed** (was 290).

### Git hygiene
- `.gitignore`: added `workspace/outputs/` (per-run chat artifacts).
- `git rm --cached` for the two report markdown files accidentally
  included in commit `41adf7b` via `git add -A`.

### Phase 2 status — not migrated this session
- `frontend/src/core/threads/chat-turn-reducer.ts` remains **scaffold only**.
  Wiring the reducer into `hooks.ts::sendMessage` requires running the
  four-scenario WebUI regression (plain / attachment / disconnect+resume /
  first-turn retry) which depends on a human operator. The three first-turn
  regressions in commits `1121af4` / `f13e874` / `87cc74c` make blind
  refactoring of `hooks.ts` too risky to attempt autonomously.
- Frontend has no vitest/jest infrastructure, so unit tests for the
  reducer would require introducing a new test runner (out of scope for
  this commit).

### Phase 6 / 7 / 8 — explicitly NOT delivered
Each is an independent multi-week project. Listing concrete next-session
slices for traceability:

- **Phase 6 (distributed dispatcher)** next slice: write a design RFC
  (leader-election strategy, worker-registry schema, durable queue
  candidate evaluation: Postgres LISTEN/NOTIFY vs Redis Streams vs
  NATS JetStream). No code yet — RFC first, then a single-leader local
  prototype before any distributed deployment.
- **Phase 7 (physical 47→8 domain merge)** next slice: pick ONE owner
  domain from `project_docs/docs/MODULE_OWNERS.md`
  (recommend `interfaces` — smallest blast radius), move only that
  domain's files under the new path, update all imports, ensure CI green.
  Then evaluate whether to continue per-domain or roll back. Topology
  freeze (Phase 0) is what makes this safe.
- **Phase 8 (SMB vertical capabilities)** next slice: define the vertical
  capability template (config schema, agent prompt skeleton, tool
  allowlist, eval set) for ONE vertical (recommend HR onboarding —
  document-heavy, low compliance risk) before building all six.

## 2026-05-26 (stability roadmap: Phases 0/1/2-scaffold/4a/5/9)

### Phase 0 — Topology freeze
- Froze `backend/src/` top-level layout (47 dirs + 12 files) onto 8 target
  domains: runtime / agents / tools / harness / gateway / storage /
  governance / interfaces (with shared `utils` + `community`).
- Added `scripts/check_topology_freeze.py` + `.github/workflows/topology-freeze.yml`
  to fail any PR that adds a new top-level module under `backend/src/`.
- Documented the freeze in `project_docs/docs/TOPOLOGY_FREEZE_2026-05-26.md`
  and the 47-module → 8-domain ownership matrix in
  `project_docs/docs/MODULE_OWNERS.md`.

### Phase 1 — Single-source runtime configuration
- New endpoint `GET /api/runtime/effective-config` returns the live snapshot
  of all `OCTO_*` / `OCTOAGENT_*` environment variables, resolved ports,
  feature flags, and the configured default model.
- All credential-like environment values (`TOKEN`, `SECRET`, `PASSWORD`,
  `API_KEY`, `AUTH`, `PRIVATE`, `COOKIE` substring match) are masked as
  `xxx***yy (len=N)` before leaving the process.
- `octoagent config show` (and `octoagent config get KEY.PATH`) call the
  endpoint and pretty-print the response so operators no longer need to
  cross-reference five files to debug a misconfigured deployment.

### Phase 2 — Chat-turn state-machine scaffold
- Added `frontend/src/core/threads/chat-turn-reducer.ts` with the typed
  `ChatTurnState` / `ChatTurnAction` model and a pure `chatTurnReducer`
  function.
- **Scaffold only**: `hooks.ts` is NOT yet migrated. The reducer is unused
  until a follow-up session wires it behind a kill-switch env flag and runs
  the four-scenario regression matrix (plain text / attachment / disconnect+
  resume / first-turn retry).

### Phase 4a — Visual tool-trace viewer
- New endpoint `GET /api/runtime/tool-trace?limit=N` tails the runtime
  tool-trace JSONL stream (`workspace/runtime/observability/tool-trace.jsonl`)
  and returns up to N (default 200, cap 2000) most-recent events.
- New frontend page `/workspace/observability/trace` renders the events as a
  filterable / refresh-able table with color-coded `kind` badges and
  status tinting.

### Phase 5 — Cross-platform install + operator UX
- `scripts/install-octoagent.sh` now detects macOS (`uname -s = Darwin`) and
  routes dependency installation to Homebrew (`git`, `python@3.12`, `pnpm`,
  `node@22`, `nginx`, `postgresql@16`). Linux apt path unchanged.
- `scripts/octoagent` CLI gained three verbs:
  - `logs [--follow] [--lines N] [--component gateway|langgraph|frontend|nginx|service]`
  - `config show` / `config get KEY.PATH`
  - `desktop-shortcut install|uninstall`
- New `scripts/install-desktop-shortcut.sh`:
  - Linux: writes `~/.local/share/applications/octoagent.desktop`
    (+ `octoagent-stop.desktop`) and refreshes the desktop database.
  - macOS: writes `~/Applications/OctoAgent.app`
    (+ `OctoAgent Stop.app`) bundles with `Info.plist` + shell launcher and
    refreshes Launch Services.

### Phase 9 — Release housekeeping
- This CHANGELOG entry.

### Explicitly deferred (NOT delivered in this session)
- **Phase 3 — test suite rewrite**: existing 290 backend tests + frontend tsc
  remained green throughout; new endpoint surface tests deferred to a
  dedicated test-hardening session.
- **Phase 6 — distributed dispatcher**: leader election, worker registry,
  and durable queue need weeks of careful work; doing it half-implemented
  would create a production-fire hazard.
- **Phase 7 — physical module merge**: 47-module → 8-domain folder
  consolidation across 84K LoC must follow the Phase 0 owner matrix in
  controlled, per-domain PRs. Topology freeze gives this room to happen
  safely; the merge itself is not in this session.
- **Phase 8 — SMB vertical capabilities**: industry verticals (HR, finance,
  legal, ecommerce, etc.) are an independent product line.

### Verified
- `pytest backend/`: **290 passed in 13.06s**.
- `frontend/`: `tsc --noEmit` clean.
- `scripts/check_topology_freeze.py`: **OK (matches 2026-05-26 snapshot)**.
- `bash -n` clean on `octoagent`, `install-octoagent.sh`,
  `install-desktop-shortcut.sh`.
- `octoagent-local.service` restarts and `/api/runtime/effective-config`
  returns 200 with secrets masked.

## 2026-05-22 (runtime governance, cleanup, and repository sync)

### Governance
- Consolidated the 2号机 systemd startup path so `octoagent-local.service`
  delegates startup and shutdown to `scripts/start-octoagent.sh` only. Runtime
  ownership repairs that previously lived in systemd `ExecStartPre` and a
  drop-in are now performed by the repository launcher.
- Standardized runtime Python execution on the single backend venv at
  `backend/.venv/bin/python` via `OCTOAGENT_PYTHON_BIN`. LangGraph, Gateway,
  nginx config rendering, frontend build helper snippets, and backend module
  execution all share the same environment stack.
- Moved host helper scripts into the repository as
  `scripts/octoagent-monitor.sh` and `scripts/octoagent-cleanup.sh`, then
  removed stale `/usr/local/bin/octoagent-*` copies from the active host.

### Cleanup
- Added repository-scoped cleanup for `.pytest_cache`, `.ruff_cache`,
  `__pycache__`, pyc/tmp/bak files, and `tmp/` contents without deleting
  required dependency/runtime stores such as `backend/.venv`,
  `frontend/node_modules`, or production `.next` build assets.
- Cleaned stale `/tmp/octoagent*`, probe, smoke, and assistant verification
  files from the 2号机 host.

### Version
- Bumped backend version to `2026.5.22` and frontend version to `20260522`.

## 2026-05-20 (#3 — permission UX, trace, lifecycle, and I/O governance)

### Bug fixes
- `frontend/src/components/workspace/input-box.tsx` — Queued follow-up text can
  now be removed after a message is already sent and waiting in the append
  queue. The queued message row has an explicit remove button.
- `backend/src/model_auth/service.py` — Updated the local provider template for
  2号机 port `8000` from the stale Gemma placeholder to the live
  `qwen3.6-35b-a3b-q8-mm-prod` OpenAI-compatible model.

### Permission governance
- Added the operator-facing three-level permission model:
  `approval` (default approval), `directory` (directory-level system
  operations), and `system` (system-level operations).
- The chat input toolbar now exposes the permission selector next to the other
  run controls. Thread context, query planning, task workspace defaults, and
  lead-agent tool loading all normalize legacy `workspace`/`yolo` values into
  the new model.
- System-scoped built-in tools are hidden unless `system` mode is selected;
  directory-scoped tools remain visible but are marked confirmation-required in
  `approval` mode.

### Observability and runtime lifecycle
- Added `backend/src/observability/tool_trace.py`, a JSONL trace sink under
  `workspace/runtime/observability/tool-trace.jsonl` for tool, subprocess,
  sandbox, provisioner HTTP, and recovery exception events.
- Added `backend/src/artifact_lifecycle.py` and wired it into the runtime
  maintenance scheduler. It prunes old transient artifacts/cache/uploads,
  rotates the tool trace, and calls `gc.collect()` during maintenance.
- Replaced selected silent `except Exception: pass` paths in task workspace,
  workflow archive, RAG fallback, sandbox, InfoQuest, and system-update code
  with warning logs and/or trace records.

### I/O and shell surface
- Wrapped blocking subprocess, container runtime, provisioner HTTP, InfoQuest,
  and system-operation paths in existing `RuntimeWorkerIsolationService` slots
  so long-running or blocking work is pushed to explicit runtime boundaries.
- Added trace events around `host_shell`, system command helpers, Codex CLI,
  local sandbox commands, aio sandbox container management, and update-service
  git/process calls.

### Quality gates
- Added permission-mode regression coverage for system-tool filtering.
- Backend validation: `ruff check src tests` passes, `pytest -q` reports
  `196 passed`.
- Frontend validation: `tsc --noEmit` and `next build` pass.

## 2026-05-20 (#2 — P0/P2 audit hardening + bounded agent runs)

### Bug fixes
- `backend/src/sandbox/local/local_sandbox.py` — Added the explicit `asyncio`
  import required by `LocalSandbox.execute_command()` and removed the stale
  `subprocess` import. The previous code only worked accidentally through
  import-chain side effects.
- `backend/src/community/infoquest/infoquest_client.py` — Added the missing
  `requests` import for the synchronous InfoQuest search path and removed an
  unused `asyncio` import.
- `backend/src/gateway/routers/channels.py` — Fixed missing
  `get_channel_service()` references in channel logout/config deletion paths.
  These endpoints could previously fail with `NameError`.
- `backend/tests/agents/test_progress_stall_middleware.py` — Updated stale
  expectations from uppercase `"END"` to LangChain's lowercase `"end"` jump
  literal and fixed the import path from `backend.src...` to `src...`.
- `backend/tests/unit/agents/test_progress_stall_middleware.py` was renamed to
  `backend/tests/unit/agents/test_progress_stall_unit_behavior.py` to remove a
  pytest import-file mismatch with the higher-level ProgressStall test module.

### Reliability / performance
- `backend/src/agents/resource_profile.py` — Replaced million-level recursion
  defaults with bounded single-run ceilings by tier (`120/200/300/500`,
  workspace up to `1000`). Hardware tier now increases capacity without letting
  one stuck agent run consume unbounded turns.
- `backend/src/tools/catalog.py` — Added operator-controlled system-tool
  gating:
  - `OCTOAGENT_SYSTEM_TOOLS_ENABLED=0` disables host-level system tools.
  - `OCTOAGENT_SYSTEM_TOOLS=host_shell,process_manage` narrows the system tool
    surface to an explicit allow-list.
  Default behavior remains backwards-compatible.
- `.gitignore` — Added `.ruff_cache/` and `.mypy_cache/` so local verification
  caches do not pollute the repository.

### Quality gates
- Cleaned ruff baseline across `backend/src` and `backend/tests`.
- Added regression tests for bounded recursion defaults and system-tool
  gating/allow-list behavior.
- Final backend validation: `ruff check src tests` passes, `pytest -q` reports
  `194 passed`.
- Frontend validation: `tsc --noEmit` and `next build` pass.

## 2026-05-20 (host_shell loop hard-stop + tool-call command visibility)

### Bug fixes
- `backend/src/agents/middlewares/progress_stall_middleware.py` — The
  ProgressStall safety net (introduced 2026-05-19) was logging
  `safety_net=True` but the run kept looping. Two silent bugs were stacked:
  - `before_model` / `abefore_model` were missing
    `@hook_config(can_jump_to=["end"])`. Without that decorator the
    LangChain agent factory does not wire a conditional END edge from the
    middleware, so any returned `{"jump_to": ...}` is dropped.
  - The hard-stop branch returned uppercase `"END"`, but
    `JumpTo = Literal["tools", "model", "end"]` is matched with `==`, so
    `"END"` never resolved to the end node.
  Combined, this meant the only thing that could break a pathological loop
  was the operator clicking Stop. Now both hooks declare
  `can_jump_to=["end"]` and emit lowercase `"end"`, so once the same
  tool-call signature is repeated past `OCTO_PROGRESS_STALL_SAFETY_NET_DUP`
  (default 12) the run actually terminates.

### UX
- `frontend/src/components/workspace/messages/message-group.tsx`,
  `frontend/src/core/tools/utils.ts` — The chat UI now surfaces the actual
  command for the whole shell-family of tools (`bash`, `host_shell`,
  `glob`, `grep`, `lsp`) instead of only `bash`. Previously `host_shell`
  fell through to the generic "Using host_shell" label which completely
  hid what the agent was executing — the operator had to dig the command
  out of raw tool-call args. The `bash` branch additionally had an early
  `return string` (not JSX) bug when `description` was missing; that is
  now fixed and the command is shown even without a description. When
  `cwd` is set to a non-default directory it is rendered as a leading
  `# cwd: ...` comment in the code block.
- `backend/src/tools/builtins/system_ops_tools.py` — `host_shell_tool`
  now accepts an optional `description` argument so the model can hint
  at intent. The chat UI uses it as the step label when provided.

### Tests
- `backend/tests/agents/test_progress_stall_safety_net.py` (new, 2 cases):
  - Asserts `before_model.__can_jump_to__` and `abefore_model.__can_jump_to__`
    both contain `"end"`.
  - Asserts the module source contains lowercase `"jump_to": "end"` and
    not the broken uppercase form.


# Changelog
## 2026-05-19 (#2 — sandbox bash tool async fix + TodoList border colour)

- **Sandbox bash/glob/grep/lsp tools**: stopped the silent agent stall where a
  run consumed ~135 turns and 19+ minutes without making real progress before
  LangGraph's recursion ceiling closed it (the user saw it as "agent stops for
  no reason"). Root cause: `bash_tool` in `backend/src/sandbox/tools.py` and
  the `_run_shell` helper in `backend/src/tools/builtins/openharness_compat_tools.py`
  (driving `glob`, `grep`, `lsp`) were sync `def` functions returning
  `sandbox.execute_command(command)` — but `LocalSandbox.execute_command` is
  async, so each call leaked an unawaited coroutine. The smoking-gun line
  `RuntimeWarning: coroutine 'LocalSandbox.execute_command' was never awaited`
  fired on every tool tick, and the model kept seeing
  `<coroutine object ...>` strings as tool output and retried forever. Fix:
  converted `bash_tool`, `_run_shell`, `glob_tool`, `grep_tool`, and `lsp_tool`
  to `async def` and `await sandbox.execute_command(...)`, so LangChain's
  `@tool` decorator populates the `coroutine` slot and ToolNode's `ainvoke`
  path uses the real async backend. Added
  `backend/tests/tools/test_sandbox_async_tools.py` (4 parametrised cases) to
  guard the regression — verifies every affected tool exposes a coroutine
  function in its `.coroutine` slot.
- **TodoList panel border colour**: the previous fix on this same date
  weakened the outer outline to `border-border/40` and added `backdrop-blur-sm`,
  but the reference `SubtaskCard` ("执行步骤框") uses the full-strength
  `border` token with no blur. The TodoList now matches that recipe exactly
  (`border` + `bg-background/95` + `rounded-t-lg` + `border-b-0`, no
  backdrop-blur) so its visible top/left/right edges look identical to the
  inline execution-step cards inside the chat thread.
- **GoalDriftMiddleware verified, not changed**: drift warnings at
  `turn=120/125/130/135 score=0.400 threshold=0.45` were a *symptom*, not a
  separate bug. The comparison `score < threshold` ⇒ drift is correct (cosine
  similarity below threshold means actions diverged from the goal). The
  warnings only fired because the broken bash tool meant the model was
  producing nonsense responses; with the tool fix they will stop on their own.
- Verified on `192.168.110.2`: `octoagent-local.service` active, nginx 19880
  returns 200 for `/`, frontend 19886 / langgraph 19884 / gateway 19882 all
  listening, fresh `langgraph.log` has zero "coroutine ... was never awaited"
  warnings. Targeted tests pass: `pytest tests/tools/test_sandbox_async_tools.py
  -v` ⇒ 4/4 green, `ruff check backend/src/sandbox/tools.py
  backend/src/tools/builtins/openharness_compat_tools.py` ⇒ clean.

## 2026-05-19 (UI polish + agent-loop safety net)

- **TodoList panel border**: the dockable to-dos panel above the chat input now uses the same hairline frame as the inline subtask 执行步骤框 cards (`border-border/40` + `rounded-t-lg` + `bg-background/95` + `bg-muted/60` header). It previously rendered a heavier visual frame because it used the full-strength `border` token, an opaque `bg-white` surface, `rounded-t-xl`, and an `bg-accent` header band, making the outer outline look thicker than every other surface in the chat thread.
- **progress_stall_middleware**: fixed an infinite agent loop where the same tool call (typically `write_todos`) was re-issued 90+ times in a single human turn. Root cause: the soft-recovery branch had no per-signature throttle (it counted the wrong marker), so a soft `<progress_stall_recovery>` system message was injected on every `before_model` tick once `dup_count >= _HARD_STOP_DUP`; meanwhile the hard-stop branch was gated behind `OCTO_PROGRESS_STALL_HARD_STOP_ENABLED` which defaulted to off, so the only way out was the user pressing Stop in the UI. Fix: (a) soft escalation now counts existing `_SOFT_ESCALATION_MARKER` messages by stable stall-signature prefix and refuses to inject more than `OCTO_PROGRESS_STALL_MAX_SOFT_PER_SIG` (default 2) per signature; (b) a new unconditional ceiling `OCTO_PROGRESS_STALL_SAFETY_NET_DUP` (default 12) forces `jump_to: END` with a terminal `<progress_stall_terminal>` message regardless of the env flag, breaking the loop automatically; (c) the soft-escalation system message now embeds the stall signature so the throttle can match it. New regression tests live in `backend/tests/agents/test_progress_stall_middleware.py` (5 cases, all green).


## 2026-05-14 (cleanup)

- Removed all live Firecrawl references from the codebase: `firecrawl-py`
  Python dependency dropped from `backend/pyproject.toml`, `requirements.txt`,
  and `backend/uv.lock`; `FIRECRAWL_API_KEY` removed from `.env.example` and
  `README.md` readiness notes; the `firecrawl` MCP entry removed from
  `extensions_config.example.json`; the Firecrawl preset card, helper, and
  env placeholder removed from `frontend/src/app/workspace/config/mcp/page.tsx`;
  the dangling `backend/src/community/_legacy_firecrawl.2026-05-14/tools.py`
  index entry purged; project_docs descriptions updated to drop Firecrawl
  mentions (catalog example switched to Tavily). Historical reports under
  `project_docs/docs/P*` keep their original wording.

## 2026-05-14

- Stood up a coherent **Execute → Check → Continue-or-Correct** agent workflow with three layered middlewares: `CriticMiddleware` (contract drift), the new `StepReflectionMiddleware` (cadence checkpoint every 3 tool batches, injects `<step_review>` forcing SUCCESS/PARTIAL/FAILED classification + branched next step), and `ProgressStallMiddleware` (Reflexion-style stall escape on duplicate calls / redundant outputs).
- Eliminated the 1,357-step "cleanup report" loop on thread `8f85b6de`: disambiguated `local_sandbox.execute_command` empty-output return value, added stable duplicate-tool-call dispatch guard in `ToolBudgetMiddleware` (`OCTO_TOOL_DUPLICATE_LIMIT=4`), and added Claude-Code style identical-tool-message coalescing in `SessionCompactionMiddleware` so the summariser never reprocesses duplicate output.
- Added scroll-up auto-expand to the chat message list (`message-list.tsx`): bumps the history window by 90 groups when `scrollTop < 240px` with anchor preservation, matching the Slack / VS Code chat virtualisation pattern.
- Verified on host 192.168.110.2: `octoagent-local.service` active, `/api/langgraph/ok=200`, `/=307`; targeted tests pass 8/8 (`test_step_reflection_middleware.py`), 6/6 (`test_progress_stall_middleware.py`), 19/19 (`test_tool_recovery_middleware.py`).
- See `project_docs/docs/AGENT_SELF_ITERATION_2026-05-14.md` for the full design, env knobs, and pattern references (Reflexion, Self-Refine, Plan-Reflect-Act, Cursor coalescing).

## 2026-05-11

- Completed full system repair and verification pass covering model fallback, subagent/workflow wiring, tool recovery, SSRF-safe web fetch behavior, sidebar hydration, stale Next chunk recovery, CLI entrypoint behavior, WebUI smoke reliability, and New Agent form accessibility.
- Added safe `--help` behavior for smoke scripts that previously initialized runtime work or printed no usage, and wired `make smoke-operator-module-closure` to its real backend smoke script.
- Verified backend compile/lint/tests, frontend lint/typecheck/build, release-readiness contract, system-execution security smoke, operator-module closure smoke, mock/real WebUI smoke, management route smoke, route-level accessibility checks, 320px reflow, and forced-colors mode.
- See `project_docs/docs/P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md` for the detailed report and validation matrix.

## 2026-05-08

- Fixed new-conversation first-message bug: the first message sent in a new chat received no reply and appeared as conversation history when a second message was sent. Root cause was Next.js App Router intercepting `history.replaceState()` and updating `useParams()`, causing `rawThreadId` to flip from `"new"` to the real UUID. This triggered `shouldVerifyExistingThread=true`, unmounting `ChatThreadView` and killing the live SSE stream. Fixed by adding a `justActivatedThreadIdRef` guard in `ChatPage` that gates the blocking thread verification for threads that were just locally created rather than navigated to externally (`frontend/src/app/workspace/chats/[thread_id]/page.tsx`).

## 2026-04-25

- Completed P0 thread recovery: stale LangGraph thread submit failures now retry once in a fresh thread instead of surfacing as an internal error.
- Cleaned repository state: removed tracked backend tests, frontend e2e tests, snapshots, test-only helper prompts, duplicate imported docs, archived stage reports, demo output copies, and transient root reports.
- Consolidated active documentation around `README.md`, `project_docs/README.md`, `project_docs/docs/PROJECT_STATUS.md`, `project_docs/docs/PROJECT_PROGRESS.md`, and `project_docs/docs/P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md`.
- Updated CI, live validation, optimization scorecard, and release precheck gates to use compile, lint, typecheck, build, and smoke validation rather than deleted test trees.
