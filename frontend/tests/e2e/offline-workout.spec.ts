import { expect, test } from '@playwright/test';

test('active workout переживает offline edit, refresh и reconnect без дублей', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let workoutOffline = false;
  let workoutMissing = false;
  let setVersion = 1;
  let setPatchCalls = 0;
  let setState = {
    actual_reps: null as number | null,
    actual_weight: null as number | null,
    is_completed: false,
  };
  const workout = () => ({
    id: 42,
    scheduled_date: '2030-01-10',
    title: 'Тренировка A',
    status: 'in_progress',
    day_number: 1,
    week_number: 1,
    started_at: '2030-01-10T10:00:00',
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Жим штанги лежа',
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 1,
        prescribed_reps: '8-10',
        rest_seconds: 90,
        notes: null,
        has_guide: false,
        sets: [
          {
            id: 201,
            set_number: 1,
            rir: null,
            set_kind: 'working',
            reached_failure: false,
            ...setState,
            version: setVersion,
          },
        ],
      },
    ],
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: 'fit_bot' },
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
          first_name: 'Тест',
          is_coach: false,
          is_admin: false,
          has_active_program: true,
          has_workout_history: false,
          onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
          profile: { full_name: 'Тестовый пользователь', timezone: 'Europe/Moscow' },
          trainer: null,
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      if (workoutMissing) {
        return route.fulfill({
          status: 404,
          json: { detail: 'На сегодня тренировка не назначена' },
        });
      }
      if (workoutOffline) return route.abort('internetdisconnected');
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/progress/summary'))
      return route.fulfill({
        json: {
          training: { last_completed_workout_on: null, next_workout: null },
          body: { latest_measurement: null, trends: [] },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
          },
        },
      });
    if (path.endsWith('/nutrition/diary'))
      return route.fulfill({
        json: {
          diary_date: '2030-01-10',
          timezone: 'Europe/Moscow',
          meals: [],
          totals: {
            energy_kcal: '0',
            protein_g: '0',
            fat_g: '0',
            carbs_g: '0',
            fiber_g: null,
          },
          targets: null,
          remaining: null,
        },
      });
    if (path.endsWith('/workouts/sets/201')) {
      setPatchCalls += 1;
      if (workoutOffline) return route.abort('internetdisconnected');
      const body = request.postDataJSON() as typeof setState;
      setState = {
        actual_reps: body.actual_reps,
        actual_weight: body.actual_weight,
        is_completed: body.is_completed,
      };
      setVersion += 1;
      return route.fulfill({
        json: { id: 201, set_number: 1, ...setState, version: setVersion },
      });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  workoutOffline = true;
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => false });
    window.dispatchEvent(new Event('offline'));
  });
  await page.getByRole('spinbutton', { name: 'Повторы, Жим штанги лежа, подход 1' }).fill('8');
  await page.getByRole('spinbutton', { name: 'Вес, Жим штанги лежа, подход 1' }).fill('40');
  await expect(page.getByText('Сохранено на устройстве')).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const key = Object.keys(localStorage).find((item) =>
          item.startsWith('fit_active_workout_v1_user_7_workout_42'),
        );
        const queue = key ? JSON.parse(localStorage.getItem(key) || '{}').queue : [];
        const values = queue?.at(-1)?.values;
        return values ? [values.actual_reps, values.actual_weight] : null;
      }),
    )
    .toEqual([8, 40]);
  const completeSet = page.getByRole('button', {
    name: 'Завершить: Жим штанги лежа, подход 1',
  });
  await completeSet.focus();
  await completeSet.click();
  await expect(page.getByRole('timer').filter({ hasText: 'Отдых' })).toContainText('1:30');
  await expect
    .poll(() =>
      page.evaluate(() => {
        const key = Object.keys(localStorage).find((item) =>
          item.startsWith('fit_active_workout_v1_user_7_workout_42'),
        );
        const queue = key ? JSON.parse(localStorage.getItem(key) || '{}').queue : [];
        return queue?.at(-1)?.values?.is_completed ?? null;
      }),
    )
    .toBe(true);

  workoutMissing = true;
  await page.reload();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page.getByRole('button', { name: /Открыть упражнение|1 из 1 сохранено/ }).click();
  await expect(
    page.getByRole('spinbutton', { name: 'Повторы, Жим штанги лежа, подход 1' }),
  ).toHaveValue('8');
  await expect(
    page.getByRole('spinbutton', { name: 'Вес, Жим штанги лежа, подход 1' }),
  ).toHaveValue('40');

  workoutOffline = false;
  workoutMissing = false;
  const callsBeforeReconnect = setPatchCalls;
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  expect(setPatchCalls - callsBeforeReconnect).toBe(1);
  expect(setState).toEqual({ actual_reps: 8, actual_weight: 40, is_completed: true });
});
