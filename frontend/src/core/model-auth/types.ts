export interface ModelAuthTemplate {
  provider_id: string;
  display_name: string;
  description: string;
  auth_methods: string[];
  default_base_url: string;
  env_var: string;
  interface_type: string;
  provider_name: string;
  default_model: string;
  default_models: string[];
  supports_official_oauth?: boolean;
  supports_unofficial_web_session?: boolean;
  docs_url?: string | null;
  notes?: string | null;
  oauth_login_url?: string | null;
  conversation_url?: string | null;
}

export interface ModelAuthProviderStatus extends ModelAuthTemplate {
  connected: boolean;
  auth_mode?: string | null;
  account_label?: string | null;
  base_url: string;
  model: string;
  credential_ref?: string | null;
  updated_at?: number | null;
}

export interface ProviderAuthorizeRequest {
  api_key?: string | null;
  account_label?: string | null;
  base_url?: string | null;
  model?: string | null;
  auth_mode?: string;
  session_payload?: Record<string, unknown> | null;
  sync_model?: boolean;
}

export interface ProviderOAuthStartRequest {
  callback_url?: string | null;
  state?: string | null;
  prefer_web_dialog?: boolean;
}

export interface ProviderOAuthStartResponse {
  ok: boolean;
  provider_id: string;
  mode: string;
  login_url: string;
  conversation_url?: string | null;
  account_login_url?: string | null;
  message: string;
  state?: string | null;
  requires_confirmation?: boolean;
}

export interface ProviderOAuthConfirmRequest {
  state: string;
}

export interface ProviderOAuthConfirmResponse {
  ok: boolean;
  provider_id: string;
  display_name: string;
  state: string;
  mode?: string | null;
  message: string;
}

export interface ProviderOAuthModelsRequest {
  state?: string | null;
}

export interface ProviderConversationModel {
  id: string;
  display_name: string;
  description?: string | null;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  supports_vision?: boolean;
  max_context_tokens?: number | null;
}

export interface ProviderOAuthModelsResponse {
  provider_id: string;
  display_name: string;
  conversation_url?: string | null;
  models: ProviderConversationModel[];
  source: string;
  message: string;
}

export interface ProviderOAuthCompleteRequest {
  model: string;
  account_label?: string | null;
  set_default?: boolean;
  state?: string | null;
}

export interface ProviderOAuthCompleteResponse {
  success: boolean;
  provider: ModelAuthProviderStatus;
  model: unknown;
  selected_model: ProviderConversationModel;
  default_model?: string | null;
  test: {
    ok: boolean;
    mode: string;
    provider_id: string;
    model: string;
    message: string;
  };
}
