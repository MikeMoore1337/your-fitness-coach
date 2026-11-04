import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

// Real browser screenshots of the approved implementation, using synthetic fixtures only.
for (const theme of ['dark', 'light'] as const) {
  for (const width of [393, 1440]) {
    test(`approved day editor ${theme} ${width}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: width < 600 ? 852 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      let writes = 0;
      page.on('request', (request) => {
        if (
          request.method() !== 'GET' &&
          new URL(request.url()).pathname.includes('/programs/templates')
        )
          writes++;
      });
      await page.goto('/app?section=programs&view=manage&start=create');
      const builder = page.locator('#program-builder');
      await expect(builder.getByRole('heading', { name: 'Создать свою программу' })).toBeVisible();
      await builder.getByRole('textbox', { name: 'Название', exact: true }).fill('Моя программа');
      await expect(builder.locator('[data-icon="move-up"], [data-icon="move-down"]')).toHaveCount(
        0,
      );
      const addDay = builder.getByRole('button', { name: 'Добавить день', exact: true });
      const addExercise = builder.getByRole('button', { name: 'Добавить упражнение', exact: true });
      const dayBox = await addDay.boundingBox();
      const exerciseBox = await addExercise.boundingBox();
      expect(dayBox).not.toBeNull();
      expect(exerciseBox).not.toBeNull();
      expect(Math.abs(dayBox!.x - exerciseBox!.x)).toBeLessThan(1);
      expect(Math.abs(dayBox!.width - exerciseBox!.width)).toBeLessThan(1);
      expect(dayBox!.height).toBeGreaterThanOrEqual(44);
      await expect(builder.getByRole('button', { name: 'Настройки и расписание' })).toHaveCount(0);
      await builder.screenshot({ path: info.outputPath('overview.png') });
      const settings = builder.locator('.program-builder-settings');
      await settings.locator(':scope > summary').click();
      await expect(builder.locator('.program-builder-primary')).toBeHidden();
      await settings
        .getByRole('combobox', { name: 'Цель', exact: true })
        .selectOption('muscle_gain');
      await settings.getByRole('spinbutton', { name: 'Длительность, недель' }).fill('4');
      await expect(settings.getByRole('button', { name: 'Сохранить настройки' })).toBeEnabled();
      await expect(settings.locator('.program-builder-optional')).not.toHaveAttribute('open', '');
      await settings.screenshot({ path: info.outputPath('settings.png') });
      await settings.getByRole('button', { name: 'Сохранить настройки' }).click();
      await expect(builder.locator('.program-builder-primary')).toBeVisible();
      await expect(builder.getByRole('textbox', { name: 'Название', exact: true })).toHaveValue(
        'Моя программа',
      );
      await settings.locator(':scope > summary').click();
      await expect(settings.getByRole('spinbutton', { name: 'Длительность, недель' })).toHaveValue(
        '4',
      );
      await page.keyboard.press('Escape');
      await expect(builder.locator('.program-builder-primary')).toBeVisible();
      expect(writes).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
    });
  }
}
