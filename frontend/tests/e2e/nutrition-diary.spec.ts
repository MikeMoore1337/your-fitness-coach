import { expect, test, type Page, type Route } from '@playwright/test';
import type { FoodDiaryEntry, HydrationEntry } from '../../src/shared/api/types';
import { nutritionDaySummary } from './fixtures/locators';

const zeroNutrition = {
  energy_kcal: '0.00',
  protein_g: '0.000',
  fat_g: '0.000',
  carbs_g: '0.000',
  fiber_g: null,
};

const yogurtEntry: FoodDiaryEntry = {
  id: 21,
  diary_date: '2026-08-19',
  meal_type: 'breakfast',
  food_id: 3,
  recipe_id: null,
  entry_kind: 'food',
  logged_at: null,
  food_name: 'Греческий йогурт',
  food_brand: 'YFC Foods',
  amount: '180.000',
  amount_unit: 'g',
  weight_g: '180.000',
  serving_amount: null,
  serving_unit: null,
  serving_weight_g: null,
  nutrition: {
    energy_kcal: '153.00',
    protein_g: '17.100',
    fat_g: '3.600',
    carbs_g: '10.800',
    fiber_g: null,
  },
  created_at: '2026-08-19T07:00:00Z',
  updated_at: '2026-08-19T07:00:00Z',
};

const oatmealFood = {
  id: 7,
  name: 'Овсяная каша',
  brand: null,
  barcode: null,
  energy_kcal_per_100g: '360.00',
  protein_g_per_100g: '12.000',
  fat_g_per_100g: '6.000',
  carbs_g_per_100g: '62.000',
  fiber_g_per_100g: '8.000',
  standard_serving_amount: '1.000',
  standard_serving_unit: 'serving',
  standard_serving_weight_g: '50.000',
  food_type: 'system',
  is_favorite: true,
  last_used_at: '2026-08-18T07:00:00Z',
  created_at: '2026-07-01T07:00:00Z',
  updated_at: '2026-07-01T07:00:00Z',
};

const riceFood = {
  ...oatmealFood,
  id: 8,
  name: 'Рис домашний',
  energy_kcal_per_100g: '130.00',
  protein_g_per_100g: '2.700',
  fat_g_per_100g: '0.300',
  carbs_g_per_100g: '28.000',
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
};

const importedRiceFood = {
  ...riceFood,
  id: 82,
  name: 'Рис белый приготовленный, без добавления масла',
  food_type: 'user',
  is_favorite: false,
};

const externalRiceFoods = [
  {
    name: 'Рис белый приготовленный, без добавления масла',
    external_id: '2708408',
    energy_kcal_per_100g: '130.00',
  },
  {
    name: 'Рис бурый приготовленный, без добавления масла',
    external_id: '2708414',
    energy_kcal_per_100g: '123.00',
  },
  {
    name: 'Рис дикий приготовленный, без добавления масла',
    external_id: '2708424',
    energy_kcal_per_100g: '101.00',
  },
].map(({ name, external_id, energy_kcal_per_100g }) => ({
  name,
  brand: null,
  barcode: null,
  energy_kcal_per_100g,
  protein_g_per_100g: '2.700',
  fat_g_per_100g: '0.300',
  carbs_g_per_100g: '28.000',
  fiber_g_per_100g: '0.400',
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  external_id,
  source: {
    provider: 'usda_fdc',
    attribution: 'U.S. Department of Agriculture, FoodData Central',
    source_url: `https://fdc.nal.usda.gov/fdc-app.html#/food-details/${external_id}/nutrients`,
    license: 'CC0-1.0',
    license_url: 'https://creativecommons.org/publicdomain/zero/1.0/',
  },
}));

const externalPotatoFoods = [
  {
    name: 'Картофель запечённый, способ приготовления не указан',
    external_id: '2709383',
    energy_kcal_per_100g: '93.00',
  },
  {
    name: 'Картофель отварной, способ приготовления не указан',
    external_id: '2709385',
    energy_kcal_per_100g: '87.00',
  },
  {
    name: 'Картофель фри из свежего картофеля, жареный',
    external_id: '2709458',
    energy_kcal_per_100g: '289.00',
  },
  {
    name: 'Картофель жареный по-домашнему из свежего картофеля',
    external_id: '2709474',
    energy_kcal_per_100g: '185.00',
  },
  {
    name: 'Картофельное пюре, способ приготовления не указан',
    external_id: '2709492',
    energy_kcal_per_100g: '113.00',
  },
].map(({ name, external_id, energy_kcal_per_100g }) => ({
  name,
  brand: null,
  barcode: null,
  energy_kcal_per_100g,
  protein_g_per_100g: '2.000',
  fat_g_per_100g: '0.500',
  carbs_g_per_100g: '20.000',
  fiber_g_per_100g: '2.000',
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  external_id,
  source: {
    provider: 'usda_fdc',
    attribution: 'U.S. Department of Agriculture, FoodData Central',
    source_url: `https://fdc.nal.usda.gov/fdc-app.html#/food-details/${external_id}/nutrients`,
    license: 'CC0-1.0',
    license_url: 'https://creativecommons.org/publicdomain/zero/1.0/',
  },
}));

