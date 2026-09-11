import { expect, test, type Page } from '@playwright/test';
import { emptyHydrationDay } from './fixtures/platform-api';

const captureLandingProductProofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_LANDING_PRODUCT_PROOFS === '1';
const captureTask116Proofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TASK_116_PROOFS === '1';

type DashboardState = {
  workout?: 'planned' | 'in_progress' | 'completed' | 'none';
  activeProgram?: boolean;
  incompleteProfile?: boolean;
  failNutrition?: boolean;
  failProgress?: boolean;
  weeklyReviewAvailable?: boolean;
  trainerComment?: boolean;
};

function todayInMoscow(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function addDays(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

async function mockDashboard(page: Page, state: DashboardState = {}) {
  const today = todayInMoscow();
  let workoutStatus = state.workout ?? 'planned';
  const activeProgram = state.activeProgram ?? true;
  const workout = () => ({
    id: 42,
    scheduled_date: today,
    scheduled_time: '18:30:00',
    title: 'Силовая база',
    status: workoutStatus,
    day_number: 2,
    week_number: 1,
    started_at: workoutStatus === 'in_progress' ? `${today}T10:00:00` : null,
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Приседания',
        sort_order: 1,
        prescribed_sets: 2,
        prescribed_reps: '8-10',
        rest_seconds: 90,
        notes: null,
        has_guide: false,
        sets: [1, 2].map((setNumber) => ({
          id: 200 + setNumber,
          set_number: setNumber,
          actual_reps: setNumber === 1 && workoutStatus === 'in_progress' ? 8 : null,
          actual_weight: setNumber === 1 && workoutStatus === 'in_progress' ? 50 : null,
          is_completed: setNumber === 1 && workoutStatus === 'in_progress',
          version: 1,
        })),
      },
    ],
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: '' },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({
        json: {
          id: 7,
          first_name: 'Анна',
          is_coach: false,
          is_admin: false,
          has_active_program: activeProgram,
          has_workout_history: state.workout === 'completed',
          onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
          profile: {
            full_name: 'Анна Петрова',
            goal: 'maintenance',
            level: state.incompleteProfile ? null : 'beginner',
            height_cm: state.incompleteProfile ? null : 168,
            workouts_per_week: state.incompleteProfile ? null : 3,
            timezone: 'Europe/Moscow',
            kbju: null,
          },
          trainer: null,
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      if (workoutStatus === 'completed' || workoutStatus === 'none') {
        return route.fulfill({
          status: 404,
          json: { detail: 'На сегодня тренировка не назначена' },
        });
      }
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/week')) {
      if (!activeProgram) return route.fulfill({ json: [] });
      if (workoutStatus === 'none') {
        return route.fulfill({
          json: [
            {
              ...workout(),
              id: 55,
              scheduled_date: addDays(today, 2),
              status: 'planned',
              title: 'Верх тела',
            },
          ],
        });
      }
      return route.fulfill({ json: [{ ...workout(), status: workoutStatus }] });
    }
    if (path.endsWith('/workouts/42/start')) {
      workoutStatus = 'in_progress';
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/42/finish')) {
      workoutStatus = 'completed';
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      if (state.failProgress) return route.abort('failed');
      return route.fulfill({
        json: {
          user_id: 7,
          period_days: 30,
          period_start: addDays(today, -29),
          period_end: today,
          training: {
            planned_workouts: 8,
            completed_workouts: 7,
            frequency_per_week: 1.63,
            volume_kg: 12400,
            new_personal_records: 1,
            last_completed_workout_on: workoutStatus === 'completed' ? today : addDays(today, -2),
            next_workout:
              workoutStatus === 'none'
                ? {
                    id: 55,
                    scheduled_date: addDays(today, 2),
                    scheduled_time: '19:00:00',
                    title: 'Верх тела',
                    status: 'planned',
                  }
                : null,
          },
          nutrition: {
            visible: true,
            logged_days: 20,
            adherence_evaluated_days: 20,
            average_calories: 1980,
            target_calories: 2100,
            average_protein_g: 130,
            target_protein_g: 140,
            target_effective_on: addDays(today, -40),
          },
          body: {
            latest_measurement: { measured_on: addDays(today, -1), weight_kg: 68.4 },
            trends: [
              {
                metric: 'weight_kg',
                first_value: 69.1,
                latest_value: 68.4,
                change: -0.7,
                first_measured_on: addDays(today, -25),
                latest_measured_on: addDays(today, -1),
                point_count: 4,
                span_days: 24,
                interpretation_status: 'available',
                points: [],
              },
            ],
            priority: null,
            guidance: {},
          },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: 84,
            included_components: ['workouts', 'calories', 'protein'],
            workouts: {},
            cardio: {},
            calories: {},
            protein: {},
          },
          data_sufficiency: {},
        },
      });
    }
    if (path.endsWith('/check-ins/weekly/current')) {
      return route.fulfill({
        json: {
          week_start: addDays(today, -3),
          week_end: addDays(today, 3),
          submitted_on: today,
          timezone: 'Europe/Moscow',
          existing: state.weeklyReviewAvailable ? null : { id: 1 },
          summary: {
            training: { completed_workouts: 0, planned_workouts: 1 },
            nutrition: { logged_days: 0 },
            progression: { new_personal_records: 0 },
            weight_trend: null,
          },
        },
      });
    }
    if (/\/workouts\/\d+\/comments$/.test(path)) {
      return route.fulfill({
        json: state.trainerComment
          ? [
              {
                id: 9,
                workout_id: 42,
                body: 'Сохрани спокойный темп в следующей тренировке.',
                created_at: `${today}T12:00:00Z`,
              },
            ]
          : [],
      });
    }
    if (path.endsWith('/nutrition/hydration')) {
      return route.fulfill({ json: emptyHydrationDay(today) });
    }
    if (path.endsWith('/nutrition/diary')) {
      if (state.failNutrition) return route.abort('failed');
      return route.fulfill({
        json: {
          diary_date: today,
          timezone: 'Europe/Moscow',
          meals: [],
          totals: {
            energy_kcal: '1450',
            protein_g: '96',
            fat_g: '48',
            carbs_g: '160',
            fiber_g: '18',
          },
          targets: {
            energy_kcal: '2100',
            protein_g: '140',
            fat_g: '70',
            carbs_g: '230',
          },
          remaining: {
            energy_kcal: '650',
            protein_g: '44',
            fat_g: '22',
            carbs_g: '70',
          },
        },
      });
    }
    return route.fulfill({ json: [] });
  });
}

