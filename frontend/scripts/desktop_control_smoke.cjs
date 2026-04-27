const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  const url = process.env.URL || 'http://127.0.0.1:19880/workspace/config/tools';
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('[data-testid^="tools-hub-item-desktop:"]', { timeout: 20000 });
  const items = await page.$$eval('[data-testid^="tools-hub-item-desktop:"]', (els) =>
    els.map((el) => el.getAttribute('data-testid')),
  );
  console.log('desktop items:', items.length, items);
  await page.screenshot({ path: '/tmp/desktop-control-tools-hub.png', fullPage: true });
  console.log('screenshot=/tmp/desktop-control-tools-hub.png');
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
