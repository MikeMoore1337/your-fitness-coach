import { expect, test, type Page } from '@playwright/test';
import { demoFixture } from './fixtures/demo-session';

const canonicalSvgPaths = [
  '/assets/brand/favicon.svg',
  '/assets/brand/favicon-light.svg',
  '/assets/brand/favicon-dark.svg',
  '/assets/brand/yfc-logo-light.svg',
  '/assets/brand/yfc-logo-dark.svg',
  '/assets/brand/yfc-mark-light.svg',
  '/assets/brand/yfc-mark-dark.svg',
];

const demoDate = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });

const emptyAdherence = () => ({
  status: 'insufficient_data',
  percent: null,
  achieved: 0,
  evaluated: 0,
  weight: 1,
  reason: 'Недостаточно данных для расчёта.',
});

const emptyDataSufficiency = () => ({
  ruleset_version: 'data-sufficiency-v1',
  workout_logging: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_completed_workouts'],
  },
  working_sets: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_logged_working_sets'],
  },
  rir_coverage: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_rir_observations'],
  },
  nutrition_coverage: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_logged_days'],
  },
  weight_trend: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_measurements'],
  },
  anthropometry: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_anthropometry_measurements'],
  },
  schedule_adherence: {
    status: 'insufficient',
    counters: { available: 0 },
    reason_keys: ['no_evaluable_planned_workouts'],
  },
});

function demoProgressSummary(date: string) {
  return {
    user_id: 900000001,
    period_days: 30,
    period_start: date,
    period_end: date,
    training: {
      planned_workouts: 0,
      completed_workouts: 0,
      skipped_workouts: 0,
      frequency_per_week: 0,
      volume_kg: 0,
      new_personal_records: 0,
      last_completed_workout_on: null,
      next_workout: null,
    },
    cardio: {
      completed_sessions: 0,
      planned_sessions: 0,
      frequency_per_week: 0,
      duration_minutes: 0,
      distance_km: null,
      zone_duration: [],
    },
    nutrition: {
      visible: true,
      logged_days: 0,
      complete_days: 0,
      incomplete_days: 0,
      fasted_days: 0,
      unlogged_days: 30,
      adherence_evaluated_days: 0,
      average_calories: null,
      target_calories: null,
      average_protein_g: null,
      target_protein_g: null,
      target_effective_on: null,
      exact_entry_count: 0,
      approximate_entry_count: 0,
      partial_entry_count: 0,
    },
    body: {
      latest_measurement: null,
      trends: [],
      priority: null,
      guidance: {
        comparison_basis: 'self',
        minimum_points_for_interpretation: 2,
        minimum_span_days_for_interpretation: 14,
        consistency_tips: [],
        circumference_limitations: [],
      },
    },
    adherence: {
      formula_version: 'adherence-v1',
      overall_percent: null,
      included_components: [],
      workouts: emptyAdherence(),
      cardio: emptyAdherence(),
      calories: emptyAdherence(),
      protein: emptyAdherence(),
    },
    data_sufficiency: emptyDataSufficiency(),
  };
}

function demoDiary(date: string) {
  const emptyNutrition = {
    energy_kcal: '0.00',
    protein_g: '0.000',
    fat_g: '0.000',
    carbs_g: '0.000',
    fiber_g: '0.000',
  };
  return {
    diary_date: date,
    timezone: 'Europe/Moscow',
    meals: (['breakfast', 'lunch', 'dinner', 'snacks'] as const).map((meal_type) => ({
      meal_type,
      entries: [],
      totals: emptyNutrition,
    })),
    totals: emptyNutrition,
    targets: null,
    remaining: null,
    status: 'unlogged',
    status_is_explicit: false,
  };
}

