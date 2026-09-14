import { expect, test, type Route } from '@playwright/test';
import { resolve } from 'node:path';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const diaryDate = '2026-09-12';
const labelPhoto = resolve(process.cwd(), 'public/assets/marketing/nutrition-photo.webp');

const zeroNutrition = {
  energy_kcal: '0.00',
  protein_g: '0.000',
  fat_g: '0.000',
  carbs_g: '0.000',
  fiber_g: null,
};

const nutrientFields = [
  'energy_kcal',
  'energy_kj',
  'protein_g',
  'fat_g',
  'carbohydrate_g',
  'sugars_g',
  'added_sugars_g',
  'fiber_g',
  'saturated_fat_g',
  'trans_fat_g',
  'salt_g',
  'sodium_mg',
  'cholesterol_mg',
] as const;

const nutrientValues: Record<string, string> = {
  energy_kcal: '480.00',
  protein_g: '8.000',
  fat_g: '24.000',
  carbohydrate_g: '56.000',
};

const nutrientUnit = (field: string) =>
  field === 'energy_kcal'
    ? 'kcal'
    : field === 'energy_kj'
      ? 'kJ'
      : field.endsWith('_mg')
        ? 'mg'
        : 'g';

const sourceFacts = Object.fromEntries(
  nutrientFields.map((field) => [
    field,
    [
      {
        value: nutrientValues[field] ?? null,
        unit: nutrientUnit(field),
        basis_ref: 'per_100_g',
        column_ref: 'main',
        evidence: nutrientValues[field] ? 'read' : 'unreadable',
      },
    ],
  ]),
);

const normalizedFacts = Object.fromEntries(
  nutrientFields.map((field) => [
    field,
    nutrientValues[field]
      ? { value: nutrientValues[field], unit: nutrientUnit(field), basis_ref: 'per_100_g' }
      : null,
  ]),
);

const fieldEvidence = Object.fromEntries(
  nutrientFields.map((field) => [field, nutrientValues[field] ? 'read' : 'unreadable']),
);

const labelDraft = {
  draft_id: 'draft-e2e-label-128c',
  revision: 1,
  status: 'draft',
  expires_at: '2030-01-01T12:15:00Z',
  product_name: 'Шоколад с орехами',
  product_brand: 'YFC Test',
  product_barcode: '3017620422003',
  nutrition: {
    schema_version: 'nutrition-label-draft-v1',
    source_language: 'ru',
    label_format: 'ru_standard',
    source_basis: 'per_100_g',
    serving_size: null,
    servings_per_container: null,
    package_amount: null,
    source_facts: sourceFacts,
    normalized_facts: normalizedFacts,
    derived_fields: {},
    displayed_daily_value_percent: {},
    field_evidence: fieldEvidence,
    confidence_kind: 'none',
    confidence: {},
    warnings: ['unreadable_field'],
    requires_user_review: true,
    metadata: {
      provider: 'local_ocr',
      model: 'not-shown',
      prompt_version: 'test',
      schema_version: 'nutrition-label-draft-v1',
      policy_revision: 'test',
    },
  },
  warnings: ['unreadable_field'],
  requires_user_review: true,
};

const labelFood = {
  id: 91,
  name: 'Шоколад с орехами',
  brand: 'YFC Test',
  barcode: '3017620422003',
  energy_kcal_per_100g: '480.00',
  protein_g_per_100g: '8.000',
  fat_g_per_100g: '24.000',
  carbs_g_per_100g: '56.000',
  fiber_g_per_100g: null,
  nutrition_basis_kind: 'per_100_g',
  nutrition_basis_amount: '100.000',
  nutrition_basis_unit: 'g',
  canonical_facts: {},
  nutrition_provenance: { source: 'user_confirmed_package' },
  catalog_quality: 'community_unverified',
  provenance: 'user_confirmed_package',
  trust_level: 'unverified',
  canonical_complete: true,
  standard_serving_amount: null,
  standard_serving_unit: null,
  standard_serving_weight_g: null,
  food_type: 'user',
  is_favorite: false,
  last_used_at: null,
  created_at: '2026-09-12T12:00:00Z',
  updated_at: '2026-09-12T12:00:00Z',
};

type DiaryRequest = {
  diary_date: string;
  meal_type: string;
  food_id: number;
  amount: number;
  amount_unit: 'g' | 'ml' | 'serving';
};

