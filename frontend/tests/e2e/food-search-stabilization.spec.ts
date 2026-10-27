import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const cases = [
  { label: 'web-360', viewport: { width: 360, height: 800 }, telegram: false },
  { label: 'tma-390-dark', viewport: { width: 390, height: 844 }, telegram: true },
  { label: 'web-430', viewport: { width: 430, height: 932 }, telegram: false },
] as const;

for (const current of cases) {
  test(`external food can be selected after local search hierarchy (${current.label})`, async ({
    page,
  }) => {
    await page.setViewportSize(current.viewport);
    if (current.telegram) {
      await installTelegramHarness(page, {
        colorScheme: 'dark',
        viewportHeight: current.viewport.height,
        viewportStableHeight: current.viewport.height,
      });
    }
    await installPlatformApi(page, { browserSession: !current.telegram });
    let importedPayload: Record<string, unknown> | null = null;
    await page.route('**/api/v1/nutrition/foods', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback();
        return;
      }
      importedPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        json: {
          id: 82,
          name: 'Nutella hazelnut spread',
          brand: 'Ferrero',
          barcode: '3017620422003',
          energy_kcal_per_100g: '539.00',
          protein_g_per_100g: '6.300',
          fat_g_per_100g: '30.900',
          carbs_g_per_100g: '57.500',
          fiber_g_per_100g: null,
          standard_serving_amount: null,
          standard_serving_unit: null,
          standard_serving_weight_g: null,
          food_type: 'user',
          is_favorite: false,
          last_used_at: null,
          created_at: '2026-08-29T18:00:00Z',
          updated_at: '2026-08-29T18:00:00Z',
        },
      });
    });
    await page.route('**/api/v1/nutrition/foods/search*', async (route) => {
      const url = new URL(route.request().url());
      const includeExternal = url.searchParams.get('include_external') === 'true';
      await route.fulfill({
        json: {
          items: [],
          external_items: includeExternal
            ? [
                {
                  name: 'Nutella hazelnut spread',
                  brand: 'Ferrero',
                  barcode: '3017620422003',
                  energy_kcal_per_100g: '539.00',
                  protein_g_per_100g: '6.300',
                  fat_g_per_100g: '30.900',
                  carbs_g_per_100g: '57.500',
                  fiber_g_per_100g: null,
                  standard_serving_amount: null,
                  standard_serving_unit: null,
                  standard_serving_weight_g: null,
                  external_id: '3017620422003',
                  source: {
                    provider: 'open_food_facts',
                    attribution: 'Open Food Facts contributors',
                    source_url: 'https://world.openfoodfacts.org/product/3017620422003',
                    license: 'ODbL-1.0',
                    license_url: 'https://opendatacommons.org/licenses/odbl/1-0/',
                  },
                },
              ]
            : [],
          total: 0,
          limit: 20,
          offset: 0,
          provider_status: includeExternal ? 'available' : 'not_requested',
        },
      });
    });

    await page.goto('/app?section=nutrition');
    const breakfast = page.getByRole('region', { name: /Завтрак/ });
    await breakfast.getByRole('button', { name: /Добавить/ }).click();
    const nameSearch = page.getByRole('searchbox', { name: 'Найти продукт' });
    await expect(nameSearch).toBeVisible();
    await expect(page.getByRole('button', { name: /штрихкод/i })).not.toBeVisible();
    await nameSearch.fill('нутелла');

    await expect(page.getByText('Nutella hazelnut spread')).toBeVisible();
    await expect(page.getByText(/Ferrero/)).toBeVisible();
    await expect(page.getByRole('link', { name: 'Источник' })).toHaveAttribute(
      'href',
      'https://world.openfoodfacts.org/product/3017620422003',
    );
    await expectNoHorizontalOverflow(page);
    if (current.telegram) {
      await page.setViewportSize({ width: current.viewport.width, height: 430 });
      await expect
        .poll(() =>
          page.evaluate(() =>
            document.documentElement.style.getPropertyValue('--yfc-viewport-height'),
          ),
        )
        .toBe('430px');
      const [searchBox, panelBox] = await Promise.all([
        nameSearch.boundingBox(),
        page.locator('.nutrition-picker__panel').boundingBox(),
      ]);
      expect(searchBox).not.toBeNull();
      expect(panelBox).not.toBeNull();
      expect(searchBox!.y + searchBox!.height).toBeLessThanOrEqual(430);
      expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(430);
    }
    await page.screenshot({
      path: `../.artifacts/screenshots/task-113A-round-4/food-search-keyboard-${current.label}.png`,
    });
    await page.getByRole('button', { name: 'Выбрать продукт' }).click();
    await expect(page.getByRole('heading', { name: 'Nutella hazelnut spread' })).toBeVisible();
    const amount = page.getByRole('spinbutton', { name: 'Количество' });
    await expect(amount).toHaveValue('100');
    await expect(amount).toBeFocused();
    await expect(amount).toBeInViewport();
    expect(importedPayload).toMatchObject({
      name: 'Nutella hazelnut spread',
      brand: 'Ferrero',
      barcode: '3017620422003',
      energy_kcal_per_100g: '539.00',
    });
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-113A-round-4/food-search-selected-result-${current.label}.png`,
    });
  });
}
