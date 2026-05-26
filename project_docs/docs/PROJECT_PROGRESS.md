# OctoAgent 项目进度与计划

> Last updated: 2026-05-15

## 当前目标

在保持现有 WebUI 与现有 API 兼容形状的前提下，继续收口运行时真相、operator 产品面、HookCore / CapabilityCore 边界、doctor/API contract smoke，以及长时间任务的上下文、检查点和资源回收闭环。

## 当前已完成

- 运行时真相已经收敛为 Next.js WebUI -> FastAPI gateway -> LangGraph runtime。
- 默认 workflow 生命周期真相已经收敛为 `task_workspaces` 与 `workflow_core` 投影；`/api/studio/*` 不再是默认产品面。
- `distributed_execution`、`monitoring`、`reflection`、`self_evolution` 已在 system settings overview 中获得最小 operator 面板，并直接复用既有 API。
- opt-in live tests 已拆分为独立的 manual/nightly workflow，不再继续污染默认 CI lane。
- 本地端口/入口链已支持 `OCTO_PUBLIC_BASE_URL`，可将统一入口迁移到外部可访问端口，例如 `11980`。
- 活跃文档已经继续压缩，当前状态、下一步、operator 状态和 handoff 文档都已回到“当前真相优先”的写法。
- Frontend lint debt has been cleared, so `pnpm lint` is now a usable hard gate again.
- `/api/runtime/doctor` now validates capability registry, capability binding contract, channels, runtime provider contract, and host memory status.
- `backend/scripts/run_system_doctor.py` now provides a repeatable local doctor/API contract smoke.
- Capability binding contract now has an auditable operator policy layer with `inherit`, `allow`, `deny`, and `audit_only` decisions.
- The oversized task workspace unified card has been partially split into transcript, inspector primitive, and status helper modules.
- Sieve host mihomo has been switched to persistent TUN mode through systemd.
- LangGraph thread/run/checkpoint contract ledger has been added at the OctoAgent runtime boundary.
- Checkpoint prune/copy/delete semantics now exist through `/api/runtime/langgraph-contract/*`.
- QueryEngine now has session maintenance, active-turn compaction budgets, and stale-session recovery.
- Runtime doctor now reports disk, worker queue, LangGraph contract, and event-loop latency checks.
- Blocking model/browser/system/research paths now pass through worker isolation counters and concurrency limits.
- Capability operator policy has a WebUI governance panel with per-capability decisions and audit history.
- The backend environment stack is aligned on `langgraph-api==0.8.1`, `langgraph-runtime-inmem==0.28.0`, OpenTelemetry `1.41.1`, `protobuf==6.33.6`, and `pydantic==2.13.3`.
- Runtime maintenance now starts with the gateway lifespan and exposes status/manual-run APIs.
- Runtime Health now has a WebUI settings page with alerts, worker isolation, LangGraph contract, and maintenance controls.
- `uv.lock` is refreshed and lock verification is bounded with `timeout 600s uv lock --locked`.
- Workflow/LangGraph contract smoke now covers remote thread creation plus pause/resume/cancel/replay/terminate lifecycle audit.
- Long-running soak now records memory, disk, process count, event-loop latency, worker queue, checkpoints, active runs, and final stability.
- Runtime Health alerts now surface through the top status bar and browser notification hook.
- QueryEngine now exposes summary quality evaluation, stale session recovery, and replay context.
- Capability operator policy now has release precheck plus WebUI import/export.
- Multi-tenant now has an operator governance surface with tenant registration, policy application, limit probe, and audit events.
- Multi-tenant registry is now persisted, exported, and bound into workspace/query/capability policy metadata.
- Distributed execution now has real HTTP remote worker dispatch, dispatch history, and live gateway remote-dispatch smoke coverage.
- `make operator-release` is the fixed release command, and CI runs it through the `release-precheck` job.
- QueryEngine replay golden now validates tenant continuity, semantic compaction quality, stale recovery, and replay context.
- Real LangGraph remote lifecycle E2E now creates an actual remote thread/run id, validates remote cancel/replay/delete behavior, and records recoverable terminate errors after cancel.
- Chat stability hardening now covers ordinary tool history, `web_search -> web_fetch/read_webpage`, multi-turn continuation, and context guard visibility in a real browser.
- SQLite checkpointer maintenance hooks are available directly on the async saver wrapper and expose operation counters.
- Runtime permission repair runs during gateway startup, and local nginx writes temp files inside repository-owned `tmp/nginx/*`.
- Right-side Artifact/execution panel desktop and mobile screenshots are produced by chat regression and uploaded by CI.
- Long-chat browser pressure now records 520-message scroll timing to `backend/reports/chat-regression-trends.jsonl`.
- Chat regression trends now have a readable threshold report via `make chat-regression-report`.
- 2h/8h/24h soak profiles are started through `make soak-baseline-suite`, with a 10-minute monitor loop writing `workspace/runtime/soak_reports/soak-monitor.{md,json}`.
- Distributed execution now prefers healthy independent worker daemons over gateway-local fallback.
- Dangerous operator deletes now require explicit confirmation headers.
- Operator Surfaces now has E2E coverage for governance summary, dispatch history, and destructive-action confirmation headers.
- Independent execution worker deployment materials now include a systemd unit, environment template, and production runbook.
- Release readiness now has a repeatable evidence gate via `backend/scripts/run_release_readiness.py` and `make release-readiness`; it scores the remaining 8 production-readiness modules against live doctor evidence, governance settings, run-record artifacts, chat trend evidence, and soak monitor artifacts.
- Release readiness now accepts an external evidence manifest for staging/soak/signed-audit artifacts and has a contract smoke at `backend/scripts/run_release_readiness_contract_smoke.py`.
- System-execution mutating and CLI routes now enforce operator/admin headers when `OCTO_OPERATOR_TOKEN` is configured, with coverage in `backend/scripts/run_system_execution_security_smoke.py`.
- P14 closes the operator-substrate module contract across `capability_core`, `hook_core`, `distributed_execution`, `multi_tenant`, `monitoring`, `reflection`, `self_evolution`, and `operator_governance`; `make operator-release` now runs `backend/scripts/run_operator_module_closure_smoke.py`.
- P18 completed the 2026-05-11 full repair pass: model fallback, subagent/workflow wiring, tool recovery, SSRF-safe web fetch redirects, sidebar hydration, stale Next chunk recovery, CLI smoke help, Makefile smoke target wiring, WebUI smoke timeout recovery, management smoke help, and `/workspace/agents/new` accessibility are all repaired and verified.
- Chat continuation now follows an in-place hidden-context handoff: context-pressure and `continue_from` flows no longer navigate to a new page, auto-submit a visible bootstrap prompt, or pre-write LangGraph state before the first run.
- `ContinuationMiddleware` now injects continuation context only into the model request as a hidden `SystemMessage`, preserving the user's visible message and persisted thread state without `<continue_context>` leakage.
- Lead-agent tool budgeting no longer applies an initialized hard cap to successful tool messages. Runtime or long-term system memory can provide a soft tool-use review budget, which is injected as hidden advisory guidance without clearing pending tool calls or forcing a premature final answer.
- Long-task caps have been loosened where they were arbitrary: Codex CLI no longer clamps explicit timeouts to 900 seconds, subagent explicit `max_turns` is no longer capped at 500, and task-workspace execution retry budgets no longer clamp auto-iteration to 10 attempts.
- Chat continuation UI now exposes the unified handoff marker as `[system：session is compressing and continuing to act]` so operators can distinguish system continuation from user-authored messages without angle-bracket system text.
- The top context token lamp now treats hidden continuation payloads as a completed handoff, so a continued chat starts its visible count from the new thread content while keeping the hidden model context available for the first turn.
- Continued chat welcome now shows the system handoff marker even while the source-thread summary is unavailable, including mock and freshly allocated thread routes.
- Chat streaming now auto-continues once when the assistant final message is an unfinished action announcement such as "现在让我检查...：". Skill-evolution run records also distinguish real tool errors from harmless log text and mark unfinished action endings as failed evidence.
- WebUI smoke now recovers when `settings=bootstrap` is temporarily intercepted by the setup wizard, completing setup and reopening the bootstrap settings deep link before asserting content.
- The 2026-05-12 20:10+ no-reason-stop incident was traced to local nginx returning 500 before LangGraph because large `/api/langgraph/*/runs/stream` POST bodies could not be written to the worker temp directory. Local startup now prepares repo-owned nginx temp directories with worker-writable sticky permissions, and LangGraph proxying disables request buffering with an explicit 128M body limit.
- Long-context continuation now carries a single context-cycle identity from WebUI hidden continuation context into backend runtime, JSON memory provenance, and SimpleMem/SystemRAG metadata. The visible token lamp uses cycle-relative tokens, so each compression/continuation cycle restarts the line from 0 and grows toward the next threshold.
- Memory extraction now records compression/continuation provenance on new facts through `sourceMetadata`, while SimpleMem/SystemRAG entries merge the same metadata into their vector-store record metadata.
- The context token lamp no longer renders a full-width rail at zero usage. It now exposes the model-derived 90% threshold token count, grows from 0 to 90% of the input top edge, prepares hidden continuation handoff at threshold, and resets the visible cycle only when that handoff is submitted.
- Chat stream supervision now verifies submitted continuation handoff metadata (`context_cycle_id` and `context_cycle_base_tokens`) against fresh persisted runtime state after stream completion. Mock streams skip backend runtime verification, and delayed confirmation is treated as a warning instead of a runtime-error overlay.
- The `767551ff-39c7-4042-bdd2-34baf5755e02` no-reason-stop incident was traced to semantic misclassification: the assistant ended with a sentence-form action announcement (`我来...首先，让我探索...。`) and no completion evidence, while the old detector only caught colon-ended variants. Frontend auto-continue and backend skill-evolution trace detection now cover this pattern.
- Continuation handoff now includes active task todos in addition to recent messages and workflows. `ContinuationMiddleware` injects the todo state as hidden task-memory context, aligning the implementation with the existing todo/planning primitives instead of creating a separate task-memory system.
- The token lamp visual has been simplified to the requested wall-wash effect: only the primary indirect light and a small progress core remain, while the previous bright line, spark, wake, stream, and separate halo semantics have been removed.
- XML-ish model output such as `<tool_call><function=bash><parameter=command>...</parameter></function></tool_call>` is now normalized into real LangChain `tool_calls` in the model semantic layer and again in `DanglingToolCallMiddleware`, so new responses can enter the tool scheduler instead of being shown as simulated tool-call text.
- Historical chats polluted with raw XML-ish assistant tool-call text are repaired before the next model call by converting those assistant messages into structured tool calls and inserting interrupted `ToolMessage` placeholders, preventing provider errors such as `Cannot have 2 or more assistant messages at the end of the list`.
- Skill-evolution run records now treat visible runtime model errors, including `NormalizedModelError`, as failed evidence instead of completed runs.
- Dangling assistant tails are now repaired before provider submission. If a persisted thread ends with multiple assistant messages, or with a visible runtime/model error assistant message, `DanglingToolCallMiddleware` replaces that invalid tail with a system repair note plus a human continuation request. This prevents repeated provider 400 loops on already-polluted histories.
- Session compaction now has a final token-budget guard after summary rebuild. Oversized messages are truncated before every model call, and rebuilt compacted histories are trimmed to the active model budget before they reach the provider.
- The token lamp now resets on first-turn threshold submission as well as existing-thread continuation. New-thread threshold detection records the cycle base before submit, while existing chats still attach the full hidden continuation source.
- The token lamp now only computes progress from the currently selected model's `max_context_tokens`. The previous fixed frontend fallback is gone; if the selected model has no context-window value, the lamp waits instead of pretending a 128k window.
- Recent chat titles now load thread `values` in the sidebar and no longer synthesize `Chat <id>` when a title is missing. Title generation also rejects placeholder model outputs such as `Chat 1234abcd` and falls back to the first user message.
- Lead-agent session compaction and model factory context trimming now use the selected model's configured `max_context_tokens` instead of fixed fallback ceilings. Each fallback candidate is trimmed against its own context window before provider submission.
- Host memory guard state is now separate from context-window trimming. Context compaction/truncation writes `context_guard_state` and `recommended_memory_action`, while `memory_guard_state` remains reserved for actual host memory pressure so the WebUI no longer shows context trimming as an `内存守护` failure.
- Web page extraction now strips common GitHub page chrome such as sponsor prompts, search pro-tips, hydration snippets, and action-restriction banners before the text enters model context. Extracted page content is capped to a compact envelope with an explicit shortening note.
- Local nginx request-body temp paths now render under `/tmp/octoagent-nginx-<port>` and `/api/query-engine/plan-operation` disables request buffering, preventing `client_body` permission failures when workers run as `nobody` under a private home directory.
- Long-running work now has a persisted `task_state` separate from raw chat messages. `TaskStateMiddleware` captures the active goal, current step, evidence, failed attempts, and next action, then injects a compact hidden checkpoint before the agent so compaction or resume markers continue execution instead of ending the task.
- Session compaction, continuation context, run records, skill-evolution failure records, frontend telemetry, and frontend auto-continue now all carry the same task-state and recoverable-failure markers. A failed final evaluation or unfinished action announcement can therefore trigger one automatic continuation from persisted state rather than requiring the user to re-prompt.
- `read_webpage` now has a semantic quality gate in addition to text cleanup. GitHub/login/page-chrome dominated extraction returns a recoverable tool error, which lets tool-budget recovery switch source instead of polluting context with sponsor prompts, hydration snippets, or action-restriction banners.
- The WebUI runtime summary now shows context-window trimming as a separate context-guard item while keeping host `内存守护` status independent, matching the backend `context_guard_state` split.
- P21 repaired the latest long-context historical conversation failure by
  bounding runtime system-message preservation and adding a hard context retry
  cap in the model factory.