async function installLabelScanApi(page: Parameters<typeof installPlatformApi>[0]) {
  let recognitionIdempotencyKey = '';
  let confirmPayload: Record<string, unknown> | null = null;
  let diaryPayload: DiaryRequest | null = null;
  const diaryEntries: Array<Record<string, unknown>> = [];

  const diaryDay = (date: string) => {
    const totals = diaryEntries.length
      ? ((diaryEntries[0]?.nutrition as typeof zeroNutrition | undefined) ?? zeroNutrition)
      : zeroNutrition;
    return {
      diary_date: date,
      timezone: 'Europe/Moscow',
      meals: [
        { meal_type: 'breakfast', entries: diaryEntries, totals },
        { meal_type: 'lunch', entries: [], totals: zeroNutrition },
        { meal_type: 'dinner', entries: [], totals: zeroNutrition },
        { meal_type: 'snacks', entries: [], totals: zeroNutrition },
      ],
      totals,
      targets: {
        energy_kcal: '2100.00',
        protein_g: '140.000',
        fat_g: '70.000',
        carbs_g: '230.000',
      },
      remaining: {
        energy_kcal: '2100.00',
        protein_g: '140.000',
        fat_g: '70.000',
        carbs_g: '230.000',
      },
      status: diaryEntries.length ? 'incomplete' : 'unlogged',
      status_is_explicit: false,
    };
  };

  const labelRoute = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/nutrition/label-scans' && request.method() === 'POST') {
      recognitionIdempotencyKey = request.headers()['idempotency-key'] ?? '';
      expect(request.postData() ?? '').toContain('name="image"');
      await route.fulfill({ status: 201, json: labelDraft });
      return;
    }
    if (path.endsWith('/confirm') && request.method() === 'POST') {
      confirmPayload = request.postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        json: {
          food: labelFood,
          visibility: 'share_to_yfc_catalog',
          contribution_state: 'accepted',
          catalog_quality: 'community_unverified',
          provenance: 'user_confirmed_package',
          diary_entry_created: false,
        },
      });
      return;
    }
    if (path.endsWith('/cancel') && request.method() === 'POST') {
      await route.fulfill({ status: 204, body: '' });
      return;
    }
    if (path.endsWith('/draft-e2e-label-128c') && request.method() === 'GET') {
      await route.fulfill({ status: 200, json: labelDraft });
      return;
    }
    await route.fallback();
  };
  await page.route('**/api/v1/nutrition/label-scans', labelRoute);
  await page.route('**/api/v1/nutrition/label-scans/**', labelRoute);

  const diaryRoute = async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/v1/nutrition/diary' && request.method() === 'GET') {
      const date = new URL(request.url()).searchParams.get('diary_date') ?? diaryDate;
      await route.fulfill({ status: 200, json: diaryDay(date) });
      return;
    }
    if (path.endsWith('/entries') && request.method() === 'POST') {
      diaryPayload = request.postDataJSON() as DiaryRequest;
      const amount = Number(diaryPayload.amount);
      const entry = {
        id: 191,
        diary_date: diaryPayload.diary_date,
        meal_type: diaryPayload.meal_type,
        food_id: diaryPayload.food_id,
        recipe_id: null,
        entry_kind: 'food',
        logged_at: null,
        food_name: labelFood.name,
        food_brand: labelFood.brand,
        amount: amount.toFixed(3),
        amount_unit: diaryPayload.amount_unit,
        weight_g: diaryPayload.amount_unit === 'g' ? amount.toFixed(3) : null,
        nutrition_basis_kind: 'per_100_g',
        nutrition_basis_amount: '100.000',
        nutrition_basis_unit: 'g',
        serving_amount: null,
        serving_unit: null,
        serving_weight_g: null,
        nutrition: {
          energy_kcal: ((Number(labelFood.energy_kcal_per_100g) * amount) / 100).toFixed(2),
          protein_g: ((Number(labelFood.protein_g_per_100g) * amount) / 100).toFixed(3),
          fat_g: ((Number(labelFood.fat_g_per_100g) * amount) / 100).toFixed(3),
          carbs_g: ((Number(labelFood.carbs_g_per_100g) * amount) / 100).toFixed(3),
          fiber_g: null,
        },
        created_at: '2026-09-12T12:05:00Z',
        updated_at: '2026-09-12T12:05:00Z',
      };
      diaryEntries.push(entry);
      await route.fulfill({ status: 201, json: entry });
      return;
    }
    await route.fallback();
  };
  await page.route('**/api/v1/nutrition/diary*', diaryRoute);
  await page.route('**/api/v1/nutrition/diary/**', diaryRoute);

  return {
    recognitionIdempotencyKey: () => recognitionIdempotencyKey,
    confirmPayload: () => confirmPayload,
    diaryPayload: () => diaryPayload,
  };
}

