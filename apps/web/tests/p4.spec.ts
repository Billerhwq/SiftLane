import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { apiAuthorization, openControlRoom } from "./helpers";

const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

test("P4 managed connector, encrypted secret and NDJSON delivery close the browser loop", async ({ page, request }) => {
  const headers = await apiAuthorization(request);
  const flowResponse = await request.post("http://127.0.0.1:8090/api/v1/flows", {
    headers,
    data: {
      name: `P4 delivery ${Date.now().toString().slice(-6)}`,
      description: "",
      enabled: true,
      visibility: "team",
      max_items: 10,
      timeout_seconds: 30,
      parameter_schema: { type: "object" },
      nodes: [
        { id: "start", type: "start", name: "Start", config: { urls: ["http://127.0.0.1:8877/integration.html"] } },
        { id: "emit", type: "emit", name: "Emit", config: {} },
      ],
      edges: [{ id: "edge", source: "start", target: "emit" }],
    },
  });
  expect(flowResponse.ok()).toBeTruthy();
  const flow = await flowResponse.json() as { id: string };
  const runResponse = await request.post("http://127.0.0.1:8090/api/v1/runs", {
    headers,
    data: { flow_id: flow.id, parameters: {}, idempotency_key: crypto.randomUUID() },
  });
  expect(runResponse.ok()).toBeTruthy();

  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);
  await page.getByRole("button", { name: "连接器" }).click();
  const drawer = page.getByRole("dialog", { name: "连接器与交付" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("JSON Feed", { exact: true })).toBeVisible();
  await expect(drawer.locator(".connector-row span").filter({ hasText: "io.siftlane.json-feed" })).toBeVisible();

  await drawer.getByRole("button", { name: "密钥", exact: true }).click();
  await drawer.getByLabel("作用域").selectOption("connector");
  await drawer.getByLabel("资源").selectOption("io.siftlane.json-feed");
  await drawer.getByLabel("密钥名称").fill("p4-browser-key");
  await drawer.getByLabel("密钥值").fill("browser-secret-never-rendered");
  await drawer.getByRole("button", { name: "加密保存" }).click();
  await expect(page.getByText("密钥已加密保存")).toBeVisible();
  await expect(drawer.getByText("p4-browser-key", { exact: true })).toBeVisible();
  await expect(drawer.getByText("browser-secret-never-rendered")).toHaveCount(0);

  await drawer.getByRole("button", { name: "交付", exact: true }).click();
  const targetName = `P4 archive ${Date.now().toString().slice(-6)}`;
  await drawer.getByLabel("目标名称").fill(targetName);
  await drawer.getByLabel("类型").selectOption("ndjson");
  await drawer.getByRole("button", { name: "创建目标" }).click();
  await expect(page.getByText("交付目标已创建")).toBeVisible();
  await expect(drawer.locator(".target-row strong").filter({ hasText: targetName })).toBeVisible();
  await drawer.getByLabel("交付目标").selectOption({ label: targetName });
  await drawer.getByLabel("运行结果").selectOption({ index: 1 });
  await drawer.getByRole("button", { name: "立即交付" }).click();
  await expect(page.getByText("交付请求已处理")).toBeVisible();
  await expect(drawer.locator(".delivery-history strong").filter({ hasText: "succeeded" }).first()).toBeVisible();
  await expect(drawer.getByText(/exports\//).first()).toBeVisible();
  await page.screenshot({ path: `${output}/p4-integrations-delivery.png`, fullPage: true });
});
