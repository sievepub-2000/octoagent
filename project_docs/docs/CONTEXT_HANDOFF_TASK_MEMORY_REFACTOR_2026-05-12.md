---
post_title: "Context Handoff and Task Memory Refactor 2026-05-12"
author1: "GitHub Copilot"
post_slug: "context-handoff-task-memory-refactor-2026-05-12"
microsoft_alias: "copilot"
featured_image: ""
categories: ["engineering"]
tags: ["octoagent", "continuation", "memory", "webui", "verification"]
ai_note: "AI assisted engineering report."
summary: "Assessment and verification record for the context handoff, task memory, unfinished-action, and token progress lamp repair on 2026-05-12."
post_date: "2026-05-12"
---

## Scope

This repair pass addressed three linked failures in the chat execution loop:

- Context handoff verification raised a frontend runtime error even when the
  handoff path was not eligible for backend runtime confirmation.
- Compression and continuation carried recent messages and workflow state, but
  did not carry active task todo state as a first-class handoff payload.
- The input token progress lamp needed a reference-style visual effect while
  preserving the operational contract: model-derived 90% threshold, growth from
  0 to 90% of the input width, and reset after continuation submission.
- The model could emit XML-ish `<tool_call>` text as visible assistant content
  instead of producing an actual structured tool call.

## Root Cause Analysis

### Handoff Verification Error

The frontend verified context handoff immediately inside `onFinish` by reading
`state.values.runtime`. That state can be a stream-finish snapshot rather than
fresh persisted runtime state. In mock mode, runtime state is not persisted at
all, so verification was guaranteed to fail and could surface as:

```text
Context handoff verification failed {}
```

The direct `console.error` path also caused Next.js development overlay noise,
which made a recoverable observation failure look like a task failure.

### Task Memory Gap

The project already had mature primitives similar to established agent systems:

- OpenHarness/Codex-compatible tools expose explicit plan mode and todo writing.
- LangChain `TodoListMiddleware` is extended by OctoAgent's `TodoMiddleware` to
  remind the model when todo tool calls fall out of context.
- `ContinuationMiddleware` injects hidden continuation context without mutating
  the visible user message.
- Session compaction stores context-cycle metadata in runtime state.

However, `buildContinuationContext` only passed recent messages and workflows.
Active `todos` were displayed in the WebUI and protected by `TodoMiddleware`,
but were not included in the explicit continuation handoff.

### Token Lamp Visual Gap

The previous token lamp had correct token math, but its visual structure was too
thin and easy to confuse with a static rail. The reference request called for a
more tangible progress effect. A first implementation with a CSS custom property
regressed width measurement in Chromium because the progress width fell back to
full width. The final implementation uses explicit inline width and left values
for the active segments while keeping the effect styling in CSS.

The later visual correction removed the remaining bright-line and spark-point
semantics. The current design keeps only a primary wall-wash light and a small
progress core. This matches the intended indirect light effect: no solid bar,
no protruding half-circle endpoint, and no separate halo layer.

### Simulated Tool Call Text

OctoAgent already had a mature semantic normalization layer for model-provider
tool-call dialects. It converted llama.cpp-style `<|tool_call:...|>` output into
real LangChain tool calls. The reported `<tool_call><function=...>` shape was a
similar provider dialect, but was not covered by the parser. That caused the UI
to show a simulated call instead of executing a real tool invocation.

The parser-only repair was not enough for streamed or already-persisted history.
The failing `767551ff` thread already contained multiple assistant messages with
raw XML-ish tool-call text, followed by a visible runtime error. That malformed
history could then be sent back to the provider and trigger `Cannot have 2 or
more assistant messages at the end of the list`.

The follow-up failure showed a second historical-contract problem: even after
XML-ish text was normalized, a thread could still end with two or more assistant
messages, or with an assistant message containing only `NormalizedModelError`.
Sending that tail back to providers repeats the same 400 failure and appends
more assistant errors, making the thread worse on every retry.

### Compaction Budget Gap

Session compaction was reducing message count, but not guaranteeing that the
rebuilt request fit the selected model window. Real logs showed compaction such
as `222 -> 112 messages` while the estimated request still exceeded the active
context limit. The provider then failed before the continuation loop could make
progress.

The fix treats compaction as a pre-provider budget contract, not just a summary
operation. Oversized messages are truncated before every model call, and the
rebuilt compacted history is trimmed to the model budget before submission.

### First-Turn Token Lamp Reset Gap

The token lamp reset correctly for existing-thread handoffs, but a first-turn
large message was guarded by `isNewThread` and never recorded its cycle base.
The textarea cleared after submit, but the lamp still counted the submitted
large human message as new cycle pressure and stayed at `100%`.

## Mature Pattern Alignment

The refactor follows proven patterns rather than inventing a new orchestration
model:

