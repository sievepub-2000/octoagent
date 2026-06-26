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
  MessageSquareIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
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
  copy,
  onEdit,
  onDelete,
}: {
  project: ProjectSummary;
  copy: ReturnType<typeof getWorkspaceLocaleCopy>["projectsPage"];
  onEdit: () => void;
  onDelete: () => void;
}) {
  const status = STATUS_CONFIG[project.status] ?? { icon: <FolderKanbanIcon className="size-3" />, label: project.status, variant: "outline" as const };

  return (
    <div className="octo-panel octo-management-card flex min-w-0 flex-col rounded-[1.5rem] p-3 transition-shadow hover:translate-y-[-1px] hover:shadow-[3px_3px_7px_var(--neu-dark-strong),-3px_-3px_7px_var(--neu-light-soft)]">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h2 className="min-w-0 break-words text-sm font-medium text-foreground">
          {project.name}
        </h2>
        <div className="octo-card-actions ml-2">
          <Badge variant={status.variant} className="text-[10px]">
            {status.icon}
            <span className="ml-1">{status.label}</span>
          </Badge>
        </div>
      </div>
      {project.goal && (
        <p className="mb-3 break-words line-clamp-2 text-xs text-muted-foreground">{project.goal}</p>
      )}
      {project.memory_summary && (
        <p className="mb-2 text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-2">{project.memory_summary}</p>
      )}
      <div className="mt-auto flex items-center justify-between gap-2">
        <Link href={`/workspace/projects/${project.project_id}`} className="flex-1">
          <Button size="sm" className="octo-card-primary-action w-full">
            <MessageSquareIcon className="mr-1.5 size-3.5" />
            {copy.openProject}
          </Button>
        </Link>
        <div className="octo-card-actions">
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
              if (window.confirm(copy.deleteConfirm(project.name))) {
                onDelete();
              }
            }}
          >
            <Trash2Icon className="size-3.5 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const { t, locale } = useI18n();
  const copy = getWorkspaceLocaleCopy(locale).projectsPage;
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
            toast.success(copy.projectUpdated);
            setIsFormOpen(false);
            setForm(EMPTY_FORM);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : copy.saveFailed),
        },
      );
    } else {
      createProject.mutate(
        { name: form.name.trim(), goal: form.goal.trim() },
        {
          onSuccess: () => {
            toast.success(copy.projectCreated);
            setIsFormOpen(false);
            setForm(EMPTY_FORM);
          },
          onError: (err) => toast.error(err instanceof Error ? err.message : copy.saveFailed),
        },
      );
    }
  }

  function handleDelete(projectId: string) {
    deleteProject.mutate(projectId, {
      onSuccess: () => toast.success(copy.projectDeleted),
      onError: (err) => toast.error(err instanceof Error ? err.message : copy.deleteFailed),
    });
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t.sidebar.projects}</h1>
          <p className="text-sm text-muted-foreground">{copy.pageDescription}</p>
        </div>
        <Button size="sm" onClick={startCreate}>
          <PlusIcon className="size-4" />
          <span className="ml-1">{copy.newProject}</span>
        </Button>
      </header>

      {isFormOpen && (
        <div className="octo-panel mb-6 rounded-[1.5rem] p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-foreground">
                {isEditing ? copy.editProject : copy.newProject}
              </div>
              <p className="text-xs text-muted-foreground">{copy.pageDescription}</p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1">
              <span className="text-xs font-medium text-muted-foreground">{copy.projectName}</span>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="My Project"
              />
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-xs font-medium text-muted-foreground">{copy.goal}</span>
              <Textarea
                value={form.goal}
                onChange={(e) => setForm((f) => ({ ...f, goal: e.target.value }))}
                placeholder={copy.goalPlaceholder}
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
              <span className="ml-1">{isEditing ? copy.saveChanges : copy.create}</span>
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => { setIsFormOpen(false); setForm(EMPTY_FORM); }}
            >
              {copy.close}
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
          <p className="text-sm">{copy.noProjects}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.project_id}
              project={project}
              copy={copy}
              onEdit={() => startEdit(project)}
              onDelete={() => handleDelete(project.project_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