const externalEggFoods = [
  {
    name: 'Яйцо целое варёное или пашот',
    external_id: '2707154',
    energy_kcal_per_100g: '155.00',
  },
  {
    name: 'Яйцо целое жареное без добавления масла',
    external_id: '2707156',
    energy_kcal_per_100g: '174.00',
  },
  {
    name: 'Яйцо целое жареное с растительным маслом',
    external_id: '2707158',
    energy_kcal_per_100g: '196.00',
  },
  {
    name: 'Яйцо целое жареное со сливочным маслом',
    external_id: '2707159',
    energy_kcal_per_100g: '196.00',
  },
].map(({ name, external_id, energy_kcal_per_100g }) => ({
  name,
  brand: null,
  barcode: null,
  energy_kcal_per_100g,
  protein_g_per_100g: '13.000',
  fat_g_per_100g: '14.000',
  carbs_g_per_100g: '1.000',
  fiber_g_per_100g: '0.000',
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  external_id,
  source: {
    provider: 'usda_fdc',
    attribution: 'U.S. Department of Agriculture, FoodData Central',
    source_url: `https://fdc.nal.usda.gov/fdc-app.html#/food-details/${external_id}/nutrients`,
    license: 'CC0-1.0',
    license_url: 'https://creativecommons.org/publicdomain/zero/1.0/',
  },
}));

