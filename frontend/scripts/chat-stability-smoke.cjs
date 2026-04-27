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
          workspace_path: "/home/sieve-pub/codex/octoagent/backend/.octoagent",
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
    setupCalls: setupResponses.length,
  }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
