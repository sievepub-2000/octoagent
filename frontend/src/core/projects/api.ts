import { deleteJSON, getJSON, postJSON, putJSON } from "../api/http";

export interface ProjectSummary {
  project_id: string;
  name: string;
  goal: string;
  status: string;
  created_at: string;
  updated_at: string;
  progress: Record<string, unknown>;
  memory_summary: string;
}

export interface ProjectDetail extends ProjectSummary {
  summary: string;
  agents: Array<{ agent_id: string; name: string; role: string; status: string }>;
  run_log: string;
  artifacts: string[];
  timeline: Array<{ created_at: string; title: string; details: string[] }>;
  memory: Record<string, unknown>;
}

export interface ProjectCreateRequest {
  name: string;
  goal?: string;
}

export interface ProjectUpdateRequest {
  name?: string;
  goal?: string;
}

export interface ProjectMemoryUpdateRequest {
  summary: string;
}

export async function listProjects() {
  return getJSON<ProjectSummary[]>("/api/projects");
}

export async function createProject(input: ProjectCreateRequest) {
  return postJSON<ProjectDetail>("/api/projects", input);
}

export async function loadProject(projectId: string) {
  return getJSON<ProjectDetail>(`/api/projects/${projectId}`);
}

export async function updateProject(projectId: string, input: ProjectUpdateRequest) {
  return putJSON<ProjectDetail>(`/api/projects/${projectId}`, input);
}

export async function deleteProject(projectId: string) {
  return deleteJSON<void>(`/api/projects/${projectId}`);
}

export async function loadProjectMemory(projectId: string) {
  return getJSON<Record<string, unknown>>(`/api/projects/${projectId}/memory`);
}

export async function updateProjectMemory(projectId: string, input: ProjectMemoryUpdateRequest) {
  return putJSON<Record<string, unknown>>(`/api/projects/${projectId}/memory`, input);
}
