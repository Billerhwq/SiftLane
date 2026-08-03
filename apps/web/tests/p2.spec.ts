import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { apiAuthorization, E2E_API_BASE_URL, openControlRoom } from "./helpers";

const engine = E2E_API_BASE_URL;
const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close({ runBeforeUnload: false });
});

test("P2 branch, retry inspector and scheduler close the UI loop", async ({ page, request }) => {
  const suffix = Date.now().toString().slice(-6);
  const flowName = `P2 branch ${suffix}`;
  const headers = await apiAuthorization(request);
  const flowResponse = await request.post(`${engine}/api/v1/flows`, {
    headers,
    data: {
      name: flowName,
      max_items: 10,
      timeout_seconds: 30,
      nodes: [
        { id: "start", type: "start", name: "Input", x: 80, y: 220, config: { urls: ["https://example.com/item"] } },
        { id: "branch", type: "condition", name: "Published?", x: 360, y: 220, config: { field: "kind", operator: "eq", value: "published" } },
        { id: "emit", type: "emit", name: "Output", x: 640, y: 220, config: {} },
      ],
      edges: [
        { id: "a", source: "start", target: "branch", source_port: "default" },
        { id: "b", source: "branch", target: "emit", source_port: "true" },
        { id: "c", source: "branch", target: "emit", source_port: "false" },
      ],
    },
  });
  expect(flowResponse.status()).toBe(201);
  const createdFlow = await flowResponse.json() as { id: string };

  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);
  await page.getByText(flowName, { exact: true }).first().click();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  const branch = page.locator(".react-flow__node").filter({ hasText: "Published?" });
  await expect(branch.locator(".condition-handle")).toHaveCount(2);
  await branch.click();
  await expect(page.getByText("Retry policy", { exact: true })).toBeVisible();
  await expect(page.locator(".inspector input[type=number]").first()).toHaveValue("1");
  await page.screenshot({ path: `${output}/p2-branch-retry.png`, fullPage: true });

  await page.locator(".utility-rail .ant-menu-item").filter({ hasText: "任务调度" }).click();
  await expect(page.getByRole("heading", { name: "任务调度中心" })).toBeVisible();
  await expect(page.getByText("未来 24 小时运行带")).toBeVisible();
  const operationsGrid = page.locator(".schedule-operations-grid");
  await page.getByRole("button", { name: "收起计划图层" }).click();
  await expect(operationsGrid).toHaveClass(/is-left-collapsed/);
  await page.getByRole("button", { name: "展开计划图层" }).click();
  await page.getByRole("button", { name: "收起任务情报" }).click();
  await expect(operationsGrid).toHaveClass(/is-right-collapsed/);
  await page.getByRole("button", { name: "展开任务情报" }).click();

  await page.getByRole("tab", { name: /计划管理/ }).click();
  await expect(page.getByText("计划管理", { exact: true }).last()).toBeVisible();

  await page.getByRole("button", { name: "新建计划" }).click();
  const drawer = page.getByRole("dialog", { name: "新建调度计划" });
  await expect(drawer).toBeVisible();
  const scheduleName = `P2 schedule ${suffix}`;
  await drawer.getByLabel("计划名称").fill(scheduleName);
  await expect(drawer.getByText(flowName, { exact: true })).toBeVisible();
  await drawer.getByLabel("Cron 表达式").fill("0 8 * * *");
  await drawer.getByRole("button", { name: "创建计划" }).click();

  const row = page.locator(".schedule-table-panel tbody tr").filter({ hasText: scheduleName });
  await expect(row).toBeVisible();
  await page.locator(".toast button").click();
  await page.screenshot({ path: `${output}/p2-scheduler-plans.png`, fullPage: true });
  await row.focus();
  await expect(row).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(row).toHaveAttribute("aria-selected", "true");

  await page.locator(".schedule-data-toolbar .ant-segmented-item").filter({ hasText: "暂停" }).click();
  await expect(row).toHaveCount(0);
  await page.locator(".schedule-data-toolbar .ant-segmented-item").filter({ hasText: "全部" }).click();
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: "暂停" }).click();
  await expect(row.getByText("已暂停", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "启用" }).click();
  await expect(row.getByText("已启用", { exact: true })).toBeVisible();

  await page.route("**/api/v1/schedules/*/trigger", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  const triggerButton = row.getByRole("button", { name: "立即运行" });
  await triggerButton.click();
  await expect(triggerButton).toBeDisabled();
  await expect(page.locator('.schedule-table-panel button[aria-label="立即运行"]:enabled')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "运行记录" })).toBeVisible();
  await expect(page.locator(".table-wrap tbody tr[aria-selected=true]")).toHaveCount(1);

  await page.locator(".utility-rail .ant-menu-item").filter({ hasText: "任务调度" }).click();
  await expect(page.getByText("未来 24 小时运行带")).toBeVisible();
  await page.locator(".toast button").click();
  await page.screenshot({ path: `${output}/p2-scheduler.png`, fullPage: true });
  await page.getByRole("tab", { name: /执行记录/ }).click();
  await page.screenshot({ path: `${output}/p2-scheduler-runs.png`, fullPage: true });
  await page.getByRole("tab", { name: /调度态势/ }).click();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.mouse.move(1268, 48);
  await page.keyboard.press("Escape");
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(150);
  await page.getByRole("button", { name: "收起计划图层" }).click();
  const rightCollapse = page.getByRole("button", { name: "收起任务情报" });
  if (await rightCollapse.isVisible().catch(() => false)) await rightCollapse.click();
  await expect(operationsGrid).toHaveClass(/is-left-collapsed/);
  await expect(operationsGrid).toHaveClass(/is-right-collapsed/);
  await page.mouse.move(1268, 48);
  await page.keyboard.press("Escape");
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(150);
  await expect(page.getByRole("heading", { name: "任务调度中心" })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${output}/p2-scheduler-1280.png`, fullPage: true });

  await page.getByRole("tab", { name: /执行记录/ }).click();
  await expect(page.getByText("执行记录", { exact: true }).last()).toBeVisible();
  await page.getByRole("tab", { name: /异常中心/ }).click();
  await expect(page.getByText("异常中心", { exact: true }).last()).toBeVisible();
  await page.getByRole("tab", { name: /计划管理/ }).click();
  const createdRow = page.locator(".schedule-table-panel tbody tr").filter({ hasText: scheduleName });
  await expect(createdRow).toBeVisible();
  await createdRow.getByRole("button", { name: "删除" }).click();
  await expect(page.getByText(`确定删除“${scheduleName}”吗？`)).toBeVisible();
  await page.locator(".ant-popconfirm-buttons .ant-btn-primary").click();
  await expect(createdRow).toHaveCount(0);

  const persistedFlow = await request.get(`${engine}/api/v1/flows/${createdFlow.id}`, { headers });
  expect(persistedFlow.ok()).toBe(true);
});