- P21 repaired daemon identity/permission drift: runtime identity now resolves
  `sieve-pub` from the effective POSIX UID, and permission repair targets the
  actual runtime UID/GID instead of stale sudo environment values.
- P21 cleared the backend Ruff/PEP8 baseline across the Python tree, added
  runtime-state ignore rules for `backend/runtime/` and `workspace/self_evolution/`,
  and configured Google provider credentials through ignored local `.env`.

## Current Verification

- Local release readiness evidence: `backend/.venv/bin/python backend/scripts/run_release_readiness.py --json --run-doctor --min-score 0` passed and generated `workspace/runtime/release_readiness/release-readiness.{json,md}` with an evidence score of 81.5 / 100 on 2026-05-06. The gate intentionally reports `ok=false` for the 95 target until fresh staging chat, soak, signed audit, chat trend, run-record, rollback, retention, and regression bundle evidence exist.
- Backend release readiness compile: `backend/.venv/bin/python -m compileall -q backend/scripts/run_release_readiness.py` passed.
- Backend release readiness lint: `backend/.venv/bin/python -m ruff check backend/scripts/run_release_readiness.py` passed.
- Backend release readiness contract: `cd backend && .venv/bin/python scripts/run_release_readiness_contract_smoke.py` passed.
- Backend system-execution security: `cd backend && .venv/bin/python scripts/run_system_execution_security_smoke.py` passed.
- Operator module closure: `cd backend && .venv/bin/python scripts/run_operator_module_closure_smoke.py --json` passed with 8/8 module checks.
- Operator release: `CI=true make operator-release` passed with 16/16 steps after adding operator module closure smoke to the existing system-execution auth, release-readiness manifest contract, Tools Hub, backend, and frontend gates.
- Backend: `backend/.venv/bin/python -m compileall -q backend/src backend/scripts` passed.
- Backend: `cd backend && .venv/bin/python -m ruff check src scripts` passed.
- Backend: `backend/scripts/run_system_doctor.py --skip-git` passed.
- Backend: `backend/.venv/bin/python -m pip check` passed.
- Frontend: `pnpm lint` passed.
- Frontend: `pnpm typecheck` passed.
- Frontend: `pnpm build` passed.
- Backend focused regression: `cd backend && .venv/bin/python -m pytest tests/agents/test_session_compaction_middleware.py tests/agents/test_title_middleware.py tests/agents/test_lead_agent_runtime.py tests/models/test_model_fallback.py -q` passed with 13 tests.
- Backend focused lint: `cd backend && .venv/bin/python -m ruff check src/agents/thread_state.py src/agents/middlewares/session_compaction_middleware.py tests/agents/test_session_compaction_middleware.py scripts/run_chat_regression_e2e.py` passed.
- Frontend focused verification: `cd frontend && pnpm typecheck && pnpm lint` passed after splitting memory guard and context guard telemetry.
- WebUI real-path verification on `http://127.0.0.1:19880`: a new chat sent through the browser showed `内存守护` as `ok`, did not show the old tool-output truncation warning, and produced no HTTP 4xx/5xx responses. Screenshot: `/tmp/octoagent-memory-guard-real-chat.png`.
- Backend focused regression: `cd /home/sieve-pub/public-workspace/octoagent/backend && .venv/bin/python -m pytest tests/agents/test_task_state_middleware.py tests/agents/test_session_compaction_middleware.py tests/agents/test_skill_evolution_trace.py tests/tools/test_web_reader_tool.py -q` passed with 20 tests after adding persisted task-state and low-quality webpage extraction coverage.
- Backend focused lint: `cd /home/sieve-pub/public-workspace/octoagent/backend && .venv/bin/python -m ruff check src/agents/middlewares/task_state_middleware.py src/agents/thread_state.py src/agents/middlewares/session_compaction_middleware.py src/agents/middlewares/continuation_middleware.py src/agent_core/run_records.py src/agents/middlewares/skill_evolution_middleware.py src/tools/builtins/web_reader_tool.py tests/agents/test_task_state_middleware.py tests/agents/test_session_compaction_middleware.py tests/tools/test_web_reader_tool.py` passed.
- Frontend focused verification: `cd /home/sieve-pub/public-workspace/octoagent/frontend && pnpm typecheck && pnpm lint` passed after adding task-state telemetry and the independent context-guard summary item.
- WebUI chat regression: `cd /home/sieve-pub/public-workspace/octoagent && backend/.venv/bin/python backend/scripts/run_chat_regression_e2e.py --frontend-url http://127.0.0.1:19880` passed on a real Chromium path, including continuation shell/history, context-guard notice visibility, web-tool history, and 520-message scroll stability.
- Final diff/API checks: `git diff --check` passed, and `/api/langgraph/threads/search` through nginx returned thread `values` successfully.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_skill_evolution_trace.py -q` passed with 3 tests.
- Backend: `cd backend && .venv/bin/python -m pytest tests -q` passed with 49 tests.
- Backend: `cd backend && .venv/bin/python -m pytest tests -q` passed with 51 tests after adding context-cycle memory provenance and runtime persistence coverage.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_memory_schema_repair.py tests/agents/test_session_compaction_middleware.py -q` passed with 9 tests.
- Backend lint: `cd backend && .venv/bin/python -m ruff check src/agents/middlewares/session_compaction_middleware.py src/agents/middlewares/continuation_middleware.py src/agents/middlewares/memory_middleware.py src/agents/memory/queue.py src/agents/memory/updater.py src/agents/memory/simplemem_bridge.py tests/agents/test_session_compaction_middleware.py tests/agents/test_memory_schema_repair.py` passed.
- Nginx config: `python3 scripts/render_nginx_config.py docker/nginx/nginx.local.conf.template tmp/nginx.local.conf && nginx -t -p /home/sieve-pub/public-workspace/octoagent -c tmp/nginx.local.conf` passed, and the rendered config contains the LangGraph request-buffering/body-size fix.
- Nginx large-body proxy smoke: a 2MB JSON POST to `/api/langgraph/threads/nonexistent/runs/stream` returned upstream JSON `400` instead of nginx HTML `500`, confirming the request reached the application layer.
- Shell syntax: `bash -n scripts/serve.sh scripts/start-daemon.sh` passed.
- Backend lint: `cd backend && .venv/bin/python -m ruff check src/agents/middlewares/skill_evolution_middleware.py tests/agents/test_skill_evolution_trace.py` passed.
- Backend lint: `cd backend && .venv/bin/python -m ruff check scripts/run_webui_smoke.py src/agents/middlewares/skill_evolution_middleware.py tests/agents/test_skill_evolution_trace.py` passed.
- Backend compile: `cd backend && .venv/bin/python -m compileall -q scripts/run_webui_smoke.py src/agents/middlewares/skill_evolution_middleware.py` passed.
- Frontend: `cd frontend && pnpm typecheck` passed.
- Frontend: `cd frontend && pnpm lint` passed.
- Frontend: `cd frontend && pnpm build` passed.
- Real WebUI smoke: `backend/.venv/bin/python backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed.
- Targeted WebUI check: a browser-created mock `continue_from` route showed `[system：session is compressing and continuing to act]`, `data-testid="context-token-lamp"`, `data-context-usage="0"`, and the forced-colors guard on the token lamp.
- Targeted WebUI check: a real browser created a mock chat, filled a 70k-character draft to cross the context threshold, and confirmed `data-testid="context-token-lamp"` returned to `data-context-usage="0"` with the forced-colors guard still present.
- Targeted WebUI check: a real browser verified token lamp progression on `http://127.0.0.1:19880`: new chat started at `data-context-usage="0"` with line width 0, the current model-derived 90% threshold was exposed as `data-context-threshold-tokens="11802"`, a 70k-character draft grew the line to 0.8999 of the input width, and submitting the threshold handoff reset line width to 0.
- Targeted WebUI check: after the reference-style token lamp update, a real browser verified line width 0 at new chat, 0.899987 of input width at threshold, endpoint spark opacity 1, reset to 0 after handoff submit, and zero `Context handoff verification failed` console entries.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_skill_evolution_trace.py -q` passed with 4 tests, including the `767551ff` sentence-ended unfinished action regression.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_continuation_middleware.py tests/agents/test_skill_evolution_trace.py -q` passed with 6 tests, including hidden todo handoff coverage.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_dangling_tool_call_middleware.py tests/models/test_semantics_tool_calls.py tests/agents/test_skill_evolution_trace.py -q` passed with 10 tests, covering XML-ish tool-call normalization, actual LangChain tool invocation through a fake agent, historical dangling repair, and runtime model error failure classification.
- Backend lint: `cd backend && .venv/bin/python -m ruff check src/models/semantics.py src/agents/middlewares/dangling_tool_call_middleware.py src/agents/middlewares/skill_evolution_middleware.py tests/agents/test_dangling_tool_call_middleware.py tests/models/test_semantics_tool_calls.py tests/agents/test_skill_evolution_trace.py` passed.
- Targeted WebUI check: after the wall-wash simplification, a real browser verified the token lamp has exactly two children, no legacy `line`, `spark`, `wake`, or `stream` classes, a 0.899987 width ratio at threshold, and both wall-wash/core opacity reset to 0 after submit.
- Targeted WebUI check: after unifying continuation wording, a real browser opened a mock `continue_from` route and confirmed `[system：session is compressing and continuing to act]` is visible while the legacy angle-bracket marker and context-guard leak text are absent, with zero console errors or failed requests.
- Targeted WebUI check: a real browser confirmed the token lamp threshold is model-derived: `qwen3.6-35b-a3b-mxfp4` reported `max_context_tokens=13114` and `data-context-threshold-tokens="11802"`, then switching to `nemotron-3-super-free` reported `max_context_tokens=262144` and `data-context-threshold-tokens="235929"`; no fixed 128k fallback was detected.
- Backend: `cd backend && .venv/bin/python -m pytest tests -q` passed with 52 tests.
- Frontend: `cd frontend && pnpm typecheck && pnpm lint && pnpm build` passed after the token lamp and handoff supervision changes.
- Real WebUI smoke: `backend/.venv/bin/python backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed after the token lamp and handoff supervision changes.
- Backend: `cd backend && .venv/bin/python -m pytest tests -q` passed with 60 tests after assistant-tail repair and final compaction budget trimming.
- Backend lint: `cd backend && .venv/bin/python -m ruff check src/agents/middlewares/dangling_tool_call_middleware.py src/agents/middlewares/session_compaction_middleware.py tests/agents/test_dangling_tool_call_middleware.py tests/agents/test_session_compaction_middleware.py` passed.
- Frontend: `cd frontend && pnpm typecheck && pnpm lint && pnpm build` passed after first-turn token cycle-base reset.
- Real WebUI smoke: `backend/.venv/bin/python backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 90 --mock` passed.
- Real non-mock WebUI tool check: a browser-created thread `640a5a0c-823c-453b-8b72-5ccc10d9c7a3` asked the model to run `bash` with `printf octoagent_tool_ok`; persisted state contained `ToolMessage(name="bash", content="octoagent_tool_ok")` and the final assistant answer `octoagent_tool_ok`, with no raw `<tool_call>`, `NormalizedModelError`, or consecutive-assistant provider error.
- Real browser token-lamp check: a new chat started at `data-context-usage="0"`, a 90k-character draft reached `data-context-width-percent="90.00"`, the decorative lamp had exactly two children and no legacy `line`, `spark`, `wake`, or `stream` classes, the model-derived threshold was `data-context-threshold-tokens="11802"`, and submit reset width and opacity to zero. Screenshot evidence was saved to `/tmp/octoagent-token-lamp-wallwash.png`.
- Diff and editor diagnostics: `git diff --check` produced no output, and VS Code diagnostics reported no errors for the touched backend, frontend, and test files.
- Backend: `cd backend && .venv/bin/python -m ruff check src/agents/middlewares/continuation_middleware.py tests/agents/test_continuation_middleware.py` passed.
- Backend: `cd backend && .venv/bin/python -m pytest tests -q` passed with 44 tests.
- Backend: `cd backend && .venv/bin/python -m pytest tests/agents/test_tool_recovery_middleware.py -q` passed with default no-hard-cap and runtime soft-budget coverage.
- Backend: `cd backend && .venv/bin/python -m ruff check src/agents/middlewares/tool_budget_middleware.py src/tools/builtins/codex_cli_tool.py tests/agents/test_tool_recovery_middleware.py` passed.
- WebUI continuation: real Playwright run against `http://127.0.0.1:19880/workspace/chats/new?continue_from=...&auto_continue=1` confirmed no initial `/runs/stream`, no visible bootstrap prompt, successful first user turn, clean URL after activation, no `<continue_context>` in UI or persisted human messages, and no thread/run 400/500 responses.
- WebUI: `backend/scripts/run_webui_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed.
- Long-running soak: `backend/scripts/run_long_running_soak.py --iterations 40 --json` passed.
- Workflow/LangGraph contract smoke: `backend/scripts/run_workflow_langgraph_contract_smoke.py --json` passed.
- Release precheck: `backend/scripts/run_release_precheck.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --mock` passed.
- Operator release: `CI=true make operator-release` passed with 16/16 steps, including tenant persistence, distributed dispatch, Tools Hub registration, QueryEngine replay golden, bounded soak, system-execution auth smoke, release-readiness manifest contract smoke, operator module closure smoke, backend lint/compile, uv lock, frontend lint/build, and system doctor.
- Distributed remote dispatch: `backend/scripts/run_distributed_dispatch_smoke.py --gateway-url http://127.0.0.1:19880 --json` passed against the live gateway.
- LangGraph real remote lifecycle: `backend/scripts/run_langgraph_remote_lifecycle_e2e.py --base-url http://127.0.0.1:19884 --allow-cancel-recovery --json` passed with a real remote run id.
- Chat regression: `make smoke-chat-regression` passed with 520-message long-scroll pressure and right-panel desktop/mobile screenshots.
- Chat trend report: `make chat-regression-report` passed with max render 3085 ms under the 5000 ms threshold.
- Long soak: 2h profile completed with `ok=true`; 8h and 24h profiles are still running under 10-minute monitor loop as of 2026-04-29T12:38:54Z.
- Operator Surfaces E2E: `pnpm exec playwright test tests/operator-surfaces.e2e.spec.ts --reporter=line` passed locally.
- Real WebUI/API smoke: `SMOKE_TIMEOUT_SECONDS=60 make smoke-real` passed with chat send, multi-turn send, continuation route, settings, and workflow task creation/cleanup.
- Focused frontend Playwright tests: `pnpm exec playwright test tests/runtime-telemetry.spec.ts tests/subtask-sync.spec.ts --reporter=line` passed.
- P18 backend full baseline: `cd backend && .venv/bin/python -m compileall -q src scripts && .venv/bin/ruff check src scripts && .venv/bin/python -m pytest` passed with 19 tests.
- P18 frontend full baseline: `cd frontend && pnpm lint && pnpm typecheck && pnpm build` passed.
- P18 CLI/smoke baseline: `make release-readiness-contract`, `make smoke-system-execution-security`, `make smoke-operator-module-closure`, `make smoke-mock SMOKE_TIMEOUT_SECONDS=90`, and `make smoke-real SMOKE_TIMEOUT_SECONDS=90` passed.
- P18 management smoke: `OCTO_AUTH_DEV_EXPOSE_CODES=1 backend/.venv/bin/python backend/scripts/run_management_menu_smoke.py --frontend-url http://127.0.0.1:19880 --gateway-url http://127.0.0.1:19880 --timeout-seconds 60 --json` passed with 14 API checks and 21 route checks.
- P18 browser accessibility sweep passed for hydration, stale chunk recovery script presence, skip link focus, accessible names, 320px reflow, and forced-colors mode.

