import { expect, test } from "@playwright/test";

test("new chat does not render prompt suggestion shortcuts", async ({ page }) => {
  await page.goto("/workspace/chats/new");

  const shortcutButtons = page.locator("button").filter({
    hasText: /小惊喜|写作|研究|收集|学习|Surprise|Write|Research|Collect|Learn/,
  });
  await expect(shortcutButtons).toHaveCount(0);
});
