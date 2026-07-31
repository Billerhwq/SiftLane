import { expect, test } from "@playwright/test";

const engine = "http://127.0.0.1:8092";
const output = "D:/Siftlane/outputs";

test("P2 branch, retry inspector and scheduler close the UI loop", async ({ page, request }) => {
  const suffix = Date.now().toString().slice(-6);
  const flowName = `P2 branch ${suffix}`;
  const flowResponse = await request.post(`${engine}/api/v1/flows`, {
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

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByText(flowName, { exact: true }).first().click();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  const branch = page.locator(".react-flow__node").filter({ hasText: "Published?" });
  await expect(branch.locator(".condition-handle")).toHaveCount(2);
  await branch.click();
  await expect(page.getByText("Retry policy", { exact: true })).toBeVisible();
  await expect(page.locator(".inspector input[type=number]").first()).toHaveValue("1");
  await page.screenshot({ path: `${output}/p2-branch-retry.png`, fullPage: true });

  await page.getByRole("button", { name: "调度" }).click();
  const drawer = page.getByRole("dialog", { name: "调度计划" });
  await expect(drawer).toBeVisible();
  const scheduleName = `P2 schedule ${suffix}`;
  await drawer.getByLabel("名称").fill(scheduleName);
  await drawer.getByLabel("流程").selectOption({ label: flowName });
  await drawer.getByLabel("Cron").fill("0 8 * * *");
  await drawer.getByRole("button", { name: "创建计划" }).click();
  const row = drawer.locator(".schedule-row").filter({ hasText: scheduleName });
  await expect(row).toBeVisible();
  await row.locator(".mini-switch input").click({ force: true });
  await expect(row.getByText("已暂停")).toBeVisible();
  await row.getByRole("button", { name: "立即运行" }).click();
  await expect(page.getByText("计划已触发")).toBeVisible();
  await page.screenshot({ path: `${output}/p2-scheduler.png`, fullPage: true });
  await drawer.getByRole("button", { name: "关闭" }).click();
  await expect(page.locator(".data-view .table-wrap tbody tr").first()).toBeVisible();
});
