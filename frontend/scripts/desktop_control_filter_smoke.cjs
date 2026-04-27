const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:19880/workspace/config/tools', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('[data-testid^="tools-hub-item-desktop:"]', { timeout: 20000 });
  // click the Desktop Control filter button (label contains "Desktop Control")
  await page.getByRole('button', { name: /Desktop Control/ }).first().click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: '/tmp/desktop-control-filtered.png', fullPage: true });
  console.log('saved /tmp/desktop-control-filtered.png');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
