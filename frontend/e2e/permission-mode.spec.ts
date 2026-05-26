import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

async function selectPermissionMode(page: Page, label: string) {
  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(page.getByText("权限模式")).toBeVisible();
  const value = label === "目录" ? "directory" : label === "系统" ? "system" : "approval";
  await page.getByTestId(`permission-mode-option-${value}`).click();
  await expect(trigger).toContainText(label);
}

test("permission mode selector switches approval scopes", async ({ page }) => {
  await page.goto("/workspace/chats/new");

  const trigger = page.getByTestId("permission-mode-trigger");
  await expect(trigger).toBeVisible({ timeout: 20_000 });
  await expect(trigger).toContainText("审批");

  await selectPermissionMode(page, "目录");
  await selectPermissionMode(page, "系统");
  await selectPermissionMode(page, "审批");
});
