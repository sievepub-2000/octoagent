const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const BASE = process.env.ADMIN_SMOKE_BASE || 'http://127.0.0.1:19880';
const OUT = path.resolve(__dirname, '../../screenshots/admin_smoke_2026-04-23');
fs.mkdirSync(OUT, { recursive: true });

const pages = [
  ['memory', '/workspace/config/memory'],
  ['tools', '/workspace/config/tools'],
  ['skills', '/workspace/config/skills'],
  ['channels', '/workspace/config/channels'],
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const report = [];
  for (const [name, url] of pages) {
    const errors = [];
    page.removeAllListeners('pageerror');
    page.on('pageerror', (e) => errors.push(String(e)));
    try {
      const resp = await page.goto(BASE + url, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(3500);
      const out = path.join(OUT, `${name}.png`);
      await page.screenshot({ path: out, fullPage: true });
      report.push({ name, status: resp?.status(), out, errors });
    } catch (e) {
      report.push({ name, error: String(e), errors });
    }
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
