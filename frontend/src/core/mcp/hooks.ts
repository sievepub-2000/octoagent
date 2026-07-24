import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { loadMCPConfig, removeMCPServer, upsertMCPServer } from "./api";
import type { MCPServerConfig } from "./types";

export function useMCPConfig() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["mcpConfig"],
    queryFn: () => loadMCPConfig(),
  });
  return { config: data, isLoading, error };
}

export function useEnableMCPServer() {
  const queryClient = useQueryClient();
  const { config } = useMCPConfig();
  return useMutation({
    mutationFn: async ({
      serverName,
      enabled,
    }: {
      serverName: string;
      enabled: boolean;
    }) => {
      if (!config) {
        throw new Error("MCP config not found");
      }
      if (!config.mcp_servers[serverName]) {
        throw new Error(`MCP server ${serverName} not found`);
      }
      await upsertMCPServer(serverName, {
        ...config.mcp_servers[serverName],
        enabled,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["mcpConfig"] });
      void queryClient.invalidateQueries({ queryKey: ["harness"] });
    },
  });
}

export function useAddMCPServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      serverName,
      server,
    }: {
      serverName: string;
      server: MCPServerConfig;
    }) => {
      await upsertMCPServer(serverName, server);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["mcpConfig"] });
      void queryClient.invalidateQueries({ queryKey: ["harness"] });
    },
  });
}

export function useRemoveMCPServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ serverName }: { serverName: string }) => {
      await removeMCPServer(serverName);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["mcpConfig"] });
      void queryClient.invalidateQueries({ queryKey: ["harness"] });
    },
  });
}
