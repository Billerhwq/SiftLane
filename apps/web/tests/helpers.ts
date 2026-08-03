import type { APIRequestContext, Page } from "@playwright/test";

export const E2E_USERNAME = "admin";
export const E2E_PASSWORD = "Admin-password-123";
export const E2E_API_BASE_URL = process.env.SIFTLANE_E2E_API_BASE_URL ?? "http://127.0.0.1:8090";

export async function apiAuthorization(request: APIRequestContext): Promise<Record<string, string>> {
  const healthResponse = await request.get(`${E2E_API_BASE_URL}/health`);
  if (healthResponse.ok() && (await healthResponse.json() as { authMode?: string }).authMode === "local") return {};
  const response = await request.post(`${E2E_API_BASE_URL}/api/v1/auth/login`, {
    data: { username: E2E_USERNAME, password: E2E_PASSWORD },
  });
  if (!response.ok()) throw new Error(`E2E login failed: ${response.status()}`);
  return { Authorization: `Bearer ${(await response.json()).access_token as string}` };
}

export async function openControlRoom(page: Page): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await page.goto("/", { waitUntil: "domcontentloaded" });
      const login = page.getByRole("heading", { name: "登录", exact: true });
      await Promise.race([
        login.waitFor({ state: "visible", timeout: 10_000 }),
        page.locator(".app-shell").waitFor({ state: "visible", timeout: 10_000 }),
      ]);
      if (await login.isVisible().catch(() => false)) {
        await page.getByLabel("用户名").fill(E2E_USERNAME);
        await page.getByLabel("密码").fill(E2E_PASSWORD);
        await page.getByRole("button", { name: "登录", exact: true }).click();
        await page.getByText("执行引擎在线").waitFor();
      }
      return;
    } catch (error) {
      if (attempt === 3 || !String(error).includes("ERR_ABORTED")) throw error;
      await page.waitForTimeout(250);
    }
  }
}