async function mockNutritionApi(
  page: Page,
  hydrationState: 'data' | 'empty' | 'error' | 'loading' = 'data',
  profileSex: 'female' | null = 'female',
) {
  let releaseHydrationLoading = () => {};
  const hydrationLoading = new Promise<void>((resolve) => {
    releaseHydrationLoading = resolve;
  });
  let entries: FoodDiaryEntry[] = [yogurtEntry];
  let hydrationEntries: HydrationEntry[] =
    hydrationState === 'empty'
      ? []
      : [
          {
            id: 81,
            volume_ml: 350,
            beverage_type: 'water',
            occurred_at: '2026-08-19T06:10:00Z',
            diary_date: '2026-08-19',
            timezone: 'Europe/Moscow',
            source: 'quick_preset',
            created_at: '2026-08-19T09:10:00',
            updated_at: '2026-08-19T09:10:00',
          },
          {
            id: 82,
            volume_ml: 500,
            beverage_type: 'tea',
            occurred_at: '2026-08-19T09:40:00Z',
            diary_date: '2026-08-19',
            timezone: 'Europe/Moscow',
            source: 'manual',
            created_at: '2026-08-19T12:40:00',
            updated_at: '2026-08-19T12:40:00',
          },
        ];
  let dayStatus: 'incomplete' | 'complete' = 'incomplete';

  await page.addInitScript(() => {
    sessionStorage.setItem('fit_access_token', 'e2e-token');
  });
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === '/api/v1/public/config') {
      return route.fulfill({
        json: {
          app_env: 'test',
          enable_dev_auth: true,
          enable_web_auth: false,
          enable_email_auth: false,
          telegram_bot_username: '',
          oauth_providers: [],
        },
      });
    }
    if (path === '/api/v1/me') {
      return route.fulfill({
        json: {
          id: 1,
          telegram_user_id: 2001,
          username: 'nutrition_user',
          first_name: 'Анна',
          is_coach: false,
          is_admin: false,
          has_active_program: false,
          has_workout_history: false,
          onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
          profile: {
            full_name: 'Анна Петрова',
            sex: profileSex,
            timezone: 'Europe/Moscow',
            goal: 'maintenance',
            kbju: null,
          },
          trainer: null,
        },
      });
    }
    if (path === '/api/v1/auth/telegram/init') {
      return route.fulfill({
        json: { access_token: 'telegram-hydration-token', token_type: 'bearer' },
      });
    }
    if (path === '/api/v1/nutrition/hydration' && request.method() === 'GET') {
      if (hydrationState === 'loading') await hydrationLoading;
      if (hydrationState === 'error') {
        return route.fulfill({ status: 503, json: { detail: 'Гидратация временно недоступна' } });
      }
      const totalMl = hydrationEntries.reduce((sum, entry) => sum + entry.volume_ml, 0);
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') || '2026-08-19',
          timezone: 'Europe/Moscow',
          total_ml: totalMl,
          goal:
            hydrationState === 'empty'
              ? null
              : {
                  id: 1,
                  enabled: true,
                  target_ml: 2200,
                  source: 'national_academies_beverages',
                  method_version: 'nasem-ai-2005-observed-beverages-v1',
                  reference_scope: 'beverages',
                  sex: 'female',
                  adult_confirmed: true,
                  effective_from: '2026-08-19',
                  effective_to: null,
                  created_at: '2026-08-19T08:00:00',
                },
          progress_percent:
            hydrationState === 'empty' ? null : Math.round((totalMl * 1000) / 2200) / 10,
          entries: hydrationEntries,
          presets: [
            { id: null, label: 'Стакан', volume_ml: 250, beverage_type: 'water', is_default: true },
            {
              id: null,
              label: 'Большой стакан',
              volume_ml: 350,
              beverage_type: 'water',
              is_default: true,
            },
            {
              id: null,
              label: 'Бутылка',
              volume_ml: 500,
              beverage_type: 'water',
              is_default: true,
            },
            {
              id: 7,
              label: 'Термокружка',
              volume_ml: 420,
              beverage_type: 'tea',
              is_default: false,
            },
          ],
          last_logged_at: hydrationEntries[0]?.occurred_at ?? null,
          reminder_suppression_key: hydrationEntries.length
            ? 'hydration-logged:1:2026-08-19'
            : null,
          action_url: '/app?section=nutrition&date=2026-08-19&hydration=quick',
        },
      });
    }
    if (path === '/api/v1/nutrition/hydration/entries' && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        volume_ml: number;
        beverage_type: HydrationEntry['beverage_type'];
        diary_date: string;
        source: string;
      };
      const created: HydrationEntry = {
        id: 90 + hydrationEntries.length,
        volume_ml: body.volume_ml,
        beverage_type: body.beverage_type,
        occurred_at: '2026-08-19T10:00:00Z',
        diary_date: body.diary_date,
        timezone: 'Europe/Moscow',
        source: body.source,
        created_at: '2026-08-19T13:00:00',
        updated_at: '2026-08-19T13:00:00',
      };
      hydrationEntries = [created, ...hydrationEntries];
      return route.fulfill({ status: 201, json: created });
    }
    if (path.startsWith('/api/v1/nutrition/hydration/entries/') && request.method() === 'DELETE') {
      const id = Number(path.split('/').at(-1));
      hydrationEntries = hydrationEntries.filter((entry) => entry.id !== id);
      return route.fulfill({ status: 204, body: '' });
    }
    if (path === '/api/v1/nutrition/hydration/goal' && request.method() === 'POST') {
      return route.fulfill({
        json: {
          id: 2,
          enabled: true,
          target_ml: 2200,
          source: 'national_academies_beverages',
          method_version: 'nasem-ai-2005-observed-beverages-v1',
          reference_scope: 'beverages',
          sex: 'female',
          adult_confirmed: true,
          effective_from: '2026-08-19',
          effective_to: null,
          created_at: '2026-08-19T13:00:00',
        },
      });
    }
    if (path === '/api/v1/nutrition/hydration/presets' && request.method() === 'POST') {
      return route.fulfill({
        status: 200,
        json: { id: 8, ...request.postDataJSON(), is_default: false },
      });
    }
    if (path.startsWith('/api/v1/nutrition/hydration/presets/') && request.method() === 'DELETE') {
      return route.fulfill({ status: 204, body: '' });
    }
    if (path === '/api/v1/nutrition/diary' && request.method() === 'GET') {
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') || '2026-08-19',
          timezone: 'Europe/Moscow',
          meals: [
            {
              meal_type: 'breakfast',
              entries,
              totals: entries.length ? yogurtEntry.nutrition : zeroNutrition,
            },
            { meal_type: 'lunch', entries: [], totals: zeroNutrition },
            { meal_type: 'dinner', entries: [], totals: zeroNutrition },
            { meal_type: 'snacks', entries: [], totals: zeroNutrition },
          ],
          totals: {
            energy_kcal: '2020.00',
            protein_g: '141.000',
            fat_g: '69.000',
            carbs_g: '221.000',
            fiber_g: null,
          },
          targets: {
            energy_kcal: '2000.00',
            protein_g: '140.000',
            fat_g: '70.000',
            carbs_g: '220.000',
          },
          remaining: {
            energy_kcal: '-20.00',
            protein_g: '-1.000',
            fat_g: '1.000',
            carbs_g: '-1.000',
          },
          status: entries.length ? dayStatus : 'unlogged',
          status_is_explicit: dayStatus === 'complete',
        },
      });
    }
    if (path === '/api/v1/nutrition/foods/recent') {
      return route.fulfill({ json: { items: [oatmealFood], total: 1, limit: 12, offset: 0 } });
    }
    if (path === '/api/v1/nutrition/foods/favorites') {
      return route.fulfill({ json: { items: [oatmealFood], total: 1, limit: 12, offset: 0 } });
    }
    if (path === '/api/v1/nutrition/foods/search') {
      const includeExternal = url.searchParams.get('include_external') === 'true';
      const query = url.searchParams.get('q') ?? '';
      const isPotatoSearch = query.includes('картофель');
      const isEggSearch = query.includes('яйцо');
      const isGenericStateSearch = isPotatoSearch || isEggSearch;
      const externalFoods = isPotatoSearch
        ? externalPotatoFoods
        : isEggSearch
          ? externalEggFoods
          : externalRiceFoods;
      return route.fulfill({
        json: {
          items: isGenericStateSearch ? [] : [riceFood],
          external_items: includeExternal ? externalFoods : [],
          total: isGenericStateSearch ? 0 : 1,
          limit: 20,
          offset: 0,
          provider_status: includeExternal ? 'available' : 'not_requested',
          provider_statuses: includeExternal
            ? [
                { provider: 'open_food_facts', status: 'available', result_count: 0 },
                {
                  provider: 'usda_fdc',
                  status: 'available',
                  result_count: externalFoods.length,
                },
              ]
            : [],
        },
      });
    }
    if (path === '/api/v1/nutrition/foods' && request.method() === 'POST') {
      return route.fulfill({ status: 201, json: importedRiceFood });
    }
    if (path === '/api/v1/nutrition/diary/status' && request.method() === 'PUT') {
      dayStatus = 'complete';
      return route.fulfill({
        json: {
          diary_date: '2026-08-19',
          timezone: 'Europe/Moscow',
          meals: [
            { meal_type: 'breakfast', entries, totals: yogurtEntry.nutrition },
            { meal_type: 'lunch', entries: [], totals: zeroNutrition },
            { meal_type: 'dinner', entries: [], totals: zeroNutrition },
            { meal_type: 'snacks', entries: [], totals: zeroNutrition },
          ],
          totals: yogurtEntry.nutrition,
          targets: null,
          remaining: null,
          status: dayStatus,
          status_is_explicit: true,
        },
      });
    }
    if (path === '/api/v1/nutrition/diary/entries' && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        diary_date: string;
        meal_type: FoodDiaryEntry['meal_type'];
        logged_at?: string | null;
        quick_add?: {
          name?: string | null;
          energy_kcal: number;
          protein_g?: number | null;
          fat_g?: number | null;
          carbs_g?: number | null;
        };
        food_id?: number | null;
        amount?: number;
        amount_unit?: 'g' | 'serving';
      };
      const isQuick = Boolean(body.quick_add);
      const selectedFood = body.food_id === importedRiceFood.id ? importedRiceFood : oatmealFood;
      const created: FoodDiaryEntry = {
        ...yogurtEntry,
        id: 22,
        diary_date: body.diary_date,
        meal_type: body.meal_type,
        food_id: isQuick ? null : selectedFood.id,
        entry_kind: isQuick ? 'quick_add' : 'food',
        logged_at: body.logged_at ?? null,
        food_name: body.quick_add?.name || (isQuick ? 'Быстрый ввод' : selectedFood.name),
        food_brand: null,
        amount:
          !isQuick && selectedFood.id === importedRiceFood.id
            ? String(body.amount ?? 100)
            : '1.000',
        amount_unit:
          !isQuick && selectedFood.id === importedRiceFood.id
            ? (body.amount_unit ?? 'g')
            : 'serving',
        weight_g:
          !isQuick && selectedFood.id === importedRiceFood.id
            ? String(body.amount ?? 100)
            : '50.000',
        serving_amount: !isQuick && selectedFood.id === importedRiceFood.id ? null : '1.000',
        serving_unit: !isQuick && selectedFood.id === importedRiceFood.id ? null : 'serving',
        serving_weight_g: !isQuick && selectedFood.id === importedRiceFood.id ? null : '50.000',
        nutrition: isQuick
          ? {
              energy_kcal: String(body.quick_add?.energy_kcal ?? 0),
              protein_g:
                body.quick_add?.protein_g == null ? null : String(body.quick_add.protein_g),
              fat_g: body.quick_add?.fat_g == null ? null : String(body.quick_add.fat_g),
              carbs_g: body.quick_add?.carbs_g == null ? null : String(body.quick_add.carbs_g),
              fiber_g: null,
            }
          : selectedFood.id === importedRiceFood.id
            ? {
                energy_kcal: '130.00',
                protein_g: '2.700',
                fat_g: '0.300',
                carbs_g: '28.000',
                fiber_g: '0.400',
              }
            : {
                energy_kcal: '180.00',
                protein_g: '6.000',
                fat_g: '3.000',
                carbs_g: '31.000',
                fiber_g: '4.000',
              },
      };
      entries = [...entries, created];
      return route.fulfill({ status: 201, json: created });
    }
    return route.fulfill({ status: 404, json: { detail: `Unhandled ${path}` } });
  });

  return { releaseHydrationLoading };
}

