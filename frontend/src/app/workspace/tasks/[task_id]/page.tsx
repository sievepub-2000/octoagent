import { redirect } from "next/navigation";

export default async function TaskWorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ task_id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { task_id } = await params;
  const { tab } = await searchParams;
  redirect(tab ? `/workspace/workflows/${task_id}?tab=${encodeURIComponent(tab)}` : `/workspace/workflows/${task_id}`);
}
