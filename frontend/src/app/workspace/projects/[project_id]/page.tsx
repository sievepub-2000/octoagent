"use client";

import { ArrowLeftIcon, FolderGit2Icon, MessageSquarePlusIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useProject } from "@/core/projects/hooks";
import { useThreads } from "@/core/threads/hooks";

export default function ProjectDetailPage() {
  const { project_id: projectId } = useParams<{ project_id: string }>();
  const { data: project, isLoading } = useProject(projectId);
  const { data: threads = [] } = useThreads();
  const projectThreads = threads.filter((thread) => thread.values?.project_id === projectId);

  if (isLoading) return <p className="p-8 text-sm text-muted-foreground">Loading project…</p>;
  if (!project) return <p className="p-8 text-sm text-muted-foreground">Project not found.</p>;

  return (
    <main className="mx-auto h-full w-full max-w-6xl overflow-y-auto px-6 py-8">
      <Link className="mb-5 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" href="/workspace/projects"><ArrowLeftIcon className="size-4" /> Projects</Link>
      <header className="flex flex-wrap items-start justify-between gap-4 border-b pb-6">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><FolderGit2Icon className="size-5" /><h1 className="truncate text-xl font-semibold">{project.name}</h1>{project.branch && <Badge variant="secondary">{project.branch}</Badge>}</div>
          <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{project.root_path}</p>
        </div>
        <Button asChild size="sm"><Link href={`/workspace/chats/new?project=${encodeURIComponent(projectId)}`}><MessageSquarePlusIcon className="size-4" /> New task</Link></Button>
      </header>

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
          <div><h2 className="text-sm font-semibold">Defaults</h2><dl className="mt-2 space-y-2 text-sm text-muted-foreground"><div className="flex justify-between gap-3"><dt>Permission</dt><dd>{project.permission_mode}</dd></div><div className="flex justify-between gap-3"><dt>Model</dt><dd>{project.default_model || "System default"}</dd></div></dl></div>
        </aside>
      </div>
    </main>
  );
}