test('Task 81A groups nutrition into five cards and keeps profile choices compact', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockNutritionApi(page, 'data', null);
  await page.goto('/app?section=nutrition&date=2026-08-19&hydration=quick');

  const cardTitles = [
    page.locator('.nutrition-completeness > .nutrition-completeness__copy h2'),
    page.locator('.nutrition-day-balance h2'),
    page.locator('.nutrition-food-card__header h2'),
    nutritionDaySummary(page).getByRole('heading', { name: 'КБЖУ', exact: true }),
    page.locator('.hydration-card h2'),
  ];
  const titlePositions: number[] = [];
  for (const heading of cardTitles) {
    await expect(heading).toBeVisible();
    titlePositions.push((await heading.boundingBox())?.y ?? 0);
  }
  expect(titlePositions).toEqual([...titlePositions].sort((left, right) => left - right));
  const balance = page.locator('.nutrition-day-balance');
  await expect(balance.getByRole('progressbar', { name: /Еда:/ })).toBeVisible();
  await expect(balance.getByRole('progressbar', { name: /Жидкость:/ })).toBeVisible();
  const foodCard = page.locator('.nutrition-food-card');
  const firstMeal = foodCard.getByRole('region', { name: 'Завтрак', exact: true });
  await expect(firstMeal).toHaveCount(1);
  const [foodCardBox, firstMealBox] = await Promise.all([
    foodCard.boundingBox(),
    firstMeal.boundingBox(),
  ]);
  expect(firstMealBox!.x - foodCardBox!.x).toBeGreaterThanOrEqual(14);
  expect(
    foodCardBox!.x + foodCardBox!.width - firstMealBox!.x - firstMealBox!.width,
  ).toBeGreaterThanOrEqual(14);
  await expect(page.getByRole('heading', { name: 'Мои кружки и бутылки' })).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: '../.artifacts/runtime/tests/screenshots/task-81A/desktop-light-five-cards.png',
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  const mobileCards = [
    page.getByRole('navigation', { name: 'Неделя дневника' }),
    page.locator('.nutrition-completeness'),
    page.locator('.nutrition-day-balance'),
    page.locator('.nutrition-food-card'),
    nutritionDaySummary(page),
    page.locator('.hydration-card'),
  ];
  const mobileCardPositions: number[] = [];
  for (const card of mobileCards) {
    await expect(card).toBeVisible();
    mobileCardPositions.push((await card.boundingBox())?.y ?? 0);
  }
  expect(mobileCardPositions).toEqual([...mobileCardPositions].sort((left, right) => left - right));
  const [mobileFoodCardBox, mobileFirstMealBox] = await Promise.all([
    foodCard.boundingBox(),
    firstMeal.boundingBox(),
  ]);
  expect(mobileFirstMealBox!.x - mobileFoodCardBox!.x).toBeGreaterThanOrEqual(12);
  expect(
    mobileFoodCardBox!.x +
      mobileFoodCardBox!.width -
      mobileFirstMealBox!.x -
      mobileFirstMealBox!.width,
  ).toBeGreaterThanOrEqual(12);
  const saveSex = page.getByText('Сохранить выбранный пол в профиле', { exact: true });
  await expect(saveSex).toBeVisible();
  expect(await saveSex.evaluate((element) => getComputedStyle(element).whiteSpace)).toBe('nowrap');
  expect((await saveSex.boundingBox())?.height).toBeLessThanOrEqual(24);
  await page.locator('.nutrition-diary').screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-81A/mobile-light-ordered-cards-round-2.png',
  });
  const hydration = page.getByRole('region', { name: 'Гидратация' });
  await hydration.scrollIntoViewIfNeeded();
  await hydration.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-81A/mobile-light-expanded-profile-and-containers.png',
  });
});

