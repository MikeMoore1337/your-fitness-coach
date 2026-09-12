import { expect, test, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';

async function settle(page: Page) {
  await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await expectNoHorizontalOverflow(page);
}

for (const theme of ['light', 'dark'] as const) {
  for (const width of [360, 390, 430, 1440]) {
    test(`soft glass surfaces ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.clock.setFixedTime(new Date('2026-09-12T09:00:00Z'));
      const api = await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-09-12',
      });
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));

      await page.goto('/');
      await expect(page.locator('.landing-hero')).toBeVisible();
      await settle(page);
      await expect(page.locator('.landing-hero__image')).toHaveJSProperty('complete', true);
      await expect(page.locator('.public-shell__header')).toHaveCSS('backdrop-filter', 'none');
      await expect(page.locator('.public-shell__header')).toHaveCSS(
        'background-color',
        'rgba(0, 0, 0, 0)',
      );
      await expect(page.locator('.public-shell__header')).toHaveCSS('box-shadow', 'none');
      await expect(page.locator('.public-shell__header')).toHaveCSS('border-bottom-width', '0px');
      const headerBox = await page.locator('.public-shell__header').boundingBox();
      const heroBox = await page.locator('.landing-hero').boundingBox();
      expect(headerBox).not.toBeNull();
      expect(heroBox).not.toBeNull();
      expect(headerBox!.y).toBe(heroBox!.y);
      const heroAction = page.locator('.landing-hero .landing-button--secondary');
      await expect(heroAction).toHaveCSS('background-color', 'rgba(20, 25, 25, 0.64)');
      await expect(heroAction).toHaveCSS(
        'backdrop-filter',
        'blur(3px) saturate(1.12) brightness(1.03)',
      );
      await expect(heroAction).toHaveCSS('filter', 'none');
      if (width < 500) {
        await page.getByRole('button', { name: 'Открыть меню', exact: true }).click();
        await expect(page.getByRole('navigation', { name: 'Навигация по странице' })).toBeVisible();
        await page.getByRole('button', { name: 'Закрыть меню', exact: true }).click();
      }
      await page.screenshot({ path: testInfo.outputPath(`landing-${width}-${theme}.png`) });

      await page.goto('/app?section=today');
      await expect(page.locator('.today-dashboard')).toBeVisible();
      await settle(page);
      const nav = page.locator('.app-bottom-nav');
      await expect(nav).toHaveCSS(
        'backdrop-filter',
        width < 900 ? 'blur(6px) saturate(1.12) brightness(1.03)' : 'none',
      );
      await expect(nav).toHaveCSS('filter', 'none');
      await expect(nav).toHaveCSS(
        'background-color',
        width >= 900
          ? theme === 'dark'
            ? 'rgb(32, 37, 37)'
            : 'rgb(243, 245, 245)'
          : theme === 'dark'
            ? 'rgba(28, 33, 33, 0.78)'
            : 'rgba(248, 250, 250, 0.8)',
      );
      const actionContrast = await page
        .getByRole('button', { name: 'Посмотреть упражнения', exact: true })
        .evaluate((element) => {
          const style = getComputedStyle(element);
          const canvas = getComputedStyle(document.documentElement)
            .getPropertyValue('--v2-canvas')
            .trim()
            .replace('#', '');
          const backdrop = [0, 2, 4].map((offset) =>
            parseInt(canvas.slice(offset, offset + 2), 16),
          );
          const luminance = (color: string) => {
            const rgba = color.match(/[\d.]+/g)!.map(Number);
            const alpha = rgba[3] ?? 1;
            const channels = rgba.slice(0, 3).map((value, index) => {
              const normalized = (value * alpha + (backdrop[index] ?? 0) * (1 - alpha)) / 255;
              return normalized <= 0.04045
                ? normalized / 12.92
                : ((normalized + 0.055) / 1.055) ** 2.4;
            });
            return channels.reduce(
              (sum, value, index) =>
                sum + value * (index === 0 ? 0.2126 : index === 1 ? 0.7152 : 0.0722),
              0,
            );
          };
          const ratio = (left: string, right: string) => {
            const a = luminance(left),
              b = luminance(right);
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          };
          return {
            edge: ratio(style.borderTopColor, style.backgroundColor),
            text: ratio(style.color, style.backgroundColor),
          };
        });
      expect(actionContrast.edge).toBeGreaterThanOrEqual(3);
      expect(actionContrast.text).toBeGreaterThanOrEqual(4.5);
      await page.screenshot({ path: testInfo.outputPath(`today-${width}-${theme}.png`) });

      await page.getByRole('button', { name: 'Начать тренировку', exact: true }).click();
      await expect(page.locator('.active-workout')).toBeVisible();
      const weight = page.getByRole('spinbutton', { name: /^Вес,/ }).first();
      const reps = page.getByRole('spinbutton', { name: /^Повторы,/ }).first();
      await weight.fill('18');
      await reps.fill('10');
      await expect
        .poll(() => api.workoutValues())
        .toMatchObject({ actualWeight: 18, actualReps: 10 });
      await expect(weight).toHaveCSS('backdrop-filter', 'none');
      const alpha = await weight.evaluate((element) => {
        const color = getComputedStyle(element).backgroundColor;
        return color.startsWith('rgb(') || /, 1\)$/.test(color);
      });
      expect(alpha).toBe(true);
      await settle(page);
      await page.screenshot({
        path: testInfo.outputPath(`workout-${width}-${theme}.png`),
        fullPage: true,
      });
      await page.getByRole('button', { name: /^Завершить:.*подход 1/ }).click();
      await expect.poll(() => api.workoutValues().completed).toBe(true);

      await page.goto('/app?section=nutrition');
      await expect(page.locator('.nutrition-diary')).toBeVisible();
      await settle(page);
      await page.screenshot({ path: testInfo.outputPath(`nutrition-${width}-${theme}.png`) });

      const session = await page.context().newCDPSession(page);
      await session.send('Emulation.setEmulatedMedia', {
        features: [
          { name: 'prefers-color-scheme', value: theme },
          { name: 'prefers-reduced-transparency', value: 'reduce' },
        ],
      });
      await expect(nav).toHaveCSS('backdrop-filter', 'none');
      await expect(nav).toHaveCSS(
        'background-color',
        theme === 'dark' ? 'rgb(32, 37, 37)' : 'rgb(243, 245, 245)',
      );
      await session.detach();
      await page.emulateMedia({ forcedColors: 'active' });
      await expect(nav).toHaveCSS('backdrop-filter', 'none');
      expect(errors).toEqual([]);
    });
  }

  test(`soft glass navigation mocked TMA ${theme}`, async ({ browser }, testInfo) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      colorScheme: theme,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    try {
      await installTelegramHarness(page, { colorScheme: theme });
      await installPlatformApi(page, { fixedDate: '2026-09-12' });
      await page.goto('/app?section=today');
      await expect(page.locator('.today-dashboard')).toBeVisible();
      await settle(page);
      await expect(page.locator('.app-bottom-nav')).toHaveCSS(
        'backdrop-filter',
        'blur(6px) saturate(1.12) brightness(1.03)',
      );
      await page.screenshot({ path: testInfo.outputPath(`today-tma-${theme}.png`) });
      await page.getByRole('button', { name: 'Начать тренировку', exact: true }).click();
      await expect(page.locator('.active-workout')).toBeVisible();
      await settle(page);
    } finally {
      await context.close();
    }
  });
}
