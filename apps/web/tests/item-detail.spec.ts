import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { apiAuthorization, openControlRoom } from "./helpers";

const engine = "http://127.0.0.1:8090";
const output = fileURLToPath(new URL("../../../outputs/", import.meta.url));
mkdirSync(output, { recursive: true });

test.setTimeout(90_000);

test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close({ runBeforeUnload: false });
});

test("result rows open a full workspace detail panel", async ({ page, request }) => {
  const suffix = Date.now().toString().slice(-6);
  const flowName = `Detail workspace ${suffix}`;
  const headers = await apiAuthorization(request);
  const flowResponse = await request.post(`${engine}/api/v1/flows`, {
    headers,
    data: {
      name: flowName,
      max_items: 10,
      timeout_seconds: 60,
      nodes: [
        { id: "start", type: "start", name: "Input", x: 40, y: 220, config: { urls: ["http://127.0.0.1:8877/detail-listing.html"] } },
        { id: "request", type: "http_request", name: "List request", x: 330, y: 220, config: { url: "{{url}}", respect_robots: false } },
        {
          id: "extract",
          type: "html_extract",
          name: "Extract article links",
          x: 580,
          y: 220,
          config: {
            item_selector: "article a",
            fields: {
              listing_title: { selector: "", attribute: "text" },
              url: { selector: "", attribute: "href" },
            },
          },
        },
        { id: "detail-request", type: "http_request", name: "Article request", x: 780, y: 220, config: { url: "{{url}}", respect_robots: false } },
        {
          id: "detail-extract",
          type: "html_extract",
          name: "Extract article detail",
          x: 1030,
          y: 220,
          config: {
            item_selector: "article.story",
            fields: {
              title: "h1",
              content: { selector: "main p", attribute: "text", all: true, separator: "\n\n" },
              source: ".source",
              author: ".author",
              published_at: { selector: "time", attribute: "datetime" },
            },
          },
        },
        {
          id: "emit",
          type: "emit",
          name: "Output",
          x: 1280,
          y: 220,
          config: {
            fields: {
              external_id: "{{url}}",
              metadata: {
                source: "{{source}}",
                author: "{{author}}",
                publishedAt: "{{published_at}}",
                listingUrl: "{{seed_url}}",
                listingTitle: "{{listing_title}}",
              },
            },
          },
        },
      ],
      edges: [
        { id: "a", source: "start", target: "request" },
        { id: "b", source: "request", target: "extract" },
        { id: "c", source: "extract", target: "detail-request" },
        { id: "d", source: "detail-request", target: "detail-extract" },
        { id: "e", source: "detail-extract", target: "emit" },
      ],
    },
  });
  expect(flowResponse.status()).toBe(201);
  const flow = await flowResponse.json();

  const runResponse = await request.post(`${engine}/api/v1/runs`, {
    headers,
    data: { flow_id: flow.id, parameters: {} },
  });
  expect(runResponse.status()).toBe(202);
  const run = await runResponse.json();
  await expect.poll(async () => {
    const response = await request.get(`${engine}/api/v1/runs/${run.id}`, { headers });
    return (await response.json()).status;
  }, { timeout: 60_000 }).toBe("SUCCEEDED");

  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);
  const shellBox = await page.locator(".app-shell").boundingBox();
  expect(shellBox).toEqual({ x: 0, y: 0, width: 1440, height: 900 });
  await page.getByText(flowName, { exact: true }).first().click();
  await page.getByRole("button", { name: "结果", exact: true }).click();
  const rows = page.locator(".result-row");
  await expect(rows).toHaveCount(2);
  const firstTitle = (await rows.first().locator("td strong").innerText()).trim();
  await rows.first().locator("td").first().click();

  const detail = page.locator(".item-detail-view");
  await expect(detail).toBeVisible();
  await expect(page.locator(".data-view")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(detail.getByRole("heading", { name: firstTitle })).toBeVisible();
  await expect(detail.locator(".item-detail-kicker span")).toHaveText("Siftlane 本地测试站");
  await expect(detail.locator(".item-detail-facts dd").first()).toHaveText("Siftlane 本地测试站");
  await expect(detail.locator(".item-detail-byline")).toContainText(/采集引擎团队|控制台体验团队/);
  await expect(detail.locator(".item-detail-byline")).toContainText(/2026-08-02T(09:30|10:15):00\+08:00/);
  await expect(detail.locator(".item-detail-body p")).toHaveCount(2);
  await expect(detail.locator(".item-detail-body")).not.toContainText("列表页摘要");

  await page.getByLabel("流程名称").focus();
  await page.keyboard.press("ArrowRight");
  await expect(detail.locator("h1")).toHaveText(firstTitle);

  await detail.getByText("完整元数据", { exact: true }).click();
  await expect(detail.locator("pre")).toContainText("listingUrl");
  const currentHeading = await detail.locator("h1").innerText();
  const nextButton = detail.getByRole("button", { name: "下一条" });
  const previousButton = detail.getByRole("button", { name: "上一条" });
  const canMoveNext = await nextButton.isEnabled();
  await (canMoveNext ? nextButton : previousButton).click();
  await expect(detail.locator("h1")).not.toHaveText(currentHeading);
  const returnTitle = await detail.locator("h1").innerText();
  await page.screenshot({ path: `${output}/item-detail-desktop.png`, fullPage: true });

  await detail.getByRole("button", { name: "返回结果" }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: returnTitle }).first()).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await rows.first().locator("td").first().click();
  await expect(detail).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const overflow = await detail.evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${output}/item-detail-mobile.png`, fullPage: true });
  await page.keyboard.press("Escape");
  await expect(rows).toHaveCount(2);
});