const cases = [
  {
    label: 'web-360-light',
    viewport: { width: 360, height: 800 },
    telegram: false,
    theme: 'light',
  },
  {
    label: 'web-390-light',
    viewport: { width: 390, height: 844 },
    telegram: false,
    theme: 'light',
  },
  { label: 'tma-390-dark', viewport: { width: 390, height: 844 }, telegram: true, theme: 'dark' },
  {
    label: 'web-430-light',
    viewport: { width: 430, height: 932 },
    telegram: false,
    theme: 'light',
  },
] as const;

for (const current of cases) {
  test(`nutrition label scan confirms before diary add and survives reload (${current.label})`, async ({
    page,
  }) => {
    await page.setViewportSize(current.viewport);
    if (current.telegram) {
      await installTelegramHarness(page, {
        colorScheme: current.theme,
        viewportHeight: current.viewport.height,
        viewportStableHeight: current.viewport.height,
      });
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
    }
    await installPlatformApi(page, { browserSession: !current.telegram, fixedDate: diaryDate });
    const labelApi = await installLabelScanApi(page);

    await page.goto(`/app?section=nutrition&date=${diaryDate}`);
    const breakfast = page.getByRole('region', { name: 'Завтрак' });
    await breakfast.getByRole('button', { name: /Добавить/ }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: 'Сканировать пищевую ценность' }).click();
    await expect(
      dialog.getByRole('heading', { name: 'Сканировать пищевую ценность' }),
    ).toBeVisible();

    await expect(dialog.locator('input[type="file"]')).not.toHaveAttribute('capture');
    await expect(dialog.getByRole('button', { name: 'Открыть камеру' })).toBeVisible();
    await dialog.locator('input[type="file"]').setInputFiles(labelPhoto);
    await expect(dialog.getByRole('button', { name: 'Распознать' })).toBeVisible();
    expect(labelApi.diaryPayload()).toBeNull();
    await dialog.getByRole('button', { name: 'Распознать' }).click();

    await expect(dialog.getByRole('heading', { name: 'Данные с пищевой этикетки' })).toBeVisible();
    await dialog.getByText('Дополнительные значения и сведения').click();
    await expect(dialog.getByText('Автоматическая точность не измерялась')).toBeVisible();

    if (current.label === 'web-390-light' || current.label === 'tma-390-dark') {
      await dialog.locator('.nutrition-picker__browse').evaluate((element) => {
        element.scrollTop = 0;
      });
      await dialog.locator('.nutrition-picker__panel').screenshot({
        path: resolve(
          process.cwd(),
          `../.artifacts/tasks/128C/evidence/screenshots/nutrition-label-${current.label}-review.png`,
        ),
      });
    }

    await dialog.getByRole('radio', { name: /Добавить в каталог YFC/ }).check();
    await dialog.getByRole('button', { name: 'Подтвердить и сохранить продукт' }).click();

    await expect(dialog.getByRole('heading', { name: 'Шоколад с орехами' })).toBeVisible();
    expect(labelApi.recognitionIdempotencyKey()).toMatch(/^nutrition-label-scan-/);
    expect(labelApi.confirmPayload()).toMatchObject({
      revision: 1,
      name: 'Шоколад с орехами',
      brand: 'YFC Test',
      barcode: '3017620422003',
      visibility: 'share_to_yfc_catalog',
      nutrition: { source_basis: 'per_100_g', energy_kcal: 480, protein_g: 8 },
    });
    expect(labelApi.diaryPayload()).toBeNull();

    const amount = dialog.getByRole('spinbutton', { name: 'Количество' });
    await amount.fill('85');
    await dialog.getByRole('button', { name: 'Добавить в дневник' }).click();
    await expect(dialog).not.toBeAttached();
    expect(labelApi.diaryPayload()).toMatchObject({
      diary_date: diaryDate,
      meal_type: 'breakfast',
      food_id: 91,
      amount: 85,
      amount_unit: 'g',
    });
    await expect(
      page.locator('.nutrition-entry').filter({ hasText: 'Шоколад с орехами' }),
    ).toContainText('408');
    await expectNoHorizontalOverflow(page);

    await page.reload();
    await expect(
      page.locator('.nutrition-entry').filter({ hasText: 'Шоколад с орехами' }),
    ).toBeVisible();
  });
}
