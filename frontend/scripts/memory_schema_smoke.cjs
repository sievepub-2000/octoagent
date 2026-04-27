const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:19880/workspace/config/memory', { waitUntil: 'domcontentloaded', timeout: 30000 });
  const panel = await page.locator('[data-testid="memory-schema-status"]').first();
  await panel.waitFor({ timeout: 15000 });
  // Wait until query finishes
  await page.locator('[data-testid="memory-schema-v2-available"]').waitFor({ timeout: 15000 });
  const v2Text = await page.locator('[data-testid="memory-schema-v2-available"]').textContent();
  const legacyText = await page.locator('[data-testid="memory-schema-legacy-backup"]').textContent();
  const preferText = await page.locator('[data-testid="memory-schema-prefer-v2"]').textContent();
  console.log('memory-schema-ui:', JSON.stringify({ v2: v2Text?.trim(), legacy: legacyText?.trim(), prefer: preferText?.trim() }));
  await page.screenshot({ path: '/tmp/memory-schema-card.png', fullPage: true });
  await browser.close();
})().catch(err => { console.error(err); process.exit(1); });
