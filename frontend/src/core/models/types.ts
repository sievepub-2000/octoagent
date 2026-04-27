export interface Model {
  id?: string;
  name: string;
  display_name?: string;
  description?: string | null;
  model?: string | null;
  use?: string | null;
  interface_type?: string | null;
  provider_name?: string | null;
  resolved_interface_type?: string | null;
  resolved_provider_family?: string | null;
  resolved_use_path?: string | null;
  adapter_type?: string | null;
  adapter_request_contract?: string | null;
  adapter_response_contract?: string | null;
  adapter_streaming_contract?: string | null;
  adapter_auth_mode?: string | null;
  proxy_compatible?: boolean;
  semantic_format?: string | null;
  thinking_semantics?: string | null;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  supports_vision?: boolean;
  fallback_models?: string[];
  max_context_tokens?: number | null;
  is_embedded_backup?: boolean;
}

export interface ModelCreateRequest {
  name: string;
  display_name?: string;
  description?: string;
  model: string;
  use?: string;
  interface_type?: string;
  provider_name?: string;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  supports_vision?: boolean;
  fallback_models?: string[];
  max_context_tokens?: number | null;
  api_key?: string;
  base_url?: string;
  google_api_key?: string;
}

export interface ModelUpdateRequest extends Partial<ModelCreateRequest> {}
