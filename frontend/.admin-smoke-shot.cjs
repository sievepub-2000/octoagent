
const { chromium } = require("@playwright/test");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }});
  const page = await ctx.newPage();
  const base = process.env.WEBUI || 'http://127.0.0.1:19880';
  const out = process.env.OUT || '/home/sieve-pub/public-workspace/octoagent/tmp/admin_smoke';
  const pages = [
    ['skills', '/workspace/config/skills'],
    ['mcp', '/workspace/config/mcp'],
    ['channels', '/workspace/config/channels'],
  ];
  const results = {};
  for (const [label, path] of pages) {
    try {
      const resp = await page.goto(base + path, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1500);
      const shot = out + '/webui_' + label + '.png';
      await page.screenshot({ path: shot, fullPage: false });
      results[label] = { status: resp?.status() || 0, shot };
    } catch (e) {
      results[label] = { error: String(e) };
    }
  }
  console.log(JSON.stringify(results));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
