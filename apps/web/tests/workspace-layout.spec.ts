import { expect, test } from "@playwright/test";

import { openControlRoom } from "./helpers";

const output = "../../outputs";

test("flow library is a submodule and the settings drawer collapses without shrinking the canvas", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);

  await expect(page.getByRole("heading", { name: "流程库", exact: true })).toBeVisible();
  await expect(page.locator(".flow-rail")).toHaveCount(0);
  await expect(page.locator(".flow-library-table, .flow-library__table")).toBeVisible();
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 1440);
  await page.screenshot({ path: `${output}/workflow-library.png`, fullPage: true });

  const firstFlow = page.locator(".flow-library__table .ant-table-row").first();
  await expect(firstFlow).toBeVisible();
  await firstFlow.click();
  await expect(page.locator(".graph-stage")).toBeVisible();
  await expect(page.locator(".inspector-wrap")).toBeVisible();

  const expandedDrawer = await page.locator(".inspector-wrap").boundingBox();
  const expandedWorkspace = await page.locator(".workspace").boundingBox();
  expect(expandedDrawer).not.toBeNull();
  expect(expandedWorkspace).not.toBeNull();
  expect(expandedDrawer!.width).toBeGreaterThan(280);
  await page.screenshot({ path: `${output}/workflow-editor-expanded.png`, fullPage: true });

  await page.getByRole("button", { name: "收起流程设置" }).click();
  await expect(page.locator(".inspector-wrap")).toHaveClass(/is-collapsed/);
  await page.waitForTimeout(240);

  const collapsedDrawer = await page.locator(".inspector-wrap").boundingBox();
  const expandedCanvasWorkspace = await page.locator(".workspace").boundingBox();
  expect(collapsedDrawer).not.toBeNull();
  expect(expandedCanvasWorkspace).not.toBeNull();
  expect(collapsedDrawer!.width).toBeLessThanOrEqual(45);
  expect(expandedCanvasWorkspace!.width).toBeGreaterThan(expandedWorkspace!.width + 240);
  expect(await page.evaluate(() => localStorage.getItem("siftlane:workflow:inspector"))).toBe("collapsed");
  await page.screenshot({ path: `${output}/workflow-editor-collapsed.png`, fullPage: true });

  await page.getByRole("button", { name: "展开流程设置" }).click();
  await expect(page.locator(".inspector-wrap")).not.toHaveClass(/is-collapsed/);
  expect(await page.evaluate(() => localStorage.getItem("siftlane:workflow:inspector"))).toBe("expanded");
  await page.locator(".react-flow__node").first().click();
  await expect(page.getByRole("button", { name: "收起节点设置" })).toBeVisible();

  await page.getByRole("button", { name: "流程库", exact: true }).click();
  await expect(page.getByRole("heading", { name: "流程库", exact: true })).toBeVisible();
  await expect(page.locator(".inspector-wrap")).toHaveCount(0);

  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 1280);
  await page.screenshot({ path: `${output}/workflow-library-1280.png`, fullPage: true });
});
