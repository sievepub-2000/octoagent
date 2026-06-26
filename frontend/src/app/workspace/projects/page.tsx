"use client";

import {
  FolderKanbanIcon,
  InfoIcon,
  Edit3Icon,
  Trash2Icon,
  PlusIcon,
  SaveIcon,
  Loader2Icon,
  CheckCircle2Icon,
  PlayIcon,
  PauseIcon,
  XCircleIcon,
  AlertCircleIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
  useUpdateProject,
} from "@/core/projects/hooks";
import type { ProjectSummary } from "@/core/projects/api";

const EMPTY_FORM = { name: "", goal: "" };

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  completed: { icon: <CheckCircle2Icon className="size-3" />, label: "Completed", variant: "default" },
  running: { icon: <PlayIcon className="size-3" />, label: "Running", variant: "default" },
  active: { icon: <PlayIcon className="size-3" />, label: "Active", variant: "default" },
  paused: { icon: <PauseIcon className="size-3" />, label: "Paused", variant: "secondary" },
  failed: { icon: <XCircleIcon className="size-3" />, label: "Failed", variant: "destructive" },
  error: { icon: <AlertCircleIcon className="size-3" />, label: "Error", variant: "destructive" },
  created: { icon: <InfoIcon className="size-3" />, label: "Created", variant: "outline" },
};

function ProjectCard({
  project,
  onEdit,
  onDelete,
}: {
  project: ProjectSummary;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const status = STATUS_CONFIG[project.status] ?? { icon: <FolderKanbanIcon className="size-3" />, label: project.status, variant: "outline" as const };

  return (
    <div
      className="octo-panel octo-management-card flex min-w-0 flex-col rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),-3px_-3px_7px_var(--neu-light-soft)]"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <h2 className="min-w-0 break-words text-sm font-medium text-foreground">
          {project.name}
        </h2>
        <div className="octo-card-actions ml-2">
          <Badge variant={status.variant} className="text-[10px]">
            {status.icon}
            <span className="ml-1">{status.label}</span>
          </Badge>
          <Button
            size="icon"
            variant="ghost"
            className="octo-card-action"
            title="Edit"
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
          >
            <Edit3Icon className="size-3.5 text-muted-foreground hover:text-primary" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="octo-card-action"
            title="Delete"
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) {
                onDelete();
              }
            }}
          >
            <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>
      </div>
      {project.goal && (
        <p className="mb-3 break-words line-clamp-2 text-xs text-muted-foreground">{project.goal}</p>
      )}
      {project.memory_summary && (
        <p className="mb-2 text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-2">{project.memory_summary}</p>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const { t } = useI18n();
  const { data: projects, isLoading } = useProjects();
  const createProject = useCreateProject();
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  function startCreate() {
    setIsEditing(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setIsFormOpen(true);
  }

  function startEdit(project: ProjectSummary) {
    setIsEditing(true);
    setEditingId(project.project_id);
    setForm({ name: project.name, goal: project.goal });
    setIsFormOpen(true);
  }

  function handleSave() {
    if (!form.name.trim()) return;
    if (isEditing && editingId) {
      updateProject.mutate(
        { projectId: editingId, input: { name: form.name.trim(), goal: form.goal.trim() } },
        {
          onSuccess: () => {
            toast.success("Project updated");
            setIsFormOpen(false);
            setForm(EMPTY_FORM);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to update project"),
        },
      );
    } else {
      createProject.mutate(
        { name: form.name.trim(), goal: form.goal.trim() },
        {
          onSuccess: () => {
            toast.success("Project created");
            setIsFormOpen(false);
            setForm(EMPTY_FORM);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to create project"),
        },
      );
    }
  }

  function handleDelete(projectId: string) {
    deleteProject.mutate(projectId, {
      onSuccess: () => toast.success("Project deleted"),
      onError: (err) => toast.error(err instanceof Error ? err.message : "Failed to delete project"),
    });
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t.sidebar.projects}</h1>
          <p className="text-sm text-muted-foreground">
            Manage projects and their isolated memory spaces.
          </p>
        </div>
        <Button size="sm" onClick={startCreate}>
          <PlusIcon className="size-4" />
          <span className="ml-1">New Project</span>
        </Button>
      </header>

      {isFormOpen && (
        <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-foreground">
                {isEditing ? "Edit Project" : "New Project"}
              </div>
              <p className="text-xs text-muted-foreground">
                {isEditing ? "Update project name and goal." : "Create a new project to organize your work."}
              </p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">Project Name</span>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="My Project"
              />
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-xs font-medium text-muted-foreground">Goal</span>
              <Textarea
                value={form.goal}
                onChange={(e) => setForm((f) => ({ ...f, goal: e.target.value }))}
                placeholder="Describe the project goal..."
                rows={3}
              />
            </label>
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!form.name.trim() || createProject.isPending || updateProject.isPending}
            >
              <SaveIcon className="size-4" />
              <span className="ml-1">{isEditing ? "Save Changes" : "Create"}</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => { setIsFormOpen(false); setForm(EMPTY_FORM); }}
            >
              Close
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2Icon className="size-8 animate-spin text-muted-foreground" />
        </div>
      ) : !projects?.length ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <FolderKanbanIcon className="mb-3 size-10 opacity-30" />
          <p className="text-sm">No projects yet. Create your first project to get started.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.project_id}
              project={project}
              onEdit={() => startEdit(project)}
              onDelete={() => handleDelete(project.project_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
