// Verifies that the chat viewport stays pinned to the latest content while
// assistant content grows. The test uses a real WebUI conversation, then
// deterministically expands the rendered assistant node to exercise the same
// ResizeObserver path used by streaming markdown/layout growth.
const { chromium } = require('/home/sieve-pub/public-workspace/octoagent/frontend/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright');

const base = process.argv[2] || process.env.OCTOAGENT_WEB_URL || 'http://127.0.0.1:19800';
const nonce = Date.now();

async function send(page, text) {
  const input = page.locator('textarea[name="message"], textarea').first();
  await input.waitFor({ timeout: 60000 });
  await input.fill(text);
  await page.locator('button[type="submit"]').last().click();
}

async function metrics(page) {
  return await page.evaluate(() => {
    const container = document.querySelector('[data-chat-scroll-container="true"]');
    const nodes = [...document.querySelectorAll('.group\\/conversation-message')];
    const last = nodes.at(-1);
    if (!container) return { ok: false, reason: 'missing container' };
    const element = container;
    const containerRect = element.getBoundingClientRect();
    const lastRect = last?.getBoundingClientRect();
    const expansion = document.querySelector('[data-scroll-regression-expansion="true"]');
    return {
      ok: true,
      scrollTop: element.scrollTop,
      scrollHeight: element.scrollHeight,
      clientHeight: element.clientHeight,
      distanceFromBottom: element.scrollHeight - element.scrollTop - element.clientHeight,
      messageCount: nodes.length,
      expansionPresent: Boolean(expansion),
      lastText: last?.textContent?.slice(-240) || '',
      lastVisible: lastRect ? lastRect.bottom <= containerRect.bottom + 8 && lastRect.top < containerRect.bottom : false,
    };
  });
}

async function waitForReply(page, marker) {
  let last;
  for (let second = 0; second < 120; second += 1) {
    last = await metrics(page);
    const body = await page.locator('body').innerText().catch(() => '');
    if (last.messageCount >= 2 && body.includes(marker)) return last;
    await page.waitForTimeout(1000);
  }
  throw new Error(`reply marker not visible: ${marker}; last=${JSON.stringify(last)}`);
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/home/sieve-pub/.cache/ms-playwright/chromium-1217/chrome-linux/chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 760 } });
  const badResponses = [];
  page.on('response', (res) => {
    const url = res.url();
    if (res.status() >= 400 && (url.includes('/threads') || url.includes('/runs'))) {
      badResponses.push(`${res.status()} ${url}`);
    }
  });

  const marker = `SCROLL_OK_${nonce}`;
  await page.goto(`${base}/workspace/chats/new`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await send(page, `请只回复这个固定令牌，不要解释：${marker}`);
  await waitForReply(page, marker);
  await page.waitForURL(/\/workspace\/chats\/[0-9a-f-]+$/i, { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1500);

  await page.evaluate(() => {
    const container = document.querySelector('[data-chat-scroll-container="true"]');
    if (container) container.scrollTop = container.scrollHeight;
  });

  await page.evaluate((marker) => {
    const container = document.querySelector('[data-chat-scroll-container="true"]');
    const content = container?.firstElementChild;
    if (!content) throw new Error('missing scroll content node');
    const expansion = document.createElement('div');
    expansion.setAttribute('data-scroll-regression-expansion', 'true');
    expansion.style.whiteSpace = 'pre-wrap';
    expansion.textContent = Array.from({ length: 120 }, (_, index) => `${marker}_EXPAND_${index}`).join('\n');
    content.appendChild(expansion);
  }, marker);

  await page.waitForTimeout(1200);
  const result = { marker, metrics: await metrics(page), badResponses };
  console.log(JSON.stringify(result, null, 2));
  await browser.close();

  if (!result.metrics.ok || !result.metrics.expansionPresent || result.metrics.distanceFromBottom >= 96 || badResponses.length) {
    process.exit(1);
  }
})().catch((error) => {
  console.error('FATAL', error);
  process.exit(2);
});
