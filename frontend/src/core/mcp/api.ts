import { deleteJSON, getJSON, postJSON, putJSON } from "@/core/api/http";

import type { MCPConfig, MCPServerConfig, MCPServerMutationResponse } from "./types";

export async function loadMCPConfig() {
  return getJSON<MCPConfig>("/api/mcp/config");
}

export async function updateMCPConfig(config: MCPConfig) {
  return putJSON<MCPConfig>("/api/mcp/config", config);
}

export async function upsertMCPServer(serverName: string, server: MCPServerConfig) {
  return postJSON<MCPServerMutationResponse>("/api/mcp/servers", {
    name: serverName,
    server,
  });
}

export async function removeMCPServer(serverName: string) {
  return deleteJSON<MCPServerMutationResponse>(`/api/mcp/servers/${encodeURIComponent(serverName)}`);
}
