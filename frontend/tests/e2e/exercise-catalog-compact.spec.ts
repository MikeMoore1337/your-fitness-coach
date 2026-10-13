import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow, MOBILE_CONTEXTS } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test('client exercise rows stay compact-first across supported mobile widths', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true, longExerciseName: true });
  await page.route('**/api/v1/programs/exercises', async (route) => {
    await route.fulfill({
      json: [
        {
          id: 1,
          title: 'Тяга верхнего блока с длинным названием для проверки переноса',
          slug: 'lat-pulldown',
          primary_muscle: 'Спина',
          equipment: 'Тросовый блок',
          primary_muscle_ids: ['back'],
          secondary_muscle_ids: ['biceps'],
          equipment_ids: ['cable'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
        },
        {
          id: 3,
          title: 'Гоблет-присед с гирей',
          slug: 'goblet-squat',
          primary_muscle: 'Квадрицепс',
          equipment: 'Гиря',
          primary_muscle_ids: ['quadriceps'],
          secondary_muscle_ids: ['glutes'],
          equipment_ids: ['kettlebell'],
          aliases: ['гоблет', 'goblet squat', 'kettlebell goblet squat'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
        },
        {
          id: 4,
          title: 'Гоблет-присед с гирей',
          slug: 'kettlebell-goblet-squat',
          canonical_slug: 'goblet-squat',
          primary_muscle: 'Ноги',
          equipment: 'Гиря',
          primary_muscle_ids: ['legs'],
          secondary_muscle_ids: ['glutes'],
          equipment_ids: ['kettlebell'],
          aliases: [],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
        },
        {
          id: 2,
          title: 'Приседания со штангой',
          slug: 'barbell-squat',
          primary_muscle: 'Ноги',
          equipment: 'Штанга',
          primary_muscle_ids: ['legs'],
          secondary_muscle_ids: ['core'],
          equipment_ids: ['barbell'],
          alternatives: [],
          difficulty_level: 'intermediate',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
        },
      ],
    });
  });

  for (const [name, viewport] of Object.entries(MOBILE_CONTEXTS)) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=catalog');
    await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();

    const rows = page.locator('.exercise-catalog-item');
    await expect(rows.first()).toBeVisible();
    const rowHeights = await rows.evaluateAll((items) =>
      items.slice(0, 3).map((item) => item.getBoundingClientRect().height),
    );
    expect(rowHeights.length).toBeGreaterThan(0);
    expect(Math.max(...rowHeights)).toBeLessThanOrEqual(128);

    const primaryAction = rows.first().getByRole('button', { name: /Техника и детали|Подробнее/ });
    expect((await primaryAction.boundingBox())?.height).toBeGreaterThanOrEqual(44);

    const search = page.getByRole('searchbox', { name: 'Поиск' });
    await search.fill('goblet squat');
    await expect(search).toBeFocused();
    await expect(page.locator('.exercise-catalog-item')).toHaveCount(1);
    await expect(page.locator('.exercise-catalog-item')).toContainText('Гоблет-присед с гирей');
    const [resultBox, filtersBox] = await Promise.all([
      page.locator('.exercise-catalog-item').first().boundingBox(),
      page.locator('.exercise-catalog__filters').boundingBox(),
    ]);
    expect(resultBox).not.toBeNull();
    expect(filtersBox).not.toBeNull();
    expect(resultBox!.y).toBeLessThan(filtersBox!.y);
    expect(resultBox!.y).toBeLessThan(viewport.height);
    await expectNoHorizontalOverflow(page);
    await page.locator('.exercise-catalog-list').screenshot({
      path: `../.artifacts/screenshots/task-120D/${test.info().project.name}-exercise-catalog-${name}-${viewport.width}.png`,
    });

    const structure = await page.evaluate(() => {
      const filters = document.querySelector('.exercise-catalog__filters');
      const count = document.querySelector('.exercise-catalog__count');
      const list = document.querySelector('.exercise-catalog-list');
      if (!filters || !count || !list) {
        throw new Error('Exercise catalog search structure is incomplete');
      }
      const follows = (before: Element, after: Element) =>
        Boolean(before.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING);
      return {
        filtersBeforeCount: follows(filters, count),
        countBeforeResults: follows(count, list),
      };
    });
    expect(structure).toEqual({ filtersBeforeCount: true, countBeforeResults: true });

    const filterControls = page.locator('.exercise-catalog__filters select');
    await expect(filterControls).toHaveCount(3);
    await search.press('Tab');
    await expect(filterControls.nth(0)).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(filterControls.nth(1)).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(filterControls.nth(2)).toBeFocused();
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app?section=catalog');
  await page.getByRole('searchbox', { name: 'Поиск' }).fill('гоблет');
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(1);
  await expect(page.locator('.exercise-catalog-item')).toContainText('Гоблет-присед с гирей');
  const [desktopResultBox, desktopFiltersBox] = await Promise.all([
    page.locator('.exercise-catalog-item').first().boundingBox(),
    page.locator('.exercise-catalog__filters').boundingBox(),
  ]);
  expect(desktopResultBox).not.toBeNull();
  expect(desktopFiltersBox).not.toBeNull();
  expect(desktopFiltersBox!.y).toBeLessThan(desktopResultBox!.y);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: `../.artifacts/screenshots/task-120D/${test.info().project.name}-exercise-catalog-desktop-1280.png`,
    fullPage: true,
  });
});
