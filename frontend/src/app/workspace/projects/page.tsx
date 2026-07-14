"use client";

import { ArchiveIcon, FolderGit2Icon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getSurfaceCopy } from "@/core/i18n/surface-copy";
import { getWorkspaceLocaleCopy } from "@/core/i18n/workspace-copy";
import { useCreateProject, useProjects, useUpdateProject } from "@/core/projects/hooks";

const EMPTY_FORM = { name: "", root_path: "/home/sieve-pub/public-workspace", instructions: "" };

export default function ProjectsPage() {
  const { locale, t } = useI18n();
  const copy = getSurfaceCopy(locale).projects;
  const projectsCopy = getWorkspaceLocaleCopy(locale).projectsPage;
  const router = useRouter();
  const { data: projects = [], isLoading } = useProjects();
  const createProject = useCreateProject();
  const updateProject = useUpdateProject();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const submit = () => {
    createProject.mutate(form, {
      onSuccess: (project) => {
        toast.success(copy.created);
        setCreating(false);
        setForm(EMPTY_FORM);
        router.push(`/workspace/projects/${project.project_id}`);
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : copy.createFailed),
    });
  };

  return (
    <main className="mx-auto flex h-full w-full max-w-6xl flex-col overflow-y-auto px-6 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{t.sidebar.projects}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{copy.description}</p>
        </div>
        <Button size="sm" onClick={() => setCreating((value) => !value)}>
          <PlusIcon className="size-4" /> {projectsCopy.newProject}
        </Button>
      </header>

      {creating && (
        <section className="mb-6 space-y-4 rounded-xl border bg-card p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5 text-sm">{copy.name}<Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            <label className="space-y-1.5 text-sm">{copy.workingDirectory}<Input value={form.root_path} onChange={(event) => setForm({ ...form, root_path: event.target.value })} /></label>
          </div>
          <label className="block space-y-1.5 text-sm">{copy.instructions}<Textarea rows={4} value={form.instructions} onChange={(event) => setForm({ ...form, instructions: event.target.value })} placeholder={copy.instructionsPlaceholder} /></label>
          <div className="flex gap-2">
            <Button size="sm" disabled={!form.name.trim() || !form.root_path.trim() || createProject.isPending} onClick={submit}>{projectsCopy.create}</Button>
            <Button size="sm" variant="outline" onClick={() => setCreating(false)}>{t.common.cancel}</Button>
          </div>
        </section>
      )}

      <section className="overflow-hidden rounded-xl border bg-card">
        {isLoading ? <p className="p-6 text-sm text-muted-foreground">{copy.loading}</p> : projects.length === 0 ? (
          <div className="p-10 text-center"><FolderGit2Icon className="mx-auto mb-3 size-8 text-muted-foreground" /><p className="text-sm font-medium">{copy.emptyTitle}</p><p className="mt-1 text-sm text-muted-foreground">{copy.emptyDescription}</p></div>
        ) : projects.map((project) => (
          <div key={project.project_id} className="flex items-center gap-4 border-b p-4 last:border-b-0">
            <FolderGit2Icon className="size-5 shrink-0 text-muted-foreground" />
            <Link className="min-w-0 flex-1" href={`/workspace/projects/${project.project_id}`}>
              <div className="flex items-center gap-2"><span className="truncate text-sm font-medium">{project.name}</span>{project.branch && <Badge variant="secondary">{project.branch}</Badge>}</div>
              <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{project.root_path}</p>
            </Link>
            <Button aria-label={copy.archive} size="icon-sm" variant="ghost" onClick={() => updateProject.mutate({ projectId: project.project_id, input: { status: "archived" } })}><ArchiveIcon className="size-4" /></Button>
          </div>
        ))}
      </section>
    </main>
  );
}
