"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export type RagConfig = {
  embedding_model: string;
  reranker_enabled: boolean;
  reranker_model: string;
  top_k_default: number;
};

export type ModelCacheStatus = {
  cached: boolean;
  size_bytes: number;
  path: string | null;
};

export type RagConfigResponse = {
  config: RagConfig;
  embedding_status: ModelCacheStatus;
  reranker_status: ModelCacheStatus;
  config_file: string;
};

const ENDPOINT = "/api/runtime/rag-config";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export function useRagConfig() {
  return useQuery({
    queryKey: ["rag-config"],
    queryFn: () => fetchJSON<RagConfigResponse>(ENDPOINT),
    staleTime: 15_000,
  });
}

export function useUpdateRagConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cfg: RagConfig) =>
      fetchJSON<RagConfigResponse>(ENDPOINT, {
        method: "PUT",
        body: JSON.stringify(cfg),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["rag-config"], data);
    },
  });
}

export function useDownloadModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: { model: string; kind: "embedding" | "reranker" }) =>
      fetchJSON<{ ok: boolean; model: string; kind: string; path: string }>(
        `${ENDPOINT}/download`,
        {
          method: "POST",
          body: JSON.stringify(req),
        },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["rag-config"] });
    },
  });
}

export function formatBytes(n: number): string {
  if (!n) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(n) / Math.log(k));
  return `${(n / k ** i).toFixed(1)} ${sizes[i]}`;
}