function demoHydration(date: string) {
  return {
    diary_date: date,
    timezone: 'Europe/Moscow',
    total_ml: 0,
    goal: null,
    progress_percent: null,
    entries: [],
    presets: [
      { id: null, label: 'Стакан', volume_ml: 250, beverage_type: 'water', is_default: true },
      {
        id: null,
        label: 'Большой стакан',
        volume_ml: 350,
        beverage_type: 'water',
        is_default: true,
      },
      { id: null, label: 'Бутылка', volume_ml: 500, beverage_type: 'water', is_default: true },
    ],
    last_logged_at: null,
    reminder_suppression_key: null,
    action_url: `/app?section=nutrition&date=${date}&hydration=quick`,
  };
}

function demoWeeklyReview(date: string) {
  return {
    week_start: date,
    week_end: date,
    submitted_on: date,
    timezone: 'Europe/Moscow',
    existing: null,
    summary: {
      ruleset_version: 'weekly-review-summary-v2',
      period_start: date,
      period_end: date,
      goal: null,
      training: { planned_workouts: 0, completed_workouts: 0, adherence: emptyAdherence() },
      nutrition: {
        logged_days: 0,
        complete_days: 0,
        incomplete_days: 0,
        fasted_days: 0,
        unlogged_days: 1,
        average_calories: null,
        target_calories: null,
        average_protein_g: null,
        target_protein_g: null,
        calories_adherence: emptyAdherence(),
        protein_adherence: emptyAdherence(),
        current_target: null,
        suspicious_low_days: [],
        exact_entry_count: 0,
        approximate_entry_count: 0,
        partial_entry_count: 0,
      },
      weight_trend: null,
      anthropometry_trends: [],
      body_priority: null,
      progression: { training_volume_kg: 0, new_personal_records: 0 },
      data_sufficiency: emptyDataSufficiency(),
      adaptive_energy: null,
    },
    progress_action: {
      kind: 'none',
      status: 'unavailable',
      target: 'progress',
      reason: 'no_supported_action',
      title: 'Нет действия',
      detail: 'Данных для действия пока нет.',
    },
  };
}

async function assertHeaderMark(
  page: Page,
  surface: 'light' | 'dark',
  width: number,
  height = width,
) {
  const mark = page.locator('.landing-header .landing-brand__mark');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveAttribute('src', `/assets/brand/yfc-mark-${surface}.svg`);
  await expect(mark).toHaveCSS('width', `${width}px`);
  await expect(mark).toHaveCSS('height', `${height}px`);
  await expect(mark).toHaveCSS('object-fit', 'contain');
  await expect(mark).toHaveAttribute('alt', '');
}

async function assertTransparentLoginHeader(page: Page) {
  const header = page.locator('.auth-public-shell .public-shell__header');
  await expect(header).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(header).toHaveCSS('background-image', 'none');
  await expect(header).toHaveCSS('box-shadow', 'none');
  await expect(header).toHaveCSS('border-top-width', '0px');
  await expect(header).toHaveCSS('border-right-width', '0px');
  await expect(header).toHaveCSS('border-bottom-width', '0px');
  await expect(header).toHaveCSS('border-left-width', '0px');
}

