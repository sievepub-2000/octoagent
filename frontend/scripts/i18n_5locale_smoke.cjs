const { chromium } = require('@playwright/test');

const LOCALES = ['en-US', 'zh-CN', 'zh-TW', 'ja', 'ko'];
const TAB_LABELS = {
  'en-US': 'Trust Scores',
  'zh-CN': '信任评分',
  'zh-TW': '信任評分',
  ja: '信頼スコア',
  ko: '신뢰 점수',
};
const DESKTOP_LABELS = {
  'en-US': 'Desktop Control',
  'zh-CN': '桌面控制',
  'zh-TW': '桌面控制',
  ja: 'デスクトップ制御',
  ko: '데스크톱 제어',
};

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const locale of LOCALES) {
    const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    await ctx.addCookies([{ name: 'locale', value: locale, url: 'http://127.0.0.1:19880' }]);
    const page = await ctx.newPage();

    await page.goto('http://127.0.0.1:19880/workspace/config/evolution', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(800);
    const tabLabel = TAB_LABELS[locale];
    const tabLoc = page.getByText(tabLabel, { exact: true }).first();
    const tabFound = (await tabLoc.count()) > 0;
    if (tabFound) { try { await tabLoc.click({ timeout: 3000 }); } catch {} }
    await page.waitForTimeout(400);
    await page.screenshot({ path: `/tmp/trust-${locale}.png`, fullPage: false });

    await page.goto('http://127.0.0.1:19880/workspace/config/tools', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(800);
    const deskLabel = DESKTOP_LABELS[locale];
    const deskFound = (await page.getByText(deskLabel, { exact: false }).count()) > 0;
    await page.screenshot({ path: `/tmp/tools-${locale}.png`, fullPage: false });

    results.push({ locale, trustTabFound: tabFound, desktopLabelFound: deskFound });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})().catch((e) => { console.error(e); process.exit(1); });