test('hydration visual evidence: mobile web compact and quick add', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
  await page.setViewportSize({ width: 390, height: 844 });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition&date=2026-08-19');
  const hydration = page.getByRole('region', { name: 'Гидратация' });
  await expect(hydration).toBeVisible();
  await expect(page.getByText('850 из 2200 мл')).toBeVisible();
  await hydration.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-81/mobile-web-light-compact.png',
  });
  await hydration.getByRole('button', { name: /Стакан.*250 мл/ }).click();
  await expect(hydration.getByText('Добавлено 250 мл')).toBeVisible();
  await hydration.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-81/mobile-web-light-quick-add-undo.png',
  });
});

test('hydration visual evidence: mocked TMA dark expanded and reduced motion', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'signed-task-81-init-data',
        initDataUnsafe: {},
        version: '8.0',
        platform: 'android',
        colorScheme: 'dark',
        themeParams: {},
        viewportHeight: 844,
        viewportStableHeight: 844,
        safeAreaInset: { top: 24, right: 0, bottom: 18, left: 0 },
        contentSafeAreaInset: { top: 8, right: 0, bottom: 10, left: 0 },
        ready() {},
        expand() {},
        onEvent() {},
        offEvent() {},
        setHeaderColor() {},
        setBackgroundColor() {},
        setBottomBarColor() {},
      },
    };
  });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition&date=2026-08-19&hydration=quick');
  const hydration = page.getByRole('region', { name: 'Гидратация' });
  await expect(hydration.getByRole('heading', { name: 'Личный ориентир' })).toBeVisible();
  await expect(hydration.getByText(/для здоровых взрослых/i)).toBeVisible();
  await hydration.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-81/mock-tma-dark-expanded-reduced-motion.png',
  });
});

for (const mode of ['light', 'dark'] as const) {
  test(`hydration visual evidence: desktop ${mode} expanded`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: mode });
    await mockNutritionApi(page);
    await page.goto('/app?section=nutrition&date=2026-08-19&hydration=quick');
    const hydration = page.getByRole('region', { name: 'Гидратация' });
    await expect(hydration.getByText('Термокружка · 420 мл')).toBeVisible();
    await hydration.screenshot({
      path: `../.artifacts/runtime/tests/screenshots/task-81/desktop-${mode}-expanded.png`,
    });
  });
}

