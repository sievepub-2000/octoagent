const { chromium } = require("@playwright/test");

const baseUrl = process.env.PLAYWRIGHT_BASE_URL || process.env.OCTO_STAGING_FRONTEND_URL;
const expectedModel = process.env.OCTO_EXPECTED_RUNTIME_MODEL || "gpt-oss-120b";
const enabled = process.env.OCTO_RUN_STAGING_SMOKE === "1";
const criticalConsoleError =
  /Maximum update depth exceeded|FileNotFoundError|Permission denied when creating directories|Requested tokens .* exceed context window|web_search is not a valid tool|Failed to fetch/i;

async function main() {
  if (!enabled) {
    console.log("staging chat smoke skipped: set OCTO_RUN_STAGING_SMOKE=1 to enable");
    return;
  }
  if (!baseUrl) {
    throw new Error("PLAYWRIGHT_BASE_URL or OCTO_STAGING_FRONTEND_URL is required");
  }

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const criticalErrors = [];
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error" && criticalConsoleError.test(text)) {
      criticalErrors.push(text);
    }
  });
  page.on("pageerror", (error) => {
    if (criticalConsoleError.test(error.message)) {
      criticalErrors.push(error.message);
    }
  });

  try {
    await page.goto(`${baseUrl.replace(/\/$/, "")}/workspace/chats/new`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    const prompt = page.locator("textarea[name='message']").first();
    await prompt.waitFor({ state: "visible", timeout: 30000 });

    await prompt.fill("一句话介绍自己，你是什么模型？只回答平台和当前运行模型。");
    await prompt.press("Enter");
    await page.locator("body").getByText(expectedModel, { exact: false }).waitFor({
      timeout: 90000,
    });
    const bodyAfterIdentity = await page.locator("body").innerText();
    if (/gemma4/i.test(bodyAfterIdentity)) {
      throw new Error("model identity drift: response contains gemma4");
    }

    await prompt.fill("帮我查询一下x.com上前十大新闻，把具体内容页详细列出。");
    await prompt.press("Enter");
    await page.waitForFunction(
      () => (document.body.innerText.match(/https:\/\/x\.com\/[^\s)]+/g) || []).length >= 10,
      null,
      { timeout: 120000 },
    );

    await prompt.fill("继续上一轮，不要丢失刚才的x.com新闻任务上下文。");
    await prompt.press("Enter");
    await page.waitForFunction(
      () => /继续|续接|上一轮|x\.com/i.test(document.body.innerText),
      null,
      { timeout: 90000 },
    );

    if (criticalErrors.length > 0) {
      throw new Error(`critical browser console errors: ${criticalErrors.join(" | ")}`);
    }
    console.log(JSON.stringify({ ok: true, baseUrl, expectedModel }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
