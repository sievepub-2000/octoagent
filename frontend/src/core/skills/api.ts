import { deleteJSON, getJSON, postJSON, putJSON } from "@/core/api/http";

import type { Skill } from "./type";

export async function loadSkills() {
  const json = await getJSON<{ skills: Skill[] }>("/api/skills");
  return json.skills;
}

export async function enableSkill(skillName: string, enabled: boolean) {
  return putJSON(`/api/skills/${skillName}`, { enabled });
}

export interface UpdateSkillRequest {
  description?: string;
  license?: string;
  content?: string;
}

export async function updateSkill(skillName: string, request: UpdateSkillRequest) {
  return putJSON<Skill>(`/api/skills/${skillName}`, request);
}

export async function deleteSkill(skillName: string) {
  return deleteJSON(`/api/skills/${skillName}`);
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  license?: string;
  content?: string;
}

export async function createSkill(request: CreateSkillRequest) {
  return postJSON<Skill>("/api/skills", request);
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

export interface InstallAgencyAgentsResponse {
  success: boolean;
  skill_name: string;
  template_count: number;
  message: string;
}

export async function installSkill(
  request: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  try {
    return await postJSON<InstallSkillResponse>("/api/skills/install", request);
  } catch (error) {
    return {
      success: false,
      skill_name: "",
      message: error instanceof Error ? error.message : "Skill install failed",
    };
  }
}

export async function installAgencyAgents(): Promise<InstallAgencyAgentsResponse> {
  return postJSON<InstallAgencyAgentsResponse>("/api/skills/install/agency-agents", {});
}