async function installPublicSurfaceApi(page: Page): Promise<Set<string>> {
  await page.route('**/api/v1/public/config', (route) =>
    route.fulfill({
      json: {
        app_env: 'test',
        enable_dev_auth: true,
        enable_web_auth: false,
        enable_email_auth: false,
        telegram_bot_username: '',
        oauth_providers: [],
      },
    }),
  );
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } }),
  );

  const snapshot = demoFixture('self_training');
  const unexpectedDemoPaths = new Set<string>();
  await page.route('**/api/v1/demo/sessions', (route) =>
    route.fulfill({
      status: 201,
      json: { ...snapshot, session_token: 'brand-assets-demo-session' },
    }),
  );
  await page.route('**/api/v1/demo/sessions/current', (route) => route.fulfill({ json: snapshot }));
  await page.route('**/api/v1/demo/sessions/current/transport', async (route) => {
    const payload = route.request().postDataJSON() as { path?: string };
    if (payload.path === '/api/v1/me') {
      await route.fulfill({
        json: {
          id: 900000001,
          telegram_user_id: null,
          username: 'demo_user',
          first_name: 'Демо',
          last_name: null,
          photo_url: null,
          custom_avatar: null,
          is_coach: false,
          is_admin: false,
          is_root: false,
          has_active_program: true,
          has_workout_history: true,
          has_food_history: true,
          onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
          profile: {
            full_name: 'Демо-профиль',
            birth_date: null,
            sex: 'male',
            goal: 'muscle_gain',
            level: 'intermediate',
            height_cm: 180,
            weight_kg: 77.1,
            workouts_per_week: 4,
            cardio_trainings_per_week: 2,
            resting_heart_rate: null,
            body_priority: { mode: 'balanced', muscle_group_ids: [] },
            training_preferences: null,
            timezone: 'Europe/Moscow',
            estimated_max_heart_rate: null,
            heart_rate_reserve: null,
            heart_rate_calculation_method: null,
            heart_rate_zones: [],
            recommended_cardio_range: null,
            kbju: null,
          },
          trainer: null,
        },
      });
      return;
    }
    const path = payload.path ?? '<missing>';
    const date = new URLSearchParams(path.split('?')[1] ?? '').get('diary_date') ?? demoDate();
    if (path.startsWith('/api/v1/workouts/progress/summary')) {
      await route.fulfill({ json: demoProgressSummary(date) });
      return;
    }
    if (path.startsWith('/api/v1/nutrition/diary?')) {
      await route.fulfill({ json: demoDiary(date) });
      return;
    }
    if (path.startsWith('/api/v1/nutrition/hydration?')) {
      await route.fulfill({ json: demoHydration(date) });
      return;
    }
    if (path === '/api/v1/workouts/week') {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === '/api/v1/workouts/recovery') {
      await route.fulfill({ json: { status: 'clear', missed_workouts: [], next_workout: null } });
      return;
    }
    if (path.startsWith('/api/v1/workouts/cardio?')) {
      await route.fulfill({ json: [] });
      return;
    }
    if (path === '/api/v1/check-ins/weekly/current') {
      await route.fulfill({ json: demoWeeklyReview(date) });
      return;
    }
    if (path === '/api/v1/workouts/today') {
      await route.fulfill({ status: 404, json: { detail: 'No workout scheduled for today' } });
      return;
    }
    unexpectedDemoPaths.add(path);
    console.error(`BRAND_FIXTURE_CONTRACT_VIOLATION ${path}`);
    await route.fulfill({ status: 500, json: { detail: `Unexpected demo path: ${path}` } });
  });
  return unexpectedDemoPaths;
}

test('canonical brand assets render on light and dark public surfaces', async ({ page }) => {
  const unexpectedDemoPaths = await installPublicSurfaceApi(page);
  const backendProxyFailures: string[] = [];
  page.on('requestfailed', (request) => {
    if (request.url().includes('127.0.0.1:8000')) backendProxyFailures.push(request.url());
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.evaluate(() => {
      window.localStorage.removeItem('app-theme');
      window.localStorage.removeItem('landing-theme');
    });
    await page.reload();
    // The landing header stays on the dark surface even when the page theme is light.
    await assertHeaderMark(page, 'dark', 38, 44);
    const wordmark = page.locator('.landing-header .yfc-lockup__wordmark');
    await expect(wordmark).toBeVisible();
    const brandBounds = await page.locator('.public-shell__brand').boundingBox();
    const actionBounds = await page.locator('.public-shell__header-actions').boundingBox();
    expect((brandBounds?.x ?? 0) + (brandBounds?.width ?? 0)).toBeLessThanOrEqual(
      actionBounds?.x ?? 0,
    );
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);

    if (viewport.name === 'desktop') {
      await page.screenshot({ path: '../.artifacts/brand/landing-light-desktop.png' });
    }

    if (viewport.name === 'mobile') {
      await page.getByRole('button', { name: 'Открыть меню', exact: true }).click();
    }
    await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
    if (viewport.name === 'mobile') {
      await page.getByRole('button', { name: 'Закрыть меню', exact: true }).click();
    }
    await assertHeaderMark(page, 'dark', 38, 44);
    await expect(page.locator('#landing-title')).toHaveCSS('color', 'rgb(255, 255, 255)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);

    if (viewport.name === 'mobile') {
      await page.screenshot({ path: '../.artifacts/brand/landing-dark-mobile.png' });
    }

    await page.goto('/login');
    await assertTransparentLoginHeader(page);
    if (viewport.name === 'mobile') {
      await assertHeaderMark(page, 'dark', 40);
      await expect(page.locator('.landing-header .yfc-lockup__wordmark')).toBeVisible();
    } else {
      await expect(page.locator('.login-continuation-brand .yfc-lockup__mark')).toBeVisible();
      await expect(page.locator('.login-continuation-brand .yfc-lockup__wordmark')).toBeVisible();
    }

    await page.goto('/training');
    await expect(page.locator('.public-header .yfc-lockup__wordmark')).toBeVisible();
    await expect(page.locator('.public-footer .yfc-lockup__wordmark')).toBeVisible();

    await page.goto('/demo');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('[data-demo-state="ready"]')).toBeVisible();
    expect([...unexpectedDemoPaths]).toEqual([]);
    expect(backendProxyFailures).toEqual([]);
    if (viewport.name === 'desktop') {
      await expect(page.locator('.app-bottom-nav__brand .yfc-lockup__wordmark')).toBeVisible();
    } else {
      await expect(page.locator('.app-bottom-nav--demo .app-bottom-nav__more')).toBeVisible();
    }
  }
});

