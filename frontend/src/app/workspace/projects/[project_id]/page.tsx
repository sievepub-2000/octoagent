"use client";

import { ArrowLeftIcon, FolderGit2Icon, MessageSquarePlusIcon, PencilIcon, SaveIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { getSurfaceCopy } from "@/core/i18n/surface-copy";
import { useModels } from "@/core/models/hooks";
import { useProject, useProjectContext, useUpdateProject } from "@/core/projects/hooks";
import { useThreads } from "@/core/threads/hooks";

export default function ProjectDetailPage() {
  const { locale, t } = useI18n();
  const copy = getSurfaceCopy(locale).projects;
  const { project_id: projectId } = useParams<{ project_id: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const { models } = useModels();
  const { data: effectiveContext } = useProjectContext(projectId);
  const { data: threads = [] } = useThreads();
  const updateProject = useUpdateProject();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ root_path: "", instructions: "", default_model: "", permission_mode: "directory" as "approval" | "directory" | "system", memory_summary: "", pinned_files: "" });
  const projectThreads = threads.filter((thread) => thread.values?.project_id === projectId);

  if (isLoading) return <p className="p-8 text-sm text-muted-foreground">{copy.loadingOne}</p>;
  if (!project) return <p className="p-8 text-sm text-muted-foreground">{copy.notFound}</p>;

  const beginEditing = () => {
    setDraft({
      root_path: project.root_path,
      instructions: project.instructions,
      default_model: project.default_model,
      permission_mode: project.permission_mode,
      memory_summary: project.memory_summary,
      pinned_files: project.pinned_files.join("\n"),
    });
    setEditing(true);
  };
  const save = () => updateProject.mutate(
    {
      projectId,
      input: {
        root_path: draft.root_path,
        instructions: draft.instructions,
        default_model: draft.default_model,
        permission_mode: draft.permission_mode,
        memory_summary: draft.memory_summary,
        pinned_files: draft.pinned_files.split("\n").map((value) => value.trim()).filter(Boolean),
      },
    },
    {
      onSuccess: () => { setEditing(false); toast.success(copy.saved); },
      onError: (error) => toast.error(error instanceof Error ? error.message : copy.saveFailed),
    },
  );

  return (
    <main className="mx-auto h-full w-full max-w-6xl overflow-y-auto px-6 py-8">
      <Link className="mb-5 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" href="/workspace/projects"><ArrowLeftIcon className="size-4" /> {t.sidebar.projects}</Link>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><FolderGit2Icon className="size-5" /><h1 className="truncate text-xl font-semibold">{project.name}</h1>{project.branch && <Badge variant="secondary">{project.branch}</Badge>}</div>
          <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{project.root_path}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={editing ? () => setEditing(false) : beginEditing}>{editing ? <XIcon className="size-4" /> : <PencilIcon className="size-4" />}{editing ? t.common.cancel : copy.edit}</Button>
          <Button asChild size="sm"><Link href={`/workspace/chats/new?project=${encodeURIComponent(projectId)}`}><MessageSquarePlusIcon className="size-4" /> {copy.newTask}</Link></Button>
        </div>
      </header>

      {editing && (
        <section className="grid gap-4 border-b py-6 md:grid-cols-2">
          <label className="space-y-1.5 text-sm md:col-span-2">{copy.workingDirectory}<Input value={draft.root_path} onChange={(event) => setDraft({ ...draft, root_path: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">{copy.defaultModel}<select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={draft.default_model} onChange={(event) => setDraft({ ...draft, default_model: event.target.value })}><option value="">{copy.systemDefault}</option>{models.map((model) => <option key={model.name} value={model.name}>{model.display_name || model.name}</option>)}</select></label>
          <label className="space-y-1.5 text-sm">{copy.permissionCeiling}<select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={draft.permission_mode} onChange={(event) => setDraft({ ...draft, permission_mode: event.target.value as typeof draft.permission_mode })}><option value="approval">{copy.approval}</option><option value="directory">{copy.directory}</option><option value="system">{copy.system}</option></select></label>
          <label className="space-y-1.5 text-sm md:col-span-2">{copy.instructions}<Textarea rows={4} value={draft.instructions} onChange={(event) => setDraft({ ...draft, instructions: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">{copy.memory}<Textarea rows={4} value={draft.memory_summary} onChange={(event) => setDraft({ ...draft, memory_summary: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">{copy.pinnedFilesHint}<Textarea rows={4} value={draft.pinned_files} onChange={(event) => setDraft({ ...draft, pinned_files: event.target.value })} /></label>
          <div className="md:col-span-2"><Button size="sm" disabled={!draft.root_path.trim() || updateProject.isPending} onClick={save}><SaveIcon className="size-4" /> {copy.saveSettings}</Button></div>
        </section>
      )}

      <div className="grid gap-6 py-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section>
          <h2 className="mb-3 text-sm font-semibold">{copy.tasks}</h2>
          <div className="overflow-hidden rounded-xl border bg-card">
            {projectThreads.length === 0 ? <p className="p-6 text-sm text-muted-foreground">{copy.emptyTasks}</p> : projectThreads.map((thread) => (
              <Link key={thread.thread_id} className="block border-b p-4 last:border-b-0 hover:bg-muted/40" href={`/workspace/chats/${thread.thread_id}`}>
                <p className="text-sm font-medium">{thread.values?.title || copy.untitledTask}</p>
                <p className="mt-1 text-xs text-muted-foreground">{new Date(thread.updated_at).toLocaleString()}</p>
              </Link>
            ))}
          </div>
        </section>
        <aside className="space-y-5 rounded-xl border bg-card p-5">
          <div><h2 className="text-sm font-semibold">{copy.instructions}</h2><p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{project.instructions || copy.noInstructions}</p></div>
          <div><h2 className="text-sm font-semibold">{copy.effectiveContext}</h2><dl className="mt-2 space-y-2 text-sm text-muted-foreground"><div className="flex justify-between gap-3"><dt>{copy.permission}</dt><dd>{effectiveContext?.permission_mode ?? project.permission_mode}</dd></div><div className="flex justify-between gap-3"><dt>{copy.model}</dt><dd className="truncate">{effectiveContext?.model_name || copy.systemDefault}</dd></div><div className="flex justify-between gap-3"><dt>{copy.workspace}</dt><dd>{copy.projectRoot}</dd></div></dl></div>
          {project.pinned_files.length > 0 && <div><h2 className="text-sm font-semibold">{copy.pinnedFiles}</h2><ul className="mt-2 space-y-1 font-mono text-xs text-muted-foreground">{project.pinned_files.map((file) => <li key={file} className="truncate">{file}</li>)}</ul></div>}
        </aside>
      </div>
    </main>
  );
}
