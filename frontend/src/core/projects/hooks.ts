import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProject,
  deleteProject,
  listProjects,
  loadProject,
  updateProject,
  updateProjectMemory,
} from "./api";
import type { ProjectCreateRequest, ProjectUpdateRequest } from "./api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });
}

export function useProject(projectId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: () => loadProject(projectId!),
    enabled: !!projectId,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectCreateRequest) => createProject(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, input }: { projectId: string; input: ProjectUpdateRequest }) =>
      updateProject(projectId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useUpdateProjectMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, input }: { projectId: string; input: { summary: string } }) =>
      updateProjectMemory(projectId, input),
    onSuccess: (_data, { projectId }) => {
      qc.invalidateQueries({ queryKey: ["projects", projectId] });
    },
  });
}
