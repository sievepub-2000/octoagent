// browser_check.cjs - load WebUI, capture console logs, errors, and render content
const { chromium } = require('/home/sieve-pub/public-workspace/octoagent/frontend/node_modules/.pnpm/playwright@1.59.1/node_modules/playwright');

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:19800/';
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();

  const consoleMsgs = [];
  const pageErrors = [];
  const requestFailures = [];
  page.on('console', m => consoleMsgs.push(`[${m.type()}] ${m.text()}`));
  page.on('pageerror', e => pageErrors.push(`${e.name}: ${e.message}\n${e.stack || ''}`));
  page.on('requestfailed', r => requestFailures.push(`${r.method()} ${r.url()} - ${r.failure()?.errorText}`));

  console.log(`>> goto ${url}`);
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  } catch (e) {
    console.log('goto error:', e.message);
  }
  await page.waitForTimeout(3000);

  const finalUrl = page.url();
  const title = await page.title();
  const bodyText = (await page.evaluate(() => document.body?.innerText || '')).slice(0, 2000);
  const bodyHTMLLen = await page.evaluate(() => document.body?.innerHTML.length || 0);
  const visibleEls = await page.evaluate(() => {
    const all = document.querySelectorAll('*');
    let visible = 0;
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) visible++;
    }
    return { total: all.length, visible };
  });
  const errorOverlay = await page.evaluate(() => {
    const next = document.querySelector('nextjs-portal, [data-nextjs-dialog-overlay]');
    return next ? next.outerHTML.slice(0, 1500) : null;
  });

  console.log('=== RESULT ===');
  console.log('finalUrl:', finalUrl);
  console.log('title:', title);
  console.log('body innerHTML length:', bodyHTMLLen);
  console.log('elements total/visible:', visibleEls.total, '/', visibleEls.visible);
  console.log('--- body innerText (first 2000) ---');
  console.log(bodyText || '(EMPTY)');
  console.log('--- console messages ---');
  console.log(consoleMsgs.slice(0, 50).join('\n'));
  console.log('--- pageerror ---');
  console.log(pageErrors.slice(0, 20).join('\n---\n'));
  console.log('--- request failures ---');
  console.log(requestFailures.slice(0, 30).join('\n'));
  console.log('--- nextjs error overlay ---');
  console.log(errorOverlay || '(none)');

  await page.screenshot({ path: '/tmp/webui.png', fullPage: false });
  console.log('screenshot saved /tmp/webui.png');
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(2); });
