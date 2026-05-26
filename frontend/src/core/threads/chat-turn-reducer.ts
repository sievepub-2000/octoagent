/**
 * Phase 2 (2026-05-26): chat-turn state-machine skeleton.
 *
 * Status: SCAFFOLD — exported reducer + types are unused until a follow-up
 * session migrates `core/threads/hooks.ts::sendMessage` to dispatch into this
 * reducer. Keeping behaviour unchanged in Phase 0/1 lockstep avoids the
 * regression class seen in commits 1121af4 / f13e874 / 87cc74c (three
 * separate first-turn submission bugs in one week, all rooted in ad-hoc
 * optimistic+streaming+URL state interleaving).
 *
 * Design principles (locked in from Vercel AI SDK `useChat` reference):
 *
 *   1. There is exactly ONE state object per chat turn. Optimistic AI/human
 *      bubbles, streaming chunks, URL transitions, and SDK lifecycle events
 *      all flow through dispatch(action).
 *
 *   2. The reducer is a pure function. No side effects (no router.push,
 *      no fetch, no setTimeout). Side effects live in middleware / a thin
 *      effect hook that observes state transitions.
 *
 *   3. State transitions are explicit: idle -> uploading -> submitting ->
 *      streaming -> settled. Invalid transitions throw in dev, no-op in prod.
 *
 *   4. The URL is only ever rewritten in the `settled` transition after the
 *      first real server message arrives.  No URL mutation during
 *      `uploading` / `submitting` / `streaming`.
 */

export type TurnPhase =
  | "idle"
  | "uploading"
  | "submitting"
  | "streaming"
  | "settled"
  | "errored";

/**
 * Minimal optimistic message shape. We intentionally don't extend the
 * langgraph-sdk Message union here — the reducer is type-erased over message
 * shape so the consumer can wire its own concrete type at the call site.
 */
export interface OptimisticMessage {
  id?: string;
  type?: string;
  content?: unknown;
  __optimistic: true;
  // Allow arbitrary additional fields from the SDK's Message union.
  [key: string]: unknown;
}

export interface ChatTurnState {
  phase: TurnPhase;
  turnId: string | null;
  threadId: string | null;
  optimisticMessages: OptimisticMessage[];
  pendingUploadCount: number;
  errorMessage: string | null;
}

export const initialChatTurnState: ChatTurnState = {
  phase: "idle",
  turnId: null,
  threadId: null,
  optimisticMessages: [],
  pendingUploadCount: 0,
  errorMessage: null,
};

export type ChatTurnAction =
  | { type: "TURN_START"; turnId: string; threadId: string; human: OptimisticMessage; uploadCount: number }
  | { type: "UPLOAD_PROGRESS"; remaining: number }
  | { type: "UPLOAD_COMPLETE"; finalHuman: OptimisticMessage }
  | { type: "UPLOAD_FAILED"; error: string }
  | { type: "SUBMIT_SENT" }
  | { type: "STREAM_FIRST_CHUNK" }
  | { type: "STREAM_FINISHED" }
  | { type: "ERRORED"; error: string }
  | { type: "RESET" };

/**
 * Pure state reducer for a single chat turn.
 *
 * Phase 2 scope: this reducer is INTENTIONALLY NOT yet wired into
 * `hooks.ts`. The migration plan, in order:
 *
 *   1. (next session) Wire the reducer into `useThreadStream` behind a
 *      `OCTO_FRONTEND_CHAT_TURN_REDUCER=1` env flag. Both implementations
 *      coexist; the flag is the kill switch.
 *   2. Run the four-scenario regression: plain text / with attachment /
 *      disconnect+resume / first-turn retry.
 *   3. Flip flag default to on; remove legacy code path.
 *   4. Delete the env flag.
 */
export function chatTurnReducer(
  state: ChatTurnState,
  action: ChatTurnAction,
): ChatTurnState {
  switch (action.type) {
    case "TURN_START":
      return {
        phase: action.uploadCount > 0 ? "uploading" : "submitting",
        turnId: action.turnId,
        threadId: action.threadId,
        optimisticMessages: [action.human],
        pendingUploadCount: action.uploadCount,
        errorMessage: null,
      };

    case "UPLOAD_PROGRESS":
      if (state.phase !== "uploading") return state;
      return { ...state, pendingUploadCount: Math.max(0, action.remaining) };

    case "UPLOAD_COMPLETE":
      if (state.phase !== "uploading") return state;
      // Converge: drop any AI placeholder, keep only the (now file-rich) human bubble.
      // This is the invariant violated by the bug fixed in commit 87cc74c.
      return {
        ...state,
        phase: "submitting",
        optimisticMessages: [action.finalHuman],
        pendingUploadCount: 0,
      };

    case "UPLOAD_FAILED":
      return { ...state, phase: "errored", errorMessage: action.error };

    case "SUBMIT_SENT":
      if (state.phase !== "submitting") return state;
      return { ...state, phase: "streaming" };

    case "STREAM_FIRST_CHUNK":
      // First real chunk = it is safe to rewrite the URL upstream (handled in effect).
      return state;

    case "STREAM_FINISHED":
      return { ...state, phase: "settled", optimisticMessages: [] };

    case "ERRORED":
      return { ...state, phase: "errored", errorMessage: action.error };

    case "RESET":
      return initialChatTurnState;

    default:
      return state;
  }
}
