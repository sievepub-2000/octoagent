import { redirect } from "next/navigation";

export default function LegacyTaskPage() {
  redirect("/workspace/projects");
}
