import type { Page } from "@playwright/test";

export async function openControlRoom(page: Page): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      await page.goto("/", { waitUntil: "domcontentloaded" });
      return;
    } catch (error) {
      if (attempt === 3 || !String(error).includes("ERR_ABORTED")) throw error;
      await page.waitForTimeout(250);
    }
  }
}
