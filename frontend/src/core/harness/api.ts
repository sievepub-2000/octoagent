import { getBackendBaseURL } from "@/core/config";

export type PermissionProbe = {
  mode: "directory" | "system";
  adapter: "container-executor" | "host-root-executor";
  executable: boolean;
  identity: string;
  network: boolean;
  duration_ms?: number;
};

export async function verifyPermissionMode(
  mode: "directory" | "system",
): Promise<PermissionProbe> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/harness/permissions/verify`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    },
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<PermissionProbe>;
}
