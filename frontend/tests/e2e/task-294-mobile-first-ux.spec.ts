import { expect, test, type Page } from '@playwright/test';
import { resolve } from 'node:path';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

const FIXED_DATE = '2026-09-06';
const CAPTURE_EVIDENCE = process.env.YFC_CAPTURE_TASK_294_EVIDENCE === '1';
const EVIDENCE_DIR = resolve(
  process.cwd(),
  '..',
  '..',
  '..',
  'tasks',
  '294',
  'evidence',
  'screenshots',
);

async function enableAiCoach(page: Page): Promise<void> {
  await page.route('**/api/v1/ai-coach/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/status')) {
      await route.fulfill({
        json: { ui_enabled: true, generic_available: true, personal_available: true },
      });
      return;
    }
    if (url.pathname.endsWith('/quota')) {
      await route.fulfill({
        json: {
          limit: 20,
          used: 2,
          remaining: 18,
          reset_at: '2026-09-07T12:00:00+03:00',
          retry_after_seconds: 86400,
          can_send: true,
        },
      });
      return;
    }
    if (url.pathname.endsWith('/conversations')) {
      await route.fulfill({ json: { items: [] } });
      return;
    }
    if (url.pathname.endsWith('/memory')) {
      await route.fulfill({
        json: {
          status: 'revoked',
          scope: 'ai_coach_memory_v1',
          consent_version: 'ai-coach-memory-v1',
          categories: [],
          category_labels: {},
          purpose: 'Отдельный контекст.',
          retention_notice: 'История и память разделены.',
          max_items: 20,
          consent_source: 'test',
          items: [],
          granted_at: null,
          paused_at: null,
          revoked_at: '2026-09-06T12:00:00Z',
        },
      });
      return;
    }
    await route.fallback();
  });
}

async function openApp(page: Page, section: string): Promise<void> {
  await page.goto(`/app?section=${section}`);
  await expect(page.locator('.app-shell')).toBeVisible();
}

test('Task 294 keeps domain content before contextual AI and removes Today AI CTA', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await enableAiCoach(page);
  await page.setViewportSize({ width: 390, height: 844 });

  await openApp(page, 'today');
  await expect(page.getByTestId('ai-coach-contextual-entry-today')).toHaveCount(0);

  for (const surface of [
    { section: 'nutrition', testId: 'ai-coach-contextual-entry-nutrition' },
    { section: 'programs', testId: 'ai-coach-contextual-entry-program' },
    { section: 'progress', testId: 'ai-coach-contextual-entry-progress' },
  ]) {
    await openApp(page, surface.section);
    const entry = page.getByTestId(surface.testId);
    await expect(entry).toBeVisible();
    await expect(entry).toContainText('контекст экрана');
    await expect(entry).toContainText('перед отправкой');
    await expect(entry).not.toContainText('рядом');
    await expect(
      entry.evaluate((node) => node.parentElement?.lastElementChild === node),
    ).resolves.toBe(true);
    await expectNoHorizontalOverflow(page);
  }
});

