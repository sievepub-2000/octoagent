# Harness Research Policy

Date: 2026-05-27

## Purpose

This document records the active OctoAgent harness behavior for user-directed web research. The policy is designed for weak/local model robustness without using hard graph stops for normal research loops.

## Source-First Research

When the user names a URL, domain, publication, platform, or source, the agent must try that source first.

- Direct URL: fetch or read the URL before broad search.
- Named source: start with the official site or a source-limited query, for example `site:reddit.com`, `site:bloomberg.com`, or an X official page.
- If source-limited evidence is enough, answer directly from that evidence.
- If the source is blocked by login, paywall, anti-bot, or a page error, say so clearly and only broaden after the source-specific gap is identified.
- Top-N requests must report the verified count when fewer than N source-backed items are available. The harness must not fill missing slots with unrelated domains.

Current named-source mapping includes:

| User wording | Source domain |
| --- | --- |
| `x.com`, `twitter` | `x.com` |
| `reddit`, `red-di`/Chinese wording | `reddit.com` |
| `bloomberg`, Chinese Bloomberg wording | `bloomberg.com` |

## Soft Loop Recovery

Research and tool-loop recovery are soft constraints. They guide the model, compact context, and narrow the next step without treating normal research repetition as task completion.

- Three repeated identical execution steps trigger a required summary/change-strategy message.
- Five consecutive failed tool/recovery steps trigger skip-and-continue guidance plus self-iteration metadata.
- The duplicate hard-stop path is opt-in only and disabled by default.
- OOM/resource protection remains the only expected automatic hard stop class.

## Research Closure

The harness closes normal web research early when enough evidence has already been collected:

- closure after a small number of web results/fetches and at least two substantive evidence-bearing results;
- web evidence is compacted before the final answer to avoid context blow-up;
- final answer model calls run without web tools where possible;
- if a weak model still emits web tool calls after closure, the middleware converts the pending call into a conservative evidence-only final answer.

The fallback answer is deliberately narrow:

- it uses only observable tool evidence;
- it filters results to the user-named source domain when a source is specified;
- it reports the verified count, for example `3/10`, instead of inventing missing entries;
- it states login/paywall/anti-bot/search-fragment limitations explicitly.

## Turn-Scoped State Lifecycle

Research closure is scoped to the latest human turn, not to the whole thread runtime:

- closure metadata records the latest human message index and a short content hash;
- final-answer/no-web-tool mode is active only when the stored marker matches the current latest user turn;
- when a new user turn arrives after prior closure, stale `research_closure`, evidence compaction, and closure reflection state are cleared;
- the reset is recorded as `research_closure_reset.reason = new_user_turn` so traces can explain why tools are available again.

This prevents a completed research turn from leaking `must_finalize` state into follow-up questions that still need web tools.

## Research Intent Routing

Server-side semantics can override weak or stale client route hints when the user clearly requests current research:

- strong research cues include `查一下`, `帮我查`, export/import, trade records, production volume, destination-to-China wording, and equivalent Chinese terms;
- strong research intent is checked before workspace/action keywords so trade-research requests are not misread as repository/tool actions;
- bad explicit routes such as `direct_answer` are overridden with `server_research_intent_overrides_client_route` when the text requires fresh evidence.

## Model Health Notes

Latest direct checks after the lifecycle/routing fix:

| Model | Config status | Runtime check |
| --- | --- | --- |
| `qwen3.6-35b-a3b-q8-mm-prod` | configured as local OpenAI-compatible llama.cpp endpoint at `http://localhost:8000/v1` | `/v1/models` returned 200 and chat completion returned `OK.` |
| `hermes-gemini-3.1-pro` | configured as `google_genai`, no direct OpenAI-compatible `base_url` | shell/service environment did not expose Google/Gemini API credentials, so no live completion could be run |
| `google-gemini-3.1-pro-preview-customtools` | configured with `api_key: $OCTOAGENT_MODEL_AUTH_GOOGLE` | service environment did not define the key; direct Google API probe timed out |

## Validation Baseline

After the 2026-05-27 harness update, live validation conversations passed for:

| Query | First web action | Duplicate max | Final behavior |
| --- | --- | ---: | --- |
| `query x.com top ten news` | `web_fetch https://x.com/explore` | 1 | source-domain-only final report |
| `query reddit top ten news` | `web_fetch https://www.reddit.com/r/popular/.json?limit=25` | 1 | source-domain-only final report, partial count allowed |
| `query Bloomberg top ten news` | `web_fetch https://www.bloomberg.com` | 1 | source-domain-only final report, partial count allowed |

Targeted regression checks:

- `ruff check src/agents/core/instruction_contracts.py src/agents/middlewares/tool_budget_middleware.py src/agents/middlewares/progress_stall_middleware.py tests/agents/test_instruction_contracts.py tests/agents/test_tool_recovery_middleware.py`
- `pytest tests/agents/test_instruction_contracts.py tests/agents/test_tool_recovery_middleware.py`

Latest lifecycle/routing result: 50 tests passed. WebUI verified through `http://127.0.0.1:19800/` and `/workspace/chats` after service restart.
