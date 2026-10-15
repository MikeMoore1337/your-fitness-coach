import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { makeProgressReportFixture } from '../fixtures/progress-report';
import { expectSelectedChoice } from './fixtures/selected-state';

test.use({ serviceWorkers: 'block' });

for (const width of [320, 360, 393, 430])
  for (const theme of ['dark', 'light'] as const) {
    test(`approved B navigation and quick add ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      await page.clock.setFixedTime(new Date('2026-10-09T12:00:00+03:00'));
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-10-09',
        progressState: 'populated',
        measurementHistory: 'many',
        programHistory: 'many',
      });
      await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, (route) =>
        route.fulfill({ json: makeProgressReportFixture('full') }),
      );
      await page.goto('/app?section=progress');
      const trigger = page.getByRole('button', { name: 'Быстро добавить', exact: true });
      const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
      const tabs = navigation.locator('.app-bottom-nav__primary .app-bottom-nav__btn');
      await expect(tabs).toHaveCount(5);
      await expect(tabs).toHaveText(['Сегодня', 'План', 'Питание', 'Прогресс', 'Добавить']);
      await expect(trigger).toHaveClass(/app-bottom-nav__quick-add/);
      await expect(trigger).not.toHaveClass(/is-active/);
      await expect(trigger).not.toHaveAttribute('aria-current');
      await expect(trigger.locator('svg[data-icon="plus"]')).toBeVisible();
      await expect(page.locator('.app-quick-add-trigger--floating')).toHaveCount(0);
      await expect(page.locator('.progress-overview')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: testInfo.outputPath(`progress-${width}-${theme}.png`) });
      if (width === 430) {
        await page.screenshot({
          path: `../.artifacts/screenshots/task-979/progress-430-${theme}.png`,
        });
      }
      const periods = page.getByRole('tablist', { name: 'Период прогресса' });
      await expectSelectedChoice(navigation.getByRole('link', { name: 'Прогресс', exact: true }));
      for (const label of ['7 дней', '30 дней', '90 дней']) {
        const period = periods.getByRole('tab', { name: label, exact: true });
        await period.click();
        await expect(period).toHaveAttribute('aria-selected', 'true');
        await expectSelectedChoice(period);
        const textFits = await period.evaluate((element) => {
          const bounds = element.getBoundingClientRect();
          const text = document.createRange();
          text.selectNodeContents(element);
          const lines = [...text.getClientRects()];
          return (
            bounds.width >= 44 &&
            bounds.height >= 44 &&
            lines.length === 1 &&
            lines[0]!.left >= bounds.left &&
            lines[0]!.right <= bounds.right
          );
        });
        expect(textFits, `${label} at ${width}px`).toBe(true);
      }
      await page.screenshot({
        path: testInfo.outputPath(`selection-period-${width}-${theme}.png`),
      });
      const period = periods.getByRole('tab', { name: '90 дней', exact: true });
      await period.focus();
      await page.keyboard.press('ArrowLeft');
      const previousPeriod = periods.getByRole('tab', { name: '30 дней', exact: true });
      await expect(previousPeriod).toBeFocused();
      await expect(previousPeriod).toHaveAttribute('aria-selected', 'true');
      await expect(previousPeriod).toHaveCSS('outline-style', 'solid');
      const calorieLines = await page
        .locator('.progress-overview__metric strong')
        .filter({ hasText: 'ккал' })
        .evaluateAll((values) =>
          values.map((element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return range.getClientRects().length;
          }),
        );
      expect(calorieLines).toEqual([1]);
      const navigationBox = (await navigation.boundingBox())!;
      const triggerBox = (await trigger.boundingBox())!;
      expect(navigationBox.height).toBeGreaterThanOrEqual(60);
      expect(navigationBox.height).toBeLessThanOrEqual(76);
      expect(triggerBox.height).toBeGreaterThanOrEqual(44);
      expect(triggerBox.y).toBeGreaterThanOrEqual(navigationBox.y);
      expect(triggerBox.y + triggerBox.height).toBeLessThanOrEqual(
        navigationBox.y + navigationBox.height,
      );
      await expect(navigation).toHaveCSS('backdrop-filter', /blur\(20px\)/);
      expect(triggerBox.x).toBeGreaterThanOrEqual(navigationBox.x);
      expect(triggerBox.x + triggerBox.width).toBeLessThanOrEqual(
        navigationBox.x + navigationBox.width,
      );
      const choices = navigation.locator('.app-bottom-nav__primary [data-yfc-choice]');
      await expect(choices).toHaveCount(4);
      for (const tab of await choices.all()) {
        await expect(tab).toHaveCSS('border-radius', '9999px');
      }
      await expect(trigger).not.toHaveAttribute('aria-current', 'page');
      for (const tab of await tabs.all()) {
        const box = (await tab.boundingBox())!;
        expect(box.width).toBeGreaterThanOrEqual(44);
        expect(box.height).toBeGreaterThanOrEqual(44);
        await expect(tab.locator('svg')).toHaveCSS('width', '24px');
        await expect(tab.locator('svg')).toHaveCSS('height', '24px');
        const labelFits = await tab.locator('.app-bottom-nav__label').evaluate((label) => {
          const bounds = label.getBoundingClientRect();
          const parent = label.parentElement!.getBoundingClientRect();
          const text = document.createRange();
          text.selectNodeContents(label);
          return (
            bounds.left >= parent.left &&
            bounds.right <= parent.right &&
            text.getBoundingClientRect().width <= bounds.width + 1
          );
        });
        expect(labelFits).toBe(true);
      }
      await trigger.click();
      const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
      await expect(sheet).toHaveCSS('backdrop-filter', /blur\(20px\)/);
      const icons = await sheet.locator('.app-quick-add-action__icon').evaluateAll((elements) =>
        elements.map((element) => {
          const style = getComputedStyle(element);
          const icon = element.querySelector('svg')!;
          return {
            color: style.color,
            background: style.backgroundColor,
            width: icon.getBoundingClientRect().width,
            height: icon.getBoundingClientRect().height,
            stroke: icon.getAttribute('stroke-width'),
          };
        }),
      );
      expect(icons).toHaveLength(5);
      expect(icons.every((icon) => JSON.stringify(icon) === JSON.stringify(icons[0]))).toBe(true);
      expect(icons[0]).toMatchObject({ width: 20, height: 20, stroke: '1.8' });
      await expect(sheet.getByRole('link')).toHaveText([
        'Еда',
        'Вода',
        'Кардио',
        'Замер',
        'Самочувствие',
      ]);
      expect(
        await sheet
          .getByRole('link')
          .evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height)),
      ).toEqual([52, 52, 52, 52, 52]);
      await page.screenshot({ path: testInfo.outputPath(`quick-add-${width}-${theme}.png`) });
      expect(
        await page
          .locator('#appContent')
          .evaluate((element) => element instanceof HTMLElement && element.inert),
      ).toBe(true);
      await expect(sheet.getByRole('link', { name: 'Вода', exact: true })).toHaveAttribute(
        'href',
        '/app?section=nutrition&hydration=quick',
      );
      await sheet.getByRole('link').last().focus();
      await page.keyboard.press('Tab');
      await expect(sheet.getByRole('button', { name: 'Закрыть быстрые действия' })).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(sheet).toHaveCount(0);
      await expect(trigger).toBeFocused();
      expect(
        await page
          .locator('#appContent')
          .evaluate((element) => element instanceof HTMLElement && element.inert),
      ).toBe(false);
      await trigger.click();
      await page.locator('.app-quick-add-layer').click({ position: { x: 2, y: 2 } });
      await expect(sheet).toHaveCount(0);
      await expect(trigger).toBeFocused();
      const progressTabs = page
        .getByRole('navigation', { name: 'Разделы прогресса' })
        .getByRole('tablist');
      await expect(progressTabs).toBeVisible();
      if (width === 393) {
        await page.screenshot({
          path: testInfo.outputPath(`progress-393-initial-${theme}.png`),
          fullPage: true,
        });
      }
      await expect(page.getByRole('button', { name: 'Предыдущие разделы прогресса' })).toHaveCount(
        0,
      );
      await expect(page.getByRole('button', { name: 'Следующие разделы прогресса' })).toHaveCount(
        0,
      );
      await progressTabs.getByRole('tab', { name: 'Тело' }).click();
      await expect(page).toHaveURL(/progress_view=body/);
      await progressTabs.getByRole('tab', { name: 'Тренировки' }).click();
      await expect(page).toHaveURL(/progress_view=training/);
      await progressTabs.getByRole('tab', { name: 'Тело' }).click();
      await expect(page).toHaveURL(/progress_view=body/);
      await progressTabs.getByRole('tab', { name: 'Обзор' }).focus();
      await page.keyboard.press('End');
      const history = progressTabs.getByRole('tab', { name: 'История' });
      await expect(history).toBeFocused();
      await history.click();
      await expect(page).toHaveURL(/progress_view=history/);
      await expect(history).toHaveAttribute('aria-selected', 'true');
      if (width === 393) {
        const historyViewport = await progressTabs.evaluate((element) => {
          const selected = element.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
          const container = element.getBoundingClientRect();
          const tab = selected?.getBoundingClientRect();
          return {
            clientWidth: element.clientWidth,
            scrollLeft: element.scrollLeft,
            scrollWidth: element.scrollWidth,
            container: { left: container.left, right: container.right },
            selected: tab ? { left: tab.left, right: tab.right } : null,
            documentWidth: document.documentElement.scrollWidth,
            viewportWidth: window.innerWidth,
          };
        });
        expect(historyViewport.scrollWidth).toBeGreaterThan(historyViewport.clientWidth);
        expect(historyViewport.scrollLeft).toBeGreaterThan(0);
        expect(historyViewport.selected).not.toBeNull();
        expect(historyViewport.selected!.left).toBeGreaterThanOrEqual(
          historyViewport.container.left - 1,
        );
        expect(historyViewport.selected!.right).toBeLessThanOrEqual(
          historyViewport.container.right + 1,
        );
        expect(historyViewport.documentWidth).toBeLessThanOrEqual(historyViewport.viewportWidth);
        await expectNoHorizontalOverflow(page);
        await page.screenshot({
          path: testInfo.outputPath(`progress-393-history-${theme}.png`),
          fullPage: true,
        });
        await page.reload();
        await expect(history).toHaveAttribute('aria-selected', 'true');
        await expect
          .poll(async () =>
            progressTabs.evaluate((element) => {
              const selected = element.querySelector<HTMLElement>(
                '[role="tab"][aria-selected="true"]',
              );
              if (!selected) return false;
              const viewport = element.getBoundingClientRect();
              const item = selected.getBoundingClientRect();
              return item.left >= viewport.left - 1 && item.right <= viewport.right + 1;
            }),
          )
          .toBe(true);
        await page.screenshot({
          path: testInfo.outputPath(`progress-393-history-direct-${theme}.png`),
          fullPage: true,
        });
      }
      await page.getByRole('link', { name: 'Скачать отчёт' }).click();
      await expect(
        page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true }),
      ).toBeVisible();
      await page.getByRole('link', { name: 'Назад', exact: true }).click();
      await expect(page).toHaveURL(/progress_view=history/);
      await expect(progressTabs.getByRole('tab', { selected: true })).toHaveText('История');
      await expectNoHorizontalOverflow(page);
      await page
        .getByRole('button', { name: 'Быстро добавить', exact: true })
        .scrollIntoViewIfNeeded();
      const dock = await page.locator('#appBottomNav').boundingBox();
      const plus = await trigger.boundingBox();
      expect(plus!.x).toBeGreaterThanOrEqual(dock!.x);
      expect(plus!.x + plus!.width).toBeLessThanOrEqual(dock!.x + dock!.width);

      for (const [section, label] of [
        ['today', 'Сегодня'],
        ['programs', 'План'],
        ['nutrition', 'Питание'],
        ['progress', 'Прогресс'],
      ] as const) {
        await navigation.getByRole('link', { name: label, exact: true }).click();
        await expect(page.locator(`.app-section--${section}`)).toBeVisible();
        await expect(navigation.getByRole('link', { name: label, exact: true })).toHaveAttribute(
          'aria-current',
          'page',
        );
        await expect(tabs).toHaveCount(5);
        await expect(page.getByText('Загружаем раздел…', { exact: true })).toHaveCount(0);
        await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        await expectNoHorizontalOverflow(page);
        await page.screenshot({ path: testInfo.outputPath(`${section}-${width}-${theme}.png`) });
        await navigation.screenshot({
          path: testInfo.outputPath(`nav-detail-${section}-${width}-${theme}.png`),
        });
        if (section === 'nutrition') {
          const week = page.getByRole('navigation', { name: 'Неделя дневника' });
          const selectedDay = week.locator('[aria-pressed="true"]');
          await expectSelectedChoice(selectedDay);
          const beforeScroll = await page.evaluate(() => window.scrollY);
          await week.getByRole('button', { name: 'Предыдущая неделя' }).click();
          await expectSelectedChoice(week.locator('[aria-pressed="true"]'));
          expect(await page.evaluate(() => window.scrollY)).toBe(beforeScroll);
          await week.scrollIntoViewIfNeeded();
          await page.screenshot({
            path: testInfo.outputPath(`selection-day-${width}-${theme}.png`),
          });
        }
      }
      for (const section of ['profile', 'catalog']) {
        await page.goto(`/app?section=${section}`);
        await expect(page.locator(`.app-section--${section}`)).toBeVisible();
        await expect(tabs).toHaveCount(5);
        await expect(trigger).toBeVisible();
        await expectNoHorizontalOverflow(page);
      }
    });
  }

test('approved B quick add fits short TMA viewport and native Back restores focus', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 844 });
  await installTelegramHarness(page, {
    viewportHeight: 480,
    viewportStableHeight: 844,
    safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
  });
  const tma = new TelegramHarness(page);
  await installPlatformApi(page, { fixedDate: '2026-10-09' });
  await page.goto('/app?section=progress');
  await expectSelectedChoice(
    page.locator('#appBottomNav').getByRole('link', { name: 'Прогресс', exact: true }),
  );
  await page.getByRole('button', { name: 'Быстро добавить', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
  await expect(sheet).toBeVisible();
  const box = await sheet.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(24);
  expect(box!.y + box!.height).toBeLessThanOrEqual(480 - 34);
  await sheet.getByRole('link').last().scrollIntoViewIfNeeded();
  await expect(sheet.getByRole('link').last()).toBeInViewport();
  await tma.clickBack();
  await expect(sheet).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Быстро добавить', exact: true })).toBeFocused();
});

test('approved B mobile picker preserves editor draft and supports keyboard search', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    programHistory: 'many',
    longExerciseName: true,
  });
  await page.goto('/app?section=programs&view=manage&start=templates');
  await expect(page.locator('.program-current-block h4')).toBeVisible();
  await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
  const editor = page.locator('.program-editor-modal');
  const title = editor.getByLabel('Название', { exact: true });
  await title.fill('Мой сохранённый черновик');
  await editor.getByRole('button', { name: 'Добавить упражнение', exact: true }).click();
  const picker = editor.getByRole('button', { name: 'Поиск упражнения', exact: true });
  await picker.click();
  const dialog = page.getByRole('dialog', { name: 'Выбор упражнения', exact: true });
  const search = dialog.getByRole('searchbox');
  await expect(search).toBeFocused();
  await search.fill('присед');
  await expect(dialog.locator('.exercise-picker__option').first()).toBeVisible();
  await search.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(editor).toBeVisible();
  await expect(title).toHaveValue('Мой сохранённый черновик');
  await expect(picker).toBeFocused();
  await picker.click();
  await dialog.getByRole('searchbox').fill('присед');
  await dialog.locator('.exercise-picker__option').first().click();
  await expect(dialog).toHaveCount(0);
  await expect(title).toHaveValue('Мой сохранённый черновик');
  await expectNoHorizontalOverflow(page);
});

test('approved B completed exercise keeps inset content and a compact empty setup', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'in_progress',
    longExerciseName: true,
  });
  const response = page.waitForResponse('**/api/v1/workouts/today');
  await page.goto('/app?section=today');
  const workout = await (await response).json();
  const completed = workout.exercises[0];
  completed.sets.forEach(
    (set: { is_completed: boolean; actual_reps: number; actual_weight: number }) => {
      set.is_completed = true;
      set.actual_reps = 12;
      set.actual_weight = 40;
    },
  );
  completed.setup_memory = null;
  const next = structuredClone(completed);
  next.id += 1;
  next.exercise_id += 1;
  next.sets.forEach((set: { id: number; is_completed: boolean }) => {
    set.id += 10;
    set.is_completed = false;
  });
  workout.exercises.push(next);
  await page.route(/\/api\/v1\/workouts\/(?:today|42)(?:\?|$)/, (route) =>
    route.fulfill({ json: workout }),
  );
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
  const card = page.locator('.active-workout-exercise.is-completed');
  await expect(card).toHaveCount(1);
  for (const width of [360, 393, 430]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(card).toHaveCSS('padding-left', '16px');
    await expect(card).toHaveCSS('padding-right', '16px');
    const setup = card.locator('.active-workout-setup-memory--empty');
    await expect(setup).toHaveCSS('border-width', '0px');
    await expect(setup).toHaveCSS('padding', '0px');
    expect(
      (await setup.getByRole('button', { name: 'Добавить настройку' }).boundingBox())!.height,
    ).toBeGreaterThanOrEqual(44);
    await expectNoHorizontalOverflow(page);
  }
  await card.getByRole('button', { name: /сохранено/ }).click();
  await expect(card.locator('.active-workout-exercise__sets')).toBeVisible();
});
