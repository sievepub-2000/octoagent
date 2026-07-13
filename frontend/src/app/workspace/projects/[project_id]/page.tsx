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
import { useModels } from "@/core/models/hooks";
import { useProject, useProjectContext, useUpdateProject } from "@/core/projects/hooks";
import { useThreads } from "@/core/threads/hooks";

export default function ProjectDetailPage() {
  const { project_id: projectId } = useParams<{ project_id: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const { models } = useModels();
  const { data: effectiveContext } = useProjectContext(projectId);
  const { data: threads = [] } = useThreads();
  const updateProject = useUpdateProject();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ root_path: "", instructions: "", default_model: "", permission_mode: "directory" as "approval" | "directory" | "system", memory_summary: "", pinned_files: "" });
  const projectThreads = threads.filter((thread) => thread.values?.project_id === projectId);

  if (isLoading) return <p className="p-8 text-sm text-muted-foreground">Loading project…</p>;
  if (!project) return <p className="p-8 text-sm text-muted-foreground">Project not found.</p>;

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
      onSuccess: () => { setEditing(false); toast.success("Project settings saved"); },
      onError: (error) => toast.error(error instanceof Error ? error.message : "Could not save project"),
    },
  );

  return (
    <main className="mx-auto h-full w-full max-w-6xl overflow-y-auto px-6 py-8">
      <Link className="mb-5 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" href="/workspace/projects"><ArrowLeftIcon className="size-4" /> Projects</Link>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><FolderGit2Icon className="size-5" /><h1 className="truncate text-xl font-semibold">{project.name}</h1>{project.branch && <Badge variant="secondary">{project.branch}</Badge>}</div>
          <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{project.root_path}</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={editing ? () => setEditing(false) : beginEditing}>{editing ? <XIcon className="size-4" /> : <PencilIcon className="size-4" />}{editing ? "Cancel" : "Edit"}</Button>
          <Button asChild size="sm"><Link href={`/workspace/chats/new?project=${encodeURIComponent(projectId)}`}><MessageSquarePlusIcon className="size-4" /> New task</Link></Button>
        </div>
      </header>

      {editing && (
        <section className="grid gap-4 border-b py-6 md:grid-cols-2">
          <label className="space-y-1.5 text-sm md:col-span-2">Working directory<Input value={draft.root_path} onChange={(event) => setDraft({ ...draft, root_path: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">Default model<select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={draft.default_model} onChange={(event) => setDraft({ ...draft, default_model: event.target.value })}><option value="">System default</option>{models.map((model) => <option key={model.name} value={model.name}>{model.display_name || model.name}</option>)}</select></label>
          <label className="space-y-1.5 text-sm">Permission ceiling<select className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm" value={draft.permission_mode} onChange={(event) => setDraft({ ...draft, permission_mode: event.target.value as typeof draft.permission_mode })}><option value="approval">Approval</option><option value="directory">Directory</option><option value="system">System</option></select></label>
          <label className="space-y-1.5 text-sm md:col-span-2">Project instructions<Textarea rows={4} value={draft.instructions} onChange={(event) => setDraft({ ...draft, instructions: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">Project memory<Textarea rows={4} value={draft.memory_summary} onChange={(event) => setDraft({ ...draft, memory_summary: event.target.value })} /></label>
          <label className="space-y-1.5 text-sm">Pinned files, one per line<Textarea rows={4} value={draft.pinned_files} onChange={(event) => setDraft({ ...draft, pinned_files: event.target.value })} /></label>
          <div className="md:col-span-2"><Button size="sm" disabled={!draft.root_path.trim() || updateProject.isPending} onClick={save}><SaveIcon className="size-4" /> Save settings</Button></div>
        </section>
      )}

      <div className="grid gap-6 py-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section>
          <h2 className="mb-3 text-sm font-semibold">Tasks</h2>
          <div className="overflow-hidden rounded-xl border bg-card">
            {projectThreads.length === 0 ? <p className="p-6 text-sm text-muted-foreground">No tasks in this project yet.</p> : projectThreads.map((thread) => (
              <Link key={thread.thread_id} className="block border-b p-4 last:border-b-0 hover:bg-muted/40" href={`/workspace/chats/${thread.thread_id}`}>
                <p className="text-sm font-medium">{thread.values?.title || "Untitled task"}</p>
                <p className="mt-1 text-xs text-muted-foreground">{new Date(thread.updated_at).toLocaleString()}</p>
              </Link>
            ))}
          </div>
        </section>
        <aside className="space-y-5 rounded-xl border bg-card p-5">
          <div><h2 className="text-sm font-semibold">Instructions</h2><p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{project.instructions || "No project-specific instructions."}</p></div>
          <div><h2 className="text-sm font-semibold">Effective context</h2><dl className="mt-2 space-y-2 text-sm text-muted-foreground"><div className="flex justify-between gap-3"><dt>Permission</dt><dd>{effectiveContext?.permission_mode ?? project.permission_mode}</dd></div><div className="flex justify-between gap-3"><dt>Model</dt><dd className="truncate">{effectiveContext?.model_name || "System default"}</dd></div><div className="flex justify-between gap-3"><dt>Workspace</dt><dd>Project root</dd></div></dl></div>
          {project.pinned_files.length > 0 && <div><h2 className="text-sm font-semibold">Pinned files</h2><ul className="mt-2 space-y-1 font-mono text-xs text-muted-foreground">{project.pinned_files.map((file) => <li key={file} className="truncate">{file}</li>)}</ul></div>}
        </aside>
      </div>
    </main>
  );
}
