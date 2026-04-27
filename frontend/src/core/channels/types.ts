export type ChannelConfigFieldKind =
  | "boolean"
  | "text"
  | "secret"
  | "string_list"
  | "url"
  | "number";

export interface ChannelConfigField {
  name: string;
  label: string;
  kind: ChannelConfigFieldKind;
  description?: string | null;
  placeholder?: string | null;
  required?: boolean;
}

export interface ChannelStatusItem {
  enabled?: boolean;
  configured?: boolean;
  running?: boolean;
  healthy?: boolean;
  integration_mode?: string;
  platform_label?: string;
  transport?: string;
  description?: string | null;
  config_path?: string | null;
  handler_path?: string | null;
  fields?: ChannelConfigField[];
  config?: Record<string, unknown>;
  bridge_project?: string | null;
  bridge_project_url?: string | null;
  ingest_path?: string | null;
  outbound_configured?: boolean;
  [key: string]: unknown;
}

export interface ChannelStatusResponse {
  service_running: boolean;
  channels: Record<string, ChannelStatusItem>;
}

export interface ChannelRestartResponse {
  success: boolean;
  message: string;
}

export interface ChannelConfigUpdateRequest {
  config: Record<string, unknown>;
}

export interface ChannelConfigUpdateResponse {
  success: boolean;
  message: string;
  channel: ChannelStatusItem;
}

export interface ChannelEnabledUpdateRequest {
  enabled: boolean;
}

export interface ChannelEnabledUpdateResponse {
  success: boolean;
  message: string;
  channel: ChannelStatusItem;
}