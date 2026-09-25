import { expect, test, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { emptyHydrationDay, installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

const FIXED_DATE = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
const CAPTURE_EVIDENCE = process.env.YFC_CAPTURE_TASK_295_EVIDENCE === '1';
const EVIDENCE_DIR = resolve(
  process.cwd(),
  '..',
  '..',
  '..',
  'tasks',
  '295',
  'evidence',
  'screenshots',
);

async function openApp(page: Page, section: string): Promise<void> {
  await page.goto(`/app?section=${section}`);
  await expect(page.locator('.app-shell')).toBeVisible();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
}

async function capture(page: Page, filename: string): Promise<void> {
  if (!CAPTURE_EVIDENCE) return;
  await page.screenshot({ path: resolve(EVIDENCE_DIR, filename), fullPage: true });
}

function populatedDiary() {
  const totals = {
    energy_kcal: '1450.00',
    protein_g: '96.000',
    fat_g: '48.000',
    carbs_g: '160.000',
    fiber_g: '18.000',
  };
  const targets = {
    energy_kcal: '2100.00',
    protein_g: '140.000',
    fat_g: '70.000',
    carbs_g: '230.000',
  };
  const entry = {
    id: 1,
    diary_date: FIXED_DATE,
    meal_type: 'breakfast',
    food_id: null,
    recipe_id: null,
    entry_kind: 'quick_add',
    logged_at: null,
    food_name: 'Овсяная каша',
    food_brand: null,
    amount: '1',
    amount_unit: 'serving',
    weight_g: null,
    nutrition_basis_kind: null,
    nutrition_basis_amount: null,
    nutrition_basis_unit: null,
    serving_amount: null,
    serving_unit: null,
    serving_weight_g: null,
    nutrition: totals,
    created_at: `${FIXED_DATE}T08:00:00Z`,
    updated_at: `${FIXED_DATE}T08:00:00Z`,
  };
  return {
    diary_date: FIXED_DATE,
    timezone: 'Europe/Moscow',
    meals: [
      { meal_type: 'breakfast', entries: [entry], totals },
      { meal_type: 'lunch', entries: [], totals },
      { meal_type: 'dinner', entries: [], totals },
      { meal_type: 'snacks', entries: [], totals },
    ],
    totals,
    targets,
    remaining: {
      energy_kcal: '650.00',
      protein_g: '44.000',
      fat_g: '22.000',
      carbs_g: '70.000',
    },
    status: 'incomplete',
    status_is_explicit: false,
  };
}

function populatedHydration() {
  return {
    ...emptyHydrationDay(FIXED_DATE),
    total_ml: 750,
    goal: {
      id: 1,
      enabled: true,
      target_ml: 2200,
      source: 'manual',
      method_version: 'task-295-fixture',
      reference_scope: 'fixture',
      sex: 'female',
      adult_confirmed: true,
      height_cm: 168,
      weight_kg: 68,
      activity_level: 'moderate',
      climate: 'temperate',
      calculated_at: `${FIXED_DATE}T07:00:00Z`,
      created_at: `${FIXED_DATE}T07:00:00Z`,
      updated_at: `${FIXED_DATE}T07:00:00Z`,
    },
    progress_percent: 34.1,
    entries: [
      {
        id: 1,
        volume_ml: 750,
        beverage_type: 'water',
        occurred_at: `${FIXED_DATE}T08:00:00Z`,
        diary_date: FIXED_DATE,
        timezone: 'Europe/Moscow',
        source: 'manual',
        created_at: `${FIXED_DATE}T08:00:00Z`,
        updated_at: `${FIXED_DATE}T08:00:00Z`,
      },
    ],
    last_logged_at: `${FIXED_DATE}T08:00:00Z`,
  };
}

function completedCardio() {
  return {
    activity_type: 'walking',
    duration_minutes: 30,
    distance_km: null,
    average_heart_rate_bpm: null,
    heart_rate_zone: null,
    note: 'Фактический результат',
    scheduled_at: `${FIXED_DATE}T09:00:00+03:00`,
    status: 'completed',
    id: 659,
    source: 'manual',
    completed_at: `${FIXED_DATE}T09:30:00+03:00`,
    created_at: `${FIXED_DATE}T08:00:00+03:00`,
    updated_at: `${FIXED_DATE}T09:30:00+03:00`,
  };
}

async function installPopulatedToday(page: Page): Promise<void> {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    measurementHistory: 'many',
    cardioState: 'completed',
  });
  await page.route('**/api/v1/nutrition/diary**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    await route.fulfill({ json: populatedDiary() });
  });
  await page.route('**/api/v1/nutrition/hydration**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    await route.fulfill({ json: populatedHydration() });
  });
  await page.route('**/api/v1/workouts/cardio**', async (route) => {
    if (route.request().method() !== 'GET') return route.fallback();
    await route.fulfill({ json: [completedCardio()] });
  });
}

