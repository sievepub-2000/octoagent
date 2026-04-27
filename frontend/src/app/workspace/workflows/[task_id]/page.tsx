"use client";

import { useParams, useSearchParams } from "next/navigation";

import { TaskWorkspaceBoardSingleCard } from "@/components/workspace/task-workspace-board-single-card";

export default function WorkflowTaskPage() {
	const { task_id } = useParams<{ task_id: string }>();
	const searchParams = useSearchParams();
	const initialTab = searchParams.get("tab") ?? undefined;

	return <TaskWorkspaceBoardSingleCard taskId={task_id ?? null} initialTab={initialTab} />;
}