test('Task 294 keeps mobile action and section surfaces bounded', async ({ page }) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    programHistory: 'many',
    measurementHistory: 'many',
  });
  await enableAiCoach(page);
  await page.setViewportSize({ width: 390, height: 844 });

  await openApp(page, 'nutrition');
  const addProduct = page.getByTestId('nutrition-add-product');
  await expect(addProduct).toBeVisible();
  const addProductGeometry = await addProduct.evaluate((button) => {
    const icon = button.querySelector('[data-icon="plus"]')?.getBoundingClientRect();
    const label = button.querySelector('span')?.getBoundingClientRect();
    const buttonBox = button.getBoundingClientRect();
    return {
      buttonCenter: buttonBox.left + buttonBox.width / 2,
      contentCenter: icon && label ? (icon.left + label.right) / 2 : Number.NaN,
    };
  });
  expect(
    Math.abs(addProductGeometry.buttonCenter - addProductGeometry.contentCenter),
  ).toBeLessThanOrEqual(2);
  await expect(page.locator('.nutrition-day-summary')).toHaveCSS('border-top-width', '1px');
  await expectNoHorizontalOverflow(page);

  await openApp(page, 'programs');
  const planAction = page.getByRole('link', { name: 'Управление программой', exact: true });
  await expect(planAction).toHaveCount(1);
  await expect(
    page.getByRole('link', { name: 'Открыть управление программой', exact: true }),
  ).toHaveCount(0);
  await expect(planAction).toBeVisible();
  const mobilePlanSummary = page.locator('.program-active__summary');
  const mobilePlanGeometry = await Promise.all([
    planAction.boundingBox(),
    mobilePlanSummary.boundingBox(),
  ]);
  expect(mobilePlanGeometry[0]).not.toBeNull();
  expect(mobilePlanGeometry[1]).not.toBeNull();
  expect(mobilePlanGeometry[0]!.x).toBeGreaterThanOrEqual(mobilePlanGeometry[1]!.x - 1);
  expect(mobilePlanGeometry[0]!.x + mobilePlanGeometry[0]!.width).toBeLessThanOrEqual(
    mobilePlanGeometry[1]!.x + mobilePlanGeometry[1]!.width + 1,
  );

  await page.setViewportSize({ width: 1280, height: 900 });
  await openApp(page, 'programs');
  const desktopPlanGeometry = await Promise.all([
    page.getByRole('link', { name: 'Управление программой', exact: true }).boundingBox(),
    page.locator('.demo-capability-fieldset').boundingBox(),
  ]);
  expect(desktopPlanGeometry[0]).not.toBeNull();
  expect(desktopPlanGeometry[1]).not.toBeNull();
  expect(desktopPlanGeometry[0]!.width).toBeLessThan(desktopPlanGeometry[1]!.width - 16);

  await openApp(page, 'today');
  const todayNutrition = page.locator('.today-nutrition');
  await expect(todayNutrition).toBeVisible();
  await expect(todayNutrition.locator('.today-nutrition__content > div')).toHaveCount(2);
  await expect(todayNutrition.locator('.today-nutrition__food-group')).toBeVisible();
  await expect(todayNutrition.locator('.today-nutrition__water')).toBeVisible();
  await expect(todayNutrition.locator('[data-icon="nav-nutrition"]')).toHaveAttribute(
    'width',
    '16',
  );
  await expect(todayNutrition.getByRole('link', { name: 'Открыть дневник питания' })).toBeVisible();
  await expect(todayNutrition.getByRole('link', { name: '+ Вода' })).toBeVisible();
  const desktopFoodGroupColumns = await todayNutrition
    .locator('.today-nutrition__food-group')
    .evaluate((group) => getComputedStyle(group).gridTemplateColumns);
  expect(desktopFoodGroupColumns).not.toContain('auto');
  await expectNoHorizontalOverflow(page);
});

