#!/usr/bin/env node

const { execSync } = require("node:child_process");
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
const chatPath = process.argv[3] || "/workspace/chats/new";
const url = new URL(chatPath, baseUrl).toString();

function readProcessSnapshot() {
  try {
    const output = execSync("ps -eo pid,comm,args,rss --sort=-rss", {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return output
      .split("\n")
      .filter((line) => /next-server|next start|pnpm|node|langgraph_cli/.test(line))
      .slice(0, 12)
      .join("\n");
  } catch {
    return "";
  }
}

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
  const page = await browser.newPage({ viewport: { width: 1680, height: 950 } });
  const consoleErrors = [];
  const pageErrors = [];
  const requestFailures = [];

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(`${error.name}: ${error.message}`));
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    const failureText = failure?.errorText || "";
    if (!/net::ERR_ABORTED|favicon/i.test(failureText + request.url())) {
      requestFailures.push(`${request.method()} ${request.url()} ${failureText}`);
    }
  });

  await page.goto(url, { waitUntil: "networkidle", timeout: 45_000 });
  await page.waitForTimeout(2_000);

  const metrics = await page.evaluate(() => {
    const rectOf = (el) => {
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      return {
        height: Math.round(rect.height),
        left: Math.round(rect.left),
        top: Math.round(rect.top),
        width: Math.round(rect.width),
      };
    };
    const textarea = document.querySelector("textarea");
    const inputShell = textarea?.closest(".max-w-5xl") || textarea?.closest("form") || textarea?.parentElement || null;
    const welcomePanel = Array.from(document.querySelectorAll(".octo-panel")).find((el) => {
      const text = el.textContent || "";
      return /OctoAgent|欢迎|Welcome/.test(text) && !el.querySelector("textarea");
    });
    const navigation = performance.getEntriesByType("navigation")[0];
    return {
      bodyTextLength: document.body.innerText.length,
      domNodes: document.querySelectorAll("*").length,
      inputRect: rectOf(inputShell),
      jsHeap: performance.memory ? {
        total: performance.memory.totalJSHeapSize,
        used: performance.memory.usedJSHeapSize,
        limit: performance.memory.jsHeapSizeLimit,
      } : null,
      navigation: navigation ? {
        domContentLoaded: Math.round(navigation.domContentLoadedEventEnd),
        loadEventEnd: Math.round(navigation.loadEventEnd),
        transferSize: Math.round(navigation.transferSize || 0),
      } : null,
      welcomeRect: rectOf(welcomePanel),
    };
  });

  await browser.close();

  const widthOk = !metrics.welcomeRect || !metrics.inputRect || metrics.welcomeRect.width <= metrics.inputRect.width + 8;
  const ok =
    widthOk &&
    metrics.bodyTextLength > 200 &&
    consoleErrors.length === 0 &&
    pageErrors.length === 0 &&
    requestFailures.length === 0;

  const result = {
    ok,
    url,
    widthOk,
    metrics,
    processSnapshot: readProcessSnapshot(),
    consoleErrors,
    pageErrors,
    requestFailures,
  };

  console.log(JSON.stringify(result, null, 2));
  if (!ok) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(2);
});
