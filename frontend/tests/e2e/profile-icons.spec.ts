import { test, expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
for (const width of [390, 1440])
  for (const theme of ['light', 'dark'] as const) {
    test(`profile vector icons ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((t) => localStorage.setItem('app-theme', t), theme);
      await installPlatformApi(page, { browserSession: true });
      await page.route('**/api/v1/ai-coach/status', (route) =>
        route.fulfill({
          json: { ui_enabled: true, generic_available: true, personal_available: false },
        }),
      );
      await page.goto('/app?section=profile');
      for (const selector of [
        '[data-icon="account-security"]',
        '[data-icon="ai-coach"]',
      ] as const) {
        const icons = page.locator(selector);
        await expect(icons).toHaveCount(2);
        for (const icon of await icons.all()) {
          await expect(icon).toBeVisible();
          await expect(icon).toHaveAttribute('stroke', 'currentColor');
          await expect(icon).toHaveAttribute('viewBox', '0 0 24 24');
        }
      }
      await page.screenshot({ path: testInfo.outputPath('profile.png'), fullPage: true });
      if (width === 390)
        await page.getByRole('button', { name: 'Открыть профиль и настройки' }).click();
      const menu = page.locator(width === 390 ? '.app-more-panel' : '.app-bottom-nav');
      await expect(menu.locator('[data-icon="logout"]')).toHaveAttribute('stroke', 'currentColor');
      const toggle = menu.getByRole('button', { name: /Включить .* тему/ });
      await toggle.click();
      await expect(page.locator('html')).toHaveAttribute(
        'data-color-scheme',
        theme === 'dark' ? 'light' : 'dark',
      );
      await expect(toggle.locator('[data-icon]')).toHaveAttribute(
        'data-icon',
        `theme-${theme === 'dark' ? 'moon' : 'sun'}`,
      );
      await page.screenshot({ path: testInfo.outputPath('menu.png') });
    });
  }
