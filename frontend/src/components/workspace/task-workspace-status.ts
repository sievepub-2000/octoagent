export function statusTone(status: string) {
  if (status === "running" || status === "completed") return "default" as const;
  if (status === "paused" || status === "waiting_review") return "secondary" as const;
  if (status === "failed" || status === "terminated") return "destructive" as const;
  return "outline" as const;
}
