"use client";

import { WorkflowsProvider } from "@/core/workflows";

export default function AgentsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <WorkflowsProvider>{children}</WorkflowsProvider>;
}
