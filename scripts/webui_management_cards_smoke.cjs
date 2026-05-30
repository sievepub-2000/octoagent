#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

function requirePlaywright() {
  const candidates = [
    "../frontend/node_modules/playwright",
    "../frontend/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright",
  ];
  for (const candidate of candidates) {
    try {
      return require(path.resolve(__dirname, candidate));
    } catch (error) {
      if (error && error.code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  throw new Error("Unable to resolve Playwright from frontend/node_modules.");
}

const { chromium } = requirePlaywright();

const baseUrl = process.argv[2] || process.env.OCTO_WEBUI_URL || "http://127.0.0.1:19800";
const paths = [
  "/workspace/agents",
  "/workspace/workflows",
  "/workspace/config/tools",
  "/workspace/config/skills",
  "/workspace/config/plugins",
  "/workspace/config/mcp",
  "/workspace/config/channels",
  "/workspace/config/models",
  "/workspace/config/evolution",
  "/workspace/config/memory",
];

function chromiumPath() {
  const candidates = [
    process.env.OCTOAGENT_BROWSER_PATH,
    "/snap/bin/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

(async () => {
  const browser = await chromium.launch({
    executablePath: chromiumPath(),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const failures = [];
  const results = [];

  page.on("pageerror", (error) => failures.push(`pageerror: ${error.name}: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console: ${message.text()}`);
  });

  for (const pagePath of paths) {
    const url = new URL(pagePath, baseUrl).toString();
    await page.goto(url, { waitUntil: "networkidle", timeout: 45_000 }).catch(async () => {
      await page.waitForLoadState("domcontentloaded", { timeout: 15_000 }).catch(() => {});
    });
    await page.waitForTimeout(1_500);
    const result = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll(".octo-management-card"));
      const overflows = [];
      for (const card of cards) {
        const cardRect = card.getBoundingClientRect();
        const children = Array.from(card.querySelectorAll("*"));
        for (const child of children) {
          const rect = child.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) continue;
          const outside =
            rect.left < cardRect.left - 1 ||
            rect.right > cardRect.right + 1 ||
            rect.top < cardRect.top - 1 ||
            rect.bottom > cardRect.bottom + 1;
          if (outside) {
            overflows.push({
              card: card.textContent?.trim().slice(0, 80) || "",
              child: child.textContent?.trim().slice(0, 80) || child.tagName,
              cardRect: {
                height: Math.round(cardRect.height),
                width: Math.round(cardRect.width),
              },
              rect: {
                bottom: Math.round(rect.bottom - cardRect.bottom),
                right: Math.round(rect.right - cardRect.right),
              },
            });
            break;
          }
        }
      }
      return {
        cardCount: cards.length,
        overflowCount: overflows.length,
        overflows: overflows.slice(0, 8),
      };
    });
    results.push({ path: pagePath, ...result });
    if (result.overflowCount > 0) {
      failures.push(`${pagePath}: ${result.overflowCount} card overflow(s)`);
    }
  }

  await browser.close();
  const payload = { ok: failures.length === 0, results, failures };
  console.log(JSON.stringify(payload, null, 2));
  if (!payload.ok) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(2);
});