async function openDashboard(page: Page) {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
}

test('shows the non-modal install option only after value on the authenticated Today surface', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    localStorage.setItem('app-theme', 'light');
    localStorage.setItem(
      'fit_pwa_install_v1',
      JSON.stringify({ appOpenCount: 2, qualified: true, dismissedUntil: 0 }),
    );
  });
  await mockDashboard(page, { workout: 'planned' });
  await openDashboard(page);

  await expect(page.getByTestId('pwa-install-prompt')).not.toBeAttached();
  await page.evaluate(() => {
    const event = new Event('beforeinstallprompt', { cancelable: true });
    Object.defineProperty(event, 'prompt', { value: () => Promise.resolve() });
    Object.defineProperty(event, 'userChoice', {
      value: Promise.resolve({ outcome: 'dismissed', platform: 'web' }),
    });
    window.dispatchEvent(event);
  });

  const prompt = page.getByTestId('pwa-install-prompt');
  await expect(prompt).toBeVisible();
  await expect(prompt.getByText('Быстрый возврат к тренировке')).toBeVisible();
  const installButton = prompt.getByRole('button', { name: 'Установить' });
  const installBounds = await installButton.boundingBox();
  expect(installBounds?.height).toBeGreaterThanOrEqual(44);
  await expect(installButton).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(installButton).toHaveCSS('color', 'rgb(9, 11, 11)');
  await expect(prompt.getByRole('button', { name: 'Не сейчас' })).toHaveCSS(
    'color',
    'rgb(21, 21, 21)',
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(installButton).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(installButton).toHaveCSS('color', 'rgb(9, 11, 11)');
  await expect(prompt.getByRole('button', { name: 'Не сейчас' })).toHaveCSS(
    'background-color',
    'rgb(20, 23, 23)',
  );
  await expect(prompt.getByRole('button', { name: 'Не сейчас' })).toHaveCSS(
    'color',
    'rgb(245, 245, 245)',
  );
  await page.setViewportSize({ width: 390, height: 844 });

  await prompt.getByRole('button', { name: 'Не сейчас' }).click();
  await expect(prompt).not.toBeAttached();
});

