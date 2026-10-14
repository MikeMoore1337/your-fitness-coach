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
        const icons = page.locator('[data-icon]');
        expect(await icons.count()).toBeGreaterThan(0);
        for (const icon of await icons.all()) {
          await expect(icon).toHaveAttribute('viewBox', '0 0 24 24');
          await expect(icon).toHaveAttribute('stroke', 'currentColor');
          await expect(icon).toHaveAttribute('stroke-width', '1.8');
          await expect(icon.locator('img')).toHaveCount(0);
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

for (const width of [390, 1440]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`native input Icon resources retain editing and search clear ${width} ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      await page.goto('/app?section=profile');
      await expect(
        page.getByRole('heading', { name: 'Профиль и настройки', exact: true }),
      ).toBeVisible();
      await page.locator('#profile-personal > summary').click();
      const date = page.getByLabel('Дата рождения', { exact: true });
      await expect(date).toBeVisible();
      await expect(date.locator('..').locator('[data-icon="calendar"]')).toBeVisible();
      await date.fill('1990-06-15');
      await expect(date).toHaveValue('1990-06-15');

      await page.locator('#profile-notifications > summary').click();
      const time = page.getByLabel('Час для напоминаний без точного времени', { exact: true });
      await expect(time).toBeVisible();
      await expect(time.locator('..').locator('[data-icon="clock"]')).toBeVisible();
      await time.fill('10:00');
      await expect(time).toHaveValue('10:00');
      await expect(page.locator('#profile-notifications')).toHaveAttribute('open');

      await page.goto('/app?section=catalog');
      await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();
      const search = page.getByRole('searchbox', { name: 'Поиск', exact: true });
      const rows = page.locator('.exercise-catalog-item');
      await expect(rows.first()).toBeVisible();
      const initialCount = await rows.count();
      await search.fill('Жим');
      await expect(search).toHaveValue('Жим');
      const box = await search.boundingBox();
      if (!box) throw new Error('Missing visible search control geometry');
      await search.click({ position: { x: box.width - 22, y: box.height / 2 } });
      await expect(search).toHaveValue('');
      await expect(rows).toHaveCount(initialCount);

      await page.goto('/nutrition');
      const sex = page.getByRole('combobox', { name: 'Пол', exact: true });
      await expect(sex).toBeVisible();
      await expect(sex).toHaveCSS('background-image', /svg/);
      await expect(sex).toHaveCSS('appearance', 'none');
      await expect(sex).toHaveCSS('padding-right', '42px');
      await sex.selectOption({ label: 'Женский' });
      await expect(sex.locator('option:checked')).toHaveText('Женский');
      if (process.env.CAPTURE_ICONS_AFTER === '1') {
        await page.screenshot({
          path: testInfo.outputPath(
            'public-nutrition-' + testInfo.project.name + '-' + theme + '-' + width + '.png',
          ),
          scale: 'css',
          fullPage: false,
          animations: 'disabled',
          caret: 'hide',
        });
      }
    });
  }
}