| Mature pattern | OctoAgent implementation |
| --- | --- |
| VS Code style task/todo extraction | `todos` remain thread state and now travel in continuation payloads. |
| Claude Code/Codex style plan mode | Existing plan/todo-compatible tools and task-workspace flows remain the control plane. |
| LangGraph/LangChain middleware state | Runtime handoff metadata is verified through persisted thread state, not only stream snapshots. |
| Hidden continuation context | Continuation metadata is injected as hidden system context, not visible user text. |
| UI progress as operational signal | Token lamp displays model-derived context pressure and resets only after handoff submission. |
| Provider tool-call normalization | XML-ish tool-call text is converted in the semantic layer and middleware before it becomes persisted answer text. |

## Implemented Changes

### Frontend Handoff Verification

`frontend/src/core/threads/hooks.ts` now:

- skips backend runtime verification in mock mode;
- records expected handoff with the target thread id;
- first checks the stream-finish state if it is already current;
- otherwise fetches `/threads/{thread_id}/state` with short retry delays;
- downgrades missing confirmation to a warning toast instead of a runtime-error
  overlay;
- avoids logging the previous `Context handoff verification failed` error.

### Continuation Task Memory

`frontend/src/core/threads/continuation.ts` and
`frontend/src/core/threads/types.ts` now include `continue_todos` in the hidden
handoff payload.

`backend/src/agents/middlewares/continuation_middleware.py` now formats that
payload as:

```text
Active task todo state to continue:
- [in_progress] verify context handoff
- [pending] write final report
```

This complements the existing `TodoMiddleware` reminder path, giving the model a
stable task-memory bridge across compression and continuation.

### Wall-Wash Token Progress Lamp

`frontend/src/components/workspace/input-box.tsx` and
`frontend/src/styles/globals.css` now render the token lamp as:

- a single primary wall-wash light layer;
- a small progress core with a restrained glow;
- no visible solid progress bar;
- no protruding spark or half-circle endpoint;
- forced-colors hiding for decorative-only graphics.

The operational values remain model-derived. The lamp exposes
`data-context-threshold-tokens`, which allows browser tests to prove that the
threshold comes from the selected model context window rather than a fixed UI
constant.

### XML-ish Tool Call Normalization

`backend/src/models/semantics.py` now parses this model-provider dialect:

```text
<tool_call>
  <function=bash>
    <parameter=description>查找系统核心文档和配置</parameter>
    <parameter=command>find /mnt -name "SOUL.md"</parameter>
  </function>
</tool_call>
```

and normalizes it to a real LangChain `tool_calls` entry with tool name,
arguments, and a stable content-derived call id.

`backend/src/agents/middlewares/dangling_tool_call_middleware.py` now applies
the same normalization twice:

- before model invocation, to repair historical assistant messages that already
  persisted raw XML-ish tool-call text;
- after model invocation, to ensure newly returned XML-ish text enters LangGraph
  as structured `tool_calls` before graph state is updated.

For historical messages where the original tool was never actually run, the
middleware inserts an interrupted `ToolMessage` placeholder immediately after the
normalized assistant message. This preserves provider message-order validity
without pretending that the old tool call succeeded. Frontend auto-continue and
backend run-record classification still treat any remaining raw `<tool_call>`
text as unfinished/failed evidence.

An agent-level regression test now proves the new response path invokes a real
LangChain tool: a fake model returns XML-ish `<tool_call>` text, the middleware
normalizes it to `AIMessage.tool_calls`, the agent executes the registered
`bash` test tool, and the final message history is `human -> ai(tool_calls) ->
tool -> ai(final)`.

The same middleware now repairs invalid assistant-only tails before provider
submission. When persisted history ends with repeated assistant messages or a
runtime/model error assistant message, the invalid tail is replaced with a
system repair note plus a human continuation request. That keeps provider
message order valid while preserving the instruction to continue the user's
latest unfinished task.

### Final Compaction Budget Guard

`backend/src/agents/middlewares/session_compaction_middleware.py` now:

- truncates oversized messages before every model call;
- trims rebuilt compacted histories to the active model budget;
- preserves leading system messages;
- inserts a context-guard system note when older messages must be dropped;
- keeps the most recent messages that fit the budget.

Focused tests cover oversized tool-output truncation and compacted-history
budget trimming.

### First-Turn Cycle Base Reset

`frontend/src/components/workspace/input-box.tsx`,
`frontend/src/app/workspace/chats/[thread_id]/page.tsx`, and the agent-chat
variant now allow threshold detection on a fresh thread. Existing chats still
attach the full hidden continuation source, while a first-turn large message
records only the cycle metadata needed to reset the visible lamp after submit.

### Runtime Error Classification

Visible runtime failure messages such as `NormalizedModelError` are now treated
as failed execution traces by `SkillEvolutionMiddleware`. This prevents trust
score and run-record systems from treating a model/provider error message as a
completed task.

### Unfinished Action Detection

The `767551ff-39c7-4042-bdd2-34baf5755e02` history case ended with a sentence
like:

```text
我来对OctoAgent系统进行全面的深度评估分析。首先，让我探索系统结构和各个模块的实现。
```