test('persists active workout on suspend and refreshes Today on return', async ({ page }) => {
  let todayRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith('/workouts/today')) todayRequests += 1;
  });
  await mockDashboard(page, { workout: 'in_progress' });
  await openDashboard(page);
  await expect(page.getByRole('button', { name: 'Продолжить тренировку' })).toBeVisible();

  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  await expect
    .poll(() =>
      page.evaluate(() => localStorage.getItem('fit_active_workout_v1_user_7_workout_42')),
    )
    .not.toBeNull();

  const requestsBeforeReturn = todayRequests;
  await page.evaluate(() => window.dispatchEvent(new Event('pageshow')));
  await expect.poll(() => todayRequests).toBeGreaterThan(requestsBeforeReturn);
});

test('core navigation keeps the locked order, labels, active state and deep links', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  await mockDashboard(page, { workout: 'planned' });
  await openDashboard(page);

  const destinations = page.locator('#appBottomNav .app-bottom-nav__primary > a');
  await expect(destinations).toHaveCount(4);
  expect(await destinations.allTextContents()).toEqual(['Сегодня', 'План', 'Питание', 'Прогресс']);
  expect(
    await destinations.evaluateAll((links) => links.map((link) => link.getAttribute('href'))),
  ).toEqual([
    '/app?section=today',
    '/app?section=programs',
    '/app?section=nutrition',
    '/app?section=progress',
  ]);
  await expect(page.getByRole('button', { name: 'Ещё', exact: true })).not.toBeAttached();

  const profileButton = page.getByRole('button', {
    name: 'Открыть профиль и настройки',
    exact: true,
  });
  const profileButtonBox = await profileButton.boundingBox();
  expect(profileButtonBox).not.toBeNull();
  expect(profileButtonBox!.width).toBeGreaterThanOrEqual(44);
  expect(profileButtonBox!.height).toBeGreaterThanOrEqual(44);
  await expect(profileButton).toHaveCSS('border-color', 'rgb(178, 245, 32)');
  await profileButton.click();
  await expect(page.getByRole('dialog', { name: 'Профиль и настройки' })).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть меню' }).click();

  await page.getByRole('link', { name: 'План', exact: true }).click();
  await expect(page.getByRole('link', { name: 'План', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByRole('heading', { name: 'План' })).toBeVisible();
});

test('planned workout starts from the primary Today CTA', async ({ page }) => {
  if (captureLandingProductProofs) {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript(() => localStorage.setItem('app-theme', 'light'));
  }
  await mockDashboard(page, { workout: 'planned' });
  await openDashboard(page);

  await expect(page.getByRole('heading', { name: 'Силовая база' })).toBeVisible();
  if (captureLandingProductProofs) {
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-today-desktop-light.png',
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-today-mobile-light.png',
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-today-desktop-dark.png',
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-today-mobile-dark.png',
    });
    return;
  }
  await page.getByRole('button', { name: 'Начать тренировку' }).click();

  await expect(page.getByText('Текущая тренировка')).toBeVisible();
  await expect(
    page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /К сводке/ }).click();
  await expect(page.getByRole('button', { name: /сегодня, .*В процессе/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /сегодня, .*Запланировано/i })).not.toBeAttached();
});

test('started workout finishes into a factual completed state', async ({ page }) => {
  await mockDashboard(page, { workout: 'in_progress' });
  await openDashboard(page);
  await expect(page.getByText('1 из 2 подходов отмечено')).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Завершить' }).click();
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
});

test('new and incomplete profile states keep program selection primary', async ({ page }) => {
  await mockDashboard(page, {
    workout: 'none',
    activeProgram: false,
    incompleteProfile: true,
  });
  await openDashboard(page);

  await expect(page.getByRole('heading', { name: 'С чего начнём?' })).toBeVisible();
  await expect(page.getByText('Сделайте рекомендации точнее')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Создать свою программу' })).toBeVisible();
  const chooseReady = page.getByRole('link', { name: 'Выбрать готовую' });
  await expect(chooseReady).toBeVisible();
  await expect(page.getByRole('link', { name: 'Заполнить профиль' })).toBeVisible();
  await expect(chooseReady).toHaveCSS('border-top-style', 'solid');
  await expect(chooseReady).toHaveCSS('border-top-width', '1px');
  const readyOutline = await chooseReady.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      fontWeight: style.fontWeight,
      height: element.getBoundingClientRect().height,
      innerStroke: style.boxShadow,
    };
  });
  expect(readyOutline.fontWeight).toBe('600');
  expect(readyOutline.height).toBeGreaterThanOrEqual(44);
  expect(readyOutline.innerStroke).toContain('0.5px');
  await expect(page.getByRole('link', { name: 'Записать питание' })).not.toBeAttached();
  await expect(page.getByRole('button', { name: 'Добавить активность' })).not.toBeAttached();
  await expect(page.locator('.today-dashboard__facts')).toHaveCSS('border-top-style', 'none');
  await expect(page.getByRole('link', { name: 'Создать свою программу' })).toBeAttached();
  await expect(page.locator('.today-dashboard details details')).toHaveCount(0);
});

