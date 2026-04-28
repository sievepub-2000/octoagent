const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const repoRoot = path.resolve(__dirname, "../..");
const frontendRequire = createRequire(path.join(repoRoot, "frontend/package.json"));
const { chromium } = require(path.join(
  __dirname,
  "../node_modules/.pnpm/playwright@1.59.1/node_modules/playwright",
));
const { Client } = frontendRequire("@langchain/langgraph-sdk/client");

const baseUrl = process.argv[2] || process.env.WEBUI || "http://127.0.0.1:19880";
const outputDir = path.join(repoRoot, "tmp");

function isFatalBrowserMessage(text) {
  return /Maximum update depth exceeded|Permission denied when creating directories|\[ChatThreadError\]/i.test(text);
}

async function createThread(page) {
  await page.goto(`${baseUrl}/workspace/chats/new`, { waitUntil: "networkidle" });
  await page.locator('textarea[name="message"]').first().waitFor({ timeout: 30_000 });
  const message = `Artifact panel E2E seed ${Date.now()}`;
  await page.locator('textarea[name="message"]').first().fill(message);
  await page.locator('textarea[name="message"]').first().press("Enter");
  await page.getByText(message, { exact: false }).waitFor({ timeout: 10_000 });
  await page.waitForURL(/\/workspace\/chats\/(?!new(?:\?|$))[^/?#]+/, { timeout: 30_000 });
  const threadId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1);
  if (!threadId || threadId === "new") {
    throw new Error(`Expected concrete thread route, got ${page.url()}`);
  }
  await page.waitForFunction(
    async (nextThreadId) => {
      const response = await fetch(`/api/langgraph/threads/${nextThreadId}/state`);
      if (!response.ok) return false;
      const payload = await response.json();
      return (payload.values?.messages?.length ?? 0) > 0;
    },
    threadId,
    { timeout: 45_000 },
  );
  return threadId;
}

async function attachArtifact(threadId) {
  const artifactName = `artifact-panel-${Date.now()}.md`;
  const artifactPath = `/mnt/user-data/outputs/${artifactName}`;
  const outputsDir = path.join(repoRoot, "workspace/default/threads", threadId, "outputs");
  fs.mkdirSync(outputsDir, { recursive: true });
  fs.writeFileSync(
    path.join(outputsDir, artifactName),
    [
      "# Artifact panel regression",
      "",
      "This document verifies preview, download, and close behavior.",
      "",
      `Thread: ${threadId}`,
      "",
    ].join("\n"),
  );

  const client = new Client({ apiUrl: `${baseUrl}/api/langgraph` });
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const runs = await client.runs.list(threadId).catch(() => []);
    const inFlight = runs.some((run) => ["pending", "running"].includes(run.status));
    if (!inFlight) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if (attempt === 59) {
      throw new Error(`Thread ${threadId} still has in-flight runs after waiting.`);
    }
  }
  const existingState = await client.threads.getState(threadId);
  await client.threads.updateState(threadId, {
    values: {
      ...(existingState.values ?? {}),
      artifacts: [artifactPath],
    },
  });

  return { artifactName, artifactPath };
}

async function openDocumentsTab(page) {
  await page.getByTestId("chat-side-panel").waitFor({ state: "attached", timeout: 30_000 });
  await page.getByTestId("chat-side-panel-documents-tab").click({ timeout: 10_000 });
  await page.getByTestId("chat-side-panel-documents").waitFor({ timeout: 10_000 });
}

(async () => {
  fs.mkdirSync(outputDir, { recursive: true });
  const browser = await chromium.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1440, height: 960 },
  });
  const page = await context.newPage();
  const errors = [];

  page.on("console", (message) => {
    const text = message.text();
    if (isFatalBrowserMessage(text)) errors.push(text);
  });
  page.on("pageerror", (error) => {
    if (isFatalBrowserMessage(error.message)) errors.push(error.message);
  });

  const threadId = await createThread(page);
  const { artifactName } = await attachArtifact(threadId);
  await page.goto(`${baseUrl}/workspace/chats/${threadId}`, { waitUntil: "networkidle" });
  await openDocumentsTab(page);
  await page.getByText(artifactName, { exact: false }).waitFor({ timeout: 20_000 });
  await page.screenshot({
    fullPage: false,
    path: path.join(outputDir, "artifact-panel-desktop.png"),
  });

  const download = await Promise.all([
    page.waitForEvent("download", { timeout: 20_000 }),
    page.getByRole("button", { name: /Download|下载|下載|ダウンロード|다운로드/i }).first().click(),
  ]).then(([downloadEvent]) => downloadEvent);
  if (!download.suggestedFilename().includes(artifactName)) {
    throw new Error(`Unexpected downloaded filename: ${download.suggestedFilename()}`);
  }

  await page.getByText(artifactName, { exact: false }).first().click();
  await page.getByText("Artifact panel regression", { exact: false }).waitFor({ timeout: 20_000 });
  await page.screenshot({
    fullPage: false,
    path: path.join(outputDir, "artifact-panel-preview.png"),
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Artifacts|文件|成果物|產出物|산출물/i }).click({ timeout: 10_000 });
  await openDocumentsTab(page);
  await page.getByText(artifactName, { exact: false }).waitFor({ timeout: 20_000 });
  await page.screenshot({
    fullPage: false,
    path: path.join(outputDir, "artifact-panel-mobile.png"),
  });
  await page.getByTestId("chat-side-panel-close").click();
  await page.waitForFunction(() => {
    const element = document.querySelector('[data-testid="chat-side-panel"]');
    if (!element) return false;
    return window.getComputedStyle(element).opacity === "0";
  }, null, { timeout: 5000 });
  const transform = await page.getByTestId("chat-side-panel").evaluate((element) => {
    const style = window.getComputedStyle(element);
    return { opacity: style.opacity, transform: style.transform };
  });

  await browser.close();

  if (errors.length > 0) {
    throw new Error(`Fatal browser errors:\n${errors.join("\n")}`);
  }
  if (transform.opacity !== "0") {
    throw new Error(`Mobile artifact panel did not close: ${JSON.stringify(transform)}`);
  }

  console.log(JSON.stringify({
    ok: true,
    threadId,
    artifactName,
    screenshots: [
      "tmp/artifact-panel-desktop.png",
      "tmp/artifact-panel-preview.png",
      "tmp/artifact-panel-mobile.png",
    ],
  }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
