import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { openControlRoom } from "./helpers";

const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close({ runBeforeUnload: false });
});

test("P1 flow closes the browser-to-engine loop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);
  await expect(page.getByText("执行引擎在线")).toBeVisible();

  await page.getByRole("button", { name: "连接器" }).click();
  await expect(page.getByRole("dialog", { name: "连接器" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "连接器" })).toHaveCount(0);

  await page.getByRole("button", { name: "新建流程" }).first().click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "新建流程" })).toHaveCount(0);
  await page.getByRole("button", { name: "新建流程" }).first().click();
  const name = `P1 联调 ${Date.now().toString().slice(-6)}`;
  const dialog = page.getByRole("dialog", { name: "新建流程" });
  await dialog.getByLabel("流程名称").fill(name);
  await dialog.getByRole("button", { name: "创建流程" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();

  await page.getByText("输入地址", { exact: true }).last().click();
  await page.locator(".inspector label.field").filter({ hasText: "urls" }).locator("textarea").fill("http://127.0.0.1:8877/integration.html");

  await page.getByText("提取内容", { exact: true }).last().click();
  await page.locator(".inspector label.field").filter({ hasText: "item selector" }).locator("input").fill("article");
  const fields = page.locator(".inspector label.field").filter({ hasText: "fields" }).locator("textarea");
  await fields.fill('{"title":"h2","content":"p"}');
  await fields.blur();

  await page.locator(".workspace-bar").getByRole("button", { name: "保存" }).click();
  await expect(page.getByText(/已保存版本/)).toBeVisible();
  await page.locator(".workspace-bar").getByRole("button", { name: "运行", exact: true }).click();
  await expect(page.getByText("运行已进入队列")).toBeVisible();
  await expect(page.locator(".event-line")).toHaveCount(2, { timeout: 20_000 });

  await page.getByRole("button", { name: "结果", exact: true }).click();
  await expect(page.locator(".table-wrap tbody tr")).toHaveCount(2, { timeout: 25_000 });
  await page.getByRole("button", { name: /条事件/ }).click();
  await expect(page.getByText("完整运行记录")).toBeVisible();
  expect(await page.locator(".event-ledger li").count()).toBeGreaterThan(8);
  await page.locator(".toast button").click({ timeout: 1_000 }).catch(() => undefined);
  await page.screenshot({ path: `${output}/p1-desktop-results.png`, fullPage: true });
  await page.getByRole("button", { name: /条事件/ }).click();
  await page.getByRole("button", { name: "编排", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(4);
  await page.screenshot({ path: `${output}/p1-desktop.png`, fullPage: true });
});

test("mobile control room keeps drawers coherent", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openControlRoom(page);
  await expect(page.getByText("执行引擎在线")).toBeVisible();
  await page.getByRole("button", { name: "打开流程列表" }).click();
  await expect(page.locator(".flow-rail.mobile-open")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".flow-rail.mobile-open")).toHaveCount(0);
  await page.getByRole("button", { name: "打开设置" }).click();
  await expect(page.locator(".inspector-wrap.mobile-open")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".inspector-wrap.mobile-open")).toHaveCount(0);
  await page.waitForTimeout(300);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${output}/p1-mobile.png`, fullPage: true });
});
