import {
  deleteJSON,
  getJSON,
  postJSON,
  putJSON,
} from "@/core/api/http";
import { getBackendBaseURL } from "@/core/config";

import type {
  Agent,
  AgentTemplate,
  AgentTemplateSummary,
  CreateAgentRequest,
  UpdateAgentRequest,
} from "./types";

type AgentConversationArchiveMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  created_at?: string | null;
};

export async function listAgents(): Promise<Agent[]> {
  const data = await getJSON<{ agents: Agent[] }>("/api/agents");
  return data.agents;
}

export async function getAgent(name: string): Promise<Agent> {
  return getJSON<Agent>(`/api/agents/${name}`);
}

export async function createAgent(request: CreateAgentRequest): Promise<Agent> {
  return postJSON<Agent>("/api/agents", request);
}

export async function listAgentTemplates(): Promise<AgentTemplateSummary[]> {
  const data = await getJSON<{ templates: AgentTemplateSummary[] }>("/api/agent-templates");
  return data.templates;
}

export async function getAgentTemplate(skillName: string, templateId: string): Promise<AgentTemplate> {
  return getJSON<AgentTemplate>(
    `/api/agent-templates/${encodeURIComponent(skillName)}/${encodeURIComponent(templateId)}`,
  );
}

export async function updateAgent(
  name: string,
  request: UpdateAgentRequest,
): Promise<Agent> {
  return putJSON<Agent>(`/api/agents/${name}`, request);
}

export async function deleteAgent(name: string): Promise<void> {
  await deleteJSON<void>(`/api/agents/${name}`);
}

export async function checkAgentName(
  name: string,
): Promise<{ available: boolean; name: string }> {
  return getJSON<{ available: boolean; name: string }>("/api/agents/check", {
    name,
  });
}

export async function uploadAgentAvatar(
  name: string,
  file: File,
): Promise<{ avatar: string; size: number }> {
  const formData = new FormData();
  formData.append("file", file);
  const base = getBackendBaseURL() || "";
  const resp = await fetch(`${base}/api/agents/${encodeURIComponent(name)}/avatar`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail ?? "Failed to upload avatar");
  }
  return resp.json();
}

export function agentAvatarUrl(name: string): string {
  const base = getBackendBaseURL() || "";
  return `${base}/api/agents/${encodeURIComponent(name)}/avatar`;
}

export async function archiveAgentConversation(
  name: string,
  threadId: string,
  payload: {
    title?: string | null;
    updated_at?: string | null;
    continuation?: Record<string, unknown> | null;
    messages: AgentConversationArchiveMessage[];
  },
) {
  return putJSON<{ thread_id: string; message_count: number }>(
    `/api/agents/${encodeURIComponent(name)}/conversations/${encodeURIComponent(threadId)}`,
    payload,
  );
}
