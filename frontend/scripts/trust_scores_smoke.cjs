const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:19880/workspace/config/evolution', { waitUntil: 'networkidle', timeout: 30000 });
  await page.getByRole('tab', { name: /Trust Scores/ }).click();
  await page.waitForSelector('[data-testid="trust-scores-panel"]', { timeout: 15000 });
  await page.waitForTimeout(500);
  const flagText = await page.locator('[data-testid="trust-scores-flag-badge"]').innerText();
  console.log('flag=', flagText);
  await page.screenshot({ path: '/tmp/trust-scores-panel.png', fullPage: true });
  console.log('screenshot=/tmp/trust-scores-panel.png');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
