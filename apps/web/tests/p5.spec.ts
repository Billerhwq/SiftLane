import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { apiAuthorization, E2E_PASSWORD, E2E_USERNAME, openControlRoom } from "./helpers";

const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

function blockingViolations(results: Awaited<ReturnType<AxeBuilder["analyze"]>>) {
  return results.violations.filter((violation) => violation.impact === "critical" || violation.impact === "serious");
}

test("P5 health, schema, metrics and accessibility gates close the browser loop", async ({ page, request }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "登录", exact: true })).toBeVisible();
  const loginAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(blockingViolations(loginAudit), JSON.stringify(loginAudit.violations, null, 2)).toEqual([]);

  await page.getByLabel("用户名").fill(E2E_USERNAME);
  await page.getByLabel("密码").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".app-shell")).toBeVisible();

  const headers = await apiAuthorization(request);
  const ready = await request.get("http://127.0.0.1:8090/health/ready");
  expect(ready.status()).toBe(200);
  expect((await ready.json()).schemaVersion).toBe(5);
  const metrics = await request.get("http://127.0.0.1:8090/metrics");
  expect(metrics.status()).toBe(200);
  expect(await metrics.text()).toContain("siftlane_database_bytes");
  const schema = await request.get("http://127.0.0.1:8090/api/v1/operations/schema", { headers });
  expect(schema.status()).toBe(200);
  expect((await schema.json()).ready).toBe(true);

  const mainAudit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(blockingViolations(mainAudit), JSON.stringify(mainAudit.violations, null, 2)).toEqual([]);

  await page.getByRole("button", { name: "连接器" }).focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "连接器与交付" });
  await expect(drawer).toBeVisible();
  const drawerAudit = await new AxeBuilder({ page }).include(".integration-drawer").withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(blockingViolations(drawerAudit), JSON.stringify(drawerAudit.violations, null, 2)).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);

  // A 720 CSS-pixel viewport is the reflow equivalent of 200% browser zoom at 1440px.
  await page.setViewportSize({ width: 720, height: 900 });
  await page.waitForTimeout(250);
  const layout = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    return {
      overflow: document.documentElement.scrollWidth - viewportWidth,
      offenders: [...document.querySelectorAll<HTMLElement>("body *")]
        .map((element) => {
          const bounds = element.getBoundingClientRect();
          return {
            element: `${element.tagName.toLowerCase()}.${element.className}`,
            left: Math.round(bounds.left),
            right: Math.round(bounds.right),
            width: Math.round(bounds.width),
          };
        })
        .filter((entry) => entry.right > viewportWidth + 1 || entry.left < -1)
        .sort((left, right) => right.right - left.right)
        .slice(0, 8),
    };
  });
  expect(layout.overflow, JSON.stringify(layout.offenders, null, 2)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${output}/p5-production-readiness.png`, fullPage: true });
});

test("P5 authentication screen remains keyboard reachable", async ({ page }) => {
  await openControlRoom(page);
  await page.getByRole("button", { name: "退出登录" }).click();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("用户名")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("密码")).toBeFocused();
});
