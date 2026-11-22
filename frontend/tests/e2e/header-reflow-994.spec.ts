import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium, expect, test, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { installTelegramHarness } from './fixtures/mobile-tma';

const routes = [
  '/app?section=today',
  '/app?section=programs',
  '/app?section=nutrition',
  '/app?section=progress',
  '/app?section=profile',
  '/coach',
];

async function expectRouteLoaded(page: Page, route: string) {
  if (route === '/app?section=today') {
    await expect(page.locator('.today-dashboard')).toBeVisible();
  } else if (route === '/coach') {
    await expect(page.getByText('Следующий шаг по клиентам')).toBeVisible();
  } else {
    const titles: Record<string, string> = {
      '/app?section=programs': 'План',
      '/app?section=nutrition': 'Питание',
      '/app?section=progress': 'Прогресс',
      '/app?section=profile': 'Профиль и настройки',
    };
    await expect(page.getByRole('heading', { name: titles[route], exact: true })).toBeVisible();
  }
}

async function expectHeaderGeometry(page: Page, wrapped: boolean) {
  const header = page.locator('.app-mobile-header');
  const profile = header.getByRole('button', { name: 'Открыть профиль и настройки' });
  await expect(profile).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const geometry = await header.evaluate((element) => {
    const text = element.querySelector('.yfc-lockup__wordmark')!;
    const button = element.querySelector('.app-mobile-header__profile')!;
    const brand = element.querySelector('.app-mobile-header__brand')!;
    const range = document.createRange();
    range.selectNodeContents(text);
    const buttonRect = button.getBoundingClientRect();
    const brandRect = brand.getBoundingClientRect();
    const overlap = [...range.getClientRects()].reduce(
      (total, line) =>
        total +
        Math.max(0, Math.min(line.right, buttonRect.right) - Math.max(line.left, buttonRect.left)) *
          Math.max(
            0,
            Math.min(line.bottom, buttonRect.bottom) - Math.max(line.top, buttonRect.top),
          ),
      0,
    );
    return {
      overlap,
      buttonTop: buttonRect.top,
      brandBottom: brandRect.bottom,
      brandTop: brandRect.top,
      buttonWidth: buttonRect.width,
      buttonHeight: buttonRect.height,
    };
  });
  expect(geometry.overlap, page.url()).toBe(0);
  expect(geometry.buttonWidth).toBeGreaterThanOrEqual(44);
  expect(geometry.buttonHeight).toBeGreaterThanOrEqual(44);
  if (wrapped) expect(geometry.buttonTop).toBeGreaterThanOrEqual(geometry.brandBottom);
  else expect(geometry.buttonTop).toBeLessThan(geometry.brandBottom);
}

for (const theme of ['light', 'dark'] as const) {
  for (const width of [196, 393]) {
    test(`header retains accessible geometry at ${width}px in ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 852 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, trainerActive: true });
      for (const route of routes) {
        await page.goto(route);
        await expectRouteLoaded(page, route);
        await expectHeaderGeometry(page, width === 196);
        if (process.env.YFC_994_EVIDENCE_DIR) {
          const name =
            route === '/coach'
              ? 'coach'
              : new URL(route, 'http://localhost').searchParams.get('section');
          await mkdir(process.env.YFC_994_EVIDENCE_DIR, { recursive: true });
          await page.screenshot({
            path: resolve(
              process.env.YFC_994_EVIDENCE_DIR,
              `${info.project.name}-${width}-${theme}-${name}.png`,
            ),
          });
        }
      }
      const profile = page.getByRole('button', { name: 'Открыть профиль и настройки' });
      await profile.click();
      await expect(profile).toHaveAttribute('aria-expanded', 'true');
      await page.keyboard.press('Escape');
      await expect(profile).toHaveAttribute('aria-expanded', 'false');
      await expect(profile).toBeFocused();
    });
  }
}

test('header remains usable in emulated Telegram safe areas', async ({ page }) => {
  await page.setViewportSize({ width: 196, height: 852 });
  await installTelegramHarness(page, {
    viewportHeight: 852,
    viewportStableHeight: 852,
    safeAreaInset: { top: 44, right: 0, bottom: 34, left: 0 },
  });
  await installPlatformApi(page, { browserSession: false });
  await page.goto('/app?section=progress');
  await expectHeaderGeometry(page, true);
});

for (const theme of ['light', 'dark'] as const) {
  test(`header does not overlap at actual Chromium zoom 200% in ${theme}`, async ({
    browserName,
    baseURL,
  }, info) => {
    test.skip(browserName !== 'chromium', 'Browser zoom is controlled with a Chromium extension');
    const extension = info.outputPath('zoom-extension');
    await mkdir(extension, { recursive: true });
    await writeFile(
      resolve(extension, 'manifest.json'),
      JSON.stringify({
        manifest_version: 3,
        name: 'YFC local header zoom test',
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
      viewport: { width: 393, height: 852 },
      ignoreDefaultArgs: ['--disable-extensions'],
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
    });
    try {
      const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent('serviceworker'));
      const page = context.pages()[0] ?? (await context.newPage());
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, trainerActive: true });
      await page.goto(new URL('/app?section=today', baseURL!).toString());
      const zoom = await worker.evaluate<number>(`(async () => {
        const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
        await chrome.tabs.setZoom(tab.id, 2);
        return chrome.tabs.getZoom(tab.id);
      })()`);
      expect(zoom).toBe(2);
      for (const route of routes) {
        await page.goto(new URL(route, baseURL!).toString());
        await expectRouteLoaded(page, route);
        await expectHeaderGeometry(page, true);
        const name =
          route === '/coach' ? 'coach' : new URL(route, baseURL!).searchParams.get('section');
        const evidence = process.env.YFC_994_EVIDENCE_DIR;
        if (evidence) await mkdir(evidence, { recursive: true });
        await page.screenshot({
          path: evidence
            ? resolve(evidence, `chromium-zoom200-${theme}-${name}.png`)
            : info.outputPath(`header-zoom-${name}-${theme}.png`),
        });
      }
    } finally {
      await context.close();
    }
  });
}
