import { expect, test } from "@playwright/test";

test("Tools Hub All count matches the rendered Tools categories", async ({ page }) => {
  await page.goto("/workspace/config/tools");

  const allFilter = page.getByRole("button", { name: /^All \(\d+\)$/ });
  await expect(allFilter).toBeVisible({ timeout: 20_000 });
  const label = await allFilter.textContent();
  const expected = Number(label?.match(/\((\d+)\)/)?.[1] ?? -1);

  await expect.poll(() => page.locator('[data-testid^="tools-hub-item-"]').count()).toBe(expected);
});
