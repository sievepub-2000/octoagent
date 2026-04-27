import fs from "fs";
import path from "path";

import type { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  {
    params,
  }: {
    params: Promise<{
      thread_id: string;
      artifact_path?: string[] | undefined;
    }>;
  },
) {
  const threadId = (await params).thread_id;
  const requestedArtifactPath = (await params).artifact_path?.join("/") ?? "";
  if (requestedArtifactPath.startsWith("mnt/")) {
    const demoThreadRoot = path.join(
      process.cwd(),
      "public",
      "demo",
      "threads",
      threadId,
    );
    const relativeArtifactPath = requestedArtifactPath.replace(/^mnt\//, "");
    const resolvedArtifactPath = path.normalize(
      path.join(demoThreadRoot, relativeArtifactPath),
    );
    const staysWithinThreadRoot =
      resolvedArtifactPath === demoThreadRoot
      || resolvedArtifactPath.startsWith(`${demoThreadRoot}${path.sep}`);

    if (!staysWithinThreadRoot) {
      return new Response("File not found", { status: 404 });
    }

    if (fs.existsSync(resolvedArtifactPath)) {
      if (request.nextUrl.searchParams.get("download") === "true") {
        // Attach the file to the response
        const headers = new Headers();
        headers.set(
          "Content-Disposition",
          `attachment; filename="${resolvedArtifactPath}"`,
        );
        return new Response(fs.readFileSync(resolvedArtifactPath), {
          status: 200,
          headers,
        });
      }
      if (resolvedArtifactPath.endsWith(".mp4")) {
        return new Response(fs.readFileSync(resolvedArtifactPath), {
          status: 200,
          headers: {
            "Content-Type": "video/mp4",
          },
        });
      }
      return new Response(fs.readFileSync(resolvedArtifactPath), { status: 200 });
    }
  }
  return new Response("File not found", { status: 404 });
}
