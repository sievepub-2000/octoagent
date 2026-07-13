"use client";

import { ArchiveIcon, FolderGit2Icon, PlusIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateProject, useDeleteProject, useProjects, useUpdateProject } from "@/core/projects/hooks";

const EMPTY_FORM = { name: "", root_path: "/home/sieve-pub/public-workspace", instructions: "" };

export default function ProjectsPage() {
  const router = useRouter();
  const { data: projects = [], isLoading } = useProjects();
  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();
  const updateProject = useUpdateProject();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const submit = () => {
    createProject.mutate(form, {
      onSuccess: (project) => {
        toast.success("Project created");
        setCreating(false);
        setForm(EMPTY_FORM);
        router.push(`/workspace/projects/${project.project_id}`);
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : "Could not create project"),
    });
  };

  return (
    <main className="mx-auto flex h-full w-full max-w-6xl flex-col overflow-y-auto px-6 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">Persistent working directories, instructions, and task history.</p>
        </div>
        <Button size="sm" onClick={() => setCreating((value) => !value)}>
          <PlusIcon className="size-4" /> New project
        </Button>
      </header>

      {creating && (
        <section className="mb-6 space-y-4 rounded-xl border bg-card p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5 text-sm">Name<Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">Working directory<Input value={form.root_path} onChange={(event) => setForm({ ...form, root_path: event.target.value })} /></label>
          </div>
          <label className="block space-y-1.5 text-sm">Project instructions<Textarea rows={4} value={form.instructions} onChange={(event) => setForm({ ...form, instructions: event.target.value })} placeholder="Repository conventions, goals, and constraints" /></label>
          <div className="flex gap-2">
            <Button size="sm" disabled={!form.name.trim() || !form.root_path.trim() || createProject.isPending} onClick={submit}>Create project</Button>
            <Button size="sm" variant="outline" onClick={() => setCreating(false)}>Cancel</Button>
          </div>
        </section>
      )}

      <section className="overflow-hidden rounded-xl border bg-card">
        {isLoading ? <p className="p-6 text-sm text-muted-foreground">Loading projects…</p> : projects.length === 0 ? (
          <div className="p-10 text-center"><FolderGit2Icon className="mx-auto mb-3 size-8 text-muted-foreground" /><p className="text-sm font-medium">No projects yet</p><p className="mt-1 text-sm text-muted-foreground">Add a working directory to group tasks and instructions.</p></div>
        ) : projects.map((project) => (
          <div key={project.project_id} className="flex items-center gap-4 border-b p-4 last:border-b-0">
            <FolderGit2Icon className="size-5 shrink-0 text-muted-foreground" />
            <Link className="min-w-0 flex-1" href={`/workspace/projects/${project.project_id}`}>
              <div className="flex items-center gap-2"><span className="truncate text-sm font-medium">{project.name}</span>{project.branch && <Badge variant="secondary">{project.branch}</Badge>}</div>
              <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{project.root_path}</p>
            </Link>
            <Button aria-label="Archive project" size="icon-sm" variant="ghost" onClick={() => updateProject.mutate({ projectId: project.project_id, input: { status: "archived" } })}><ArchiveIcon className="size-4" /></Button>
            <Button aria-label="Delete project" size="icon-sm" variant="ghost" onClick={() => { if (window.confirm(`Delete ${project.name}?`)) deleteProject.mutate(project.project_id); }}><Trash2Icon className="size-4" /></Button>
          </div>
        ))}
      </section>
    </main>
  );
}
