"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function WorkflowsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/workspace/projects");
  }, [router]);

  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Redirecting to projects...
    </div>
  );
}
