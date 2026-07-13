import { redirect } from "next/navigation";

export default function LegacyWorkflowPage() {
  redirect("/workspace/projects");
}
