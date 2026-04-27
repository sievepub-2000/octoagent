const { chromium } = require('@playwright/test');
const fs = require('fs');
const LOCALES = ['en-US', 'zh-CN', 'zh-TW', 'ja', 'ko'];
(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = {};
  for (const loc of LOCALES) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addCookies([{ name: 'locale', value: loc, url: 'http://127.0.0.1:19880' }]);
    const page = await ctx.newPage();
    try {
      await page.goto('http://127.0.0.1:19880/workspace/config/memory', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.locator('[data-testid="memory-schema-v2-available"]').waitFor({ timeout: 15000 });
      const v2 = (await page.locator('[data-testid="memory-schema-v2-available"]').textContent() || '').trim();
      const legacy = (await page.locator('[data-testid="memory-schema-legacy-backup"]').textContent() || '').trim();
      const prefer = (await page.locator('[data-testid="memory-schema-prefer-v2"]').textContent() || '').trim();
      await page.screenshot({ path: `/tmp/memory-schema-${loc}.png`, fullPage: false });
      results[loc] = { v2, legacy, prefer };
    } catch (e) {
      results[loc] = { error: String(e).slice(0, 200) };
    }
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  fs.writeFileSync('/tmp/memory-schema-i18n.json', JSON.stringify(results, null, 2));
})().catch(err => { console.error(err); process.exit(1); });
