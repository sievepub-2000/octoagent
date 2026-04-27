import { getJSON, putJSON } from "@/core/api/http";

import type { MCPConfig } from "./types";

export async function loadMCPConfig() {
  return getJSON<MCPConfig>("/api/mcp/config");
}

export async function updateMCPConfig(config: MCPConfig) {
  return putJSON<MCPConfig>("/api/mcp/config", config);
}
