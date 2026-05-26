# P17 WebUI Chat Scroll and Queue Fix - 2026-05-08

## Scope

This pass closes the WebUI chat auto-scroll regression where the conversation viewport did not follow assistant content as the rendered message height changed.

It also hardens local LangGraph daemon startup after validation exposed a false empty-state symptom: the in-memory runtime was running with one background worker on the shared loop, so one slow local model request could leave later first-turn and scroll checks pending with HTTP 200 but no persisted state yet.

## Root Cause

- The message list only reacted to message group count and loading state. Streaming markdown, code blocks, images, or other layout expansion can change DOM height without changing the group count.
- A `ResizeObserver` was needed on the rendered scroll content, but it must be attached after the first non-empty chat render. Empty fresh chats initially render without the content ref.
- Programmatic or layout-induced scroll events can briefly report a large distance from bottom after content grows. The sticky-bottom intent must be tracked separately from derived `atBottom` React state.
- LangGraph dev startup defaulted to one queued background job because the CLI patches `N_JOBS_PER_WORKER=1` unless `--n-jobs-per-worker` is supplied.

## Fix

- `frontend/src/components/workspace/messages/message-list.tsx`
  - Added a content-height signature and `ResizeObserver`-driven follow-to-bottom behavior.
  - Added `stickToBottomRef` and scroll-height tracking so content growth does not accidentally disable auto-follow while the user is already at the bottom.
  - Rebinds the observer when an empty thread becomes non-empty.

- `scripts/start-daemon.sh` and `scripts/serve.sh`
  - Start LangGraph with `BG_JOB_ISOLATED_LOOPS=true` by default.
  - Pass `--n-jobs-per-worker ${OCTO_LANGGRAPH_N_JOBS_PER_WORKER:-4}` so local WebUI checks and short chats are not serialized behind one slow run.

- `scripts/chat-scroll-regression.cjs`
  - Adds a real WebUI regression for chat scroll behavior.
  - Waits for a real assistant reply, then deterministically expands the rendered scroll content and asserts that the viewport remains pinned to the bottom.

## Validation

Executed on 2号机 against the real local entrypoint `http://127.0.0.1:19880`:

```bash
cd /home/sieve-pub/public-workspace/octoagent/frontend
npm run typecheck

sudo systemctl restart octoagent-local.service
systemctl is-active octoagent-local.service

cd /home/sieve-pub/public-workspace/octoagent
node scripts/chat-scroll-regression.cjs
node scripts/first-turn-chat-regression.cjs
```

Observed results:

- TypeScript check passed.
- Service restarted and reported `active`.
- LangGraph log confirmed `Starting queue with isolated loops` and `Starting 4 background workers`.
- Scroll regression passed with `expansionPresent: true` and `distanceFromBottom: 0`.
- First-turn regression passed for both direct `/workspace/chats/new` and the New Chat button path, with two persisted messages and no bad `/threads` or `/runs` responses.

## Notes

`npm run check` still includes the known broken `next lint` wrapper in this repository shape. This pass used `npm run typecheck` plus real Playwright WebUI regressions for the touched chat surface.