for (const state of ['loading', 'error', 'empty'] as const) {
  test(`hydration visual evidence: ${state} state`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-08-19T13:00:00+03:00'));
    await page.setViewportSize({ width: 390, height: 844 });
    const hydrationApi = await mockNutritionApi(page, state);
    await page.goto('/app?section=nutrition&date=2026-08-19');
    const hydration = page.locator('.hydration-card');
    await expect(hydration).toBeVisible();
    if (state === 'loading') {
      await expect(hydration.getByText('Загружаем гидратацию…')).toBeVisible();
      hydrationApi.releaseHydrationLoading();
      await expect(hydration.getByText('850 из 2200 мл', { exact: true })).toBeVisible();
    }
    if (state === 'error')
      await expect(hydration.getByText('Гидратация временно недоступна')).toBeVisible();
    if (state === 'empty') await expect(hydration.getByText('0 мл записано')).toBeVisible();
    await hydration.screenshot({
      path: `../.artifacts/runtime/tests/screenshots/task-81/mobile-${state}.png`,
    });
  });
}

test('hydration touch matrix has no horizontal overflow and keeps controls reachable', async ({
  browser,
}) => {
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    const context = await browser.newContext({ viewport, hasTouch: true, isMobile: true });
    const page = await context.newPage();
    await mockNutritionApi(page);
    await page.goto('/app?section=nutrition&date=2026-08-19&hydration=quick');
    const hydration = page.getByRole('region', { name: 'Гидратация' });
    await expect(hydration).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    const quickButtons = hydration.locator('.hydration-presets .ui-button');
    for (let index = 0; index < (await quickButtons.count()); index += 1) {
      const box = await quickButtons.nth(index).boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
    }
    const customVolume = hydration.getByRole('region', { name: 'Другой объём', exact: true });
    const volume = customVolume.getByLabel('Объём, мл');
    await expect(volume).toHaveCount(1);
    await volume.focus();
    await expect(volume).toBeFocused();
    await expect(volume).toBeInViewport();
    await context.close();
  }
});

const russianSearchVisualCases = [
  { label: 'desktop-1280', viewport: { width: 1280, height: 900 }, dark: false },
  { label: 'mobile-web-360', viewport: { width: 360, height: 800 }, dark: false },
  { label: 'dark-mobile-390', viewport: { width: 390, height: 844 }, dark: true },
] as const;

for (const current of russianSearchVisualCases) {
  test(`Russian multi-variant food search visual evidence (${current.label})`, async ({ page }) => {
    await page.setViewportSize(current.viewport);
    await page.emulateMedia({ colorScheme: current.dark ? 'dark' : 'light' });
    await mockNutritionApi(page);
    await page.goto('/app?section=nutrition');
    const breakfast = page.getByRole('region', { name: 'Завтрак' });
    await breakfast.getByRole('button', { name: /Добавить/ }).click();
    await page.getByRole('searchbox', { name: 'Поиск по названию или бренду' }).fill('рис');
    await expect(page.getByText('Рис белый приготовленный, без добавления масла')).toBeVisible();
    await expect(page.getByText('Рис бурый приготовленный, без добавления масла')).toBeVisible();
    await expect(page.getByText('Рис дикий приготовленный, без добавления масла')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
      current.viewport.width,
    );
    await page.screenshot({
      path: `../.artifacts/runtime/tests/screenshots/task-114a/russian-food-variants-${current.label}.png`,
    });
  });
}

test('Russian search shows separate preparation states with their own macros', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition');
  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await page.getByRole('searchbox', { name: 'Поиск по названию или бренду' }).fill('картофель');

  await expect(
    page.getByText('Картофель запечённый, способ приготовления не указан'),
  ).toBeVisible();
  await expect(page.getByText('Картофель отварной, способ приготовления не указан')).toBeVisible();
  await expect(page.getByText('Картофель фри из свежего картофеля, жареный')).toBeVisible();
  await expect(page.getByText('Картофель жареный по-домашнему из свежего картофеля')).toBeVisible();
  await expect(page.getByText('Картофельное пюре, способ приготовления не указан')).toBeVisible();
  await expect(page.getByText('93 ккал / 100 г')).toBeVisible();
  await expect(page.getByText('87 ккал / 100 г')).toBeVisible();
  await expect(page.getByText('289 ккал / 100 г')).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-114a/russian-food-preparation-states-mobile-390.png',
  });
  await page.getByText('Картофель фри из свежего картофеля, жареный').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-114a/russian-food-preparation-states-lower-mobile-390.png',
  });
});

