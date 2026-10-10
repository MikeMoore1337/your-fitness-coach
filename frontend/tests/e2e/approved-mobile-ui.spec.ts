import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { makeProgressReportFixture } from '../fixtures/progress-report';

test.use({ serviceWorkers: 'block' });

for (const width of [360, 393, 430])
  for (const theme of ['dark', 'light'] as const) {
    test(`approved B navigation and quick add ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.clock.setFixedTime(new Date('2026-10-09T12:00:00+03:00'));
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-10-09',
        progressState: 'populated',
        measurementHistory: 'many',
      });
      await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, (route) =>
        route.fulfill({ json: makeProgressReportFixture('full') }),
      );
      await page.goto('/app?section=progress');
      const trigger = page.getByRole('button', { name: 'Быстро добавить', exact: true });
      await trigger.click();
      const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
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
      const rail = page.locator('.progress-category-nav__rail');
      await rail.getByRole('link', { name: /^Тело/ }).click();
      await expect(page).toHaveURL(/progress_view=body/);
      await rail.getByRole('link', { name: /^Тренировки/ }).click();
      await expect(page).toHaveURL(/progress_view=training/);
      await rail.getByRole('link', { name: /^Тело/ }).click();
      await expect(page).toHaveURL(/progress_view=body/);
      await rail.getByRole('link', { name: /^Обзор/ }).focus();
      await page.keyboard.press('End');
      const history = rail.getByRole('link', { name: /^История/ });
      await expect(history).toBeFocused();
      await expect(history).toHaveAttribute('data-clipped', 'false');
      await history.click();
      await expect(page).toHaveURL(/progress_view=history/);
      await expect(history).toHaveAttribute('aria-current', 'page');
      await page.getByRole('link', { name: 'Скачать отчёт' }).click();
      await expect(
        page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true }),
      ).toBeVisible();
      await page.getByRole('link', { name: 'Назад', exact: true }).click();
      await expect(page).toHaveURL(/progress_view=history/);
      await expect(
        page.locator('.progress-category-nav__rail [aria-current="page"]'),
      ).toHaveAttribute('data-clipped', 'false');
      await expectNoHorizontalOverflow(page);
      await page
        .getByRole('button', { name: 'Быстро добавить', exact: true })
        .scrollIntoViewIfNeeded();
      const dock = await page.locator('#appBottomNav').boundingBox();
      const plus = await trigger.boundingBox();
      expect(dock!.x + dock!.width).toBeLessThan(plus!.x);
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
