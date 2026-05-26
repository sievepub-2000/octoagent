# P23 Host Environment and Long-Task Runtime Repair

Date: 2026-05-15

## Host Repair

- Ubuntu 24.04.4 LTS / NVIDIA 6.17 kernel inspected.
- GDM, Xorg, GNOME Shell, NVIDIA driver, keyboard, mouse, and display seat are present.
- NVMe SMART health passed: media errors 0, critical warning 0.
- Removed failed swap units by disabling missing `/swap.img`, `/swapfile`, and `/swap_extra_32g.img` fstab entries. Existing zram swap remains active.
- Restored system nginx service after earlier local service cleanup killed the system unit.
- Installed/enabled `acpid` and upgraded GNOME Shell packages to the current noble-updates revision.
- Ran Ubuntu package upgrade; remaining upgradable packages are NVIDIA/CUDA/kernel-tooling packages held by apt to protect the currently working driver stack.

## OctoAgent Environment

- `firecrawl-py` remains treated as a removed component.
- Crawl4AI is restored as an isolated project-local tool environment under `backend/tool_envs/crawl4ai`, not as a main OctoAgent venv dependency.
- Web fetch fallback is now `tavily -> DDG -> scrapling -> crawl4ai`.
- Python venv now passes `pip check`.
- Project startup scripts now keep OctoAgent caches under the repository:
  - `runtime/cache/huggingface`
  - `runtime/cache/sentence_transformers`
  - `runtime/cache/pip`
  - `runtime/cache/uv`
  - `runtime/cache/xdg`
  - `runtime/cache/ms-playwright`
- Existing Hugging Face cache used by OctoAgent was copied into `runtime/cache/huggingface`.

## Runtime JSON Consolidation

`src.runtime_config.RuntimeJsonStore` now centralizes path handling, corrupt JSON quarantine, and atomic writes for runtime JSON state. These stores now use it:

- plugin registry
- browser runtime sessions
- system execution store
- channel store

This keeps state handling consistent without moving each domain model into one large global config object.

## Router Tags

Router contract still blocks duplicate method/path collisions. Tag checking now has a report-first path and an opt-in strict mode:

- `ROUTER_TAG_REPORT` records missing router/route tags.
- `OCTOAGENT_STRICT_ROUTER_TAGS=1` upgrades tag issues to startup errors.

## Long-Running Task Semantics

Session compaction now defaults toward review-oriented summarization instead of hard truncation:

- compaction summaries are stage reviews;
- runtime state asks for self-feedback, memory follow-up, and resource recovery;
- hard context truncation is opt-in via `OCTOAGENT_ALLOW_HARD_CONTEXT_TRUNCATION=1`;
- task continuity should prefer soft compression and self-review unless a true system-level error requires emergency trimming.

`ExecutionReviewMiddleware` now turns three runtime signals into a fixed soft-review checkpoint before the next model call:

- every context compaction / emergency trim;
- any visible tool error in the current human turn;
- active or incomplete tasks whose last review is older than 5 minutes.

The review checkpoint asks the model to audit progress, errors, memory follow-up, resource recovery, and the next action. It records `execution_review_*` runtime fields and deliberately avoids a hard stop for normal tool failures.

## Startup Ownership

`octoagent-local.service` is the single startup owner for the local OctoAgent stack. The deploy unit now matches the host unit shape: `Type=oneshot`, `RemainAfterExit=yes`, `OCTOAGENT_MANAGED_BY_SYSTEMD=1`, and `ExecStop=scripts/stop-services.sh`.

`scripts/start-daemon.sh` refuses manual startup while the enabled systemd unit is active unless the operator explicitly sets `OCTOAGENT_ALLOW_MANUAL_START=1`. This prevents the previous duplicate-start ambiguity where systemd reported `active (exited)` while manually launched child processes continued under PID 1.

The launcher also defaults `PYTHONDONTWRITEBYTECODE=1` so service runtime does not repopulate project source directories with `__pycache__` after cleanup.

## Token Counter

The chat input now exposes a visible top-level token counter just below the input border beside the existing context lamp. It reports estimated live context tokens, model context window, raw estimate, and compacted cycle base through DOM data attributes and the hover title.

## Model Tool Calling

The tool layer treats removed or temporarily unavailable web providers as optional stale configuration and skips them instead of failing agent construction. Crawl4AI was restored as a project-local isolated tool environment under `backend/tool_envs/crawl4ai` because its `lxml~=5.3` dependency conflicts with Scrapling's `lxml>=6.1.0` requirement in the main OctoAgent venv.

The configured fetch chain is now `tavily -> DDG -> scrapling -> crawl4ai`. Crawl4AI HTTP/browser tools return structured JSON errors when browser assets or network access are unavailable, instead of blocking model/tool execution.

Model tool-call normalization now supports common provider output shapes:

- native OpenAI-compatible raw `additional_kwargs.tool_calls`;
- Gemini-style `additional_kwargs.function_call`;
- Anthropic / Gemini content-block `tool_use` / `tool_call` / `function_call`;
- JSON payloads inside `<tool_call>...</tool_call>` or fenced JSON;
- existing llama.cpp and XML-ish tool-call formats;
- Gemma/local Python-call tool-code blocks such as `<|tool_code|>tool_name(arg="value")<|tool_code|>`, including streamed chunk output.

## Remaining Notes

- The local `/root/llm-server` stack is not an OctoAgent component and was not changed.
- `uv lock --upgrade-package lxml` did not complete in a reasonable time, so `requirements.txt` was aligned to the working environment and `uv.lock` should be regenerated in a dedicated dependency-maintenance window.