## 当前仍在收口的点

- HookCore 仍需继续从“已接线”推进到更明确的事件所有权边界。
- CapabilityCore 已完成 active caller 收敛，并已具备可审计 operator policy 基线；下一步是做 WebUI 策略治理面、导入导出和策略变更审计。
- `multi_tenant`、`distributed_execution`、`monitoring`、`reflection`、`self_evolution` 的 repository-level operator contract 已通过 P14 收口；剩余工作转为 staging/prod evidence：真实 auth-claim binding、生产 role mapping、signed audit export、rollback drill、外部 retention 和长 soak artifact。
- 当前本地证据门禁的主要阻塞项是 staging 真实对话证明、2h/8h/24h soak artifact、`OCTO_OPERATOR_AUDIT_SECRET`、chat regression trend summary、runtime run record artifact、移动端/可访问性截图和外部留存证明。

## 下一步计划

1. 继续保持 task-workspace lifecycle 和 public runtime projection 作为唯一默认 workflow 真相。
2. 使用 `make release-readiness` 作为 95 分发布前置门禁；staging/prod 可通过 `--evidence-manifest` 提供真实 artifact，但低于 `RELEASE_READINESS_MIN_SCORE=95` 不进入生产发布。
3. 将 chat regression 的趋势 JSONL 汇总成可读报告，给 520+ 长对话设置性能阈值趋势告警，并把 summary 纳入 release readiness evidence。
4. 运行真实 2h、8h、24h soak，并将报告保存到 `workspace/runtime/soak_reports/` 或 CI artifact。
5. 将 remote worker 从 gateway self-dispatch 推进到独立 daemon，补节点权限、容量治理和结果回传重试。
6. 接入 operator role、危险操作二次确认、secret redaction 和不可抵赖审计。
7. 继续精修 Runtime Health、tenant、distributed、policy 前端治理面，减少重复状态展示。
8. 建立生产部署、backup/restore、migration、observability dashboard 和回归矩阵。
9. 继续维持每个代码切片后的 lint + typecheck + build + doctor smoke + operator release + release readiness 验证闭环。

