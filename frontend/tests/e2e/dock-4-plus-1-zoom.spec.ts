import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium, expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

for (const theme of ['light', 'dark'] as const) {
  test(`dock reflows at actual Chromium zoom 200% in ${theme}`, async ({
    browserName,
    baseURL,
  }, info) => {
    test.skip(browserName !== 'chromium', 'Browser zoom is controlled with a Chromium extension');
    test.setTimeout(90_000);
    const extension = info.outputPath('zoom-extension');
    await mkdir(extension, { recursive: true });
    await writeFile(
      resolve(extension, 'manifest.json'),
      JSON.stringify({
        manifest_version: 3,
        name: 'YFC local dock zoom test',
        version: '1.0',
        permissions: ['tabs'],
        background: { service_worker: 'background.js' },
      }),
    );
    await writeFile(
      resolve(extension, 'background.js'),
      'chrome.runtime.onInstalled.addListener(() => {});',
    );
    const context = await chromium.launchPersistentContext('', {
      channel: 'chromium',
      headless: true,
      viewport: { width: 393, height: 844 },
      ignoreDefaultArgs: ['--disable-extensions'],
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
    });
    try {
      const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent('serviceworker'));
      const page = context.pages()[0] ?? (await context.newPage());
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-09' });
      await page.goto(new URL('/app?section=today', baseURL!).toString());
      await expect(page.locator('.today-dashboard')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const zoom = await worker.evaluate<number>(`(async () => {
        const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
        await chrome.tabs.setZoom(tab.id, 2);
        return chrome.tabs.getZoom(tab.id);
      })()`);
      expect(zoom).toBe(2);
      const dock = page.locator('#appBottomNav');
      const add = dock.getByRole('button', { name: 'Быстро добавить' });
      const tabs = dock.locator('.app-bottom-nav__primary > a');
      for (const width of [320, 360, 390, 393, 430]) {
        await page.setViewportSize({ width, height: 844 });
        await expect(tabs).toHaveCount(4);
        await expect(add).toBeVisible();
        await expect(tabs.first().locator('.app-bottom-nav__label')).toHaveCSS('font-size', '10px');
        const geometry = await tabs.evaluateAll((items) =>
          items.map((item) => {
            const box = item.getBoundingClientRect();
            const label = item.querySelector<HTMLElement>('.app-bottom-nav__label')!;
            return {
              width: box.width,
              height: box.height,
              y: Math.round(box.y),
              text: label.textContent,
              fontSize: getComputedStyle(label).fontSize,
              padding: getComputedStyle(item).padding,
              viewport: window.innerWidth,
              media250: window.matchMedia('(max-width: 250px)').matches,
              rootFont: getComputedStyle(document.documentElement).fontSize,
              safe: getComputedStyle(document.documentElement).getPropertyValue(
                '--yfc-layout-safe-left',
              ),
              dock: document.querySelector('#appBottomNav')?.getBoundingClientRect().toJSON(),
              capsule: item.parentElement?.getBoundingClientRect().toJSON(),
              labelWidth: label.clientWidth,
              textWidth: label.scrollWidth,
            };
          }),
        );
        expect(new Set(geometry.map((item) => item.y)).size, `rows at ${width}`).toBe(2);
        for (const item of geometry) {
          expect(item.width).toBeGreaterThanOrEqual(44);
          expect(item.height).toBeGreaterThanOrEqual(44);
          expect(item.textWidth, JSON.stringify({ width, item })).toBeLessThanOrEqual(
            item.labelWidth + 1,
          );
        }
        const addBox = (await add.boundingBox())!;
        expect(addBox.width).toBeGreaterThanOrEqual(44);
        expect(addBox.height).toBeGreaterThanOrEqual(44);
        if (width === 393)
          await page.screenshot({ path: info.outputPath(`dock-zoom-200-${theme}.png`) });
        await add.click();
        await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toHaveCount(0);
        await expect(add).toBeFocused();
      }
    } finally {
      await context.close();
    }
  });
}
