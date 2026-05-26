export interface MCPServerConfig extends Record<string, unknown> {
  enabled: boolean;
  description: string;
  type?: "stdio" | "sse" | "http";
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  status?: "ready" | "disabled" | "configuration_error";
  status_reason?: string;
  missing_env?: string[];
}

export interface MCPConfig {
  mcp_servers: Record<string, MCPServerConfig>;
}

export interface MCPServerMutationResponse {
  success: boolean;
  message: string;
  mcp_servers: Record<string, MCPServerConfig>;
}
