/**
 * Hardware-aware runtime profile fetched from the gateway.
 *
 * NOTE on `recursion_limit`:
 * LangGraph's `recursion_limit` is a *hard* super-step counter intended as a
 * last-resort safety net against infinite loops.  Real anti-loop protection
 * for OctoAgent lives in `ProgressStallMiddleware` and `ToolBudgetMiddleware`,
 * which inspect actual tool/output progress rather than raw step counts.
 *
 * Each visible tool round consumes ~18 LangGraph super-steps, so a low
 * recursion_limit (e.g. 400) terminates deep-research runs prematurely at
 * around step 22.  Worse, the value is cached in the browser between
 * sessions: an old fetched value will *override* server-side defaults until
 * the page is hard-refreshed.
 *
 * To make the limit robust regardless of stale browser cache, the frontend
 * always submits a very large `recursion_limit` (the FALLBACK value).  The
 * hardware-aware `recursion_default` from the backend profile is still used
 * server-side for non-streaming paths (channels manager, sub-agent runners,
 * task workspaces) ? those Python entrypoints read `get_resource_profile()`
 * directly and do not depend on the browser.
 */
export type RuntimeProfile = {
  total_mem_gb: number;
  cpu_cores: number;
  tier: "tiny" | "small" | "medium" | "large" | string;
  recursion_default: number;
  timeout_default_s: number;
  workspace_timeout_s: number;
  workspace_branch_timeout_s: number;
  workspace_recursion_default: number;
  recursion_ceiling: number;
};

const FALLBACK: RuntimeProfile = {
  total_mem_gb: 0,
  cpu_cores: 0,
  tier: "unknown",
  recursion_default: 1_000_000,
  timeout_default_s: 1800,
  workspace_timeout_s: 3600,
  workspace_branch_timeout_s: 14400,
  workspace_recursion_default: 500_000,
  recursion_ceiling: 1_000_000_000,
};

// The single source of truth for what the frontend submits as recursion_limit.
// Decoupled from `cached.recursion_default` to immunize the browser against
// stale per-session caches of older (lower) profile values.
const CLIENT_RECURSION_LIMIT = 1_000_000;

let cached: RuntimeProfile = FALLBACK;
let inflight: Promise<RuntimeProfile> | null = null;

async function fetchProfile(): Promise<RuntimeProfile> {
  try {
    const res = await fetch("/api/runtime/profile", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as RuntimeProfile;
    cached = { ...FALLBACK, ...data };
    return cached;
  } catch (err) {
    console.warn("[runtime-profile] using fallback caps:", err);
    return cached;
  }
}

// Kick off fetch eagerly when this module is first imported (browser only).
if (typeof window !== "undefined") {
  inflight = fetchProfile();
}

export function getRuntimeProfile(): RuntimeProfile {
  return cached;
}

export async function ensureRuntimeProfile(): Promise<RuntimeProfile> {
  if (inflight) return inflight;
  inflight = fetchProfile();
  return inflight;
}

export function getRecursionLimit(): number {
  // Deliberately decoupled from cached.recursion_default; see file header.
  return CLIENT_RECURSION_LIMIT;
}