test('Task 295 keeps Today compact, factual and one-column on mobile', async ({ page }) => {
  await installPopulatedToday(page);
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });

  for (const surface of [
    { name: 'today-390-populated-light', width: 390, height: 844, theme: 'light' as const },
    { name: 'today-390-populated-dark', width: 390, height: 844, theme: 'dark' as const },
    { name: 'today-1280-populated-light', width: 1280, height: 900, theme: 'light' as const },
    { name: 'today-1440-populated-light', width: 1440, height: 900, theme: 'light' as const },
    { name: 'today-1440-populated-dark', width: 1440, height: 900, theme: 'dark' as const },
  ]) {
    await page.emulateMedia({ colorScheme: surface.theme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: surface.width, height: surface.height });
    await openApp(page, 'today');

    await expect(page.getByRole('heading', { name: 'Силовая база' })).toBeVisible();
    const nutrition = page.getByRole('region', { name: 'Питание на сегодня' });
    await expect(nutrition).toContainText('1450 / 2100 ккал');
    await expect(nutrition).toContainText('Осталось 650 ккал');
    await expect(nutrition).toContainText('Белок');
    await expect(nutrition).toContainText('96 / 140 г');
    await expect(nutrition).toContainText('Вода 750 из 2200 мл');
    await expect(page.getByRole('region', { name: 'Активность за сегодня' })).toContainText(
      'Кардио · ходьба · 30 мин',
    );
    await expect(page.getByRole('link', { name: 'Открыть прогресс' })).toHaveAttribute(
      'href',
      '/app?section=progress',
    );

    const trainingBox = await page.locator('.today-dashboard__training').boundingBox();
    const factsBox = await page.locator('.today-dashboard__facts').boundingBox();
    expect(trainingBox).not.toBeNull();
    expect(factsBox).not.toBeNull();
    if (surface.width <= 899) {
      const factBoxes = await page.locator('.today-dashboard__facts > *').evaluateAll((elements) =>
        elements.map((element) => {
          const box = element.getBoundingClientRect();
          return { x: box.x, width: box.width, y: box.y };
        }),
      );
      expect(factBoxes.length).toBeGreaterThanOrEqual(3);
      expect(new Set(factBoxes.map((box) => Math.round(box.x))).size).toBe(1);
      expect(new Set(factBoxes.map((box) => Math.round(box.width))).size).toBe(1);
      expect(trainingBox!.y).toBeLessThan(factBoxes[0]!.y);
    } else {
      expect(trainingBox!.width).toBeGreaterThan(factsBox!.width);
    }
    await expectNoHorizontalOverflow(page);
    if (surface.name === 'today-390-populated-light') {
      await capture(page, `${surface.name}.png`);
    }
  }
});