## P18 Full System Repair and Verification - 2026-05-11

P18 closes the latest local stability and accessibility repair lane. It standardizes CLI/smoke behavior, fixes WebUI smoke cold-compile timeout handling, confirms SSRF-safe web fetch behavior, prevents sidebar cookie hydration mismatch, adds stale chunk recovery, and repairs New Agent form accessible names.

Current local verification passed across backend compile/lint/tests, frontend lint/typecheck/build, release-readiness contract, system-execution security, operator module closure, mock and real WebUI smoke, management menu smoke, full route accessibility sweep, 320px reflow, and forced-colors mode.

See `P18_FULL_SYSTEM_REPAIR_AND_VERIFICATION_2026-05-11.md` for the detailed validation matrix.

## P15 Hermes Gemini WebUI And 95 Local Readiness - 2026-05-06

P15 configured the 2号机 WebUI/API default model from 3号机 Hermes metadata as `hermes-gemini-3.1-pro` using the Google Gemini native interface. The 2号机 daemon startup now loads local `.env`, preserves HTTP(S) proxy egress for model providers, and keeps SOCKS/FTP disabled for clients that reject SOCKS URLs. Local nginx `/api/` timeouts now cover long model fallback calls.

Live WebUI/API verification passed through `http://127.0.0.1:19880`: setup status, model metadata, module API probes, real dialogue suggestions, and real browser WebUI smoke all passed. Google currently returns `429 RESOURCE_EXHAUSTED` for `gemini-3.1-pro-preview` generation under the synced Hermes key, so OctoAgent correctly keeps Hermes Gemini as default and falls back to `qwen3.6-plus` for live dialogue.

