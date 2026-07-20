import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function selectPermissionMode(page: Page, label: string) {
  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(page.getByText("权限模式")).toBeVisible();
  const value = label === "容器权限" ? "directory" : "system";
  await page.getByTestId(`permission-mode-option-${value}`).click();
  await expect(trigger).toContainText(label);
}

test("permission mode selector switches real container and system scopes", async ({ page }) => {
  await page.goto("/workspace/chats/new");

  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible({ timeout: 20_000 });
  await expect(trigger).toContainText("容器权限");

  await trigger.click();
  await expect(page.getByTestId("permission-mode-option-approval")).toHaveCount(0);
  await page.keyboard.press("Escape");

  await selectPermissionMode(page, "系统权限");
  await selectPermissionMode(page, "容器权限");
});
