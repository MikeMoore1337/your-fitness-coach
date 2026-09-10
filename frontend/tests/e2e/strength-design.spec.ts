import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ video: { mode: 'on', size: { width: 1280, height: 900 } } });

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 768, 1440]) {
    test(`redesign core surfaces ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.clock.setFixedTime(new Date('2026-09-06T12:00:00+03:00'));
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-09-06',
        measurementHistory: 'many',
        programHistory: 'many',
      });
      const failures: string[] = [];
      page.on('pageerror', (error) => failures.push(error.message));
      for (const section of ['today', 'programs', 'nutrition', 'progress', 'profile']) {
        await page.goto(`/app?section=${section}`);
        await expect(page.locator('.app-shell')).toBeVisible();
        await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
        const contrast = await page.evaluate(() => {
          const styles = getComputedStyle(document.documentElement);
          const luminance = (token: string) => {
            const hex = styles.getPropertyValue(token).trim().replace('#', '');
            const channels = [0, 2, 4].map((offset) => {
              const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
              return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
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
            text: ratio('--v2-text-primary', '--v2-canvas'),
            muted: ratio('--v2-text-secondary', '--v2-surface'),
            action: ratio('--v2-on-lime', '--v2-lime'),
            focus: ratio('--v2-focus', '--v2-surface'),
          };
        });
        expect(contrast.text).toBeGreaterThanOrEqual(4.5);
        expect(contrast.muted).toBeGreaterThanOrEqual(4.5);
        expect(contrast.action).toBeGreaterThanOrEqual(4.5);
        expect(contrast.focus).toBeGreaterThanOrEqual(3);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
          width,
        );
        await page.screenshot({ path: testInfo.outputPath(`${section}.png`), fullPage: true });
        await page.screenshot({ path: testInfo.outputPath(`${section}-viewport.png`) });
      }
      expect(failures).toEqual([]);
    });
  }
}

test.describe('motion demonstration', () => {
  test('scene finishes offscreen and hidden without replaying or delaying actions', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto('/');
    const scene = page.locator('.strength-scene');
    await expect(page.getByRole('link', { name: 'Начать', exact: true })).toBeInViewport();
    await expect(scene).toHaveAttribute('data-phase', '0');
    for (const chapter of await page.locator('.landing-chapter').all()) {
      await chapter.scrollIntoViewIfNeeded();
      await expect(chapter).toHaveAttribute('data-motion-phase', 'idle');
    }
    await scene.scrollIntoViewIfNeeded();
    await expect(scene).toHaveAttribute('data-phase', '0');
    await page.reload();
    await expect(scene).toHaveAttribute('data-phase', '0');
    await page.locator('footer').scrollIntoViewIfNeeded();
    await expect(scene).toHaveAttribute('data-phase', '2');
    await scene.scrollIntoViewIfNeeded();
    await expect(scene).toHaveAttribute('data-phase', '2');
    await page.reload();
    await expect(scene).toHaveAttribute('data-phase', '0');
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(scene).toHaveAttribute('data-phase', '0');
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(scene).toHaveAttribute('data-phase', '0');
  });
});