Local active-runtime/module progress is above 95% for the checked WebUI -> Gateway -> LangGraph path. Strict production release readiness remains 81.5 / 100 until external staging/soak/audit/retention artifacts are supplied.

See `P15_HERMES_GEMINI_WEBUI_AND_95_LOCAL_READINESS_2026-05-06.md` for the detailed record.

## P14 Operator Module Closure - 2026-05-06

P14 closes the operator-substrate contract for the 8 previously active-closure modules. Mutating and export surfaces now consistently pass through operator/admin gates when `OCTO_OPERATOR_TOKEN` is configured, monitoring has a signed governance snapshot endpoint, and one smoke validates the whole module group.

Verification command:

```bash
cd backend && .venv/bin/python scripts/run_operator_module_closure_smoke.py --json
```

Result: `ok=true`, 8/8 module checks passed.

See `P14_OPERATOR_MODULE_CLOSURE_REPORT_2026-05-06.md` for the detailed closure record.

## P13 Release Readiness Audit Gate - 2026-05-06

P13 adds a strict release-readiness/audit evidence gate for the remaining production work. The gate converts the 8 module estimates into repeatable evidence checks and writes JSON/Markdown artifacts under `workspace/runtime/release_readiness/`.

Current local result:

- Overall evidence score: 80.5 / 100.
- Target score: 95 / 100.
- Live doctor/API contract evidence: executed and passed for the checked runtime surfaces.
- Hard blockers for a truthful 95+ claim: staging real conversation proof, 2h/8h/24h soak monitor evidence, signed operator audit secret, chat regression trend summary, runtime run-record artifact, mobile/accessibility screenshot proof, and external retention evidence.