test('favicon is canonical SVG and remains distinct at 16 and 32 pixels', async ({ page }) => {
  await installPublicSurfaceApi(page);
  await page.goto('/');

  await expect(page.locator('link[rel="icon"]:not([media])')).toHaveAttribute(
    'href',
    '/assets/brand/favicon.svg',
  );
  await expect(
    page.locator('link[rel="icon"][media="(prefers-color-scheme: light)"]'),
  ).toHaveAttribute('href', '/assets/brand/favicon-light.svg');
  await expect(
    page.locator('link[rel="icon"][media="(prefers-color-scheme: dark)"]'),
  ).toHaveAttribute('href', '/assets/brand/favicon-dark.svg');
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
    'href',
    '/assets/brand/apple-touch-icon.png',
  );

  for (const assetPath of canonicalSvgPaths) {
    const source = await page.evaluate(async (path) => {
      const response = await fetch(path);
      return { body: await response.text(), ok: response.ok };
    }, assetPath);
    expect(source.ok).toBe(true);
    expect(source.body).not.toMatch(/(?:data:|<image\b|(?:href|src)="https?:\/\/|@font-face)/i);
  }

  await page.setViewportSize({ width: 720, height: 420 });
  await page.setContent(`
    <style>
      body { display: grid; gap: 20px; margin: 0; padding: 20px; background: #f1f3ec; }
      .dark { padding: 20px; background: #0d120f; }
      img { display: block; width: 180px; height: auto; }
    </style>
    <img src="/assets/brand/yfc-logo-light.svg" width="180" height="150" alt="Your Fitness Coach" />
    <div class="dark"><img src="/assets/brand/yfc-logo-dark.svg" width="180" height="150" alt="Your Fitness Coach" /></div>
  `);
  await expect(page.getByRole('img', { name: 'Your Fitness Coach' })).toHaveCount(2);
  await page.screenshot({ path: '../.artifacts/brand/logo-variants.png' });

  await page.setViewportSize({ width: 96, height: 64 });
  await page.setContent(`
    <style>
      body { display: flex; gap: 24px; align-items: center; margin: 8px; background: #0d120f; }
      img { display: block; }
    </style>
    <img src="/assets/brand/favicon-dark.svg" width="16" height="16" alt="" />
    <img src="/assets/brand/favicon-dark.svg" width="32" height="32" alt="" />
  `);
  await expect(page.locator('img')).toHaveCount(2);
  await page.screenshot({ path: '../.artifacts/brand/favicon-16-32-dark.png' });
});