test('Task 295 keeps empty Today and Progress states distinct from zero', async ({ page }) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    workoutStatus: 'none',
    measurementHistory: 'none',
    cardioState: 'empty',
    progressState: 'sparse',
  });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await openApp(page, 'today');

  await expect(page.getByRole('region', { name: 'Питание на сегодня' })).toContainText(
    'Записей за день пока нет',
  );
  await expect(page.getByRole('region', { name: 'Главное о прогрессе' })).toContainText(
    'Появится после первых тренировок и замеров',
  );
  await expect(page.getByRole('region', { name: 'Активность за сегодня' })).toHaveCount(0);
  const diaryAction = page.getByRole('link', { name: 'Открыть дневник питания' });
  await expect(diaryAction).toHaveAttribute('href', `/app?section=nutrition&date=${FIXED_DATE}`);
  expect(await diaryAction.evaluate((element) => (element as HTMLElement).innerText)).toBe(
    'Открыть дневник',
  );
  await page.mouse.wheel(0, 120);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  const [diaryActionBox, todayBottomNavBox, todayFabBox] = await Promise.all([
    diaryAction.boundingBox(),
    page.locator('#appBottomNav').boundingBox(),
    page.locator('.app-quick-add-trigger').boundingBox(),
  ]);
  expect(diaryActionBox).not.toBeNull();
  expect(todayBottomNavBox).not.toBeNull();
  expect(todayFabBox).not.toBeNull();
  expect(diaryActionBox!.height).toBeGreaterThanOrEqual(44);
  const overlaps = (
    first: NonNullable<typeof diaryActionBox>,
    second: NonNullable<typeof fabBox>,
  ) =>
    first.x < second.x + second.width &&
    first.x + first.width > second.x &&
    first.y < second.y + second.height &&
    first.y + first.height > second.y;
  expect(overlaps(diaryActionBox!, todayFabBox!)).toBe(false);
  expect(overlaps(diaryActionBox!, todayBottomNavBox!)).toBe(false);
  await expectNoHorizontalOverflow(page);
  await capture(page, 'today-390-sparse-light.png');

  for (const width of [360, 389, 390, 393, 400, 430, 439, 440, 768]) {
    await page.setViewportSize({ width, height: 844 });
    await openApp(page, 'today');
    await page.mouse.wheel(0, 120);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    const action = page.getByRole('link', { name: 'Открыть дневник питания' });
    const water = page.getByRole('link', { name: '+ Вода' });
    const group = page.locator('.today-nutrition__food-group');
    const nutrition = page.getByRole('region', { name: 'Питание на сегодня' });
    const values = nutrition.locator('.today-nutrition__values');
    const [actionBox, waterBox, groupBox, nutritionBox, valuesBox] = await Promise.all([
      action.boundingBox(),
      water.boundingBox(),
      group.boundingBox(),
      nutrition.boundingBox(),
      values.boundingBox(),
    ]);
    expect(actionBox).not.toBeNull();
    expect(waterBox).not.toBeNull();
    expect(groupBox).not.toBeNull();
    expect(nutritionBox).not.toBeNull();
    expect(valuesBox).not.toBeNull();
    if (!actionBox || !waterBox || !groupBox || !nutritionBox || !valuesBox) continue;
    if (width >= 390 && width <= 440) {
      expect(
        Math.abs(actionBox.x + actionBox.width - (waterBox.x + waterBox.width)),
      ).toBeLessThanOrEqual(2);
    }
    expect(actionBox.x).toBeGreaterThanOrEqual(nutritionBox.x);
    expect(actionBox.x + actionBox.width).toBeLessThanOrEqual(
      nutritionBox.x + nutritionBox.width + 1,
    );
    expect(actionBox.x).toBeGreaterThanOrEqual(groupBox.x);
    expect(actionBox.x + actionBox.width).toBeLessThanOrEqual(groupBox.x + groupBox.width + 1);
    expect(valuesBox.x + valuesBox.width).toBeLessThanOrEqual(actionBox.x + 1);
    expect(actionBox!.height).toBeGreaterThanOrEqual(44);
    expect(await action.evaluate((element) => (element as HTMLElement).innerText)).toBe(
      width < 440 ? 'Открыть дневник' : 'Открыть дневник питания',
    );
    const [fabBox, bottomNavBox] = await Promise.all([
      page.locator('.app-quick-add-trigger').boundingBox(),
      page.locator('#appBottomNav').boundingBox(),
    ]);
    expect(fabBox).not.toBeNull();
    expect(bottomNavBox).not.toBeNull();
    if (width < 440) {
      expect(overlaps(actionBox!, fabBox!)).toBe(false);
      expect(overlaps(actionBox!, bottomNavBox!)).toBe(false);
    }
    await expectNoHorizontalOverflow(page);
    if (CAPTURE_EVIDENCE && width !== 400) {
      await page.screenshot({
        path: resolve(EVIDENCE_DIR, `hotfix-today-nutrition-${width}.png`),
        fullPage: false,
      });
    }
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await openApp(page, 'progress');
  const metrics = page.locator('.progress-overview__metrics .progress-overview__metric');
  await expect(metrics).toHaveCount(4);
  expect(
    await metrics.evaluateAll((elements) =>
      elements.every((element) => element.getAttribute('data-progress-state') === 'sparse'),
    ),
  ).toBe(true);
  const sparseHeights = await metrics.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect().height),
  );
  expect(
    await metrics.evaluateAll((elements) =>
      elements.every((element) => !element.querySelector('small')),
    ),
  ).toBe(true);
  expect(await metrics.first().evaluate((element) => (element as HTMLElement).innerText)).toContain(
    'Тело\nМало данных',
  );
  expect(
    await metrics.first().evaluate((element) => (element as HTMLElement).innerText),
  ).not.toContain('Мало данных\nМало данных');
  const sparseStyles = await metrics.evaluateAll((elements) =>
    elements.map((element) => getComputedStyle(element).minHeight),
  );
  expect(sparseStyles.every((minHeight) => minHeight === '0px')).toBe(true);
  expect(sparseHeights.every((height) => height >= 44 && height < 86)).toBe(true);
  const lastMetric = metrics.last();
  await lastMetric.scrollIntoViewIfNeeded();
  const [lastMetricBox, bottomNavBox, fabBox] = await Promise.all([
    lastMetric.boundingBox(),
    page.locator('#appBottomNav').boundingBox(),
    page.locator('.app-quick-add-trigger').boundingBox(),
  ]);
  expect(lastMetricBox).not.toBeNull();
  expect(bottomNavBox).not.toBeNull();
  expect(fabBox).not.toBeNull();
  expect(lastMetricBox!.y + lastMetricBox!.height).toBeLessThanOrEqual(bottomNavBox!.y + 1);
  const overlapsFab =
    lastMetricBox!.x < fabBox!.x + fabBox!.width &&
    lastMetricBox!.x + lastMetricBox!.width > fabBox!.x &&
    lastMetricBox!.y < fabBox!.y + fabBox!.height &&
    lastMetricBox!.y + lastMetricBox!.height > fabBox!.y;
  expect(overlapsFab).toBe(false);
  await expectNoHorizontalOverflow(page);
  await capture(page, 'progress-390-sparse-light.png');
});