This does not replace staging verification. It makes the missing staging and production-governance evidence explicit and blocks `make release-readiness` by default until the target score is met.

## P0 Closure - 2026-04-25

P0 is closed for the current main branch. The stale LangGraph thread submit failure is handled as a recoverable missing-thread condition, tracked tests and duplicate historical documents were removed, and repository validation now relies on compile/typecheck/build/smoke checks. See `P0_COMPLETION_AND_REPOSITORY_CLEANUP_REPORT.md` for the full closure record.

## P1-P5 Closure - 2026-04-25

P1-P5 is closed for the current delivery pass. The repository roadmap formally defines P1-P3 and does not define named P4/P5 phases, so P4 is treated as release governance and repository sync, while P5 is treated as full code assessment and next-plan closure.

Implemented closure items:

- CapabilityCore now includes channel capabilities in the unified registry.
- `/api/capabilities/binding-contract` now exposes normalized bindable targets, dispatch contracts, blockers, and audit metadata.
- Task-workspace frontend query keys are centralized in `frontend/src/core/task-workspaces/query-keys.ts`.
- Backend compile, capability contract construction, frontend typecheck, and frontend production build passed.

Known carryover:

- `pnpm lint` still fails on pre-existing frontend lint debt outside the files changed in this pass.
- Distributed execution, multi-tenant, reflection, monitoring, and self-evolution remain real but not fully product-complete; they need proof, audit, and UI hardening before promotion.