test('Russian preparation states and oil variants apply beyond potatoes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition');
  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  await page.getByRole('searchbox', { name: 'Поиск по названию или бренду' }).fill('яйцо');

  await expect(page.getByText('Яйцо целое варёное или пашот')).toBeVisible();
  await expect(page.getByText('Яйцо целое жареное без добавления масла')).toBeVisible();
  await expect(page.getByText('Яйцо целое жареное с растительным маслом')).toBeVisible();
  await expect(page.getByText('Яйцо целое жареное со сливочным маслом')).toBeVisible();
  await expect(page.getByText('155 ккал / 100 г')).toBeVisible();
  await expect(page.getByText('174 ккал / 100 г')).toBeVisible();
  const friedWithOil = page.getByRole('article').filter({
    hasText: 'Яйцо целое жареное с растительным маслом',
  });
  const friedWithButter = page.getByRole('article').filter({
    hasText: 'Яйцо целое жареное со сливочным маслом',
  });
  await expect(friedWithOil).toHaveCount(1);
  await expect(friedWithButter).toHaveCount(1);
  await expect(friedWithOil).toContainText('196 ккал / 100 г');
  await expect(friedWithButter).toContainText('196 ккал / 100 г');
  await page.getByText('Яйцо целое жареное с растительным маслом').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-114a/russian-food-oil-variants-mobile-390.png',
  });
});

