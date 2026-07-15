import { expect, test } from "@playwright/test";

test("collapsed sidebar reopens from the octopus mark", async ({ page }) => {
  await page.goto("/workspace/chats/new");

  const sidebar = page.locator('[data-slot="sidebar"][data-state]');
  const trigger = sidebar.locator('[data-sidebar="trigger"]');
  await expect(trigger).toBeVisible({ timeout: 20_000 });

  await trigger.click();
  await expect(sidebar).toHaveAttribute("data-state", "collapsed");

  const collapsedBrandTrigger = page.getByTestId("sidebar-collapsed-brand-trigger");
  await expect(collapsedBrandTrigger).toBeVisible();
  await collapsedBrandTrigger.click();

  await expect(sidebar).toHaveAttribute("data-state", "expanded");
});