See `P1_P5_COMPLETION_AND_FULL_CODE_ASSESSMENT_REPORT.md` for the full assessment and next plan.

## P6 Operational Hardening - 2026-04-25

P6 is closed for the current delivery pass. It clears frontend lint debt, adds doctor/API contract smoke, partially splits the task workspace frontend surface, promotes capability binding into an auditable operator policy layer, validates the local stack, and switches sieve host mihomo to persistent TUN mode.

Known carryover:

- LangGraph runtime dependency should be upgraded after compatibility testing.
- The checkpointer must support prune/copy/delete semantics to keep long-running conversations sustainable.
- Blocking runtime work should be isolated away from the shared event loop.
- Provider-node health for mihomo should be monitored separately from local TUN service health.

See `P6_OPERATIONAL_HARDENING_AND_LONG_RUNNING_ASSESSMENT_2026-04-25.md` for the full validation record, assessment, and next work plan.

## P7 Long-Running Runtime Closure - 2026-04-25

P7 is closed for the current delivery pass. It adds the OctoAgent-side LangGraph workflow contract ledger, checkpoint prune/copy/delete APIs, query session maintenance and stale-session recovery, long-running doctor metrics, worker isolation counters/limits, capability policy WebUI governance, and a bounded soak test.

Known carryover:

