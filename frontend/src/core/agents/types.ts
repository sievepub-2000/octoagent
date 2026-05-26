export interface Agent {
  id?: string | null;
  name: string;
  display_name?: string | null;
  description: string;
  model: string | null;
  tool_groups: string[] | null;
  soul?: string | null;
  avatar?: string | null;
  source?: "custom" | "template";
  editable?: boolean;
  deletable?: boolean;
  chat_enabled?: boolean;
  template_skill_name?: string | null;
  template_id?: string | null;
  source_category?: string | null;
  source_path?: string | null;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  model?: string | null;
  tool_groups?: string[] | null;
  soul?: string;
}

export interface UpdateAgentRequest {
  name?: string | null;
  description?: string | null;
  model?: string | null;
  tool_groups?: string[] | null;
  soul?: string | null;
}

export interface AgentTemplateSummary {
  skill_name: string;
  skill_enabled: boolean;
  template_id: string;
  name: string;
  description: string;
  source_category?: string | null;
  source_path?: string | null;
  color?: string | null;
}

export interface AgentTemplate extends AgentTemplateSummary {
  model?: string | null;
  tool_groups?: string[] | null;
  soul: string;
}