test('nutrition diary is responsive, keyboard-safe and supports local quick add', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-19T09:00:00+03:00'));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition');

  await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await expect(page.getByText('Греческий йогурт')).toBeVisible();
  await expect(nutritionDaySummary(page)).toHaveCount(1);
  await expect(nutritionDaySummary(page)).toBeVisible();
  await expect(page.getByText('Немного выше ориентира: 20 ккал')).toBeVisible();
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
    { width: 360, height: 740 },
  ]) {
    await page.setViewportSize(viewport);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    const week = page.getByRole('navigation', { name: 'Неделя дневника' });
    await expect(week.locator('button[aria-current="date"]')).toBeVisible();
    await expect(week.locator('button[aria-pressed="true"]')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Дата дневника' })).not.toBeAttached();
    const selectedDay = week.locator('button[aria-pressed="true"]');
    expect((await selectedDay.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    const summary = nutritionDaySummary(page);
    const targetBadge = summary.getByText('Цель КБЖУ настроена', { exact: true });
    const [weekBox, summaryBox, targetBadgeBox] = await Promise.all([
      week.boundingBox(),
      summary.boundingBox(),
      targetBadge.boundingBox(),
    ]);
    expect(weekBox).not.toBeNull();
    expect(summaryBox).not.toBeNull();
    expect(targetBadgeBox).not.toBeNull();
    expect(summaryBox!.y).toBeGreaterThanOrEqual(weekBox!.y + weekBox!.height);
    expect(targetBadgeBox!.y).toBeGreaterThanOrEqual(weekBox!.y + weekBox!.height);
  }

  const compactBreakfast = page.getByRole('region', { name: 'Завтрак' });
  const compactLunch = page.getByRole('region', { name: 'Обед' });
  const entry = compactBreakfast.getByRole('listitem');
  await expect(entry).toHaveCount(1);
  const [entryBox, headerBox] = await Promise.all([
    entry.boundingBox(),
    compactBreakfast.locator('.nutrition-meal__header').boundingBox(),
  ]);
  expect(entryBox).not.toBeNull();
  expect(headerBox).not.toBeNull();
  expect(entryBox!.height).toBeLessThanOrEqual(96);
  expect(headerBox!.height).toBeLessThanOrEqual(124);
  await expect(compactLunch.getByRole('button', { name: 'Обед' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  expect((await compactLunch.boundingBox())?.height).toBeLessThanOrEqual(88);
  await compactLunch.getByRole('button', { name: 'Обед' }).click();
  await expect(compactLunch.getByRole('button', { name: 'Обед' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await expect(
    compactLunch.getByText('Добавьте продукт — недавние будут под рукой.'),
  ).toBeVisible();
  await compactLunch.getByRole('button', { name: 'Обед' }).click();
  for (const action of await entry.locator('.nutrition-entry__actions button').all()) {
    expect((await action.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
  await compactBreakfast.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-113A-round-5/nutrition-collapsible-meals-360.png',
  });

  await page.getByRole('button', { name: 'Предыдущая неделя' }).click();
  await expect(page.getByRole('heading', { name: 'Неделя', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Следующая неделя' }).click();
  await expect(page.getByRole('heading', { name: 'Эта неделя', exact: true })).toBeVisible();

  await page.getByRole('button', { name: /Быстрый ввод/ }).click();
  const calories = page.getByRole('spinbutton', { name: 'Калории' });
  await expect(calories).toHaveAttribute('inputmode', 'decimal');
  await expect(calories).toHaveAttribute('enterkeyhint', 'next');
  await page.getByRole('textbox', { name: 'Название (необязательно)' }).fill('Обед вне дома');
  await calories.fill('640');
  await page.getByLabel('Время (необязательно)').fill('13:10');
  await expect(page.getByRole('button', { name: 'Сохранить Quick Add' })).toBeInViewport();
  await page.getByRole('button', { name: 'Сохранить Quick Add' }).click();
  await expect(page.getByRole('dialog')).not.toBeAttached();
  await expect(page.getByText('Обед вне дома')).toBeVisible();
  await expect(page.getByText('Быстрый ввод · 13:10')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);

  await page.getByRole('button', { name: 'День заполнен' }).click();
  await expect(page.getByText('Подтверждено')).toBeVisible();

  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  const addButton = breakfast.getByRole('button', { name: /Добавить/ });
  await addButton.focus();
  await page.keyboard.press('Enter');
  const barcodeEntry = page.getByRole('button', { name: 'Поиск по штрихкоду' });
  const search = page.getByRole('searchbox', { name: 'Поиск по названию или бренду' });
  await expect(barcodeEntry).toBeFocused();
  await expect(search).toBeVisible();
  await expect(page.getByRole('button', { name: /Свой продукт/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Рецепты' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeAttached();
  await expect(addButton).toBeFocused();

  await addButton.click();
  await page.getByRole('button', { name: 'Добавить Овсяная каша' }).click();
  await expect(page.getByRole('spinbutton', { name: 'Количество' })).toHaveValue('1');
  await page.getByRole('button', { name: 'Добавить в дневник' }).click();
  await expect(page.getByRole('dialog')).not.toBeAttached();
  await expect(page.getByText('Овсяная каша')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);

  const oatmeal = page.locator('.nutrition-entry').filter({ hasText: 'Овсяная каша' });
  await oatmeal.getByRole('button', { name: 'Повторить Овсяная каша' }).click();
  await expect(page.getByRole('dialog', { name: 'Повторить продукт' })).toBeVisible();
  await expect(page.getByText('Новые записи добавятся к уже существующим.')).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Дата назначения' })).toHaveValue('2026-08-19');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeAttached();
});

test('dark nutrition uses the shared lime status and progress accents', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await mockNutritionApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?section=nutrition');

  const status = page.getByText('Цель КБЖУ настроена');
  await expect(status).toHaveCSS('background-color', 'rgb(34, 34, 34)');
  await expect(status).toHaveCSS('border-color', 'rgb(89, 111, 56)');
  await expect(status).toHaveCSS('color', 'rgb(185, 234, 114)');
  await expect(
    page.getByRole('progressbar', { name: /Калории:/ }).locator(':scope > span'),
  ).toHaveCSS('background-color', 'rgb(181, 239, 50)');
  await expect(page.getByRole('link', { name: 'Питание', exact: true })).toHaveCSS(
    'background-color',
    'rgb(34, 34, 34)',
  );
  const lunch = page.getByRole('region', { name: 'Обед' });
  await expect(lunch.getByRole('button', { name: 'Обед' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  expect((await lunch.boundingBox())?.height).toBeLessThanOrEqual(88);
  await lunch.scrollIntoViewIfNeeded();
  await lunch.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-113A-round-5/nutrition-collapsible-meals-dark-390x844.png',
  });
});

test('Russian search supplements local food with USDA generic result and persists the diary entry', async ({
  page,
}) => {
  await page.clock.setFixedTime(new Date('2026-08-19T09:00:00+03:00'));
  await page.setViewportSize({ width: 390, height: 844 });
  await mockNutritionApi(page);
  await page.goto('/app?section=nutrition');

  const breakfast = page.getByRole('region', { name: 'Завтрак' });
  await breakfast.getByRole('button', { name: /Добавить/ }).click();
  const search = page.getByRole('searchbox', { name: 'Поиск по названию или бренду' });
  await search.fill('рис');

  await expect(page.getByRole('button', { name: 'Добавить Рис домашний' })).toBeVisible();
  await expect(page.getByText('Рис белый приготовленный, без добавления масла')).toBeVisible();
  await expect(page.getByText('Рис бурый приготовленный, без добавления масла')).toBeVisible();
  await expect(page.getByText('Рис дикий приготовленный, без добавления масла')).toBeVisible();
  await expect(page.getByText(/CC0-1.0/).first()).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-114a/generic-rice-search-390x844.png',
  });
  await page
    .getByText('Рис белый приготовленный, без добавления масла')
    .locator('..')
    .locator('..')
    .getByRole('button', { name: 'Выбрать продукт' })
    .click();
  const amount = page.getByRole('spinbutton', { name: 'Количество' });
  await expect(amount).toHaveValue('100');
  await expect(amount).toBeFocused();
  await page.getByRole('button', { name: 'Добавить в дневник' }).click();

  await expect(page.getByRole('dialog')).not.toBeAttached();
  const entry = page
    .locator('.nutrition-entry')
    .filter({ hasText: 'Рис белый приготовленный, без добавления масла' });
  await expect(entry).toContainText('130');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.reload();
  const reloadedEntry = page
    .locator('.nutrition-entry')
    .filter({ hasText: 'Рис белый приготовленный, без добавления масла' });
  await expect(reloadedEntry).toBeVisible();
  await reloadedEntry.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-114a/generic-rice-added-390x844.png',
  });
});