test('Task 294 keeps Progress desktop hierarchy and Profile nav title-first on mobile', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    programHistory: 'many',
    measurementHistory: 'many',
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });

  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    for (const width of [1024, 1280, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await openApp(page, 'progress');
      const overview = page.locator('.progress-overview');
      const primaryGrid = overview.locator('.progress-overview__primary-grid');
      const rightStack = primaryGrid.locator('.progress-overview__right-stack');
      const trend = overview.locator('.progress-trend-panel');
      const metrics = overview.locator('.progress-overview__metrics');
      const metricCards = metrics.locator('.progress-overview__metric');
      const insights = overview.locator('.progress-overview__analysis-row');
      const insightCards = insights.locator('.progress-insights__column');
      const adherence = insights.locator('.progress-overview__adherence');
      const trendBox = await trend.boundingBox();
      const primaryGridBox = await primaryGrid.boundingBox();
      const rightStackBox = await rightStack.boundingBox();
      const metricsBox = await metrics.boundingBox();
      const metricCardBoxes = await Promise.all(
        (await metricCards.all()).map((card) => card.boundingBox()),
      );
      const insightRowBox = await insights.boundingBox();
      const insightCardBoxes = await Promise.all(
        (await insightCards.all()).map((card) => card.boundingBox()),
      );
      const adherenceBox = await adherence.boundingBox();
      expect(trendBox).not.toBeNull();
      expect(primaryGridBox).not.toBeNull();
      expect(rightStackBox).not.toBeNull();
      expect(metricsBox).not.toBeNull();
      expect(metricCardBoxes).toHaveLength(4);
      expect(metricCardBoxes.every((box) => box !== null)).toBe(true);
      expect(insightRowBox).not.toBeNull();
      expect(insightCardBoxes).toHaveLength(2);
      expect(insightCardBoxes.every((box) => box !== null)).toBe(true);
      expect(adherenceBox).not.toBeNull();
      await expect(insights.locator(':scope > *')).toHaveCount(3);
      expect(await insights.getByRole('heading', { name: 'Что идёт хорошо' })).toBeVisible();
      expect(await insights.getByRole('heading', { name: 'Что требует внимания' })).toBeVisible();
      await expect(adherence).toContainText('Выполнение плана');

      const primaryAlignment = await primaryGrid.evaluate((grid) => {
        const styles = getComputedStyle(grid);
        return { alignItems: styles.alignItems, gridTemplateAreas: styles.gridTemplateAreas };
      });
      const rightStackStyles = await rightStack.evaluate((stack) => {
        const styles = getComputedStyle(stack);
        return {
          alignContent: styles.alignContent,
          gridTemplateColumns: styles.gridTemplateColumns,
        };
      });
      const insightStyles = await insights.evaluate((grid) => {
        const styles = getComputedStyle(grid);
        return { alignItems: styles.alignItems, gridTemplateColumns: styles.gridTemplateColumns };
      });
      expect(primaryAlignment.alignItems).toBe('start');
      expect(rightStackStyles.alignContent).toBe('start');
      expect(insightStyles.alignItems).toBe('start');
      expect(insightStyles.gridTemplateColumns.split(' ')).toHaveLength(2);
      expect(insightRowBox!.x).toBeGreaterThanOrEqual(rightStackBox!.x - 1);
      expect(insightRowBox!.x + insightRowBox!.width).toBeLessThanOrEqual(
        rightStackBox!.x + rightStackBox!.width + 1,
      );
      expect(insightRowBox!.y).toBeGreaterThanOrEqual(metricsBox!.y + metricsBox!.height - 1);
      expect(
        metricCardBoxes.every(
          (box) =>
            box!.x >= metricsBox!.x - 1 &&
            box!.x + box!.width <= metricsBox!.x + metricsBox!.width + 1 &&
            box!.y >= metricsBox!.y - 1 &&
            box!.y + box!.height <= metricsBox!.y + metricsBox!.height + 1,
        ),
      ).toBe(true);

      const firstRow = metricCardBoxes.slice(0, 2);
      const secondRow = metricCardBoxes.slice(2);
      expect(Math.abs(firstRow[0]!.y - firstRow[1]!.y)).toBeLessThanOrEqual(1);
      expect(Math.abs(secondRow[0]!.y - secondRow[1]!.y)).toBeLessThanOrEqual(1);
      expect(secondRow[0]!.y).toBeGreaterThan(firstRow[0]!.y);
      expect(Math.abs(firstRow[0]!.x - secondRow[0]!.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(firstRow[1]!.x - secondRow[1]!.x)).toBeLessThanOrEqual(1);
      expect(adherenceBox!.width).toBeGreaterThanOrEqual(insightRowBox!.width - 1);
      expect(adherenceBox!.y).toBeGreaterThanOrEqual(
        Math.max(...insightCardBoxes.map((box) => box!.y + box!.height)) - 1,
      );

      if (width >= 1101) {
        expect(Math.abs(trendBox!.y - metricsBox!.y)).toBeLessThanOrEqual(1);
        expect(trendBox!.x + trendBox!.width).toBeLessThanOrEqual(rightStackBox!.x + 1);
        expect(Math.abs(metricsBox!.x - rightStackBox!.x)).toBeLessThanOrEqual(1);
        expect(trendBox!.width).toBeGreaterThan(firstRow[0]!.width);
        expect(primaryAlignment.gridTemplateAreas).toContain('trend');
        expect(primaryAlignment.gridTemplateAreas).toContain('right');
      } else {
        expect(trendBox!.y + trendBox!.height).toBeLessThanOrEqual(rightStackBox!.y + 1);
        expect(Math.abs(rightStackBox!.x - primaryGridBox!.x)).toBeLessThanOrEqual(1);
      }

      expect(insightRowBox!.height).toBeGreaterThan(0);
      await expectNoHorizontalOverflow(page);
    }
  }

  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });
  await openApp(page, 'progress');
  const mobileOverview = page.locator('.progress-overview');
  const mobilePrimaryGrid = mobileOverview.locator('.progress-overview__primary-grid');
  const mobileMetrics = mobileOverview.locator('.progress-overview__metrics');
  const mobileTrend = mobileOverview.locator('.progress-trend-panel');
  const mobileInsights = mobileOverview.locator('.progress-overview__analysis-row');
  const mobileMetricsBox = await mobileMetrics.boundingBox();
  const mobileTrendBox = await mobileTrend.boundingBox();
  const mobileInsightsBox = await mobileInsights.boundingBox();
  const mobilePrimaryStyles = await mobilePrimaryGrid.evaluate((grid) => ({
    columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
    areas: getComputedStyle(grid).gridTemplateAreas,
  }));
  expect(mobileMetricsBox).not.toBeNull();
  expect(mobileTrendBox).not.toBeNull();
  expect(mobileInsightsBox).not.toBeNull();
  expect(mobilePrimaryStyles.columns).toBe(1);
  expect(mobilePrimaryStyles.areas).toContain('metrics');
  expect(mobilePrimaryStyles.areas).toContain('trend');
  expect(mobilePrimaryStyles.areas).toContain('insights');
  expect(mobileMetricsBox!.y).toBeLessThan(mobileTrendBox!.y);
  expect(mobileTrendBox!.y + mobileTrendBox!.height).toBeLessThanOrEqual(mobileInsightsBox!.y + 1);
  await expectNoHorizontalOverflow(page);

  for (const width of [320, 360, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    await openApp(page, 'profile');
    const profileNavigation = page.locator('.profile-settings-nav.section-navigation');
    await expect(profileNavigation).toBeVisible();
    await expect(profileNavigation.locator(':scope > a > small')).toHaveCount(6);
    await expect(profileNavigation.locator(':scope > a > small').first()).toBeHidden();
    const titleBoxes = await Promise.all(
      (await profileNavigation.locator(':scope > a > span').all()).map((title) =>
        title.boundingBox(),
      ),
    );
    const navigationBoxes = await Promise.all(
      (await profileNavigation.locator(':scope > a').all()).map((item) => item.boundingBox()),
    );
    expect(titleBoxes.every((box) => box !== null)).toBe(true);
    expect(navigationBoxes.every((box) => box !== null && box.height <= 60)).toBe(true);
    await expectNoHorizontalOverflow(page);
  }
});

