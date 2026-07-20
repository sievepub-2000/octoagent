import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function selectPermissionMode(page: Page, value: "directory" | "system") {
  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible();
  await expect(trigger).toHaveAttribute("data-state", "closed");
  await trigger.click();
  await expect(trigger).toHaveAttribute("data-state", "open");
  await expect(page.getByTestId("permission-mode-option-approval")).toHaveCount(0);
  const option = page.getByTestId(`permission-mode-option-${value}`);
  await expect(option).toBeVisible();
  const expectedLabel = (await option.innerText()).split("\n", 1)[0] ?? "";
  expect(expectedLabel).not.toBe("");
  await option.click();
  await expect(trigger).toHaveAttribute("data-state", "closed");
  await expect(trigger).toContainText(expectedLabel);
}

test("permission mode selector switches real container and system scopes", async ({ page }) => {
  await page.goto("/workspace/chats/new");

  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible({ timeout: 20_000 });
  await expect(trigger).toContainText(/容器权限|Container permission/);

  await selectPermissionMode(page, "system");
  await page.reload();
  await expect(trigger).toContainText(/系统权限|System permission/);
  await selectPermissionMode(page, "directory");
});
