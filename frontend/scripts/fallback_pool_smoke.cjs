const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  const url = 'http://127.0.0.1:19880/workspace/config/models';
  console.log('[nav]', url);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  try {
    await page.waitForSelector('[data-testid="fallback-pool-status"]', { timeout: 15000 });
    console.log('[ok] card present');
  } catch (e) {
    console.error('[miss] card not found:', e.message);
  }
  const out = '/tmp/fallback-pool-status.png';
  await page.screenshot({ path: out, fullPage: true });
  console.log('[shot]', out);
  await browser.close();
})();
