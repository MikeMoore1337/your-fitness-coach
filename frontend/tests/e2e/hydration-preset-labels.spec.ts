import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block' });

for (const width of [320, 360, 393, 430, 768, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`#869 full water labels ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((mode) => localStorage.setItem('app-theme', mode), theme);
      if (width === 393) {
        await installTelegramHarness(page, {
          colorScheme: theme,
          viewportHeight: 900,
          safeAreaInset: { top: 24, bottom: 34, left: 0, right: 0 },
        });
      }
      await installPlatformApi(page, { browserSession: width !== 393, fixedDate: '2026-08-19' });
      await page.goto('/app?section=nutrition');
      const hydration = page.getByRole('region', { name: 'Гидратация' });
      const largeGlass = hydration.getByRole('button', { name: /Большой стакан.*350 мл/ });
      await largeGlass.scrollIntoViewIfNeeded();
      for (const label of await hydration.locator('.hydration-presets button span').all()) {
        const geometry = await label.evaluate((node) => ({
          width: node.clientWidth,
          scrollWidth: node.scrollWidth,
          height: node.clientHeight,
          scrollHeight: node.scrollHeight,
          overflow: getComputedStyle(node).overflow,
          ellipsis: getComputedStyle(node).textOverflow,
        }));
        expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1);
        expect(geometry.scrollHeight).toBeLessThanOrEqual(geometry.height + 1);
        expect(geometry.ellipsis).not.toBe('ellipsis');
      }
      await expect(largeGlass.locator('strong')).toHaveText('+350 мл');
      expect((await largeGlass.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width + 1,
      );
      await hydration.screenshot({ path: testInfo.outputPath('full-water-labels.png') });
    });
  }
}
