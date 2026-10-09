import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block' });

for (const width of [320, 360, 393, 430, 768, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`#870 full selected goal ${width} ${theme}`, async ({ page }, testInfo) => {
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
      await installPlatformApi(page, { browserSession: width !== 393 });
      const received = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith('/api/v1/me'),
      );
      await page.goto('/app?section=profile');
      const user = await (await received).json();
      const writes: Record<string, unknown>[] = [];
      await page.route('**/api/v1/me/profile', async (route) => {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        writes.push(body);
        user.profile = { ...user.profile, ...body };
        await route.fulfill({ json: user });
      });
      await page.route('**/api/v1/me', (route) => route.fulfill({ json: user }));
      await page.getByRole('link', { name: 'Цели', exact: true }).click();
      const goal = page.getByRole('combobox', { name: 'Цель', exact: true });
      await goal.selectOption('recomposition');
      const hint = page.locator('#profile-goal-value');
      await expect(hint).toHaveText('Улучшить форму без фокуса на вес');
      await expect(goal).toHaveAccessibleDescription('Улучшить форму без фокуса на вес');
      await goal.evaluate((node) => node.scrollIntoView({ block: 'center' }));
      const size = await hint.evaluate((node) => ({
        width: node.clientWidth,
        scrollWidth: node.scrollWidth,
        height: node.clientHeight,
        scrollHeight: node.scrollHeight,
      }));
      expect(size.scrollWidth).toBeLessThanOrEqual(size.width + 1);
      expect(size.scrollHeight).toBeLessThanOrEqual(size.height + 1);
      expect((await goal.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width + 1,
      );
      await page.screenshot({ path: testInfo.outputPath('full-selected-goal.png') });

      await page.locator('#profile-personal > summary').click();
      await page.getByRole('link', { name: 'Цели', exact: true }).click();
      await expect(goal).toHaveValue('recomposition');
      expect(writes).toHaveLength(0);
      await page.getByRole('button', { name: 'Сохранить изменения', exact: true }).click();
      await expect(page.getByText('Профиль сохранён', { exact: true })).toBeVisible();
      expect(writes).toHaveLength(1);
      expect(writes[0]).toMatchObject({
        goal: 'recomposition',
        height_cm: 168,
        workouts_per_week: 3,
      });
      await page.reload();
      await page.getByRole('link', { name: 'Цели', exact: true }).click();
      await expect(goal).toHaveValue('recomposition');
      await expect(hint).toHaveText('Улучшить форму без фокуса на вес');
    });
  }
}