test('Task 294 keeps Today secondary cards readable across desktop and mobile widths', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    programHistory: 'many',
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });

  for (const width of [1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await openApp(page, 'today');

    const training = page.locator('.today-dashboard__training');
    const calendar = training.locator('.week-strip');
    const nutrition = page.locator('.today-nutrition');
    const progress = page.locator('.today-progress-grid');
    const nutritionBox = await nutrition.boundingBox();
    const progressBox = await progress.boundingBox();
    const trainingBox = await training.boundingBox();
    const calendarBox = await calendar.boundingBox();
    expect(nutritionBox).not.toBeNull();
    expect(progressBox).not.toBeNull();
    expect(trainingBox).not.toBeNull();
    expect(calendarBox).not.toBeNull();
    expect(nutritionBox!.width).toBeGreaterThanOrEqual(300);
    expect(progressBox!.width).toBeGreaterThanOrEqual(300);
    expect(Math.abs(nutritionBox!.x - progressBox!.x)).toBeLessThanOrEqual(1);
    expect(progressBox!.y).toBeGreaterThanOrEqual(nutritionBox!.y + nutritionBox!.height - 1);
    expect(Math.abs(calendarBox!.x - trainingBox!.x)).toBeLessThanOrEqual(1);
    expect(calendarBox!.width).toBeLessThanOrEqual(trainingBox!.width + 1);

    const foodValuesBox = await nutrition.locator('.today-nutrition__values').boundingBox();
    const foodActionBox = await nutrition
      .getByRole('link', { name: 'Открыть дневник питания' })
      .boundingBox();
    const waterTextBox = await nutrition.locator('.today-nutrition__water > span').boundingBox();
    const waterActionBox = await nutrition.getByRole('link', { name: '+ Вода' }).boundingBox();
    expect(foodValuesBox).not.toBeNull();
    expect(foodActionBox).not.toBeNull();
    expect(waterTextBox).not.toBeNull();
    expect(waterActionBox).not.toBeNull();
    expect(foodActionBox!.y).toBeGreaterThanOrEqual(foodValuesBox!.y + foodValuesBox!.height - 1);
    expect(
      Math.abs(
        waterTextBox!.y +
          waterTextBox!.height / 2 -
          (waterActionBox!.y + waterActionBox!.height / 2),
      ),
    ).toBeLessThanOrEqual(1);
    expect(waterTextBox!.x + waterTextBox!.width).toBeLessThanOrEqual(waterActionBox!.x);

    const progressCard = progress.locator('.today-summary-card--progress');
    const progressCopyBox = await progressCard.locator('.semantic-card__copy').boundingBox();
    const progressActionBox = await progressCard.locator('.semantic-card__action').boundingBox();
    expect(progressCopyBox).not.toBeNull();
    expect(progressActionBox).not.toBeNull();
    expect(progressCopyBox!.x + progressCopyBox!.width).toBeLessThanOrEqual(progressActionBox!.x);
    await expectNoHorizontalOverflow(page);
  }

  for (const width of [320, 360, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await openApp(page, 'today');
    const nutritionBox = await page.locator('.today-nutrition').boundingBox();
    const progressBox = await page.locator('.today-progress-grid').boundingBox();
    expect(nutritionBox).not.toBeNull();
    expect(progressBox).not.toBeNull();
    expect(Math.abs(nutritionBox!.x - progressBox!.x)).toBeLessThanOrEqual(1);
    expect(progressBox!.y).toBeGreaterThanOrEqual(nutritionBox!.y + nutritionBox!.height - 1);
    await expectNoHorizontalOverflow(page);
  }
});