test('Task 295 lets populated Progress cards use their content height on mobile and desktop', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    workoutStatus: 'completed',
    measurementHistory: 'many',
    cardioState: 'completed',
    progressState: 'populated',
  });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });

  for (const surface of [
    { name: 'progress-390-populated-light', width: 390, height: 844 },
    { name: 'progress-1440-populated-light', width: 1440, height: 900 },
  ]) {
    await page.setViewportSize({ width: surface.width, height: surface.height });
    await openApp(page, 'progress');
    const metrics = page.locator('.progress-overview__metrics .progress-overview__metric');
    await expect(metrics).toHaveCount(4);
    expect(
      await metrics.evaluateAll((elements) =>
        elements.every((element) => element.getAttribute('data-progress-state') === 'populated'),
      ),
    ).toBe(true);
    expect(
      await metrics.evaluateAll((elements) =>
        elements.every((element) => element.querySelector('small')),
      ),
    ).toBe(true);
    await expectNoHorizontalOverflow(page);
    if (surface.name === 'progress-390-populated-light') {
      await capture(page, `${surface.name}.png`);
    }
  }
});

test('Task 295 keeps Profile shortcuts title-first and untruncated at narrow widths', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });

  for (const surface of [
    { name: 'profile-320-light', width: 320, height: 568 },
    { name: 'profile-360-light', width: 360, height: 800 },
    { name: 'profile-390-light', width: 390, height: 844 },
    { name: 'profile-1280-light', width: 1280, height: 900 },
  ]) {
    await page.setViewportSize({ width: surface.width, height: surface.height });
    await openApp(page, 'profile');
    const navigation = page.getByRole('navigation', { name: 'Разделы профиля' });
    const shortcuts = navigation.locator('.profile-settings-nav__item');
    await expect(shortcuts).toHaveCount(6);
    const expectedLabels = [
      'Личные данные',
      'Цели',
      'Тренер',
      'Уведомления',
      'Безопасность',
      'AI Coach',
    ];
    for (const [index, shortcut] of (await shortcuts.all()).entries()) {
      await expect(shortcut.locator(':scope > span')).toHaveText(expectedLabels[index]!);
      const box = await shortcut.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      if (surface.width <= 430) {
        await expect(shortcut.locator('small')).toBeHidden();
        const titleStyle = await shortcut.locator(':scope > span').evaluate((element) => {
          const style = getComputedStyle(element);
          return {
            overflow: style.overflow,
            textOverflow: style.textOverflow,
            whiteSpace: style.whiteSpace,
          };
        });
        expect(titleStyle).toEqual({
          overflow: 'visible',
          textOverflow: 'clip',
          whiteSpace: 'nowrap',
        });
        const [iconBox, titleBox, chevronBox] = await Promise.all([
          shortcut.locator(':scope > .section-navigation__leading-icon').boundingBox(),
          shortcut.locator(':scope > span').boundingBox(),
          shortcut.locator(':scope > .section-navigation__chevron').boundingBox(),
        ]);
        expect(iconBox).not.toBeNull();
        expect(titleBox).not.toBeNull();
        expect(chevronBox).not.toBeNull();
        expect(titleBox!.height).toBeLessThan(24);
        const titleCenter = titleBox!.y + titleBox!.height / 2;
        expect(Math.abs(titleCenter - (iconBox!.y + iconBox!.height / 2))).toBeLessThan(3);
        expect(Math.abs(titleCenter - (chevronBox!.y + chevronBox!.height / 2))).toBeLessThan(3);
      }
    }
    const profile = page.locator('.profile-settings');
    for (const sectionTitle of [
      'Личные данные и фитнес-профиль',
      'Тренировочные предпочтения',
      'Тренер и приглашения',
      'Уведомления',
      'Доступ и безопасность',
    ]) {
      await expect(profile).toContainText(sectionTitle);
    }
    await expectNoHorizontalOverflow(page);
    await capture(page, `${surface.name}.png`);
  }
});
