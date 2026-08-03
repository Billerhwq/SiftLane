import { expect, test } from "@playwright/test";

import { apiAuthorization, E2E_API_BASE_URL, openControlRoom } from "./helpers";

const engine = E2E_API_BASE_URL;

test.afterEach(async ({ page }) => {
  if (!page.isClosed()) await page.close({ runBeforeUnload: false });
});

test("dragging keeps static nodes visible and persists only the final position", async ({ page, request }) => {
  const suffix = Date.now().toString().slice(-6);
  const flowName = `Drag stability ${suffix}`;
  const headers = await apiAuthorization(request);
  const createResponse = await request.post(`${engine}/api/v1/flows`, {
    headers,
    data: {
      name: flowName,
      nodes: [
        { id: "start", type: "start", name: "Static input", x: 80, y: 220, config: { urls: ["https://example.com"] } },
        { id: "request", type: "http_request", name: "Moving request", x: 360, y: 220, config: { url: "{{url}}" } },
        { id: "emit", type: "emit", name: "Static output", x: 640, y: 220, config: {} },
      ],
      edges: [
        { id: "a", source: "start", target: "request" },
        { id: "b", source: "request", target: "emit" },
      ],
    },
  });
  expect(createResponse.status()).toBe(201);
  const created = await createResponse.json() as { id: string };

  await page.setViewportSize({ width: 1440, height: 900 });
  await openControlRoom(page);
  await page.getByText(flowName, { exact: true }).first().click();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);

  const moving = page.locator(".react-flow__node").filter({ hasText: "Moving request" });
  const save = page.locator(".workspace-bar").getByRole("button", { name: "保存" });
  await expect(moving).toBeVisible();
  await expect(save).toBeDisabled();

  await page.evaluate(() => {
    const nodes = [...document.querySelectorAll<HTMLElement>(".react-flow__node")];
    const stationary = nodes.filter((node) => !node.textContent?.includes("Moving request"));
    const visibilityHistory = stationary.map((node) => [getComputedStyle(node).visibility]);
    const observers = stationary.map((node, index) => {
      const observer = new MutationObserver(() => {
        visibilityHistory[index].push(getComputedStyle(node).visibility);
      });
      observer.observe(node, { attributes: true, attributeFilter: ["style"] });
      return observer;
    });
    Object.assign(window, { __dragVisibilityHistory: visibilityHistory, __dragVisibilityObservers: observers });
  });

  const box = await moving.boundingBox();
  expect(box).not.toBeNull();
  const startX = box!.x + box!.width / 2;
  const startY = box!.y + box!.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 180, startY + 110, { steps: 60 });

  await expect(save).toBeDisabled();
  const hiddenDuringDrag = await page.evaluate(() => {
    const histories = (window as Window & { __dragVisibilityHistory?: string[][] }).__dragVisibilityHistory ?? [];
    return histories.some((history) => history.includes("hidden"));
  });
  expect(hiddenDuringDrag).toBe(false);

  await page.mouse.up();
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page.getByText(/已保存版本/)).toBeVisible();

  const savedResponse = await request.get(`${engine}/api/v1/flows/${created.id}`, { headers });
  expect(savedResponse.ok()).toBe(true);
  const saved = await savedResponse.json() as { nodes: Array<{ id: string; x: number; y: number }> };
  const savedMovingNode = saved.nodes.find((node) => node.id === "request");
  expect(savedMovingNode).toBeDefined();
  expect(savedMovingNode!.x).toBeGreaterThan(360);
  expect(savedMovingNode!.y).toBeGreaterThan(220);

  await page.evaluate(() => {
    const observers = (window as Window & { __dragVisibilityObservers?: MutationObserver[] }).__dragVisibilityObservers ?? [];
    observers.forEach((observer) => observer.disconnect());
  });
  expect((await request.delete(`${engine}/api/v1/flows/${created.id}`, { headers })).ok()).toBe(true);
});
