const { chromium } = require('C:/Users/26058/AppData/Local/Temp/siftlane-playwright/node_modules/playwright-core');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const root = __dirname;
const output = path.resolve(root, '../../outputs/prototypes');
const executablePath = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const requestedVariant = process.argv[2] && process.argv[2].toUpperCase();
const variants = [
  ['A', 'variant-A.html', 'wire-desk.png', '.details'],
  ['B', 'variant-B.html', 'signal-bench.png', '.detail-button'],
  ['C', 'variant-C.html', 'fold-map.png', '.detail'],
  ['D', 'variant-D.html', 'cloud-blue.png', '.detail'],
].filter(([id]) => !requestedVariant || id === requestedVariant);

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    executablePath,
    headless: true,
    args: ['--allow-file-access-from-files'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const failures = [];

  for (const [id, file, image, detailSelector] of variants) {
    const page = await context.newPage();
    const runtimeErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') runtimeErrors.push(message.text());
    });
    page.on('pageerror', (error) => runtimeErrors.push(error.message));
    await page.goto(pathToFileURL(path.join(root, file)).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts && document.fonts.ready);

    const layout = await page.evaluate(() => {
      const doc = document.documentElement;
      const visibleOutside = [...document.querySelectorAll('body *')]
        .filter((element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 1 || rect.height < 1) return false;
          return rect.left < -1 || rect.right > innerWidth + 1;
        })
        .slice(0, 8)
        .map((element) => ({ tag: element.tagName, className: String(element.className), rect: element.getBoundingClientRect().toJSON() }));
      return {
        title: document.title,
        viewport: [innerWidth, innerHeight],
        document: [doc.scrollWidth, doc.scrollHeight],
        visibleOutside,
      };
    });

    if (layout.document[0] > layout.viewport[0] || layout.document[1] > layout.viewport[1]) {
      failures.push(`${id}: document overflow ${layout.document.join('x')} > ${layout.viewport.join('x')}`);
    }
    if (layout.visibleOutside.length) failures.push(`${id}: visible elements outside viewport ${JSON.stringify(layout.visibleOutside)}`);
    if (runtimeErrors.length) failures.push(`${id}: runtime errors ${runtimeErrors.join(' | ')}`);

    const detail = page.locator(detailSelector);
    await detail.click();
    const expanded = await detail.getAttribute('aria-expanded');
    const ledgerVisible = await page.locator('.ledger').isVisible();
    if (expanded !== 'true' || !ledgerVisible) failures.push(`${id}: event ledger did not open`);
    await detail.click();
    if (await page.locator('.ledger').isVisible()) failures.push(`${id}: event ledger did not close`);

    await page.screenshot({ path: path.join(output, image) });
    console.log(`${id}: ${layout.title} ${layout.viewport.join('x')} OK`);
    await page.close();
  }

  if (!requestedVariant) {
  const board = await context.newPage();
  const boardErrors = [];
  board.on('console', (message) => {
    if (message.type() === 'error') boardErrors.push(message.text());
  });
  board.on('pageerror', (error) => boardErrors.push(error.message));
  await board.goto(pathToFileURL(path.join(root, 'index.html')).href, { waitUntil: 'load' });
  for (const id of ['A', 'B', 'C', 'D']) {
    await board.locator(`.board-tab[data-id="${id}"]`).click();
    await board.waitForFunction((variantId) => {
      const frame = document.getElementById('variantFrame');
      return frame && frame.contentWindow && frame.contentDocument &&
        frame.contentDocument.readyState === 'complete' &&
        frame.contentWindow.location.href.includes(`variant-${variantId}.html`);
    }, id);
  }
  await board.locator('.board-tab[data-id="A"]').click();
  await board.waitForFunction(() => {
    const frame = document.getElementById('variantFrame');
    return frame.contentDocument.readyState === 'complete' && frame.contentWindow.location.href.includes('variant-A.html');
  });
  await board.waitForTimeout(150);
  await board.screenshot({ path: path.join(output, 'comparison-board.png') });
  if (boardErrors.length) failures.push(`Board: runtime errors ${boardErrors.join(' | ')}`);
  await board.close();
  }
  await browser.close();

  if (failures.length) {
    console.error(failures.join('\n'));
    process.exitCode = 1;
  } else {
    console.log('All prototype checks passed.');
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
