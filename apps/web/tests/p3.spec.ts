import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { E2E_PASSWORD, E2E_USERNAME, openControlRoom } from "./helpers";

const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

test("P3 authentication, team management and audit close the browser loop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "登录", exact: true })).toBeVisible();
  await page.getByLabel("用户名").fill(E2E_USERNAME);
  await page.getByLabel("密码").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("执行引擎在线")).toBeVisible();

  await page.getByRole("button", { name: "团队" }).click();
  const drawer = page.getByRole("dialog", { name: "团队与审计" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "添加成员" }).click();
  const suffix = Date.now().toString().slice(-6);
  await drawer.getByLabel("用户名").fill(`viewer-${suffix}`);
  await drawer.getByLabel("显示名称").fill(`审计查看者 ${suffix}`);
  await drawer.getByLabel("初始密码").fill("Viewer-password-123");
  await drawer.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByText("成员已创建")).toBeVisible();
  await expect(drawer.getByText(`审计查看者 ${suffix}`)).toBeVisible();

  await drawer.getByRole("button", { name: "审计", exact: true }).click();
  await expect(drawer.getByText("user.create").first()).toBeVisible();
  await expect(drawer.getByText("安全事件")).toBeVisible();
  await page.screenshot({ path: `${output}/p3-team-audit.png`, fullPage: true });
  await drawer.getByRole("button", { name: "关闭" }).click();

  await page.getByRole("button", { name: "新建流程" }).first().click();
  const flowName = `P3 team flow ${suffix}`;
  const flowDialog = page.getByRole("dialog", { name: "新建流程" });
  await flowDialog.getByLabel("流程名称").fill(flowName);
  await flowDialog.getByRole("button", { name: "创建流程" }).click();
  await expect(page.getByRole("heading", { name: flowName })).toBeVisible();
  await page.getByLabel("可见范围").selectOption("private");
  await page.locator(".workspace-bar").getByRole("button", { name: "保存" }).click();
  await expect(page.getByText(/已保存版本/)).toBeVisible();
  await page.screenshot({ path: `${output}/p3-private-flow.png`, fullPage: true });
});

test("P3 session can be revoked from the control plane", async ({ page }) => {
  await openControlRoom(page);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "登录", exact: true })).toBeVisible();
});
