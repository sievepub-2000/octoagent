const path = require("node:path");

const { chromium } = require(path.join(
  __dirname,
  "../node_modules/.pnpm/playwright@1.59.1/node_modules/playwright",
));

const baseUrl = process.argv[2] || process.env.WEBUI || "http://127.0.0.1:19880";

function isFatalBrowserMessage(text) {
  return /Maximum update depth exceeded|Permission denied when creating directories|\[ChatThreadError\]/i.test(text);
}

async function readJson(page, route) {
  return page.evaluate(async (url) => {
    const response = await fetch(url);
    return response.json();
  }, route);
}

async function waitForUploadedFile(page, threadId, filename) {
  const uploaded = await page.waitForFunction(
    async ({ threadId: nextThreadId, filename: nextFilename }) => {
      const response = await fetch(`/api/threads/${nextThreadId}/uploads/list`);
      if (!response.ok) return false;
      const payload = await response.json();
      return (payload.files || []).some((file) => file.filename === nextFilename);
    },
    { threadId, filename },
    { timeout: 30_000 },
  );
  return uploaded.jsonValue();
}

async function assertRuntimeIdentity(page, expected) {
  await page.getByText(/^System Default model:/).click({ timeout: 10_000 });
  await page.getByTestId("runtime-identity-agent").waitFor({ timeout: 10_000 });

  const identity = {
    agent: (await page.getByTestId("runtime-identity-agent").textContent())?.trim(),
    chatModel: (await page.getByTestId("runtime-identity-chat-model").textContent())?.trim(),
    activeModel: (await page.getByTestId("runtime-identity-active-model").textContent())?.trim(),
  };
  await page.keyboard.press("Escape");

  if (expected.agent) {
    const expectedAgents = Array.isArray(expected.agent) ? expected.agent : [expected.agent];
    if (!expectedAgents.includes(identity.agent)) {
      throw new Error(`Runtime identity agent mismatch: expected ${expectedAgents.join(" or ")}, got ${identity.agent}`);
    }
  }
  if (expected.chatModel && ![expected.chatModel.name, expected.chatModel.display_name].filter(Boolean).includes(identity.chatModel)) {
    throw new Error(`Runtime identity chat model mismatch: expected ${expected.chatModel.name}, got ${identity.chatModel}`);
  }
  if (expected.activeModel && identity.activeModel !== expected.activeModel) {
    throw new Error(`Runtime identity active model mismatch: expected ${expected.activeModel}, got ${identity.activeModel}`);
  }

  return identity;
}

