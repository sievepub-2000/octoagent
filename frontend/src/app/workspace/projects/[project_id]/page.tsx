"use client";

import { useParams, useSearchParams } from "next/navigation";
import { TaskWorkspaceBoardSingleCard } from "@/components/workspace/task-workspace-board-single-card";

export default function ProjectDetailPage() {
  const { project_id } = useParams<{ project_id: string }>();
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") ?? undefined;
  return <TaskWorkspaceBoardSingleCard taskId={project_id ?? null} initialTab={initialTab} />;
}