- The new contract ledger is the OctoAgent operator control plane; the underlying LangGraph remote checkpointer still needs native prune/copy/delete support through upgrade or replacement.
- Soak validation currently proves the contract/maintenance layer with bounded simulation. A real multi-hour workflow soak is still required before production promotion.
- Runtime health metrics are available through API/doctor; a dedicated WebUI health panel and alert thresholds should come next.

See `P7_LONG_RUNNING_RUNTIME_CLOSURE_2026-04-25.md` for the full closure record.

## P8 Environment Stack and Runtime Health Closure - 2026-04-25

P8 is closed for the current delivery pass. It aligns the backend environment stack on LangGraph API 0.8.1, LangGraph in-memory runtime 0.28.0, OpenTelemetry 1.41.1, protobuf 6.33.6, and pydantic 2.13.3; starts runtime maintenance from gateway lifespan; adds maintenance APIs; exposes Runtime Health in WebUI settings; extends doctor/API smoke; and validates the stack with backend, frontend, doctor, and soak gates.

Known carryover:

- `uv.lock` still needs a dedicated refresh because the resolver hung during the LangGraph upgrade attempt.
- Real multi-hour workflow soak is still required before production promotion.
- LangGraph pause/resume/cancel/replay/terminate contract smoke should be added against remote threads/runs/checkpoints.

See `P8_ENVIRONMENT_STACK_AND_RUNTIME_HEALTH_CLOSURE_2026-04-25.md` for the full closure record.

## P9 Finalization Roadmap and Governance Closure - 2026-04-26

P9 is closed for the current delivery pass. It refreshes `uv.lock`, adds bounded lock verification, extends workflow/LangGraph lifecycle contract smoke, upgrades long-running soak sampling, connects Runtime Health alerts to the status bar and notification hook, improves QueryEngine recovery/replay/summary quality, adds capability policy release precheck and WebUI import/export, and promotes multi-tenant to an operator governance surface.

Known carryover:

- Real 2h/8h/24h soak reports should be run before production promotion.
- LangGraph remote lifecycle smoke should move from contract-level proof to real run-id cancellation/replay proof.
- Multi-tenant and distributed execution still need persistence, auth, and real enforcement/dispatch.

See `P9_FINALIZATION_ROADMAP_AND_GOVERNANCE_CLOSURE_2026-04-26.md` for the full closure record and final remaining workload estimate.

## P17 WebUI Chat Scroll and Queue Fix - 2026-05-08

P17 closes the chat auto-scroll regression in the workspace WebUI. The message list now keeps a sticky-bottom intent separate from derived scroll state, observes rendered content height changes after a fresh chat becomes non-empty, and scrolls immediately plus on the next animation frame when streamed or expanded assistant content changes height.

The validation pass also fixed the local daemon's LangGraph startup so short WebUI checks are not serialized behind one slow run: `scripts/start-daemon.sh` and `scripts/serve.sh` now enable isolated background loops and pass `--n-jobs-per-worker ${OCTO_LANGGRAPH_N_JOBS_PER_WORKER:-4}`.

Validation passed on 2号机 against `http://127.0.0.1:19880`:

- `cd frontend && npm run typecheck`
- `sudo systemctl restart octoagent-local.service && systemctl is-active octoagent-local.service`
- `node scripts/chat-scroll-regression.cjs` with `expansionPresent: true` and `distanceFromBottom: 0`
- `node scripts/first-turn-chat-regression.cjs` for direct `/new` and New Chat button paths

See `P17_WEBUI_CHAT_SCROLL_AND_QUEUE_FIX_2026-05-08.md` for the full root cause and validation record.

## P20 WebUI Performance, Trust Scores, Memory, and Full Verification - 2026-05-12

P20 closes the settings/runtime reliability and WebUI performance pass. The
frontend remains Next.js 16 plus React 19 and TypeScript, not Vue 3 plus Vite.
The settings drawer now lazy-loads heavy sections, the workspace layout avoids
mounting settings content outside settings routes, the status bar uses the
unified tools registry summary, chat route props/context are stabilized, and the
runtime inspector is deferred until after the initial chat surface paints.

Runtime repairs in this pass enabled observation-only skill trust scoring,
surfaced built-in runtime tools in Tools Hub, fixed the `settings=tools` route,
and normalized legacy memory stores so overview summaries backfill from facts.

Validation passed on 2号机 against `http://127.0.0.1:19880`:

- `cd backend && .venv/bin/python -m pytest` with 42 tests passed
- `cd backend && .venv/bin/python -m ruff check src tests scripts`
- `cd frontend && pnpm lint && pnpm typecheck && pnpm build`
- all Python, shell, and Node script entry syntax/load checks
- 19 backend argparse CLI `--help` checks
- real browser route/settings/chat WebUI巡检 plus repository WebUI smoke

See `P20_PERFORMANCE_TRUST_MEMORY_AND_FULL_VERIFICATION_2026-05-12.md` for the
full optimization, verification, repository hygiene, and carryover record.
