import { test, expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
for (const width of [390, 1440])
  for (const theme of ['light', 'dark'] as const) {
    test(`profile squircle icons ${width} ${theme}`, async ({ page }, testInfo) => {
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
      for (const [selector, asset] of [
        ['[data-icon="account-security"]', 'security'],
        ['[data-icon="ai-coach"]', 'ai'],
      ]) {
        const icons = page.locator(selector);
        await expect(icons).toHaveCount(2);
        for (const icon of await icons.all()) {
          await expect(icon).toBeVisible();
          const img = icon.locator('img:visible');
          await expect(img).toHaveAttribute('src', `/assets/icons/flat-${asset}.webp`);
          await expect
            .poll(() => img.evaluate((n: HTMLImageElement) => n.naturalWidth))
            .toBeGreaterThan(0);
        }
      }
      await page.screenshot({ path: testInfo.outputPath('profile.png'), fullPage: true });
      if (width === 390)
        await page.getByRole('button', { name: 'Открыть профиль и настройки' }).click();
      const menu = page.locator(width === 390 ? '.app-more-panel' : '.app-bottom-nav');
      await expect(menu.locator('[data-icon="logout"] img:visible')).toHaveAttribute(
        'src',
        '/assets/icons/flat-logout.webp',
      );
      const toggle = menu.getByRole('button', { name: /Включить .* тему/ });
      await toggle.click();
      await expect(page.locator('html')).toHaveAttribute(
        'data-color-scheme',
        theme === 'dark' ? 'light' : 'dark',
      );
      await expect(toggle.locator('img:visible')).toHaveAttribute(
        'src',
        `/assets/icons/flat-${theme === 'dark' ? 'moon' : 'sun'}.webp`,
      );
      await page.screenshot({ path: testInfo.outputPath('menu.png') });
    });
  }
