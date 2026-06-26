"use client";

import { PlusIcon, ExternalLinkIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { getJSON, postJSON, deleteJSON } from "@/core/api/http";
import { useI18n } from "@/core/i18n/hooks";

interface ProjectSummary {
  project_id: string;
  name: string;
  goal: string;
  status: string;
  created_at: string;
  updated_at: string;
  memory_summary: string;
}

export default function ProjectsPage() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newGoal, setNewGoal] = useState("");

  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => getJSON<ProjectSummary[]>("/api/projects"),
  });

  const createMutation = useMutation({
    mutationFn: () => postJSON("/api/projects", { name: newName, goal: newGoal }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setCreateOpen(false);
      setNewName(""); setNewGoal("");
      toast.success("Project created");
    },
    onError: () => toast.error("Failed to create project"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteJSON(`/api/projects/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project deleted");
    },
    onError: () => toast.error("Failed to delete project"),
  });

  const statusIcon = (s: string) => {
    switch (s) {
      case "completed": return "\u2705";
      case "running": case "active": return "\U0001f504";
      case "failed": case "error": return "\u274c";
      case "paused": return "\u23f8\ufe0f";
      default: return "\U0001f4cb";
    }
  };

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t.sidebar.projects}</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="mr-2 size-4" /> New Project
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2Icon className="size-8 animate-spin text-muted-foreground" />
        </div>
      ) : !projects?.length ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <p className="text-lg mb-2">No projects yet</p>
          <p className="text-sm mb-4">Create your first project to get started.</p>
          <Button variant="outline" onClick={() => setCreateOpen(true)}>
            <PlusIcon className="mr-2 size-4" /> Create Project
          </Button>
        </div>
      ) : (
        <div className="grid gap-3">
          {projects.map((p) => (
            <Link
              key={p.project_id}
              href={`/workspace/projects/${p.project_id}`}
              className="flex items-center justify-between rounded-lg border p-4 hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-lg">{statusIcon(p.status)}</span>
                <div className="min-w-0">
                  <div className="font-medium truncate">{p.name}</div>
                  {p.goal && <div className="text-sm text-muted-foreground truncate">{p.goal}</div>}
                  {p.memory_summary && (
                    <div className="text-xs text-muted-foreground/70 truncate mt-1">
                      {p.memory_summary}
                    </div>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  p.status === "completed" ? "bg-green-100 text-green-700" :
                  p.status === "running" || p.status === "active" ? "bg-blue-100 text-blue-700" :
                  p.status === "failed" || p.status === "error" ? "bg-red-100 text-red-700" :
                  "bg-gray-100 text-gray-600"
                }`}>{p.status}</span>
                <ExternalLinkIcon className="size-4 text-muted-foreground" />
              </div>
            </Link>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Project</DialogTitle>
            <DialogDescription>Create a new project to organize your work.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Input placeholder="Project name" value={newName} onChange={e => setNewName(e.target.value)} />
            <Textarea placeholder="Goal / description (optional)" value={newGoal} onChange={e => setNewGoal(e.target.value)} rows={3} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={() => createMutation.mutate()} disabled={!newName.trim() || createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
