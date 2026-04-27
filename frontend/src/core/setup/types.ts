export interface ValidateWorkspaceResponse {
  valid: boolean;
  resolved_path: string;
  exists: boolean;
  writable: boolean;
  free_space_mb: number;
  error: string;
}

export interface ApplySetupResponse {
  success: boolean;
  workspace_path: string;
  default_model: string;
  sandbox_mode: "local" | "docker";
  directories_created: string[];
  error: string;
}

export interface SystemSetupStatus {
  workspace_ready: boolean;
  workspace_path: string;
  configured_default_model: string;
  configured_sandbox_mode: "local" | "docker";
  models_configured: number;
  skills_available: number;
  mcp_servers: number;
  gateway_healthy: boolean;
  langgraph_reachable: boolean;
  embedding_backend?: string;
  embedding_dim?: number;
}

export interface DirectoryEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface BrowseDirectoryResponse {
  resolved_path: string;
  parent: string;
  entries: DirectoryEntry[];
  error: string;
}

export interface CreateDirectoryResponse {
  success: boolean;
  resolved_path: string;
  error: string;
}

export interface ApplySetupRequest {
  workspace_path: string;
  default_model: string;
  sandbox_mode: "local" | "docker";
  preserve_existing_workspace?: boolean;
}

export interface UpdateDefaultModelRequest {
  default_model: string;
}

export interface UpdateDefaultModelResponse {
  success: boolean;
  workspace_path: string;
  default_model: string;
  sandbox_mode: "local" | "docker";
  error: string;
}