(async () => {
  const browser = await chromium.launch({
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage();
  const errors = [];
  const setupResponses = [];

  page.on("console", (message) => {
    const text = message.text();
    if (isFatalBrowserMessage(text)) {
      errors.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (isFatalBrowserMessage(error.message)) {
      errors.push(error.message);
    }
  });
  page.on("response", async (response) => {
    if (!response.url().includes("/api/setup/")) {
      return;
    }
    setupResponses.push({
      url: response.url(),
      status: response.status(),
      body: await response.text().catch(() => ""),
    });
  });

  await page.goto(`${baseUrl}/workspace/chats/new`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.setItem(
      "octoagent.local-settings",
      JSON.stringify({
        appearance: { preset: "default" },
        notification: { enabled: true },
        bootstrap: { onboarding_enabled: false },
        context: { agent_name: "gemma4-serving-analyst", model_name: undefined },
        layout: { sidebar_collapsed: false },
        setup: {
          completed: true,
          workspace_path: ["/home/sieve-pub", "codex/octoagent/backend/.octoagent"].join("/"),
          default_model: "gpt-oss-120b-free",
          sandbox_mode: "local",
        },
      }),
    );
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  const initialState = await page.evaluate(() => ({
    settings: JSON.parse(localStorage.getItem("octoagent.local-settings") || "{}"),
    body: document.body.innerText,
  }));
  if (initialState.settings.context?.agent_name) {
    throw new Error(`New workspace chat retained stale agent_name=${initialState.settings.context.agent_name}`);
  }
  if (initialState.body.includes("/home/sieve-pub/codex")) {
    throw new Error("New workspace chat rendered a stale legacy workspace path.");
  }
  if (/gemma4-serving-analyst/i.test(initialState.body)) {
    throw new Error("New workspace chat rendered a stale agent identity.");
  }

  const statusBefore = await readJson(page, "/api/setup/status");
  const modelsPayload = await readJson(page, "/api/models");
  const models = modelsPayload.models || [];
  const originalModel = statusBefore.configured_default_model;
  const alternate = models.find((model) => model.name !== originalModel);

  if (alternate) {
    await page.getByText(/^System Default model:/).click({ timeout: 10_000 });
    await page.getByText(alternate.display_name || alternate.name).first().click({ timeout: 10_000 });
    await page.waitForTimeout(1000);
    const statusAfterAlternate = await readJson(page, "/api/setup/status");
    if (statusAfterAlternate.configured_default_model !== alternate.name) {
      throw new Error(`Default model did not switch to ${alternate.name}.`);
    }

    await page.getByText(/^System Default model:/).click({ timeout: 10_000 });
    const original = models.find((model) => model.name === originalModel);
    await page.getByText(original?.display_name || originalModel).first().click({ timeout: 10_000 });
    await page.waitForTimeout(1000);
    const statusAfterRestore = await readJson(page, "/api/setup/status");
    if (statusAfterRestore.configured_default_model !== originalModel) {
      throw new Error(`Default model did not restore to ${originalModel}.`);
    }
  }

  await page.goto(`${baseUrl}/workspace/chats`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.goto(`${baseUrl}/workspace/chats/new`, { waitUntil: "networkidle" });
  await page.locator('textarea[name="message"]').first().waitFor({ timeout: 30_000 });
  const originalModelObject = models.find((model) => model.name === originalModel);
  await assertRuntimeIdentity(page, {
    agent: ["Default", "系统默认", "系統預設", "デフォルト", "기본"],
    chatModel: originalModelObject,
    activeModel: originalModel,
  });

  const agentsPayload = await readJson(page, "/api/agents");
  const agents = Array.isArray(agentsPayload) ? agentsPayload : agentsPayload.agents || [];
  const selectableAgent = agents.find((agent) => agent && agent.name);
  if (selectableAgent) {
    await page.getByText(/Default|默认|預設|デフォルト|기본/).first().click({ timeout: 10_000 });
    await page.getByText(selectableAgent.name, { exact: true }).first().click({ timeout: 10_000 });
    await page.waitForTimeout(500);
    await assertRuntimeIdentity(page, {
      agent: selectableAgent.name,
    });
  }

  const attachmentName = `chat-e2e-${Date.now()}.txt`;
  await page.locator('input[aria-label="Upload files"]').first().setInputFiles({
    name: attachmentName,
    mimeType: "text/plain",
    buffer: Buffer.from("chat e2e attachment\n"),
  });
  await page.getByText(attachmentName, { exact: false }).waitFor({ timeout: 10_000 });

  const firstMessage = `Browser E2E first turn ${Date.now()}`;
  const input = page.locator('textarea[name="message"]').first();
  await input.fill(firstMessage);
  await input.press("Enter");
  await page.getByText(firstMessage, { exact: false }).waitFor({ timeout: 10_000 });
  await page.waitForURL(/\/workspace\/chats\/(?!new(?:\?|$))[^/?#]+/, { timeout: 30_000 });
  const threadId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1);
  if (!threadId || threadId === "new") {
    throw new Error(`Expected concrete thread route, got ${page.url()}`);
  }
  await waitForUploadedFile(page, threadId, attachmentName);
  const threadStateAfterFirstTurn = await readJson(page, `/api/langgraph/threads/${threadId}/state`);
  const runtimeActiveModel = threadStateAfterFirstTurn.values?.runtime?.active_model;
  if (runtimeActiveModel) {
    await assertRuntimeIdentity(page, {
      activeModel: runtimeActiveModel,
    });
  }

  const followUp = `Browser E2E follow-up ${Date.now()}`;
  await page.locator('textarea[name="message"]').first().fill(followUp);
  await page.locator('textarea[name="message"]').first().press("Enter");
  await page.getByText(followUp, { exact: false }).waitFor({ timeout: 10_000 });

  await page.goto(`${baseUrl}/workspace/chats/new?continue_from=${threadId}`, {
    waitUntil: "domcontentloaded",
  });
  await page.locator('textarea[name="message"]').first().waitFor({ timeout: 30_000 });
  if (!page.url().includes("continue_from=")) {
    throw new Error("Continuation route did not stay open.");
  }

  await page.waitForTimeout(3000);

  await browser.close();

  if (errors.length > 0) {
    throw new Error(`Fatal browser errors:\n${errors.join("\n")}`);
  }
  if (setupResponses.some((response) => response.status >= 400 || /Permission denied/i.test(response.body))) {
    throw new Error(`Setup API failure:\n${JSON.stringify(setupResponses, null, 2)}`);
  }

  console.log(JSON.stringify({
    ok: true,
    originalModel,
    switchedModel: alternate?.name ?? null,
    selectedAgent: selectableAgent?.name ?? null,
    threadId,
    attachmentName,
    setupCalls: setupResponses.length,
  }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