test('task 116 owner-checkpoint screenshots', async ({ browser }) => {
  test.skip(!captureTask116Proofs, 'Owner-checkpoint capture is opt-in');

  const cases = [
    {
      name: 'desktop-today-planned-light-1440x900.png',
      viewport: { width: 1440, height: 900 },
      theme: 'light',
      state: { workout: 'planned' as const },
      heading: 'Силовая база',
    },
    {
      name: 'mobile-today-quick-start-light-390x844.png',
      viewport: { width: 390, height: 844 },
      theme: 'light',
      state: { workout: 'none' as const, activeProgram: false, incompleteProfile: true },
      heading: 'С чего начнём?',
    },
    {
      name: 'mobile-today-planned-dark-390x844.png',
      viewport: { width: 390, height: 844 },
      theme: 'dark',
      state: { workout: 'planned' as const },
      heading: 'Силовая база',
    },
  ];

  for (const capture of cases) {
    const context = await browser.newContext({ viewport: capture.viewport });
    const page = await context.newPage();
    await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), capture.theme);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await mockDashboard(page, capture.state);
    await openDashboard(page);
    await expect(page.getByRole('heading', { name: capture.heading })).toBeVisible();
    await page.screenshot({
      path: `../.artifacts/runtime/tests/screenshots/task-116/${capture.name}`,
      fullPage: true,
    });
    await context.close();
  }
});

test('rest, completed, weekly review and trainer comment use one primary action', async ({
  page,
}) => {
  await mockDashboard(page, { workout: 'none' });
  await openDashboard(page);
  await expect(page.getByRole('link', { name: 'Добавить питание' })).toBeVisible();

  await page.unrouteAll({ behavior: 'wait' });
  await mockDashboard(page, { workout: 'completed' });
  await page.reload();
  await expect(page.getByRole('link', { name: 'Посмотреть итог' })).toBeVisible();

  await page.unrouteAll({ behavior: 'wait' });
  await mockDashboard(page, { workout: 'none', weeklyReviewAvailable: true });
  await page.reload();
  await expect(page.getByRole('link', { name: 'Пройти короткую проверку' })).toBeVisible();

  await page.unrouteAll({ behavior: 'wait' });
  await mockDashboard(page, {
    workout: 'completed',
    weeklyReviewAvailable: true,
    trainerComment: true,
  });
  await page.reload();
  await expect(page.getByRole('link', { name: 'Открыть комментарий' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Пройти короткую проверку' })).not.toBeAttached();
});

test('secondary API failure does not erase the dashboard', async ({ page }) => {
  await mockDashboard(page, { workout: 'planned', failNutrition: true });
  await openDashboard(page);

  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  await expect(page.getByText('Сводка питания временно недоступна')).toBeVisible();
  await expect(page.getByText(/последний вес 68,4 кг/)).toBeVisible();
});

test('Today keeps hierarchy and has no horizontal overflow at required widths', async ({
  page,
}) => {
  await mockDashboard(page, { workout: 'planned' });
  await openDashboard(page);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeInViewport();
    await expect(page.getByRole('heading', { name: 'Питание на сегодня' })).toBeVisible();
    const nutritionCard = page.getByRole('region', { name: 'Питание на сегодня' });
    const progressCard = page.getByRole('region', { name: 'Главное о прогрессе' });
    await expect(nutritionCard).toHaveCount(1);
    await expect(progressCard).toHaveCount(1);
    const [nutritionBox, progressBox] = await Promise.all([
      nutritionCard.boundingBox(),
      progressCard.boundingBox(),
    ]);
    expect(nutritionBox).not.toBeNull();
    expect(progressBox).not.toBeNull();
    const summaryGap = progressBox!.y - (nutritionBox!.y + nutritionBox!.height);
    if (viewport.width >= 900) {
      expect(Math.abs(progressBox!.y - nutritionBox!.y)).toBeLessThanOrEqual(1);
      expect(progressBox!.x - (nutritionBox!.x + nutritionBox!.width)).toBeGreaterThanOrEqual(11);
    } else {
      expect(summaryGap).toBeGreaterThanOrEqual(11);
      expect(summaryGap).toBeLessThanOrEqual(13);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }
});
