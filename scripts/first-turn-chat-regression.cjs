// Verifies that fresh conversations answer on the first turn from both
// /workspace/chats/new and the New Chat button, with matching UI and state.
const fs = require('fs');
const { chromium } = require('/home/sieve-pub/public-workspace/octoagent/frontend/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright');

const base = process.argv[2] || process.env.OCTOAGENT_WEB_URL || 'http://127.0.0.1:19800';
const langgraphBase = process.env.OCTOAGENT_LANGGRAPH_URL || 'http://127.0.0.1:19804';
const nonce = Date.now();

function resolveChromiumExecutable() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    process.env.OCTOAGENT_BROWSER_PATH,
    process.env.OCTOPUSAGENT_BROWSER_PATH,
    ...fs.globSync('/home/sieve-pub/public-workspace/octoagent/runtime/cache/ms-playwright/chromium-*/chrome-linux/chrome'),
    chromium.executablePath(),
    '/home/sieve-pub/.cache/ms-playwright/chromium-1217/chrome-linux/chrome',
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate));
}

async function send(page, text) {
  const input = page.locator('textarea[name="message"], textarea').first();
  await input.waitFor({ timeout: 60000 });
  await input.fill(text);
  const submit = page.locator('button[type="submit"]').last();
  await submit.waitFor({ timeout: 60000 });
  await submit.click();
}

async function waitForFreshRouteReady(page) {
  await page.waitForFunction(() => {
    const parts = window.location.pathname.split('/');
    const id = parts.at(-1);
    return Boolean(id && id !== 'new' && id.length > 20);
  }, { timeout: 60000 });
  await page.locator('textarea[name="message"], textarea').first().waitFor({ timeout: 60000 });
  await page.locator('button[type="submit"]').last().waitFor({ timeout: 60000 });
  await page.waitForTimeout(750);
}

async function stateMessages(page, threadId) {
  return await page.evaluate(async ({ langgraphBase, threadId }) => {
    const res = await fetch(`${langgraphBase}/threads/${threadId}/state`);
    if (!res.ok) return { status: res.status, messages: [] };
    const state = await res.json();
    return { status: res.status, messages: state?.values?.messages || [] };
  }, { langgraphBase, threadId });
}

async function waitForUiAndState(page, expected, seconds = 120) {
  let last;
  for (let i = 0; i < seconds; i += 1) {
    const threadId = page.url().split('/workspace/chats/')[1]?.split(/[?#]/)[0];
    const state = threadId ? await stateMessages(page, threadId) : { status: 0, messages: [] };
    const messageNodes = await page
      .locator('.group\\/conversation-message')
      .evaluateAll((nodes) => nodes.map((node) => node.innerText?.trim()))
      .catch((error) => [`ERR ${error}`]);
    const stateAi = state.messages
      .filter((message) => message.type === 'ai')
      .map((message) => String(message.content || ''));
    last = {
      url: page.url(),
      threadId,
      stateStatus: state.status,
      stateCount: state.messages.length,
      stateAi,
      messageNodes,
    };
    const nodeHit = messageNodes.some((text) => text.includes(expected));
    const stateHit = stateAi.some((text) => text.includes(expected));
    if (nodeHit && stateHit) return { ok: true, last };
    await page.waitForTimeout(1000);
  }
  return { ok: false, last };
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: resolveChromiumExecutable(),
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const badResponses = [];
  page.on('response', (res) => {
    const url = res.url();
    if (res.status() >= 400 && (url.includes('/threads') || url.includes('/runs'))) {
      badResponses.push(`${res.status()} ${url}`);
    }
  });

  const directExpected = `OK_DIRECT_${nonce}`;
  const navExpected = `OK_NAV_${nonce}`;

  await page.goto(`${base}/workspace/chats/new`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await waitForFreshRouteReady(page);
  await send(page, `请只回复这个固定令牌，不要解释：${directExpected}`);
  const direct = await waitForUiAndState(page, directExpected);

  await page.getByRole('button', { name: /新对话|New chat/ }).first().click();
  await waitForFreshRouteReady(page);
  const afterNewUrl = page.url();
  await send(page, `请只回复这个固定令牌，不要解释：${navExpected}`);
  const nav = await waitForUiAndState(page, navExpected);

  const result = {
    direct,
    afterNewUrl,
    nav,
    badResponses,
    threadReused: direct.last?.threadId === nav.last?.threadId,
  };
  console.log(JSON.stringify(result, null, 2));
  await browser.close();

  if (!direct.ok || !nav.ok || badResponses.length || result.threadReused) {
    process.exit(1);
  }
})().catch((error) => {
  console.error('FATAL', error);
  process.exit(2);
});
