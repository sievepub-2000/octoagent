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

Latest result: 39 tests passed.
