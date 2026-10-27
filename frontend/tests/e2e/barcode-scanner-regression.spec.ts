import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const cases = [
  { label: 'mobile-web-360', viewport: { width: 360, height: 800 }, telegram: false },
  { label: 'mock-tma-390', viewport: { width: 390, height: 844 }, telegram: true },
  { label: 'mobile-web-430', viewport: { width: 430, height: 932 }, telegram: false },
] as const;

async function openNutritionPicker(
  page: Parameters<typeof installPlatformApi>[0],
  viewport: { width: number; height: number },
  telegram: boolean,
) {
  await page.setViewportSize(viewport);
  if (telegram) {
    await installTelegramHarness(page, {
      colorScheme: 'dark',
      viewportHeight: viewport.height,
      viewportStableHeight: viewport.height,
    });
  }
  await installPlatformApi(page, { browserSession: !telegram });
  await page.goto('/app?section=nutrition');
  await page
    .getByRole('region', { name: 'Завтрак' })
    .getByRole('button', { name: /Добавить/ })
    .click();
}

for (const current of cases) {
  test(`barcode UI stays out of the primary add paths (${current.label})`, async ({ page }) => {
    await openNutritionPicker(page, current.viewport, current.telegram);

    await expect(page.getByRole('button', { name: 'По фото этикетки' })).toBeVisible();
    await expect(page.getByRole('searchbox', { name: 'Найти продукт' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ввести вручную' })).toBeVisible();
    await expect(page.getByRole('button', { name: /штрихкод/i })).not.toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
}

test('manual food keeps the optional barcode field for future identity reuse', async ({ page }) => {
  await openNutritionPicker(page, { width: 1280, height: 900 }, false);
  await page.getByRole('button', { name: 'Ввести вручную' }).click();

  const barcode = page.getByRole('textbox', { name: 'Штрихкод' });
  await expect(barcode).toBeVisible();
  await barcode.fill('3017620422003');
  await expect(barcode).toHaveValue('3017620422003');
  await expect(page.getByRole('button', { name: 'Сканировать камерой' })).not.toBeAttached();
  await expectNoHorizontalOverflow(page);
});
