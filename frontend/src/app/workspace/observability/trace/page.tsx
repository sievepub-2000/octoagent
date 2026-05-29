"use client";

/**
 * Phase 4a (2026-05-26): visual tool-trace viewer.
 *
 * Reads /api/runtime/tool-trace and renders the last N events as a
 * sortable timeline. Read-only; no interactions besides refresh + filter.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

interface TraceEvent {
  ts: string | null;
  kind: string | null;
  name: string | null;
  duration_ms: number | null;
  status: string | null;
  extra: Record<string, unknown>;
}

interface TraceResponse {
  generated_at: string;
  source_file: string;
  file_exists: boolean;
  total_lines: number;
  events: TraceEvent[];
}

const KIND_COLORS: Record<string, string> = {
  tool: "bg-blue-500/20 text-blue-100 border-blue-400/30",
  subprocess: "bg-amber-500/20 text-amber-100 border-amber-400/30",
  sandbox: "bg-purple-500/20 text-purple-100 border-purple-400/30",
  recovery: "bg-rose-500/20 text-rose-100 border-rose-400/30",
  exception: "bg-red-600/30 text-red-100 border-red-400/40",
};

export default function TraceViewerPage() {
  const [data, setData] = useState<TraceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(200);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const fetchTrace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/runtime/tool-trace?limit=${limit}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as TraceResponse;
      setData(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void fetchTrace();
  }, [fetchTrace]);

  const filteredEvents = useMemo(() => {
    if (!data) return [];
    const needle = filter.trim().toLowerCase();
    if (!needle) return data.events;
    return data.events.filter((ev) => {
      const blob = `${ev.ts ?? ""} ${ev.kind ?? ""} ${ev.name ?? ""} ${ev.status ?? ""} ${JSON.stringify(ev.extra)}`.toLowerCase();
      return blob.includes(needle);
    });
  }, [data, filter]);

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Runtime tool-trace</h1>
          <p className="text-sm text-zinc-400">
            Last {data?.total_lines ?? 0} events from{" "}
            <code className="rounded bg-zinc-800 px-1 text-xs">{data?.source_file ?? "tool-trace.jsonl"}</code>
            {data?.file_exists === false && (
              <span className="ml-2 rounded bg-amber-500/20 px-2 py-0.5 text-amber-200">
                file not present yet
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            Limit
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1"
            >
              {[100, 200, 500, 1000, 2000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <input
            type="search"
            placeholder="filter…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-sm"
          />
          <button
            type="button"
            onClick={fetchTrace}
            disabled={loading}
            className="rounded bg-zinc-800 px-3 py-1 text-sm hover:bg-zinc-700 disabled:opacity-50"
          >
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          Failed to load: {error}
        </div>
      )}

      <div className="flex-1 overflow-auto rounded border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-zinc-900/95 text-left text-xs uppercase tracking-wide text-zinc-400">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Kind</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2 text-right">ms</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Extra</th>
            </tr>
          </thead>
          <tbody>
            {filteredEvents.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-zinc-500">
                  No events.
                </td>
              </tr>
            )}
            {filteredEvents.map((ev, idx) => (
              <tr key={idx} className="border-t border-zinc-800/60 align-top">
                <td className="px-3 py-2 font-mono text-xs text-zinc-400">{ev.ts ?? "—"}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded border px-2 py-0.5 text-xs ${
                      KIND_COLORS[ev.kind ?? ""] ?? "border-zinc-700 bg-zinc-800/60 text-zinc-200"
                    }`}
                  >
                    {ev.kind ?? "—"}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{ev.name ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
                  {typeof ev.duration_ms === "number" ? ev.duration_ms.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-2 text-xs">
                  {ev.status ? (
                    <span
                      className={`rounded px-2 py-0.5 ${
                        ev.status === "ok"
                          ? "bg-emerald-500/15 text-emerald-200"
                          : ev.status === "error" || ev.status === "timeout"
                            ? "bg-red-500/15 text-red-200"
                            : "bg-zinc-700/40 text-zinc-300"
                      }`}
                    >
                      {ev.status}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-[10px] text-zinc-500">
                  {Object.keys(ev.extra).length > 0 ? JSON.stringify(ev.extra) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
