import { test, expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

for (const width of [360, 390, 768, 1440]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`project icons ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true });
      for (const section of ['today', 'programs', 'nutrition', 'progress', 'profile']) {
        await page.goto(`/app?section=${section}`);
        await expect(page.locator('h1').first()).toBeVisible();
        await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        if (section === 'today') {
          await page.locator('.week-strip__legend-summary').click();
          await expect(page.getByRole('list', { name: 'Обозначения недели' })).toBeVisible();
        }
        await expect
          .poll(async () =>
            page
              .locator('[data-icon] img')
              .evaluateAll((images) =>
                images.every(
                  (image) =>
                    image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
                ),
              ),
          )
          .toBe(true);
        for (const image of await page.locator('[data-icon] img').all()) {
          await expect(image).toHaveAttribute('src', /\/assets\/icons\/flat-[a-z-]+\.webp$/);
        }
        await page.screenshot({
          path: testInfo.outputPath(`${section}-${width}-${theme}.png`),
          fullPage: section === 'profile' || section === 'today',
        });
      }
      await page.goto('/');
      await expect(page.locator('h1').first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: testInfo.outputPath(`landing-${width}-${theme}.png`) });
    });
  }
}