test('Task 294 keeps light-theme lime actions readable with dark ink', async ({ page }) => {
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: FIXED_DATE,
    programHistory: 'many',
  });
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 390, height: 844 });

  const assertLimeInk = async (locator: import('@playwright/test').Locator) => {
    await expect(locator).toBeVisible();
    await expect(locator).toHaveCSS('color', 'rgb(9, 11, 11)');
  };

  await openApp(page, 'programs');
  await assertLimeInk(page.getByRole('link', { name: 'Управление программой', exact: true }));
  await openApp(page, 'nutrition');
  await assertLimeInk(page.getByTestId('nutrition-add-product'));
  await openApp(page, 'today');
  await assertLimeInk(page.getByRole('button', { name: 'Начать тренировку', exact: true }));
});

test('Task 294 keeps period tabs balanced and custom period truthful when opened', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await enableAiCoach(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await openApp(page, 'progress');

  const tabs = page.getByRole('tab');
  await expect(tabs).toHaveCount(4);
  const tabContainer = page.locator('.progress-period-controls__tabs');
  const containerBox = await tabContainer.boundingBox();
  const tabBoxes = await Promise.all((await tabs.all()).map((tab) => tab.boundingBox()));
  expect(containerBox).not.toBeNull();
  expect(tabBoxes[0]).not.toBeNull();
  expect(tabBoxes.at(-1)).not.toBeNull();
  expect(tabBoxes[0]!.x).toBeGreaterThanOrEqual(containerBox!.x);
  expect(tabBoxes.at(-1)!.x + tabBoxes.at(-1)!.width).toBeLessThanOrEqual(
    containerBox!.x + containerBox!.width,
  );
  expect(tabBoxes.at(-1)!.x + tabBoxes.at(-1)!.width - tabBoxes[0]!.x).toBeGreaterThan(0);

  await page.getByRole('tab', { name: 'Свой период', exact: true }).click();
  await expect(page.getByRole('tab', { name: 'Свой период', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.locator('.progress-period-controls__custom')).toBeVisible();
  await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1);
  await expectNoHorizontalOverflow(page);
});

test('Task 294 uses one shared navigation treatment in Profile and Progress', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true, fixedDate: FIXED_DATE });
  await page.setViewportSize({ width: 390, height: 844 });

  await openApp(page, 'profile');
  const profileNavigation = page.locator('.profile-settings-nav.section-navigation');
  await expect(profileNavigation).toBeVisible();
  const profileStyle = await profileNavigation
    .locator(':scope > a')
    .first()
    .evaluate((item) => {
      const styles = getComputedStyle(item);
      return {
        borderRadius: styles.borderRadius,
        backgroundColor: styles.backgroundColor,
        borderTopWidth: styles.borderTopWidth,
      };
    });
  const profileNavigationMetrics = await profileNavigation.evaluate((navigation) => ({
    columns: getComputedStyle(navigation).gridTemplateColumns.split(' ').length,
    itemHeights: Array.from(navigation.children).map((item) => item.getBoundingClientRect().height),
  }));
  expect(profileNavigationMetrics.columns).toBe(2);
  expect(Math.max(...profileNavigationMetrics.itemHeights)).toBeLessThanOrEqual(60);
  const profileFitnessLink = profileNavigation.getByRole('link', { name: 'Цели' });
  await profileFitnessLink.click();
  await expect(profileFitnessLink).toHaveClass(/is-active/);
  await expect(profileFitnessLink).toHaveAttribute('aria-current', 'location');

  await openApp(page, 'progress');
  const progressNavigation = page.locator('.progress-category-nav.section-navigation');
  await expect(progressNavigation).toBeVisible();
  const progressStyle = await progressNavigation
    .locator(':scope > a')
    .nth(1)
    .evaluate((item) => {
      const styles = getComputedStyle(item);
      return {
        borderRadius: styles.borderRadius,
        backgroundColor: styles.backgroundColor,
        borderTopWidth: styles.borderTopWidth,
      };
    });
  expect(progressStyle).toEqual(profileStyle);
  const progressNavigationMetrics = await progressNavigation.evaluate((navigation) => ({
    columns: getComputedStyle(navigation).gridTemplateColumns.split(' ').length,
    itemHeights: Array.from(navigation.children).map((item) => item.getBoundingClientRect().height),
  }));
  expect(progressNavigationMetrics.columns).toBe(2);
  expect(Math.max(...progressNavigationMetrics.itemHeights)).toBeLessThanOrEqual(60);
  await expect(progressNavigation.locator(':scope > a').first()).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expectNoHorizontalOverflow(page);
});

