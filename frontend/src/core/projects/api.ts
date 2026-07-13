import { deleteJSON, getJSON, postJSON, putJSON } from "../api/http";

export interface Project {
  project_id: string;
  name: string;
  root_path: string;
  instructions: string;
  default_model: string;
  permission_mode: "approval" | "directory" | "system";
  status: "active" | "archived";
  repo_url: string;
  branch: string;
  created_at: string;
  updated_at: string;
  memory_summary: string;
  pinned_files: string[];
}

export interface ProjectCreateRequest {
  name: string;
  root_path: string;
  instructions?: string;
  default_model?: string;
  permission_mode?: Project["permission_mode"];
}

export type ProjectUpdateRequest = Partial<Omit<ProjectCreateRequest, "name">> & {
  name?: string;
  status?: Project["status"];
  pinned_files?: string[];
};

export const listProjects = () => getJSON<Project[]>("/api/projects");
export const createProject = (input: ProjectCreateRequest) => postJSON<Project>("/api/projects", input);
export const loadProject = (projectId: string) => getJSON<Project>(`/api/projects/${projectId}`);
export const updateProject = (projectId: string, input: ProjectUpdateRequest) => putJSON<Project>(`/api/projects/${projectId}`, input);
export const deleteProject = (projectId: string) => deleteJSON<void>(`/api/projects/${projectId}`);
export const loadProjectMemory = (projectId: string) => getJSON<Record<string, unknown>>(`/api/projects/${projectId}/memory`);
export const updateProjectMemory = (projectId: string, input: { summary: string }) => putJSON<Record<string, unknown>>(`/api/projects/${projectId}/memory`, input);
