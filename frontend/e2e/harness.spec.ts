import { expect, test } from "@playwright/test";

test("Harness count matches rendered capability cards", async ({ page }) => {
  await page.goto("/workspace?settings=harness");

  await expect(page.getByRole("heading", { name: "Harness" })).toBeVisible({ timeout: 20_000 });
  const allFilter = page.getByRole("button", { name: /^All \(\d+\)$/ });
  const label = await allFilter.textContent();
  const expected = Number(label?.match(/\((\d+)\)/)?.[1] ?? -1);

  await expect.poll(() => page.locator('[data-testid^="harness-item-"]').count()).toBe(expected);
});
