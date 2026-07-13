import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProject,
  listProjects,
  loadProject,
  loadProjectContext,
  updateProject,
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

export function useProjectContext(projectId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId, "context"],
    queryFn: () => loadProjectContext(projectId!),
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