test('Task 294 captures owner visual evidence', async ({ browser }) => {
  test.skip(!CAPTURE_EVIDENCE, 'Set YFC_CAPTURE_TASK_294_EVIDENCE=1 to capture owner evidence.');

  const surfaces = [
    { name: 'today', section: 'today', mobile: true, viewport: 'mobile-390' },
    { name: 'plan', section: 'programs', mobile: true, viewport: 'mobile-390' },
    { name: 'nutrition', section: 'nutrition', mobile: true, viewport: 'mobile-390' },
    { name: 'progress', section: 'progress', mobile: true, viewport: 'mobile-390' },
    { name: 'profile', section: 'profile', mobile: true, viewport: 'mobile-390' },
    { name: 'today', section: 'today', mobile: false, viewport: 'desktop-1280' },
    { name: 'today', section: 'today', mobile: false, viewport: 'desktop-1440' },
    { name: 'plan', section: 'programs', mobile: false, viewport: 'desktop-1280' },
    { name: 'nutrition', section: 'nutrition', mobile: false, viewport: 'desktop-1280' },
    { name: 'progress', section: 'progress', mobile: false, viewport: 'desktop-1024' },
    { name: 'progress', section: 'progress', mobile: false, viewport: 'desktop-1280' },
    { name: 'progress', section: 'progress', mobile: false, viewport: 'desktop-1440' },
    { name: 'profile', section: 'profile', mobile: false, viewport: 'desktop-1280' },
  ] as const;

  for (const theme of ['light', 'dark'] as const) {
    for (const surface of surfaces) {
      const context = await browser.newContext({
        colorScheme: theme,
        viewport:
          surface.viewport === 'desktop-1024'
            ? { width: 1024, height: 900 }
            : surface.viewport === 'desktop-1440'
              ? { width: 1440, height: 900 }
              : surface.mobile
                ? { width: 390, height: 844 }
                : { width: 1280, height: 900 },
        hasTouch: surface.mobile,
      });
      const page = await context.newPage();
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: FIXED_DATE,
        programHistory: 'many',
        measurementHistory: 'many',
      });
      await enableAiCoach(page);
      await openApp(page, surface.section);
      await expect(page.locator('h1').first()).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path: resolve(EVIDENCE_DIR, `task-294-${surface.name}-${surface.viewport}-${theme}.png`),
        fullPage: true,
      });
      await context.close();
    }
  }
});