The previous detector only caught colon-ended action announcements. Frontend
auto-continue and backend skill-evolution trace detection now catch this
sentence-ended action-intent shape unless completion markers are present.

## Verification Results

### Focused Automated Checks

```bash
cd frontend && pnpm typecheck && pnpm lint
```

Passed.

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/test_continuation_middleware.py \
  tests/agents/test_skill_evolution_trace.py -q
```

Passed with 6 tests.

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/test_dangling_tool_call_middleware.py \
  tests/models/test_semantics_tool_calls.py \
  tests/agents/test_skill_evolution_trace.py -q
```

Passed with 10 tests.

### Browser Verification

A real Playwright browser against `http://127.0.0.1:19880` verified:

- new mock chat starts with `data-context-usage="0"`;
- token lamp line width starts at `0`;
- current model-derived threshold is exposed as
  `data-context-threshold-tokens="11802"`;
- a 70k-character draft grows the line to `0.899987` of input width;
- the wall-wash light grows to `0.899987` of input width;
- the small progress core opacity is `1` at threshold;
- submitting the handoff resets the line width to `0`;
- no console entry contains `Context handoff verification failed`.

Additional browser verification after the wall-wash simplification confirmed
the token lamp has exactly two children, no legacy `line`, `spark`, `wake`, or
`stream` classes, and returns both the wall-wash light and progress core to
zero opacity after handoff submission.

### Follow-up Verification

After the assistant-tail, compaction-budget, and first-turn reset fixes, the
following checks passed:

```bash
cd backend && .venv/bin/python -m pytest tests -q
```

Passed with 60 tests.

```bash
cd backend && .venv/bin/python -m ruff check \
  src/agents/middlewares/dangling_tool_call_middleware.py \
  src/agents/middlewares/session_compaction_middleware.py \
  tests/agents/test_dangling_tool_call_middleware.py \
  tests/agents/test_session_compaction_middleware.py
```

Passed.

```bash
cd frontend && pnpm typecheck && pnpm lint && pnpm build
```

Passed.

```bash
backend/.venv/bin/python backend/scripts/run_webui_smoke.py \
  --frontend-url http://127.0.0.1:19880 \
  --gateway-url http://127.0.0.1:19880 \
  --timeout-seconds 90 \
  --mock
```

Passed.

A real non-mock browser thread verified the actual tool path. The user prompt
asked for `bash` execution of `printf octoagent_tool_ok`; persisted state for
thread `640a5a0c-823c-453b-8b72-5ccc10d9c7a3` contained
`ToolMessage(name="bash", content="octoagent_tool_ok")`, and the final
assistant answer was `octoagent_tool_ok`. The checked state did not contain raw
`<tool_call>` text, `NormalizedModelError`, or the consecutive-assistant
provider error.

A real browser token-lamp check verified the first-turn reset path: new chat
started at `data-context-usage="0"`; a 90k-character draft reached
`data-context-width-percent="90.00"`; the decorative lamp had exactly two
children and no legacy `line`, `spark`, `wake`, or `stream` classes; the
model-derived threshold was `data-context-threshold-tokens="11802"`; and submit
reset width and opacity to zero. Screenshot evidence was written to
`/tmp/octoagent-token-lamp-wallwash.png`.

`git diff --check` produced no output, and VS Code diagnostics reported no
errors for the touched backend, frontend, and test files.

## Accessibility And Performance Notes

- The lamp remains `aria-hidden="true"`; the screen-reader status remains the
  existing live text message.
- Decorative forced-colors rendering is disabled with `forced-colors:hidden` so
  high-contrast users are not forced to interpret a nonessential visual effect.
- Layout and paint containment are applied to the lamp to reduce repaint scope.
- Width and endpoint position are driven by simple inline numeric styles, which
  keeps animation cheap and avoids React state churn beyond the existing token
  calculation.

## Residual Risk

- Real-provider handoff verification still depends on backend thread state being
  available shortly after stream finish. The new implementation treats delayed
  observation as a warning rather than a hard failure.
- The task-memory handoff now carries todos and workflows, but deeper automatic
  extraction quality still depends on the model correctly using `write_todos`.
- The Pinterest reference was not directly accessible as structured design data;
  the implemented visual is an abstracted light-stream progress effect, not a
  copied image or asset.
- The real tool-call browser check proves the server tool scheduler path. It
  does not imply every model will always choose a tool for every tool-like user
  request; it verifies that XML-ish or structured tool-call output no longer has
  to appear as visible simulated text.

## Recommendation

Keep the current architecture and avoid a large rewrite. The safer path is to
continue strengthening these mature primitives:

- use explicit thread-state contracts for handoff metadata;
- treat todos, workflows, and recent messages as separate handoff channels;
- keep hidden system continuation separate from visible user messages;
- validate UI context-pressure behavior with browser-level pixel checks;
- add more regression fixtures from real stopped chats when found.
