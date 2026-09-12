import { expect, test, type Page } from '@playwright/test';
import { openDetailsByHeading as openCard } from './fixtures/locators';
import { contextualReminderTemplates, emptyHydrationDay } from './fixtures/platform-api';

type AppDestination = 'Сегодня' | 'План' | 'Прогресс' | 'Питание' | 'Упражнения' | 'Профиль';

async function openAppDestination(page: Page, destination: AppDestination) {
  const mainNavigation = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(mainNavigation).toBeVisible();
  const desktopLabel = destination === 'Профиль' ? 'Профиль и настройки' : destination;
  const mobileLabel = destination === 'Профиль' ? 'Профиль и настройки' : destination;
  const directLink = mainNavigation.getByRole('link', { name: desktopLabel, exact: true });
  for (let index = 0; index < (await directLink.count()); index += 1) {
    const candidate = directLink.nth(index);
    if (await candidate.isVisible()) {
      await candidate.click();
      return;
    }
  }
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page.locator('#appMorePanel').getByRole('link', { name: mobileLabel, exact: true }).click();
}

test('логотип и кнопки в шапке имеют одинаковую высоту', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    const brandTarget = await page.locator('.landing-header .landing-brand').boundingBox();
    const logo = await page.locator('.landing-header .landing-brand__mark').boundingBox();
    const themeButton = await page.locator('.landing-theme-toggle').boundingBox();
    const loginButton = page.locator('.landing-button--compact');

    expect(logo).not.toBeNull();
    expect(brandTarget).not.toBeNull();
    expect(themeButton).not.toBeNull();
    expect(Math.min(brandTarget!.width, brandTarget!.height)).toBeGreaterThanOrEqual(44);
    expect(themeButton?.height).toBeGreaterThanOrEqual(44);
    await expect(loginButton).toBeVisible();
    expect((await loginButton.boundingBox())?.height).toBeGreaterThanOrEqual(44);

    const themeControl = page.getByRole('button', { name: /Включить .* тему/ });
    await themeControl.hover();
    const themeHoverStyles = await themeControl.evaluate((element) => {
      const styles = getComputedStyle(element);
      return {
        boxShadow: styles.boxShadow,
        transform: styles.transform,
      };
    });
    expect(themeHoverStyles).toEqual({ boxShadow: 'none', transform: 'none' });

    const menuButton = page.getByRole('button', { name: 'Открыть меню' });
    if (viewport.width < 980) {
      await expect(menuButton).toBeVisible();
      expect((await menuButton.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      await menuButton.hover();
      await expect(menuButton).toHaveCSS('box-shadow', 'none');
      await expect(menuButton).toHaveCSS('transform', 'none');
      await menuButton.click();
      await expect(page.getByRole('navigation', { name: 'Навигация по странице' })).toHaveClass(
        /is-open/,
      );
      await expect(page.getByRole('link', { name: 'Продукт', exact: true })).toBeVisible();
      await page.getByRole('link', { name: 'Продукт', exact: true }).click();
      await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    } else {
      await expect(menuButton).toBeHidden();
    }
  }
});

test('описания самостоятельного и тренерского сценариев сохраняют читаемый цвет', async ({
  page,
}) => {
  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');

    const selfDescription = page.locator('.landing-practice > div > p:not(.landing-kicker)');
    const coachDescription = page.locator('.landing-trainer__copy > p:not(.landing-kicker)');

    await expect(selfDescription).toHaveCSS('color', 'rgb(172, 177, 177)');
    await expect(coachDescription).toHaveCSS('color', 'rgb(17, 17, 17)');
  }
});

test('мобильное меню не сохраняет активную заливку после касания', async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:4173',
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.goto('/');

  expect(await page.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
  const menuButton = page.getByRole('button', { name: 'Открыть меню' });
  const restStyles = await menuButton.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      backgroundColor: styles.backgroundColor,
      borderColor: styles.borderColor,
      boxShadow: styles.boxShadow,
      color: styles.color,
    };
  });

  await menuButton.tap();
  const closeMenuButton = page.getByRole('button', { name: 'Закрыть меню' });
  await expect
    .poll(() =>
      closeMenuButton.evaluate((element) => {
        const styles = getComputedStyle(element);
        return {
          backgroundColor: styles.backgroundColor,
          borderColor: styles.borderColor,
          boxShadow: styles.boxShadow,
          color: styles.color,
        };
      }),
    )
    .toEqual(restStyles);

  await context.close();
});

test('первый экран лендинга объясняет продукт и не создаёт горизонтальный скролл', async ({
  page,
}) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: /сила в действии/i })).toBeVisible();
    await expect(
      page.locator('.landing-hero__actions').getByRole('link', { name: 'Начать', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.landing-hero__image')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }
});

test('вторичный hero CTA сохраняет контрастный текст при наведении в обеих темах', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');

  for (const scheme of ['light', 'dark'] as const) {
    await page.evaluate(() => window.localStorage.removeItem('app-theme'));
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await page.reload();

    const expectedBackground = 'rgba(20, 25, 25, 0.64)';
    const expectedText = 'rgb(255, 255, 255)';
    for (const link of [
      page.locator('.landing-hero__actions').getByRole('link', { name: /Попробовать демо/ }),
    ]) {
      await link.hover();
      await expect(link).toHaveCSS('background-color', expectedBackground);
      await expect(link).toHaveCSS('color', expectedText);
      await expect(link.locator('.yfc-icon')).toHaveCSS('color', expectedText);
    }
  }
});

test('лендинг остаётся адаптивным на контрольных ширинах', async ({ page }) => {
  for (const width of [360, 390, 430, 768, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
    await page.goto('/');

    const pageMetrics = await page.evaluate(() => ({
      viewport: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
    }));
    expect(pageMetrics.documentWidth).toBeLessThanOrEqual(pageMetrics.viewport);
    expect(pageMetrics.bodyWidth).toBeLessThanOrEqual(pageMetrics.viewport);
    await expect(
      page.locator('.landing-hero__actions').getByRole('link', { name: 'Начать', exact: true }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: /Включить .* тему/ })).toBeInViewport();
    await expect(page.locator('.landing-continuity__rail')).toBeVisible();
  }
});

test('лендинг доступен с клавиатуры и содержит метаданные', async ({ page }) => {
  await page.goto('/');

  const skipLink = page.getByRole('link', { name: 'К содержимому' });
  await skipLink.focus();
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('#landing-content')).toBeFocused();

  await expect(page).toHaveTitle(/тренировки, питание и прогресс в браузере и telegram/i);
  expect(await page.locator('meta[name="description"]').getAttribute('content')).toMatch(
    /фиксировать результаты.*ориентиры кбжу/i,
  );
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute(
    'content',
    /в браузере и telegram/i,
  );
  await expect(page.locator('meta[property="og:type"]')).toHaveAttribute('content', 'website');
});

test('блок возможностей показывает пользу спортсмену и инструменты тренеру', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    await expect(page.getByRole('heading', { name: /питание без догадок/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /замечай своё движение/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /тренер рядом с планом/i })).toBeVisible();
    await expect(page.locator('.landing-feature')).toHaveCount(2);
    if (viewport.width <= 430) {
      const compactTextLinks = page.locator('.landing-brand, .landing-footer a');
      for (const link of await compactTextLinks.all()) {
        expect((await link.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }
});

test('сценарий и платформы остаются понятными на разных экранах', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    await expect(page.locator('.landing-start__steps li')).toHaveCount(3);
    await expect(
      page.getByRole('heading', { name: /от настройки — к повторяемому ритму/i }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: /web для полного контекста/i })).toBeVisible();
    await expect(
      page.getByText(/telegram mini app не является отдельным приложением/i),
    ).toBeVisible();

    const platformRail = page.locator('.landing-continuity__rail');
    await expect(platformRail).toBeVisible();
    await expect(platformRail).toContainText('Web');
    await expect(platformRail).toContainText('Telegram Mini App');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }
});

test('сценарии спортсмена и тренера ведут в веб-приложение', async ({ page }) => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/');

    await expect(page.locator('.landing-practice')).toBeVisible();
    await expect(page.locator('.landing-trainer')).toBeVisible();
    await expect(page.getByText(/попробуй сам/i)).toBeVisible();
    await expect(page.getByRole('heading', { name: /тренер рядом с планом/i })).toBeVisible();
    await expect(
      page.locator('.landing-footer').getByRole('link', { name: 'Тренировки', exact: true }),
    ).toHaveAttribute('href', '/training');
    await expect(page.getByRole('link', { name: /посмотреть кабинет тренера/i })).toHaveAttribute(
      'href',
      '/for-trainers',
    );
    await expect(page.locator('.landing-practice').getByText(/попробуй сам/i)).toBeVisible();
    await expect(
      page.locator('.landing-contact__actions').getByRole('link', { name: /открыть приложение/i }),
    ).toHaveAttribute('href', '/app');
    await expect(
      page.locator('.landing-contact').getByRole('link', { name: /попробовать демо/i }),
    ).toHaveAttribute('href', '/demo?cabinet=1&scenario=self_training&section=today');
    await expect(page.getByRole('link', { name: /поддержка в telegram/i })).toHaveAttribute(
      'href',
      'https://t.me/your_fitness_coach_bot?start=support',
    );
    const heroButtons = page.locator('.landing-hero__actions .landing-button');
    const contactButtons = page.locator('.landing-contact__actions .landing-button');
    for (const buttons of [heroButtons, contactButtons]) {
      await expect(buttons).toHaveCount(2);
      const boxes = await Promise.all((await buttons.all()).map((button) => button.boundingBox()));
      expect(boxes).toHaveLength(2);
      expect(boxes[0]).not.toBeNull();
      expect(boxes[1]).not.toBeNull();
      expect(boxes[0]!.height).toBe(boxes[1]!.height);
      if (viewport.width === 390) {
        expect(boxes[0]!.width).toBeGreaterThanOrEqual(44);
        expect(boxes[1]!.width).toBeGreaterThanOrEqual(44);
      }
    }
    const featureCards = page.locator('.landing-feature');
    await expect(featureCards).toHaveCount(2);
    await expect(featureCards.getByRole('link')).toHaveCount(2);
    if (viewport.width === 390) {
      const brand = page.locator('.landing-header .landing-brand');
      const brandWordmark = brand.locator('.yfc-lockup__wordmark');
      await expect(brandWordmark).toBeVisible();
      const brandBox = await brand.boundingBox();
      expect(brandBox).not.toBeNull();
      expect(brandBox!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    if (viewport.width === 390) {
      const footerTagline = page.locator('.landing-footer__brand > p');
      await expect(footerTagline).toHaveCount(1);
      await expect(footerTagline).toBeVisible();
    }
  }
});

async function mockApi(
  page: Page,
  {
    completeProfile = false,
    fullName = 'Демо пользователь',
    coachClientName = 'Тестовый клиент',
    withCoachClient = false,
    withCoachProgram = false,
    withTrainingPreferences = false,
    notificationItems = [] as Array<Record<string, unknown>>,
    telegramLinked = true,
    staleNotificationIds = [] as number[],
  } = {},
) {
  let role: 'client' | 'coach' | 'admin' = 'client';
  let trainingPreferences = {
    preferred_duration_min: withTrainingPreferences ? 40 : null,
    preferred_duration_max: withTrainingPreferences ? 70 : null,
    preferred_weekdays: withTrainingPreferences ? [0, 2, 4] : [],
    preferred_time: withTrainingPreferences ? '18:30:00' : null,
    location_profiles: withTrainingPreferences
      ? [
          {
            location: 'gym' as const,
            equipment_ids: ['bodyweight', 'dumbbell', 'barbell', 'bench', 'cable', 'machine'],
          },
        ]
      : [],
    preferred_exercise_ids: withTrainingPreferences ? [2] : [],
    avoided_exercises: withTrainingPreferences
      ? [{ exercise_id: 1, reason: 'not_enjoyable' as const }]
      : [],
    note: withTrainingPreferences ? 'Не ставить тяжёлые жимы в два дня подряд.' : null,
    updated_at: withTrainingPreferences ? '2030-01-10T12:00:00' : null,
    updated_by: withTrainingPreferences
      ? {
          user_id: 9,
          display_name: 'Тренер Анна',
          role: 'trainer' as 'trainer' | 'self',
        }
      : null,
    conflict: withTrainingPreferences
      ? {
          status: 'review_required' as const,
          active_program_id: 501,
          reasons: [
            'В активной программе есть упражнение из списка «избегать».',
            'Для активной программы может не хватать оборудования: Гиря.',
          ],
        }
      : { status: 'none' as const, active_program_id: null, reasons: [] },
  };
  const heartRateZones = [
    { zone: 1, title: 'Восстановление', min_bpm: 130, max_bpm: 140 },
    { zone: 2, title: 'Лёгкая', min_bpm: 140, max_bpm: 151 },
    { zone: 3, title: 'Аэробная', min_bpm: 151, max_bpm: 162 },
    { zone: 4, title: 'Пороговая', min_bpm: 162, max_bpm: 173 },
    { zone: 5, title: 'Максимальная', min_bpm: 173, max_bpm: 184 },
  ];
  const emptyProgress = {
    workouts_total: 0,
    workouts_completed: 0,
    workouts_skipped: 0,
    workouts_missed: 0,
    adherence_percent: 0,
    current_streak: 0,
    weight_change_kg: null,
    weights: [],
    weekly_volume: [],
    personal_records: [],
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path.endsWith('/public/config'))
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: 'fit_bot' },
      });
    if (path.endsWith('/auth/refresh'))
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    if (path.endsWith('/auth/telegram/init'))
      return route.fulfill({ json: { access_token: 'telegram-test-token', token_type: 'bearer' } });
    if (path.endsWith('/auth/dev-login')) {
      const body = request.postDataJSON() as { is_admin: boolean; is_coach: boolean };
      role = body.is_admin ? 'admin' : body.is_coach ? 'coach' : 'client';
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/me/profile/heart-rates/preview')) {
      const body = request.postDataJSON() as {
        resting_heart_rate: number | null;
        goal: 'fat_loss' | 'recomposition' | 'maintenance' | 'muscle_gain' | null;
      };
      const recommendations = {
        fat_loss: { min_bpm: 130, max_bpm: 140 },
        recomposition: { min_bpm: 124, max_bpm: 140 },
        maintenance: { min_bpm: 119, max_bpm: 140 },
        muscle_gain: { min_bpm: 119, max_bpm: 130 },
      };
      return route.fulfill({
        json: {
          estimated_max_heart_rate: 184,
          heart_rate_reserve: body.resting_heart_rate === null ? null : 109,
          heart_rate_calculation_method:
            body.resting_heart_rate === null ? 'percent_maximum' : 'heart_rate_reserve',
          heart_rate_zones: heartRateZones,
          recommended_cardio_range: body.goal ? recommendations[body.goal] : null,
        },
      });
    }
    if (path.endsWith('/me/profile') && request.method() === 'PATCH') {
      const body = request.postDataJSON() as {
        training_preferences?: typeof trainingPreferences;
      };
      if (body.training_preferences) {
        trainingPreferences = {
          ...trainingPreferences,
          ...body.training_preferences,
          updated_at: '2030-01-10T12:30:00',
          updated_by: { user_id: 1, display_name: fullName, role: 'self' },
        };
      }
      return route.fulfill({
        json: { id: 1, profile: { training_preferences: trainingPreferences } },
      });
    }
    if (path.endsWith('/me'))
      return route.fulfill({
        json: {
          id: 1,
          telegram_user_id: 2001,
          username: 'demo',
          first_name: 'Демо',
          is_coach: role === 'coach',
          is_admin: role === 'admin',
          is_root: role === 'admin',
          has_active_program: false,
          has_workout_history: false,
          onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
          profile: {
            full_name: fullName,
            goal: 'maintenance',
            level: completeProfile ? 'beginner' : null,
            workouts_per_week: completeProfile ? 3 : null,
            timezone: 'Europe/Moscow',
            kbju: null,
            training_preferences: trainingPreferences,
          },
          trainer: null,
        },
      });
    if (path.endsWith('/me/trainer-capability')) {
      let activatedNow = false;
      if (request.method() === 'POST') {
        activatedNow = role !== 'coach';
        role = 'coach';
      }
      if (request.method() === 'DELETE') {
        if (withCoachClient) {
          return route.fulfill({
            status: 409,
            json: { detail: 'Сначала завершите активные отношения с клиентами.' },
          });
        }
        role = 'client';
      }
      return route.fulfill({
        json: {
          is_active: role === 'coach',
          activated_now: activatedNow,
          active_client_count: role === 'coach' && withCoachClient ? 1 : 0,
          pending_invite_count: 0,
          can_disable: role === 'coach' && !withCoachClient,
          terms_version: 'trainer-capability-v1',
        },
      });
    }
    if (path.endsWith('/workouts/today'))
      return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка не назначена' } });
    if (path.endsWith('/workouts/progress/summary'))
      return route.fulfill({
        json: {
          user_id: 1,
          period_days: 30,
          period_start: '2030-01-01',
          period_end: '2030-01-10',
          training: {
            planned_workouts: 0,
            completed_workouts: 0,
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
            adherence_evaluated_days: 0,
            average_calories: null,
            target_calories: null,
            average_protein_g: null,
            target_protein_g: null,
            target_effective_on: null,
          },
          body: {
            latest_measurement: null,
            trends: [],
            priority: null,
            guidance: { consistency_tips: [], circumference_limitations: [] },
          },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
            workouts: {},
            cardio: {},
            calories: {},
            protein: {},
          },
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: { status: 'insufficient', counters: {}, reason_keys: [] },
            working_sets: { status: 'insufficient', counters: {}, reason_keys: [] },
            rir_coverage: { status: 'insufficient', counters: {}, reason_keys: [] },
            nutrition_coverage: { status: 'insufficient', counters: {}, reason_keys: [] },
            weight_trend: { status: 'insufficient', counters: {}, reason_keys: [] },
            anthropometry: { status: 'insufficient', counters: {}, reason_keys: [] },
            schedule_adherence: { status: 'insufficient', counters: {}, reason_keys: [] },
          },
        },
      });
    if (path.endsWith('/workouts/progress/training-analytics'))
      return route.fulfill({
        json: {
          period_days: 30,
          period_start: '2030-01-01',
          period_end: '2030-01-10',
          exercise_history_limit: 20,
          completed_set_count: 0,
          reps_total: 0,
          reps_recorded_sets: 0,
          external_load_volume_kg: 0,
          volume_recorded_sets: 0,
          exercises: [],
          rir: {
            completed_set_count: 0,
            recorded_set_count: 0,
            missing_set_count: 0,
            distribution: [],
          },
          primary_muscle_exposure: [],
          secondary_muscle_exposure: [],
          completed_sets_without_muscle_metadata: 0,
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: { status: 'insufficient', counters: {}, reason_keys: [] },
            working_sets: { status: 'insufficient', counters: {}, reason_keys: [] },
            rir_coverage: { status: 'insufficient', counters: {}, reason_keys: [] },
          },
        },
      });
    if (path.endsWith('/nutrition/hydration')) {
      return route.fulfill({
        json: emptyHydrationDay(url.searchParams.get('diary_date') || '2030-01-10'),
      });
    }
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
          status: 'unlogged',
          status_is_explicit: false,
        },
      });
    if (path.endsWith('/workouts/progress')) return route.fulfill({ json: emptyProgress });
    if (path.endsWith('/check-ins/weekly/current'))
      return route.fulfill({
        json: {
          week_start: '2030-01-07',
          week_end: '2030-01-13',
          submitted_on: '2030-01-10',
          timezone: 'Europe/Moscow',
          existing: null,
          summary: {
            ruleset_version: 'weekly-check-in-summary-v1',
            period_start: '2030-01-07',
            period_end: '2030-01-10',
            goal: null,
            training: {
              planned_workouts: 0,
              completed_workouts: 0,
              adherence: {
                status: 'not_applicable',
                percent: null,
                achieved: 0,
                evaluated: 0,
                weight: 0.4,
              },
            },
            nutrition: {
              logged_days: 0,
              average_calories: null,
              target_calories: null,
              average_protein_g: null,
              target_protein_g: null,
              calories_adherence: {
                status: 'not_applicable',
                percent: null,
                achieved: 0,
                evaluated: 0,
                weight: 0.2,
              },
              protein_adherence: {
                status: 'not_applicable',
                percent: null,
                achieved: 0,
                evaluated: 0,
                weight: 0.2,
              },
            },
            weight_trend: null,
            anthropometry_trends: [],
            body_priority: null,
            progression: { training_volume_kg: 0, new_personal_records: 0 },
            data_sufficiency: {
              weight_trend: { status: 'insufficient', counters: {}, reason_keys: [] },
            },
          },
        },
      });
    if (path.endsWith('/check-ins/weekly'))
      return route.fulfill({ json: { items: [], total: 0, limit: 4, offset: 0 } });
    if (path.endsWith('/workouts/schedule')) return route.fulfill({ json: [] });
    if (path.endsWith('/workouts/history/summary'))
      return route.fulfill({
        json: { workouts_completed: 0, completed_sets: 0, volume_kg: 0 },
      });
    if (path.endsWith('/workouts/history') || path.endsWith('/workouts/week'))
      return route.fulfill({ json: [] });
    if (path.endsWith('/me/coach-invites/link/preview'))
      return route.fulfill({
        json: {
          invite_id: 77,
          coach: {
            id: 9,
            telegram_user_id: 9009,
            username: 'test_coach',
            full_name: 'Тестовый тренер',
            can_open_chat: true,
            chat_url: 'https://t.me/test_coach',
            chat_unavailable_reason: null,
          },
          created_at: '2030-01-01T10:00:00',
          expires_at: '2030-01-15T10:00:00',
          requires_trainer_change: false,
          already_current_trainer: false,
          current_trainer: null,
        },
      });
    if (path.endsWith('/me/coach-invites/link/confirm'))
      return route.fulfill({ status: 204, body: '' });
    if (path.endsWith('/notifications/settings'))
      return route.fulfill({
        json: {
          workout_reminders_enabled: true,
          weekly_check_in_reminders_enabled: true,
          measurement_reminders_enabled: false,
          meal_reminders_enabled: false,
          hydration_reminders_enabled: false,
          movement_reminders_enabled: false,
          telegram_enabled: true,
          telegram_linked: telegramLinked,
          reminder_hour: 9,
          quiet_hours_start: null,
          quiet_hours_end: null,
        },
      });
    if (path.endsWith('/notifications/templates'))
      return route.fulfill({
        json: contextualReminderTemplates.map((template) => ({
          ...template,
          telegram_linked: telegramLinked,
          channel_note: telegramLinked
            ? template.channel_note
            : 'В приложении доступно всегда; Telegram появится после связывания аккаунта.',
        })),
      });
    if (/\/notifications\/templates\/(meal_logging|hydration|movement_break)$/.test(path)) {
      const templateKey = path.split('/').pop();
      const template = contextualReminderTemplates.find(
        (item) => item.template_key === templateKey,
      );
      return route.fulfill({ json: { ...template, ...request.postDataJSON() } });
    }
    if (path.endsWith('/notifications/read-all'))
      return route.fulfill({ json: { updated: notificationItems.length } });
    const notificationOpenMatch = path.match(/\/notifications\/(\d+)\/open$/);
    if (notificationOpenMatch) {
      const notificationId = Number(notificationOpenMatch[1]);
      const stale = staleNotificationIds.includes(notificationId);
      return route.fulfill({
        json: {
          destination: stale ? '/app?section=profile#profile-notifications' : '/app?section=today',
          stale,
          message: stale
            ? 'Связанный объект больше недоступен. Вы вернулись в центр уведомлений.'
            : null,
        },
      });
    }
    if (path.endsWith('/notifications')) return route.fulfill({ json: notificationItems });
    if (path.endsWith('/programs/exercises/1'))
      return route.fulfill({
        json: {
          id: 1,
          title: 'Тяга блока',
          primary_muscle: 'Спина',
          equipment: 'Блок',
          primary_muscle_ids: ['back'],
          secondary_muscle_ids: ['biceps'],
          equipment_ids: ['cable'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
          guide: {
            technique_steps: ['Зафиксируйте корпус', 'Выполните движение под контролем'],
            breathing: 'Выдох в фазе усилия, вдох при возврате.',
            common_mistakes: ['Раскачивание корпусом'],
            muscles: [
              {
                identifier: 'back',
                name: 'Спина',
                role_id: 'primary',
                role: 'Основная',
                function: 'Тянет плечевой пояс назад.',
              },
              {
                identifier: 'biceps',
                name: 'Бицепс',
                role_id: 'secondary',
                role: 'Дополнительная',
                function: 'Сгибает локоть.',
              },
            ],
            equipment: [{ identifier: 'cable', name: 'Тросовый блок' }],
            safety_notes: ['Сохраняйте устойчивое положение корпуса.'],
            alternatives: [],
            images: [
              {
                phase: 'Фаза усилия',
                url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>',
                alt: 'Фаза усилия',
              },
              {
                phase: 'Фаза возврата',
                url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>',
                alt: 'Фаза возврата',
              },
            ],
            media: [
              {
                type: 'image',
                phase_id: 'concentric_end',
                phase: 'Фаза усилия',
                url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>',
                poster:
                  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>',
                alt: 'Фаза усилия',
                asset_id: 'test-lat-pulldown-concentric',
                asset_version: 'test-v1',
                variant_key: 'test-cable-lat-pulldown',
                source_name: 'Test source',
                source_url: 'https://example.com',
                source_license: 'Public domain',
                source_license_url: null,
                width: 400,
                height: 300,
                byte_size: 100,
                sort_order: 0,
                sources: [
                  {
                    url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>',
                    mime_type: 'image/svg+xml',
                    width: 400,
                    height: 300,
                    byte_size: 100,
                  },
                ],
              },
              {
                type: 'image',
                phase_id: 'eccentric_end',
                phase: 'Фаза возврата',
                url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>%20',
                poster:
                  'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>%20',
                alt: 'Фаза возврата',
                asset_id: 'test-lat-pulldown-eccentric',
                asset_version: 'test-v1',
                variant_key: 'test-cable-lat-pulldown',
                source_name: 'Test source',
                source_url: 'https://example.com',
                source_license: 'Public domain',
                source_license_url: null,
                width: 400,
                height: 300,
                byte_size: 100,
                sort_order: 1,
                sources: [
                  {
                    url: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"/>%20',
                    mime_type: 'image/svg+xml',
                    width: 400,
                    height: 300,
                    byte_size: 100,
                  },
                ],
              },
            ],
            source_name: 'Test source',
            source_url: 'https://example.com',
            source_license: 'Public domain',
            source_license_url: null,
            media_reference: 'test:lat-pulldown',
          },
        },
      });
    if (path.endsWith('/programs/exercises'))
      return route.fulfill({
        json: [
          {
            id: 1,
            title: 'Тяга блока',
            primary_muscle: 'Спина',
            equipment: 'Блок',
            primary_muscle_ids: ['back'],
            secondary_muscle_ids: ['biceps'],
            equipment_ids: ['cable'],
            alternatives: [],
            difficulty_level: 'beginner',
            is_custom: false,
            is_personalized: false,
            has_guide: true,
            guide: null,
          },
        ],
      });
    if (path.endsWith('/programs/templates/mine'))
      return route.fulfill({
        json: [
          {
            id: 10,
            title: 'Программа на всё тело — 3 дня',
            slug: 'full-body-3-days',
            goal: 'recomposition',
            level: 'beginner',
            owner_user_id: null,
            owner_telegram_user_id: null,
            owner_full_name: null,
            created_by_user_id: null,
            is_public: true,
            is_example: true,
            is_assigned_to_current_user: false,
            is_active_for_current_user: false,
            assigned_by_user_id: null,
            assigned_by_full_name: null,
            days: [
              {
                id: 100,
                day_number: 1,
                title: 'Всё тело',
                exercises: [
                  {
                    id: 1000,
                    exercise_id: 1,
                    exercise_title: 'Тяга блока',
                    prescribed_sets: 3,
                    prescribed_reps: '10–12',
                    rest_seconds: 90,
                    notes: null,
                    has_guide: true,
                  },
                ],
              },
            ],
          },
          {
            id: 11,
            title: 'Текущий план от тренера',
            slug: 'coach-active-plan',
            goal: 'maintenance',
            level: 'beginner',
            owner_user_id: null,
            owner_telegram_user_id: null,
            owner_full_name: null,
            created_by_user_id: 99,
            is_public: false,
            is_example: false,
            is_assigned_to_current_user: true,
            is_active_for_current_user: true,
            can_edit: false,
            assigned_by_user_id: 99,
            assigned_by_full_name: 'Тренер Анна',
            assigned_program_id: 501,
            assigned_program_status: 'active',
            assigned_program_start_date: '2030-01-01',
            assigned_program_duration_weeks: 4,
            current_revision_number: 1,
            days: [
              {
                id: 110,
                day_number: 1,
                title: 'База',
                exercises: [
                  {
                    id: 1100,
                    exercise_id: 1,
                    exercise_title: 'Тяга блока',
                    prescribed_sets: 3,
                    prescribed_reps: '10–12',
                    rest_seconds: 90,
                    notes: null,
                    superset_group: null,
                    superset_order: null,
                    has_guide: true,
                  },
                ],
              },
            ],
          },
        ],
      });
    if (path.endsWith('/programs/templates/recommendation')) {
      const criteria = request.postDataJSON() as {
        goal: string;
        experience: string;
        workouts_per_week: number;
        training_location: string | null;
        available_equipment_ids: string[] | null;
      };
      return route.fulfill({
        json: {
          status: 'recommended',
          criteria: { ...criteria, profile_fields_used: [] },
          missing_fields: [],
          message: 'Сначала посмотрите состав программы.',
          recommendation: {
            template: {
              id: 10,
              title: 'Программа на всё тело — 3 дня',
              slug: 'full-body-3-days',
              goal: 'recomposition',
              level: 'beginner',
              split_type: 'full_body',
              owner_user_id: null,
              owner_telegram_user_id: null,
              owner_full_name: null,
              created_by_user_id: null,
              is_public: true,
              is_example: true,
              is_assigned_to_current_user: false,
              is_active_for_current_user: false,
              can_edit: false,
              assigned_by_user_id: null,
              assigned_by_full_name: null,
              days: [
                {
                  id: 100,
                  day_number: 1,
                  title: 'Всё тело',
                  exercises: [
                    {
                      id: 1000,
                      exercise_id: 1,
                      exercise_title: 'Тяга блока',
                      prescribed_sets: 3,
                      prescribed_reps: '10–12',
                      rest_seconds: 90,
                      notes: null,
                      has_guide: true,
                    },
                  ],
                },
                {
                  id: 101,
                  day_number: 2,
                  title: 'Всё тело B',
                  exercises: [],
                },
                {
                  id: 102,
                  day_number: 3,
                  title: 'Всё тело C',
                  exercises: [],
                },
              ],
            },
            reason: 'Совпадает с выбранной целью, уровнем и ритмом.',
            fit_facts: [
              'Цель подбора: улучшение композиции тела.',
              'В шаблоне 3 тренировки за цикл.',
              'Для шаблона не требуется отдельное оборудование.',
            ],
            limitations: [],
          },
          alternatives: [],
          requires_explicit_start: true,
        },
      });
    }
    if (path.endsWith('/programs/assigned/501/revisions'))
      return route.fulfill({
        json: [
          {
            id: 1,
            user_program_id: 501,
            revision_number: 1,
            changed_by_user_id: 99,
            actor_role: 'trainer',
            change_kind: 'assigned',
            reason: null,
            changed_fields: {},
            snapshot: {},
            created_at: '2030-01-01T10:00:00',
          },
        ],
      });
    if (path.endsWith('/programs/assigned/501/blocks')) return route.fulfill({ json: [] });
    if (path.endsWith('/programs/templates/hidden')) return route.fulfill({ json: [] });
    if (path.endsWith('/admin/users')) return route.fulfill({ json: [] });
    if (/\/coach\/clients\/\d+\/analytics$/.test(path))
      return route.fulfill({ json: emptyProgress });
    if (/\/coach\/clients\/\d+\/workouts$/.test(path)) return route.fulfill({ json: [] });
    if (path.endsWith('/coach/assigned-programs'))
      return route.fulfill({
        json: withCoachProgram
          ? [
              {
                id: 701,
                client_id: 2,
                client_telegram_user_id: 3002,
                client_username: 'client',
                client_full_name: 'Тестовый клиент',
                template_id: 10,
                title: 'План клиента на четыре недели',
                goal: 'maintenance',
                level: 'beginner',
                assigned_at: '2030-01-01T10:00:00',
                is_active: true,
                status: 'active',
                start_date: '2030-01-01',
                duration_weeks: 4,
                schedule_weekdays: [0, 2, 4],
                completed_at: null,
                workouts_total: 12,
                workouts_completed: 4,
                workouts_planned: 8,
                next_workout_date: '2030-01-08',
                current_revision_number: 2,
              },
            ]
          : [],
      });
    if (path.endsWith('/programs/assigned/701/revisions')) return route.fulfill({ json: [] });
    if (path.endsWith('/programs/assigned/701/blocks')) return route.fulfill({ json: [] });
    if (path.endsWith('/coach/client-summaries'))
      return route.fulfill({
        json: {
          items: withCoachClient
            ? [
                {
                  user_id: 2,
                  client_name: coachClientName,
                  period_days: 30,
                  period_start: '2026-07-22',
                  period_end: '2026-08-20',
                  training: {
                    planned_workouts: 8,
                    completed_workouts: 6,
                    frequency_per_week: 1.5,
                    volume_kg: 12000,
                    new_personal_records: 1,
                    last_completed_workout_on: '2026-08-18',
                    next_workout: null,
                  },
                  nutrition: {
                    visible: true,
                    logged_days: 12,
                    adherence_evaluated_days: 10,
                    average_calories: 2000,
                    target_calories: 2100,
                    average_protein_g: 130,
                    target_protein_g: 140,
                    target_effective_on: '2026-07-01',
                  },
                  body: {
                    latest_measurement: { measured_on: '2026-08-17', weight_kg: 75 },
                    trends: [],
                    priority: null,
                    guidance: {},
                  },
                  adherence: {
                    formula_version: 'adherence-v1',
                    overall_percent: 75,
                    included_components: ['workouts'],
                    workouts: {
                      status: 'available',
                      percent: 75,
                      achieved: 6,
                      evaluated: 8,
                      weight: 1,
                    },
                    cardio: { status: 'not_applicable', achieved: 0, evaluated: 0, weight: 0 },
                    calories: { status: 'not_applicable', achieved: 0, evaluated: 0, weight: 0 },
                    protein: { status: 'not_applicable', achieved: 0, evaluated: 0, weight: 0 },
                  },
                  data_sufficiency: {},
                },
              ]
            : [],
          total: withCoachClient ? 1 : 0,
          limit: 100,
          offset: 0,
        },
      });
    if (path.endsWith('/coach/clients'))
      return route.fulfill({
        json: withCoachClient
          ? [
              {
                id: 2,
                invite_id: null,
                telegram_user_id: 3002,
                username: 'client',
                full_name: coachClientName,
                goal: 'maintenance',
                level: 'beginner',
                height_cm: 175,
                weight_kg: 75,
                workouts_per_week: 3,
                cardio_trainings_per_week: 1,
                kbju: null,
                status: 'active',
              },
            ]
          : [],
      });
    if (path.endsWith('/workouts/progress/nutrition-report')) {
      return route.fulfill({ status: 503, json: { detail: 'Отчёт не входит в этот fixture' } });
    }
    return route.fulfill({ json: [] });
  });
}

test('клиент входит и видит экран тренировки', async ({ page }) => {
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'С чего начнём?' })).toBeVisible();
});

test('цветовая система сохраняет иерархию в светлой и тёмной темах', async ({ page }) => {
  await mockApi(page);
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/app');

  const authPanel = page.locator('.login-card');
  await expect(page.getByRole('heading', { name: 'Вернитесь к своему плану.' })).toBeVisible();
  await expect(authPanel).toHaveCSS('background-color', 'rgb(255, 255, 255)');

  const clientButton = page.getByRole('button', { name: 'Клиент' });
  await expect(clientButton).toHaveCSS('border-radius', '14px');
  await expect(clientButton).toHaveCSS('background-color', 'rgb(240, 240, 240)');
  await expect(clientButton).toHaveCSS('color', 'rgb(21, 21, 21)');

  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(authPanel).toHaveCSS('background-color', 'rgb(9, 11, 11)');
  await expect(clientButton).toHaveCSS('background-color', 'rgb(27, 31, 31)');
  await expect(clientButton).toHaveCSS('color', 'rgb(245, 245, 245)');

  await clientButton.click();
  const selectedDestination = page.getByRole('link', { name: 'Сегодня', exact: true });
  const selectedDestinationIcon = selectedDestination.locator('.app-bottom-nav__icon');
  const nutritionDestinationIcon = page
    .getByRole('link', { name: 'Питание', exact: true })
    .locator('.app-bottom-nav__icon');
  await expect(selectedDestination).toHaveAttribute('aria-current', 'page');
  await expect(selectedDestination).toHaveCSS('border-radius', '10px');
  await expect(selectedDestination).toHaveCSS('background-color', 'rgb(27, 31, 31)');
  await expect(selectedDestinationIcon).toBeVisible();
  await expect(nutritionDestinationIcon).toBeVisible();
  await expect(nutritionDestinationIcon.locator('.yfc-icon')).toBeVisible();
  await expect(page.locator('.app-bottom-nav__sequence')).toHaveCount(0);
  await expect(selectedDestinationIcon).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(selectedDestinationIcon).toHaveCSS('color', 'rgb(185, 234, 114)');
  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await expect(selectedDestinationIcon).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  await expect(selectedDestinationIcon).toHaveCSS('color', 'rgb(72, 100, 20)');
});

test('Web theme preference следует системе и сохраняет ручной выбор', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/');
  let toggle = page.getByRole('button', { name: 'Включить тёмную тему' });
  await toggle.focus();
  await expect(toggle).toBeFocused();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');

  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');

  toggle = page.getByRole('button', { name: 'Включить светлую тему' });
  await toggle.click();
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await page.reload();
  await expect(page.getByRole('button', { name: 'Включить тёмную тему' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');

  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
});

test('Mobile Web и Telegram используют одну YFC palette и геометрию', async ({ browser }) => {
  const viewport = { width: 390, height: 844 };
  const webPage = await browser.newPage({ viewport });
  const telegramPage = await browser.newPage({ viewport });
  await telegramPage.addInitScript(() => {
    const themeHandlers = new Set<() => void>();
    const shellColors = {
      background: [] as string[],
      bottomBar: [] as string[],
      header: [] as string[],
    };
    const telegram = {
      initData: 'signed-test-data',
      colorScheme: 'light' as 'light' | 'dark',
      themeParams: { bg_color: '#ffffff', button_color: '#ff00ff', text_color: '#00ffff' },
      ready() {},
      expand() {},
      onEvent(event: string, callback: () => void) {
        if (event === 'themeChanged') themeHandlers.add(callback);
      },
      offEvent(event: string, callback: () => void) {
        if (event === 'themeChanged') themeHandlers.delete(callback);
      },
      setHeaderColor(color: string) {
        shellColors.header.push(color);
      },
      setBackgroundColor(color: string) {
        shellColors.background.push(color);
      },
      setBottomBarColor(color: string) {
        shellColors.bottomBar.push(color);
      },
    };
    Object.assign(window, {
      Telegram: { WebApp: telegram },
      __telegramShellColors: shellColors,
      __setTelegramTheme(colorScheme: 'light' | 'dark') {
        telegram.colorScheme = colorScheme;
        themeHandlers.forEach((callback) => callback());
      },
    });
  });

  await mockApi(webPage);
  await mockApi(telegramPage);
  await webPage.goto('/app');
  await webPage.getByRole('button', { name: 'Клиент' }).click();
  await telegramPage.goto('/app');
  await expect(webPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect(telegramPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await expect(telegramPage.getByRole('button', { name: /Включить .* тему/ })).not.toBeAttached();

  const snapshot = (page: Page) =>
    page.evaluate(() => {
      const rootStyle = getComputedStyle(document.documentElement);
      const surfaceElement = document.querySelector<HTMLElement>('.today-workout-spotlight')!;
      const card = surfaceElement.getBoundingClientRect();
      const container = document.querySelector<HTMLElement>('.container')!.getBoundingClientRect();
      const navigation = document
        .querySelector<HTMLElement>('#appBottomNav')!
        .getBoundingClientRect();
      const destinations = Array.from(
        document.querySelectorAll<HTMLElement>(
          '.app-bottom-nav__primary > a, .app-bottom-nav__primary > button',
        ),
      ).map((destination) => {
        const rect = destination.getBoundingClientRect();
        return { height: rect.height, width: rect.width, x: rect.x, y: rect.y };
      });
      return {
        tokens: ['--bg', '--card', '--text', '--accent', '--border'].map((token) =>
          rootStyle.getPropertyValue(token).trim(),
        ),
        card: {
          width: card.width,
          borderRadius: getComputedStyle(surfaceElement).borderRadius,
        },
        container: { width: container.width, x: container.x },
        navigation: {
          height: navigation.height,
          width: navigation.width,
          x: navigation.x,
          y: navigation.y,
        },
        destinations,
      };
    });

  expect(await snapshot(telegramPage)).toEqual(await snapshot(webPage));
  expect(await telegramPage.evaluate(() => document.documentElement.dataset.themeSource)).toBe(
    'telegram',
  );
  expect(
    await telegramPage.evaluate(() =>
      (
        window as unknown as Window & { __telegramShellColors: { background: string[] } }
      ).__telegramShellColors.background.at(-1),
    ),
  ).toBe('#f4f5f2');

  await webPage.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await webPage.getByRole('dialog').getByRole('button', { name: 'Включить тёмную тему' }).click();
  await webPage.getByRole('button', { name: 'Закрыть меню' }).click();
  await telegramPage.evaluate(() =>
    (
      window as unknown as Window & { __setTelegramTheme(theme: 'light' | 'dark'): void }
    ).__setTelegramTheme('dark'),
  );
  await expect(telegramPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  expect(await snapshot(telegramPage)).toEqual(await snapshot(webPage));
  await expect(telegramPage.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();

  await webPage.close();
  await telegramPage.close();
});

test('primary CTA лендинга и Войти остаются lime в обеих темах', async ({ page }) => {
  await page.goto('/');
  await page.mouse.move(0, 700);
  const primary = page.locator('.landing-hero__actions').getByRole('link', {
    name: 'Начать',
    exact: true,
  });
  const login = page.getByRole('link', { name: 'Войти' });

  await expect(primary).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(primary).toHaveCSS('color', 'rgb(9, 11, 11)');
  await expect(login).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(login).toHaveCSS('color', 'rgb(9, 11, 11)');
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click();
  await expect(primary).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(primary).toHaveCSS('color', 'rgb(9, 11, 11)');
  await expect(login).toHaveCSS('background-color', 'rgb(178, 245, 32)');
  await expect(login).toHaveCSS('color', 'rgb(9, 11, 11)');
});

test('deep link показывает тренера до явного подтверждения', async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => sessionStorage.setItem('fit_access_token', 'test-token'));
  const previewRequest = page.waitForRequest((request) =>
    new URL(request.url()).pathname.endsWith('/me/coach-invites/link/preview'),
  );
  await page.goto('/app?startapp=trainer_test-invite-token-0000');
  await previewRequest;

  await expect(page.getByRole('heading', { name: 'Мой тренер' })).toBeVisible();
  await openCard(page, 'Мой тренер');
  await expect(page.getByRole('heading', { name: 'Тестовый тренер' })).toBeVisible();
  await page.getByRole('button', { name: 'Подтвердить подключение' }).click();
  await expect(page.getByText('Тренер подключён')).toBeVisible();
});

test('desktop app shell centers the brand lockup and navigation surfaces', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(navigation).toBeVisible();
    const desktopAlignment = await navigation.evaluate((element) => {
      const navigationBox = element.getBoundingClientRect();
      const centerOffset = (target: Element | null) => {
        if (!target) return Number.POSITIVE_INFINITY;
        const box = target.getBoundingClientRect();
        return Math.abs(navigationBox.left + navigationBox.width / 2 - (box.left + box.width / 2));
      };
      const groupCenterOffset = (
        targets: Element[],
        referenceBox: Pick<DOMRect, 'left' | 'width'> = navigationBox,
      ) => {
        if (targets.length === 0) return Number.POSITIVE_INFINITY;
        const boxes = targets.map((target) => target.getBoundingClientRect());
        const left = Math.min(...boxes.map((box) => box.left));
        const right = Math.max(...boxes.map((box) => box.right));
        return Math.abs(referenceBox.left + referenceBox.width / 2 - (left + right) / 2);
      };
      const lockup = element.querySelector('.yfc-lockup');
      const groupLabel = element.querySelector<HTMLElement>('.app-bottom-nav__group-label');
      const themeButton = element.querySelector('.app-theme-toggle--nav');
      const logoutButton = element.querySelector('.app-bottom-nav__logout');
      return {
        buttonOffsets: Array.from(
          element.querySelectorAll<HTMLElement>(
            '.app-bottom-nav__primary .app-bottom-nav__btn, .app-bottom-nav__secondary .app-bottom-nav__btn',
          ),
        )
          .filter((button) => button.offsetParent !== null)
          .map(centerOffset),
        coachOffset: centerOffset(element.querySelector('.yfc-lockup__wordmark > span')),
        fitnessOffset: centerOffset(element.querySelector('.yfc-lockup__wordmark > strong')),
        groupLabelFits: groupLabel
          ? groupLabel.scrollWidth <= groupLabel.clientWidth &&
            window.getComputedStyle(groupLabel).whiteSpace === 'nowrap'
          : false,
        labelsFit: Array.from(element.querySelectorAll<HTMLElement>('.app-bottom-nav__label'))
          .filter((label) => label.offsetParent !== null)
          .every((label) => label.scrollWidth <= label.clientWidth),
        lockupDirection: lockup ? window.getComputedStyle(lockup).flexDirection : null,
        markOffset: centerOffset(element.querySelector('.yfc-lockup__mark')),
        navigationWidth: navigationBox.width,
        primaryLabelSize: window.getComputedStyle(
          element.querySelector('.app-bottom-nav__primary .app-bottom-nav__label')!,
        ).fontSize,
        secondaryLabelSize: window.getComputedStyle(
          element.querySelector('.app-bottom-nav__secondary .app-bottom-nav__label')!,
        ).fontSize,
        logoutButtonHeight: logoutButton?.getBoundingClientRect().height ?? 0,
        logoutButtonOffset: centerOffset(logoutButton),
        logoutButtonWidth: logoutButton?.getBoundingClientRect().width ?? 0,
        themeContentOffset: themeButton
          ? groupCenterOffset(
              Array.from(
                themeButton.querySelectorAll('.app-bottom-nav__icon, .app-bottom-nav__label'),
              ),
              themeButton.getBoundingClientRect(),
            )
          : Number.POSITIVE_INFINITY,
        themeBorderStyle: themeButton ? window.getComputedStyle(themeButton).borderTopStyle : null,
        themeBorderWidth: themeButton ? window.getComputedStyle(themeButton).borderTopWidth : null,
        themeButtonHeight: themeButton?.getBoundingClientRect().height ?? 0,
        themeButtonOffset: centerOffset(themeButton),
        themeButtonWidth: themeButton?.getBoundingClientRect().width ?? 0,
        themeLabelSize: window.getComputedStyle(
          element.querySelector('.app-theme-toggle--nav .app-bottom-nav__label')!,
        ).fontSize,
      };
    });
    const contentAlignment = await page.locator('#appContent').evaluate((content) => {
      const navigation = document.querySelector('#appBottomNav');
      if (!navigation) return null;
      const contentBox = content.getBoundingClientRect();
      const navigationBox = navigation.getBoundingClientRect();
      return {
        leftGap: contentBox.left - navigationBox.right,
        rightGap: window.innerWidth - contentBox.right,
      };
    });

    expect(desktopAlignment.lockupDirection).toBe('column');
    expect(desktopAlignment.navigationWidth).toBe(220);
    expect(desktopAlignment.markOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.fitnessOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.coachOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.groupLabelFits).toBe(true);
    expect(desktopAlignment.labelsFit).toBe(true);
    expect(desktopAlignment.primaryLabelSize).toBe('13px');
    expect(desktopAlignment.secondaryLabelSize).toBe('12.8px');
    expect(desktopAlignment.buttonOffsets.length).toBeGreaterThan(0);
    expect(desktopAlignment.buttonOffsets.every((offset) => offset <= 1)).toBe(true);
    expect(desktopAlignment.themeContentOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.themeBorderStyle).toBe('solid');
    expect(desktopAlignment.themeBorderWidth).toBe('1px');
    expect(desktopAlignment.themeButtonOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.themeLabelSize).toBe('12.8px');
    expect(desktopAlignment.logoutButtonOffset).toBeLessThanOrEqual(1);
    expect(desktopAlignment.logoutButtonWidth).toBe(desktopAlignment.themeButtonWidth);
    expect(desktopAlignment.logoutButtonHeight).toBe(desktopAlignment.themeButtonHeight);
    expect(contentAlignment).not.toBeNull();
    expect(Math.abs(contentAlignment!.leftGap - contentAlignment!.rightGap)).toBeLessThanOrEqual(1);

    if (viewport.width === 1440) {
      await navigation.screenshot({
        path: '../.artifacts/screenshots/desktop-navigation/rail-1440-dark.png',
      });
      await navigation.locator('.app-bottom-nav__utility').screenshot({
        path: '../.artifacts/screenshots/desktop-navigation/utility-1440-dark.png',
      });
      await page.screenshot({
        path: '../.artifacts/screenshots/desktop-navigation/app-1440-dark.png',
        fullPage: true,
      });
    }
  }

  await page.getByRole('button', { name: 'Включить светлую тему' }).click();
  await navigation.screenshot({
    path: '../.artifacts/screenshots/desktop-navigation/rail-1280-light.png',
  });
  await navigation.locator('.app-bottom-nav__utility').screenshot({
    path: '../.artifacts/screenshots/desktop-navigation/utility-1280-light.png',
  });

  await page.setViewportSize({ width: 390, height: 780 });
  await expect(page.locator('.app-bottom-nav__brand')).not.toBeVisible();
  await expect(
    page.locator('.app-bottom-nav__primary a:visible, .app-bottom-nav__primary button:visible'),
  ).toHaveCount(4);
});

test('app shell сохраняет композицию и доступность на целевых viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 780 },
    { width: 360, height: 740 },
  ]) {
    await page.setViewportSize(viewport);
    const primaryNavigation = page.locator('.app-bottom-nav__primary');
    const visibleDestinations = primaryNavigation.locator('a:visible, button:visible');
    await expect(visibleDestinations).toHaveCount(4);
    for (const destination of await visibleDestinations.all()) {
      await expect(destination).toBeInViewport();
    }
    if (viewport.width >= 900) {
      await expect(
        page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }),
      ).not.toBeVisible();
      await expect(page.getByRole('link', { name: 'Упражнения', exact: true })).toBeVisible();
      await expect(
        page.getByRole('link', { name: 'Профиль и настройки', exact: true }),
      ).toBeVisible();
      await expect(page.getByRole('link', { name: 'Профиль', exact: true })).not.toBeAttached();
      await expect(page.getByText('Ресурсы', { exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: 'База знаний', exact: true })).not.toBeAttached();
      const accountName = page.locator('.app-desktop-account-entry .account-identity__name');
      const logout = page
        .getByRole('navigation', { name: 'Основная навигация' })
        .getByRole('button', {
          name: 'Выйти из аккаунта',
        });
      await expect(accountName).toHaveText('Демо пользователь');
      const accountNameSize = await accountName.evaluate((element) => ({
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        textOverflow: window.getComputedStyle(element).textOverflow,
      }));
      expect(accountNameSize.clientWidth).toBeGreaterThan(0);
      expect(accountNameSize.scrollWidth).toBeGreaterThanOrEqual(accountNameSize.clientWidth);
      expect(accountNameSize.textOverflow).toBe('ellipsis');
      await expect(logout).toHaveText('Выйти');
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    if (viewport.width === 1280 || viewport.width === 360) {
      await page.screenshot({
        path: `../.artifacts/screenshots/task-121/web-app-shell-${viewport.width}x${viewport.height}.png`,
        fullPage: true,
      });
    }
  }

  await page.setViewportSize({ width: 390, height: 780 });
  await openAppDestination(page, 'Прогресс');
  await expect(page).toHaveURL('/app?section=progress');
  await openAppDestination(page, 'Питание');
  await expect(page).toHaveURL('/app?section=nutrition');
  await page.goBack();
  await expect(page).toHaveURL('/app?section=progress');
  await expect(page.getByRole('link', { name: 'Прогресс', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.goForward();
  await expect(page).toHaveURL('/app?section=nutrition');

  await openAppDestination(page, 'Сегодня');
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();

  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeInViewport();
  const moreButton = page.getByRole('button', {
    name: 'Открыть профиль и настройки',
    exact: true,
  });
  await moreButton.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeAttached();
  await expect(moreButton).toBeFocused();

  await moreButton.click();
  await page.getByRole('dialog').getByRole('button', { name: 'Выйти из аккаунта' }).click();
  await expect(page.getByRole('heading', { name: 'Войти и продолжить' })).toBeVisible();
});

test('desktop sidebar keeps long client names contained and logout reachable', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page, { fullName: 'Александра Константинопольская-Северная' });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  const accountName = page.locator('.app-desktop-account-entry .account-identity__name');
  const logout = navigation.getByRole('button', { name: 'Выйти из аккаунта' });

  await expect(accountName).toHaveText('Александра Константинопольская-Северная');
  await expect(accountName).toHaveCSS('text-overflow', 'ellipsis');
  expect(await accountName.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
    true,
  );
  await expect(logout).toBeInViewport();
  await logout.focus();
  await expect(logout).toBeFocused();
  expect(await navigation.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
    true,
  );
});

test('desktop sidebar keeps the longest capability label visible at the larger type scale', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockApi(page);
  await page.goto('/admin');
  await page.getByRole('button', { name: 'Админ' }).click();

  const adminLink = page.getByRole('link', { name: 'Админ-панель' });
  const adminLabel = adminLink.locator('.app-bottom-nav__label');
  await expect(adminLink).toBeVisible();
  await expect(adminLabel).toHaveCSS('font-size', '12.8px');
  const adminLabelWidth = await adminLabel.evaluate((label) => ({
    clientWidth: label.clientWidth,
    scrollWidth: label.scrollWidth,
  }));
  expect(adminLabelWidth.scrollWidth).toBeLessThanOrEqual(adminLabelWidth.clientWidth);
});

test('desktop sidebar keeps trainer workspaces reachable at a short viewport', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 560 });
  await mockApi(page);
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();

  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(navigation).toHaveCSS('overflow-y', 'auto');
  await expect(
    page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }),
  ).not.toBeVisible();
  await expect(page.getByRole('link', { name: 'Тренер', exact: true })).toBeVisible();
  expect(await navigation.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(
    true,
  );

  const utility = navigation.locator('.app-bottom-nav__utility');
  await utility.scrollIntoViewIfNeeded();
  await expect(utility).toBeInViewport();
  await expect(navigation.getByRole('button', { name: /Включить .* тему/ })).toBeVisible();
  expect(
    await navigation
      .locator('.app-bottom-nav__group-label')
      .evaluateAll((labels) => labels.every((label) => label.scrollWidth <= label.clientWidth)),
  ).toBe(true);
});

test('профиль содержит уведомления, а карточка упражнения открывает полное описание', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 780 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  let guideRequests = 0;
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith('/programs/exercises/1')) {
      guideRequests += 1;
    }
  });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  await openAppDestination(page, 'Профиль');
  await page.getByRole('link', { name: 'Уведомления' }).click();
  await expect(page.getByRole('heading', { name: 'Каналы' })).toBeVisible();
  await expect(page.getByText('Личное напоминание', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Подписка' })).toHaveCount(0);

  await page.getByRole('link', { name: 'Личные данные' }).click();
  const birthDate = page.getByLabel('Дата рождения');
  const birthDateControl = page.locator('.profile-birth-date-control');
  const [birthDateBox, birthDateControlBox] = await Promise.all([
    birthDate.boundingBox(),
    birthDateControl.boundingBox(),
  ]);
  expect(birthDateBox).not.toBeNull();
  expect(birthDateControlBox).not.toBeNull();
  expect(birthDateBox!.x).toBeGreaterThanOrEqual(birthDateControlBox!.x);
  expect(birthDateBox!.x + birthDateBox!.width).toBeLessThanOrEqual(
    birthDateControlBox!.x + birthDateControlBox!.width,
  );

  const reminderTime = page.getByLabel('Час для напоминаний без точного времени');
  const reminderTimeControl = page.locator('.reminder-time-control');
  const [reminderTimeBox, reminderTimeControlBox] = await Promise.all([
    reminderTime.boundingBox(),
    reminderTimeControl.boundingBox(),
  ]);
  expect(reminderTimeBox).not.toBeNull();
  expect(reminderTimeControlBox).not.toBeNull();
  expect(reminderTimeBox!.x).toBeGreaterThanOrEqual(reminderTimeControlBox!.x);
  expect(reminderTimeBox!.x + reminderTimeBox!.width).toBeLessThanOrEqual(
    reminderTimeControlBox!.x + reminderTimeControlBox!.width,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);

  await page.getByText('Личное напоминание', { exact: true }).click();
  const notificationDate = page.locator('.notification-date-control input');
  await expect(notificationDate).toHaveAttribute('type', 'date');
  await expect(notificationDate).toHaveCSS('text-align', 'center');
  await expect(page.locator('input[type="datetime-local"]')).toHaveCount(0);
  const [notificationDateBox, notificationDateControlBox] = await Promise.all([
    notificationDate.boundingBox(),
    page.locator('.notification-date-control').boundingBox(),
  ]);
  expect(notificationDateBox).not.toBeNull();
  expect(notificationDateControlBox).not.toBeNull();
  expect(notificationDateBox!.x).toBeGreaterThanOrEqual(notificationDateControlBox!.x);
  expect(notificationDateBox!.x + notificationDateBox!.width).toBeLessThanOrEqual(
    notificationDateControlBox!.x + notificationDateControlBox!.width,
  );

  const notificationRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname.endsWith('/notifications') && request.method() === 'POST',
  );
  await page.getByRole('button', { name: 'Создать напоминание' }).click();
  const notificationPayload = (await notificationRequest).postDataJSON() as {
    scheduled_for: string;
  };
  expect(notificationPayload.scheduled_for).toMatch(/^\d{4}-\d{2}-\d{2}T09:00:00$/);

  await openAppDestination(page, 'Питание');
  await expect(page.getByRole('heading', { name: 'Каналы' })).toHaveCount(0);

  await openAppDestination(page, 'Упражнения');
  await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();
  expect(guideRequests).toBe(0);
  await page.getByRole('button', { name: 'Техника и детали' }).click();
  expect(guideRequests).toBe(1);
  await expect(page.getByRole('heading', { name: 'Основные мышцы' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Дополнительные мышцы' })).toBeVisible();
  await expect(page.getByText('Тянет плечевой пояс назад.')).toBeVisible();
  const [guidePanelBox, guideHeadBox] = await Promise.all([
    page.locator('.exercise-guide-modal__panel').boundingBox(),
    page.locator('.exercise-guide-modal__head').boundingBox(),
  ]);
  expect(guidePanelBox).not.toBeNull();
  expect(guideHeadBox).not.toBeNull();
  expect(Math.abs(guideHeadBox!.x - guidePanelBox!.x)).toBeLessThanOrEqual(2);
  expect(
    Math.abs(guideHeadBox!.x + guideHeadBox!.width - (guidePanelBox!.x + guidePanelBox!.width)),
  ).toBeLessThanOrEqual(2);
  const phaseImage = page.getByAltText('Фаза усилия');
  await expect(phaseImage).toHaveAttribute('loading', 'lazy');
  await expect(phaseImage).toHaveAttribute('width', '400');
  expect(
    await phaseImage.evaluate((image) =>
      Number.parseFloat(getComputedStyle(image).transitionDuration),
    ),
  ).toBeLessThanOrEqual(0.001);
  await page.getByRole('button', { name: 'Увеличить: Фаза усилия' }).click();
  await expect(page.locator('.exercise-lightbox')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.exercise-lightbox')).toHaveCount(0);
});

test('notification settings explain unavailable Telegram and stale targets recover in place', async ({
  page,
}) => {
  const notificationItems = [
    {
      id: 64,
      category: 'trainer_comment',
      event_kind: 'transactional',
      title: 'Комментарий тренера к тренировке',
      body: 'Сохраняйте контролируемый темп в эксцентрической фазе и не ускоряйте последний повтор очень длинного рабочего подхода.',
      created_at: '2030-01-10T10:15:00',
      scheduled_for: '2030-01-10T10:15:00',
      delivery_status: 'cancelled',
      sent_at: null,
      read_at: null,
      action_url: '/app?workout_id=999&comment_id=991',
    },
  ];
  await mockApi(page, {
    notificationItems,
    telegramLinked: false,
    staleNotificationIds: [64],
  });
  await page.goto('/app?section=profile#profile-notifications');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');
  await page.getByRole('link', { name: 'Уведомления' }).click();
  const templatesDisclosure = page.locator('details.notification-templates');
  await expect(templatesDisclosure).not.toHaveAttribute('open');
  await templatesDisclosure.locator(':scope > summary').click();
  await expect(templatesDisclosure).toHaveAttribute('open');
  const reminderTemplates = page.locator('.notification-template-card');
  await expect(reminderTemplates).toHaveCount(3);
  const mealTemplate = reminderTemplates.filter({ hasText: 'Записать приём пищи' });
  await expect(
    mealTemplate.getByRole('button', { name: 'Сохранить шаблон «Записать приём пищи»' }),
  ).toBeDisabled();
  await mealTemplate.getByRole('checkbox', { name: 'Включить: Записать приём пищи' }).check();
  await expect(mealTemplate.getByText('Окно 1')).toBeVisible();
  await expect(
    mealTemplate.getByRole('button', { name: 'Сохранить шаблон «Записать приём пищи»' }),
  ).toBeEnabled();
  for (const visualState of [
    { scheme: 'light' as const, width: 1280, height: 900, name: 'desktop-light' },
    { scheme: 'dark' as const, width: 1280, height: 900, name: 'desktop-dark' },
    { scheme: 'light' as const, width: 390, height: 844, name: 'mobile-light' },
    { scheme: 'dark' as const, width: 390, height: 844, name: 'mobile-dark' },
  ]) {
    await page.emulateMedia({ colorScheme: visualState.scheme, reducedMotion: 'reduce' });
    await page.setViewportSize({ width: visualState.width, height: visualState.height });
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', visualState.scheme);
    const sectionBox = await page.locator('#profile-notifications').boundingBox();
    expect(sectionBox).not.toBeNull();
    expect(sectionBox!.width).toBeLessThanOrEqual(visualState.width);
    await page.locator('#profile-notifications').screenshot({
      path: `../.artifacts/tasks/84/evidence/visual/${visualState.name}.png`,
    });
  }
  const notificationCenter = page.locator('details.notification-center');
  await notificationCenter.locator(':scope > summary').click();
  await expect(notificationCenter).toHaveAttribute('open');

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
    { width: 1280, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await expect(
      page.getByText('Недоступно: сначала свяжите Telegram в разделе доступа'),
    ).toBeVisible();
    await expect(page.getByLabel('Telegram')).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }

  const unread = page.locator('.notification-row--unread');
  const unreadColors = await unread.evaluate((element) => {
    const styles = getComputedStyle(element);
    const boundarySample = document.createElement('span');
    boundarySample.style.color = 'var(--v2-lime)';
    const surfaceSample = document.createElement('span');
    surfaceSample.style.backgroundColor = 'var(--v2-surface-secondary)';
    document.body.append(boundarySample, surfaceSample);
    const expectedBoundary = getComputedStyle(boundarySample).color;
    const expectedSurface = getComputedStyle(surfaceSample).backgroundColor;
    boundarySample.remove();
    surfaceSample.remove();
    return {
      boundary: styles.borderInlineStartColor,
      expected: expectedBoundary,
      surface: styles.backgroundColor,
      expectedSurface,
    };
  });
  expect(unreadColors.boundary).toBe(unreadColors.expected);
  expect(unreadColors.surface).toBe(unreadColors.expectedSurface);

  await page.getByRole('button', { name: 'Открыть: Комментарий тренера к тренировке' }).click();
  await expect(page).toHaveURL('/app?section=profile#profile-notifications');
  await expect(page.getByText(/Связанный объект больше недоступен/)).toBeVisible();
});

test('notification nutrition deep links open the intended quick entry context', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.addInitScript(() => sessionStorage.setItem('fit_access_token', 'test-token'));
  await page.goto('/app?section=nutrition&date=2030-01-10&meal=lunch');
  await expect(page.getByRole('dialog', { name: 'Быстрый ввод' })).toBeVisible();
  await expect(
    page.getByText('Обед · 2030-01-10. Название и время можно не указывать.'),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Закрыть добавление' }).click();

  await page.goto('/app?section=nutrition&date=2030-01-10&hydration=quick');
  await expect(page.getByRole('button', { name: 'Скрыть детали' })).toBeVisible();
});

test('notification empty and error states keep compact profile rhythm', async ({ page }) => {
  await mockApi(page, { notificationItems: [] });
  await page.route('**/api/v1/notifications/settings', (route) =>
    route.fulfill({ status: 503, json: { detail: 'Настройки временно недоступны' } }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');
  await page.getByRole('link', { name: 'Уведомления' }).click();
  await expect(page.getByText('Настройки временно недоступны')).toBeVisible();
  const notificationCenter = page.locator('details.notification-center');
  await expect(
    notificationCenter.locator('summary').getByText('Уведомлений пока нет'),
  ).toBeVisible();
  await notificationCenter.locator(':scope > summary').click();
  await expect(notificationCenter.locator('.ui-state__title')).toHaveText('Уведомлений пока нет');

  const stateHeights = await page
    .locator('#profile-notifications .ui-state')
    .evaluateAll((states) => states.map((state) => state.getBoundingClientRect().height));
  expect(stateHeights).toHaveLength(2);
  expect(Math.max(...stateHeights)).toBeLessThanOrEqual(150);

  const sectionRhythm = await page.evaluate(() => {
    const notificationSection = document.querySelector<HTMLElement>('#profile-notifications');
    const securitySection = document.querySelector<HTMLElement>('#profile-security');
    return [notificationSection, securitySection].map((section) => {
      const styles = getComputedStyle(section!);
      return {
        gap: Number.parseFloat(styles.rowGap),
        paddingTop: Number.parseFloat(styles.paddingTop),
      };
    });
  });
  for (const rhythm of sectionRhythm) {
    expect(rhythm.gap).toBeLessThanOrEqual(12);
    expect(rhythm.paddingTop).toBeLessThanOrEqual(18);
  }
});

test('описание упражнения использует широкую панель в веб-версии', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Упражнения');
  await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Техника и детали' }).click();

  const guidePanel = page.locator('.exercise-guide-modal__panel');
  const guidePanelBox = await guidePanel.boundingBox();
  expect(guidePanelBox).not.toBeNull();
  expect(guidePanelBox!.width).toBeGreaterThan(800);
  await expect(guidePanel).toHaveCSS('overflow-x', 'hidden');
  const noteColumns = await guidePanel
    .locator('.exercise-guide-notes')
    .evaluate((notes) => getComputedStyle(notes).gridTemplateColumns.split(' '));
  expect(noteColumns).toHaveLength(2);
});

test('профиль сохраняет иерархию Design V2 в light/dark и на целевых ширинах', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
      browserErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');

  const cases = [
    { width: 1440, height: 900, theme: 'light' },
    { width: 768, height: 900, theme: 'dark' },
    { width: 430, height: 932, theme: 'dark' },
    { width: 390, height: 844, theme: 'light' },
    { width: 360, height: 800, theme: 'dark' },
  ] as const;

  for (const current of cases) {
    await page.setViewportSize({ width: current.width, height: current.height });
    await page.evaluate((theme) => localStorage.setItem('app-theme', theme), current.theme);
    await page.reload();

    await expect(page.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
    await expect(page.getByText('Профиль стоит дополнить')).toBeVisible();
    await expect(page.getByText('1 из 3')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Разделы профиля' })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Личные данные и фитнес-профиль' }),
    ).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', current.theme);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);

    if (current.width <= 390) {
      const navTargets = await page
        .getByRole('navigation', { name: 'Разделы профиля' })
        .getByRole('link')
        .evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height));
      expect(navTargets.every((height) => height >= 44)).toBe(true);
    }
    await page.screenshot({
      path: `../.artifacts/screenshots/task-113A/profile-${current.width}x${current.height}-${current.theme}.png`,
    });
  }

  await page.getByRole('link', { name: 'Личные данные' }).click();
  await page.getByLabel('Имя').fill('Черновик профиля');
  const saveProfile = page.getByRole('button', { name: 'Сохранить изменения' });
  await expect(saveProfile).toBeDisabled();
  await page.getByLabel('Уровень подготовки').selectOption('beginner');
  await expect(saveProfile).toBeEnabled();
  await page.getByLabel('Силовых тренировок в неделю').fill('15');
  await expect(page.getByText('Укажите целое число от 0 до 14.')).toBeVisible();
  await expect(saveProfile).toBeDisabled();
  await page.getByLabel('Силовых тренировок в неделю').fill('3');
  await expect(saveProfile).toBeEnabled();
  await expect(page.getByLabel('Имя')).toHaveValue('Черновик профиля');

  await page.getByRole('link', { name: 'Доступ и безопасность' }).click();
  await expect(page.getByRole('heading', { name: 'Доступ и безопасность' })).toBeInViewport();
  const [securityHeading, dangerZone] = await Promise.all([
    page.getByRole('heading', { name: 'Доступ и безопасность' }).boundingBox(),
    page.locator('.profile-danger-zone').boundingBox(),
  ]);
  expect(securityHeading).not.toBeNull();
  expect(dangerZone).not.toBeNull();
  expect(dangerZone!.y).toBeGreaterThan(securityHeading!.y);
  expect(browserErrors).toEqual([]);
});

test('профиль не показывает completion prompt после заполнения 3 из 3', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { completeProfile: true });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');

  await expect(page.getByText('Настройки программы заполнены')).toHaveCount(0);
  await expect(page.getByText('3 из 3')).toHaveCount(0);
  await expect(page.locator('.profile-status-shell')).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: 'Разделы профиля' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Личные данные и фитнес-профиль' })).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-113A/profile-complete-390x844-light.png',
  });
});

test('training preferences сохраняют Mobile Web/TMA композицию и скриншоты всех версий', async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const cases = [
    { surface: 'mobile-web', width: 360, height: 800, theme: 'light' },
    { surface: 'mobile-web', width: 390, height: 844, theme: 'dark' },
    { surface: 'mobile-web', width: 430, height: 932, theme: 'light' },
    { surface: 'mobile-web', width: 768, height: 900, theme: 'dark' },
    { surface: 'desktop-web', width: 1440, height: 900, theme: 'light' },
    { surface: 'tma-mock', width: 360, height: 800, theme: 'dark' },
    { surface: 'tma-mock', width: 390, height: 844, theme: 'light' },
    { surface: 'tma-mock', width: 430, height: 932, theme: 'dark' },
  ] as const;

  for (const current of cases) {
    const page = await browser.newPage({
      viewport: { width: current.width, height: current.height },
      hasTouch: current.width <= 768,
    });
    if (current.surface === 'tma-mock') {
      await page.addInitScript(
        ({ theme }) => {
          const handlers = new Map<string, Set<() => void>>();
          const telegram = {
            initData: 'signed-task-54-data',
            colorScheme: theme,
            themeParams: {},
            viewportHeight: window.innerHeight,
            viewportStableHeight: window.innerHeight,
            isActive: true,
            safeAreaInset: { top: 0, right: 0, bottom: 16, left: 0 },
            contentSafeAreaInset: { top: 0, right: 0, bottom: 16, left: 0 },
            ready() {},
            expand() {},
            setHeaderColor() {},
            setBackgroundColor() {},
            setBottomBarColor() {},
            onEvent(event: string, callback: () => void) {
              const callbacks = handlers.get(event) ?? new Set();
              callbacks.add(callback);
              handlers.set(event, callbacks);
            },
            offEvent(event: string, callback: () => void) {
              handlers.get(event)?.delete(callback);
            },
            emit(event: string) {
              handlers.get(event)?.forEach((callback) => callback());
            },
            BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
          };
          Object.assign(window, { Telegram: { WebApp: telegram } });
        },
        { theme: current.theme },
      );
    } else {
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), current.theme);
    }
    await mockApi(page, { completeProfile: true, withTrainingPreferences: true });
    await page.goto('/app');
    if (current.surface !== 'tma-mock') {
      await page.getByRole('button', { name: 'Клиент' }).click();
    }
    await openAppDestination(page, 'Профиль');
    const card = page.locator('.training-preferences-card');
    await expect(card).toBeVisible();
    await card.locator(':scope > summary').click();
    await expect(card.getByText('Текущую программу нужно проверить')).toBeVisible();
    await card.getByText('Упражнения и движения, которых хотите избегать').click();
    await expect(card.getByText(/Это не медицинская оценка/)).toBeVisible();
    if (current.surface === 'tma-mock') {
      await card.getByText('Расписание', { exact: true }).click();
      const durationMax = card.getByLabel('До, минут');
      await durationMax.fill('75');
      await durationMax.blur();
      const otherTheme = current.theme === 'light' ? 'dark' : 'light';
      await page.evaluate((theme) => {
        const webApp = (
          window as unknown as {
            Telegram: {
              WebApp: { colorScheme: string; emit: (event: string) => void };
            };
          }
        ).Telegram.WebApp;
        webApp.colorScheme = theme;
        webApp.emit('themeChanged');
      }, otherTheme);
      await page.setViewportSize({ width: current.width, height: current.height - 40 });
      await page.evaluate((height) => {
        const webApp = (
          window as unknown as {
            Telegram: {
              WebApp: {
                viewportHeight: number;
                viewportStableHeight: number;
                emit: (event: string) => void;
              };
            };
          }
        ).Telegram.WebApp;
        webApp.viewportHeight = height;
        webApp.viewportStableHeight = height;
        webApp.emit('viewportChanged');
      }, current.height - 40);
      await page.setViewportSize({ width: current.width, height: current.height });
      await page.evaluate(({ height, theme }) => {
        const webApp = (
          window as unknown as {
            Telegram: {
              WebApp: {
                colorScheme: string;
                viewportHeight: number;
                viewportStableHeight: number;
                emit: (event: string) => void;
              };
            };
          }
        ).Telegram.WebApp;
        webApp.colorScheme = theme;
        webApp.viewportHeight = height;
        webApp.viewportStableHeight = height;
        webApp.emit('themeChanged');
        webApp.emit('viewportChanged');
      }, current);
      await expect(durationMax).toHaveValue('75');
    }
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', current.theme);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(current.width);
    const targets = await card
      .locator('summary, button, input:not([type="checkbox"]), select, textarea, a')
      .evaluateAll((items) =>
        items
          .filter((item) => {
            const style = getComputedStyle(item);
            return style.display !== 'none' && style.visibility !== 'hidden';
          })
          .map((item) => ({
            target: `${item.tagName.toLowerCase()}.${item.className}`,
            label: item.getAttribute('aria-label') ?? item.textContent?.trim().slice(0, 60) ?? '',
            height: item.getBoundingClientRect().height,
          })),
      );
    expect(
      targets.filter(({ height }) => height > 0 && height < 40),
      'Все интерактивные цели должны иметь высоту не меньше 40px',
    ).toEqual([]);
    await card.getByText('Упражнения и движения, которых хотите избегать').click();
    await card.getByText('Текущую программу нужно проверить').scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `../.artifacts/task-54-training-preferences/${current.surface}-${current.width}x${current.height}-${current.theme}.png`,
    });
    await openAppDestination(page, 'План');
    const planManagementLink = page.getByRole('link', {
      name: 'Управление программой',
      exact: true,
    });
    await expect(planManagementLink).toBeVisible();
    await planManagementLink.click();
    await expect(page).toHaveURL('/app?section=programs&view=manage');
    await page.getByRole('button', { name: 'Подобрать другую' }).click();
    const wizard = page.getByRole('dialog', { name: 'Цель' });
    await expect(wizard).toBeVisible();
    await expect(wizard.getByText(/подставили достоверные ответы из профиля/i)).toBeVisible();
    expect(
      await wizard
        .locator('.program-wizard__panel')
        .evaluate((element) => element.scrollWidth <= element.clientWidth),
    ).toBe(true);
    await page.close();
  }
});

test('пользователь напрямую включает режим тренера из профиля', async ({ browser }) => {
  const page = await browser.newPage({
    colorScheme: 'light',
    hasTouch: true,
    reducedMotion: 'reduce',
    viewport: { width: 360, height: 1050 },
  });
  expect(await page.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');
  await openCard(page, 'Тренер и приглашения');

  const activate = page.getByRole('button', { name: 'Включить режим тренера' });
  const trainerCard = page
    .getByRole('heading', { name: 'Режим тренера', exact: true })
    .locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " card ")][1]');
  await expect(activate).toBeDisabled();
  await trainerCard.screenshot({
    path: '../.artifacts/screenshots/task-70/01-pre-activation-mobile-light.png',
  });
  const terms = page.getByRole('checkbox', { name: /принимаю условия/i });
  await terms.focus();
  await expect(terms).toBeFocused();
  await page.keyboard.press('Space');
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(terms).toBeChecked();
  await activate.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  await page.screenshot({
    path: '../.artifacts/screenshots/task-70/01b-terms-and-activation-cta-mobile-light.png',
  });
  await activate.click();

  await expect(trainerCard.getByText('Режим тренера включён')).toBeVisible();
  const repeatedActivation = await page.evaluate(async () => {
    const response = await fetch('/api/v1/me/trainer-capability', {
      body: JSON.stringify({ accepted_terms: true }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    return response.json() as Promise<{ activated_now: boolean; is_active: boolean }>;
  });
  expect(repeatedActivation).toMatchObject({ activated_now: false, is_active: true });
  const modeSwitch = page.getByRole('navigation', { name: 'Режим работы' });
  await expect(modeSwitch.getByRole('link', { name: 'Для себя' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  await trainerCard.screenshot({
    path: '../.artifacts/screenshots/task-70/02-post-activation-desktop-light.png',
  });
  await page.addInitScript(() => {
    const themeHandlers = new Set<() => void>();
    const telegram = {
      initData: 'mocked-task-70-init-data',
      colorScheme: 'dark' as const,
      themeParams: { bg_color: '#101310', text_color: '#f4f7ee' },
      ready() {},
      expand() {},
      onEvent(event: string, callback: () => void) {
        if (event === 'themeChanged') themeHandlers.add(callback);
      },
      offEvent(event: string, callback: () => void) {
        if (event === 'themeChanged') themeHandlers.delete(callback);
      },
    };
    Object.defineProperty(window, 'Telegram', {
      configurable: true,
      value: { WebApp: telegram },
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await openCard(page, 'Тренер и приглашения');
  await modeSwitch.getByRole('link', { name: 'Клиенты' }).click();
  await expect(page.getByRole('heading', { name: 'Кабинет тренера' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Клиенты', exact: true }).first()).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByRole('heading', { name: 'Добавьте первого клиента' })).toBeVisible();
  const modeCopyPadding = await page
    .locator('.trainer-mode-context__copy')
    .evaluate((element) => Number.parseFloat(getComputedStyle(element).paddingLeft));
  expect(modeCopyPadding).toBeGreaterThanOrEqual(8);
  const emptyClients = page.locator('.coach-client-roster > .empty-state');
  await expect(emptyClients.getByText('Клиентов пока нет')).toBeVisible();
  const emptyStateGap = await emptyClients.evaluate((element) => {
    const tools = element.parentElement?.querySelector<HTMLElement>('.coach-client-tools');
    return tools ? element.getBoundingClientRect().top - tools.getBoundingClientRect().bottom : 0;
  });
  expect(emptyStateGap).toBeGreaterThanOrEqual(12);
  await page.setViewportSize({ width: 390, height: 1050 });
  await page.locator('.coach-zero-state').screenshot({
    path: '../.artifacts/screenshots/task-70/03-first-client-onboarding-dark-tma-390.png',
  });
  await page.locator('.coach-client-roster').screenshot({
    path: '../.artifacts/screenshots/task-70/06-empty-clients-spacing-dark-tma-390.png',
  });

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 768, height: 900 },
    { width: 1280, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      viewport.width,
    );
    const switchTargets = await page
      .getByRole('navigation', { name: 'Режим работы' })
      .getByRole('link')
      .evaluateAll((links) => links.map((link) => link.getBoundingClientRect().height));
    expect(switchTargets.every((height) => height >= 44)).toBe(true);
  }
  await page.close();
});

test('активные клиенты блокируют отключение режима тренера', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  const longClientName = 'Александра Константинопольская-Северная с длинным именем';
  await mockApi(page, { coachClientName: longClientName, withCoachClient: true });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await page.getByRole('button', { name: 'Открыть профиль и настройки', exact: true }).click();
  await page
    .locator('#appMorePanel')
    .getByRole('link', { name: 'Кабинет тренера', exact: true })
    .click();
  await page.getByText(longClientName, { exact: true }).first().click();
  const clientContext = page.locator('.trainer-mode-context__copy small');
  await expect(clientContext).toContainText(longClientName);
  await expect(clientContext).toHaveCSS('text-overflow', 'ellipsis');
  expect(await clientContext.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(
    true,
  );
  await clientContext.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-70/04-long-client-context-dark-360.png',
  });
  await page
    .getByRole('navigation', { name: 'Режим работы' })
    .getByRole('link', { name: 'Для себя' })
    .click();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  await openAppDestination(page, 'Профиль');
  await openCard(page, 'Тренер и приглашения');
  await openCard(page, 'Режим тренера');
  await page.setViewportSize({ width: 360, height: 1050 });

  await expect(page.getByText(/всеми активными клиентами \(1\)/i)).toBeVisible();
  const disableButton = page.getByRole('button', { name: 'Выключить режим тренера' });
  await expect(disableButton).toBeDisabled();
  await page
    .getByRole('heading', { name: 'Режим тренера', exact: true })
    .locator('xpath=ancestor::details[1]')
    .screenshot({
      path: '../.artifacts/screenshots/task-70/05-active-client-disable-guard-dark-360.png',
    });
  await disableButton.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  await page.screenshot({
    path: '../.artifacts/screenshots/task-70/05b-active-client-disabled-action-dark-360.png',
  });
  await page.setViewportSize({ width: 360, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
});

test('рекомендация кардио меняется с целью, а физиологические зоны остаются прежними', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'Профиль');
  await page.getByRole('link', { name: 'Личные данные' }).click();
  await page.getByText('Пульс и кардио-ориентиры').click();

  await page.getByLabel('Дата рождения').fill('1992-08-12');
  await page.getByText('Средний пульс в покое, уд/мин').locator('..').locator('input').fill('75');
  await page.getByLabel('Цель').selectOption('fat_loss');
  await expect(page.getByText('130–140 уд/мин')).toHaveCount(2);

  const zones = page.getByText('Пульсовые зоны').locator('..').locator('+ .list-grid');
  const initialZones = await zones.textContent();

  await page.getByLabel('Цель').selectOption('recomposition');
  await expect(page.getByText('124–140 уд/мин')).toBeVisible();
  await page.getByLabel('Цель').selectOption('maintenance');
  await expect(page.getByText('119–140 уд/мин')).toBeVisible();
  await page.getByLabel('Цель').selectOption('muscle_gain');
  await expect(page.getByText('119–130 уд/мин')).toBeVisible();

  await expect(zones).toHaveText(initialZones ?? '');
  await expect(page.getByText('184 уд/мин', { exact: true })).toBeVisible();
  await expect(page.locator('body')).not.toContainText('HRR');
  await expect(page.locator('body')).not.toContainText('MET');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('поля профиля и питания выровнены на десктопе и остаются адаптивными', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  await openAppDestination(page, 'Профиль');
  await page.getByRole('link', { name: 'Личные данные' }).click();
  const profileControlTops = await page.locator('.profile-form-grid--fitness').evaluate((grid) =>
    Array.from(grid.querySelectorAll<HTMLElement>(':scope > .field'))
      .slice(0, 3)
      .map((field) => {
        const control = field.querySelector<HTMLElement>('input, select, .date-control');
        return control?.getBoundingClientRect().top ?? 0;
      }),
  );
  expect(new Set(profileControlTops.map(Math.round)).size).toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileProfileFields = await page.locator('.profile-form-grid--fitness').evaluate((grid) =>
    Array.from(grid.querySelectorAll<HTMLElement>(':scope > .field')).map((field) => {
      const box = field.getBoundingClientRect();
      return { left: box.left, right: box.right, top: box.top };
    }),
  );
  expect(mobileProfileFields.every((field) => field.left >= 0 && field.right <= 390)).toBe(true);
  expect(
    mobileProfileFields.every(
      (field, index) => index === 0 || field.top > mobileProfileFields[index - 1]!.top,
    ),
  ).toBe(true);

  await page.setViewportSize({ width: 1440, height: 900 });
  await openAppDestination(page, 'Питание');
  await openCard(page, 'КБЖУ');
  const nutritionControlTops = await page
    .locator('.nutrition-form-grid')
    .first()
    .evaluate((grid) =>
      Array.from(grid.querySelectorAll<HTMLElement>(':scope > .field'))
        .slice(5, 8)
        .map((field) => {
          const control = field.querySelector<HTMLElement>('input, select');
          return control?.getBoundingClientRect().top ?? 0;
        }),
    );
  expect(new Set(nutritionControlTops.map(Math.round)).size).toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileFields = await page
    .locator('.nutrition-form-grid')
    .first()
    .evaluate((grid) =>
      Array.from(grid.querySelectorAll<HTMLElement>(':scope > .field')).map((field) => {
        const box = field.getBoundingClientRect();
        return { left: box.left, right: box.right, top: box.top };
      }),
    );
  expect(mobileFields.every((field) => field.left >= 0 && field.right <= 390)).toBe(true);
  expect(
    mobileFields.every((field, index) => index === 0 || field.top > mobileFields[index - 1]!.top),
  ).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('поля адаптируются к разным iPhone, а пример программы открывает состав', async ({ page }) => {
  await page.setViewportSize({ width: 440, height: 956 });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();

  await openAppDestination(page, 'Прогресс');
  const measurementForm = page.locator('.measurement-diary__form');
  const dateField = measurementForm.locator('input[type="date"]');
  const weightField = measurementForm.getByLabel('Вес, кг');
  const diaryGrid = measurementForm.locator('.diary-form-grid');
  const dateControl = measurementForm.locator('.diary-date-control');
  const [dateBox, dateControlBox, weightBox, diaryGridBox] = await Promise.all([
    dateField.boundingBox(),
    dateControl.boundingBox(),
    weightField.boundingBox(),
    diaryGrid.boundingBox(),
  ]);
  expect(dateBox).not.toBeNull();
  expect(dateControlBox).not.toBeNull();
  expect(weightBox).not.toBeNull();
  expect(diaryGridBox).not.toBeNull();
  expect(dateBox!.y + dateBox!.height).toBeLessThanOrEqual(weightBox!.y);
  expect(dateControlBox!.x).toBeGreaterThanOrEqual(diaryGridBox!.x);
  expect(dateControlBox!.x + dateControlBox!.width).toBeLessThanOrEqual(
    diaryGridBox!.x + diaryGridBox!.width,
  );
  expect(dateBox!.x).toBeGreaterThanOrEqual(dateControlBox!.x);
  expect(dateBox!.x + dateBox!.width).toBeLessThanOrEqual(
    dateControlBox!.x + dateControlBox!.width,
  );

  await openAppDestination(page, 'Питание');
  const nutritionDiary = page.locator('.nutrition-day-summary');
  await expect(nutritionDiary).toHaveCount(1);
  await expect(nutritionDiary).toBeVisible();
  expect(
    await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      content: document.documentElement.scrollWidth,
    })),
  ).toEqual({ viewport: 440, content: 440 });
  await page.evaluate(() => window.scrollTo({ left: 1000 }));
  expect(await page.evaluate(() => window.scrollX)).toBe(0);

  await openAppDestination(page, 'Упражнения');
  await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();
  const search = page.getByRole('searchbox', { name: 'Поиск' });
  await search.fill('Тяга');
  await expect(page.getByText('Тяга блока', { exact: true })).toBeVisible();
  const searchBox = await search.boundingBox();
  expect(searchBox).not.toBeNull();
  expect(searchBox!.x + searchBox!.width).toBeLessThanOrEqual(440);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  const bottomNavigation = page.locator('#appBottomNav');
  await expect(search).toBeFocused();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(bottomNavigation).toBeHidden();
  await search.evaluate((element) => element.blur());
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  await expect(bottomNavigation).toBeVisible();
  await expect(page).toHaveURL('/app?section=catalog');
  await expect(search).toHaveValue('Тяга');
  await expect(page.getByText('Тяга блока', { exact: true })).toBeVisible();

  await openAppDestination(page, 'План');
  await expect(page.getByRole('heading', { name: 'Текущий план от тренера' })).toBeVisible();
  const planManagementLink = page.getByRole('link', {
    name: 'Управление программой',
    exact: true,
  });
  await expect(planManagementLink).toBeVisible();
  await planManagementLink.click();
  await expect(page).toHaveURL('/app?section=programs&view=manage');
  await expect(page.getByText('Назначил тренер Тренер Анна')).toBeVisible();
  await page.getByText('Все этапы и изменения', { exact: true }).click();
  await expect(page.getByText('Тренировочные блоки ещё не настроены')).toBeVisible();
  await expect(page.getByText('Программа назначена')).toBeVisible();
  await page.getByText('Все этапы и изменения', { exact: true }).click();
  await openCard(page, 'Программы и шаблоны');
  const example = page.getByRole('button', {
    name: 'Посмотреть шаблон «Программа на всё тело — 3 дня»',
  });
  await expect(example).toContainText('Рекомпозиция · Начальный уровень · 1 тренировка в цикле');
  await expect(example).toContainText('Готовый шаблон');
  await expect(example).not.toContainText('recomposition');
  await expect(example).not.toContainText('beginner');
  await example.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'День 1. Всё тело' })).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Тяга блока')).toBeVisible();
  await expect(page.getByRole('dialog').getByText('3 подх. × 10–12 · отдых 90 сек.')).toBeVisible();
  const [programPanelBox, programHeadBox] = await Promise.all([
    page.locator('.program-example-modal__panel').boundingBox(),
    page.locator('.program-example-modal__head').boundingBox(),
  ]);
  expect(programPanelBox).not.toBeNull();
  expect(programHeadBox).not.toBeNull();
  expect(programPanelBox!.x).toBeLessThanOrEqual(1);
  expect(Math.abs(programPanelBox!.width - 390)).toBeLessThanOrEqual(1);
  expect(Math.abs(programHeadBox!.x - programPanelBox!.x)).toBeLessThanOrEqual(2);
  expect(
    Math.abs(
      programHeadBox!.x + programHeadBox!.width - (programPanelBox!.x + programPanelBox!.width),
    ),
  ).toBeLessThanOrEqual(2);
  await page.getByRole('button', { name: 'Техника и детали' }).click();
  const exerciseGuide = page.locator('.exercise-guide-modal__panel');
  await expect(exerciseGuide.getByRole('img', { name: 'Фаза усилия' })).toBeVisible();
  await expect(exerciseGuide.getByRole('img', { name: 'Фаза возврата' })).toBeVisible();
  await expect(
    exerciseGuide.locator('.exercise-guide-images figcaption').getByText('Фаза усилия'),
  ).toBeVisible();
  await expect(
    exerciseGuide.locator('.exercise-guide-images figcaption').getByText('Фаза возврата'),
  ).toBeVisible();
  await exerciseGuide.getByRole('button', { name: 'Увеличить: Фаза усилия' }).click();
  await expect(page.locator('.exercise-lightbox')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.exercise-lightbox')).toHaveCount(0);
});

test('мастер подбора сохраняет ответы и ведёт к явному запуску на mobile и desktop', async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'План');

  const planManagementLink = page.getByRole('link', {
    name: 'Управление программой',
    exact: true,
  });
  await expect(planManagementLink).toBeVisible();
  await planManagementLink.click();
  await expect(page).toHaveURL('/app?section=programs&view=manage');

  const launcher = page.getByRole('button', { name: 'Подобрать другую' });
  await launcher.click();
  const wizard = page.getByRole('dialog', { name: 'Цель' });
  await expect(wizard).toBeVisible();
  await expect(wizard.getByText(/профиль от этого не обновится/i)).toBeVisible();
  const progressBounds = await wizard.locator('.program-wizard__progress').boundingBox();
  const prefillBounds = await wizard.locator('.program-wizard__prefill').boundingBox();
  expect(progressBounds).not.toBeNull();
  expect(prefillBounds).not.toBeNull();
  expect(prefillBounds!.y - (progressBounds!.y + progressBounds!.height)).toBeGreaterThanOrEqual(8);
  expect(
    await wizard.locator('.program-wizard__panel').evaluate((element) => ({
      client: element.clientWidth,
      scroll: element.scrollWidth,
    })),
  ).toEqual({ client: 360, scroll: 360 });
  await page.screenshot({
    path: '../.artifacts/screenshots/task-113A/program-stepper-360x800-light.png',
  });

  await wizard.getByRole('radio', { name: /Рекомпозиция/ }).check();
  await wizard.getByRole('button', { name: 'Далее' }).click();
  await page.getByRole('radio', { name: /Начинаю или возвращаюсь/ }).check();
  await page.getByRole('button', { name: 'Далее' }).click();
  const threeWorkouts = page.locator('input[name="recommendation-frequency"][value="3"]');
  await threeWorkouts.check();
  await page.getByRole('button', { name: 'Назад' }).click();
  await expect(page.getByRole('radio', { name: /Начинаю или возвращаюсь/ })).toBeChecked();
  await page.getByRole('button', { name: 'Далее' }).click();
  await expect(threeWorkouts).toBeChecked();
  await page.getByRole('button', { name: 'Далее' }).click();
  await page.getByRole('radio', { name: /Тренажёрный зал/ }).check();
  await page.getByRole('button', { name: 'Далее' }).click();
  await page.getByRole('radio', { name: /Учесть только доступное/ }).check();
  await page.getByRole('checkbox', { name: 'Только собственный вес' }).check();
  await page.getByRole('button', { name: 'Показать рекомендацию' }).click();

  const result = page.getByRole('dialog', { name: 'Ваш результат' });
  await expect(
    result.getByRole('heading', { name: 'Программа на всё тело — 3 дня' }),
  ).toBeVisible();
  await expect(result.getByText(/Всё тело — основные мышечные группы/)).toBeVisible();
  await expect(result.getByText(/не является медицинской рекомендацией/i)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await result
      .locator('.program-wizard__panel')
      .evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);
  await expect(result.getByText('Рекомпозиция', { exact: true })).toBeVisible();
  const frequencySummary = result
    .getByText('Частота', { exact: true })
    .locator('xpath=following-sibling::dd');
  await expect(frequencySummary).toContainText('3 тренировки в неделю');
  await expect(frequencySummary).toContainText('В программе: 3 тренировки в цикле');
  const mobileSummary = await result.locator('.program-wizard-result__summary').boundingBox();
  expect(mobileSummary).not.toBeNull();
  expect(mobileSummary!.height).toBeGreaterThan(150);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-113A/program-result-390x844-light.png',
  });

  await result.getByRole('button', { name: 'Посмотреть план' }).click();
  const preview = page.getByRole('dialog', { name: /Программа на всё тело — 3 дня/ });
  await expect(
    preview.getByRole('button', { name: 'Настроить расписание и запустить' }),
  ).toBeVisible();
  await preview.locator('.program-example-modal__close').click();

  await page.setViewportSize({ width: 1440, height: 900 });
  await launcher.click();
  const desktopPanel = page
    .getByRole('dialog', { name: 'Ваш результат' })
    .locator('.program-wizard__panel');
  const desktopBox = await desktopPanel.boundingBox();
  expect(desktopBox).not.toBeNull();
  expect(desktopBox!.width).toBeLessThanOrEqual(760);
  expect(Math.abs(desktopBox!.x + desktopBox!.width / 2 - 720)).toBeLessThanOrEqual(1);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'Ваш результат' })).toHaveCount(0);
  await expect(launcher).toBeFocused();
});

test('клиент собирает и переупорядочивает личную программу', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await mockApi(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await openAppDestination(page, 'План');
  await page.goto('/app?section=programs&view=manage');

  const builder = page.locator('#program-builder');
  await expect(builder.getByRole('heading', { name: 'Создать свою программу' })).toBeVisible();
  expect(
    await page
      .locator('#program-builder, #program-library')
      .evaluateAll((elements) => elements.map((element) => element.id)),
  ).toEqual(['program-builder', 'program-library']);
  await expect(builder.getByLabel('Название', { exact: true })).toHaveValue('Моя программа');
  await expect(builder.getByLabel('Название дня 1')).toHaveValue('Тренировка 1');
  await expect(builder.getByText('Настройки программы', { exact: true })).toBeVisible();
  await expect(builder.getByRole('combobox', { name: 'Цель', exact: true })).toBeHidden();
  const settings = builder.locator('.program-builder-settings');
  await settings.locator('summary').click();
  const goal = builder.getByRole('combobox', { name: 'Цель', exact: true });
  await goal.selectOption('recomposition');
  await expect(goal).toHaveValue('recomposition');
  await goal.selectOption('maintenance');
  const duration = builder.getByRole('spinbutton', { name: 'Длительность, недель' });
  await duration.fill('2');
  await expect(duration).toHaveValue('2');
  await duration.fill('1');
  await settings.locator('summary').click();
  await expect(goal).toBeHidden();

  const exercisePicker = builder.getByRole('combobox', { name: 'Поиск упражнения' }).first();
  await exercisePicker.fill('Тяга');
  await builder.getByRole('button', { name: 'Техника: Тяга блока' }).click();
  await expect(page.getByRole('dialog', { name: /Тяга блока/ })).toBeVisible();
  const closeGuide = page.getByRole('button', { name: 'Закрыть карточку упражнения' });
  await expect(closeGuide).toBeInViewport();
  await closeGuide.click();
  await expect(exercisePicker).toHaveValue('Тяга');
  await exercisePicker.focus();
  await builder.getByRole('option', { name: /Тяга блока/ }).click();
  await expect(exercisePicker).toHaveValue('Тяга блока');
  await expect(builder.getByText('1 тренировка · 1 упр.', { exact: true })).toBeVisible();

  await builder.getByRole('button', { name: 'Добавить упражнение' }).first().click();
  const exercisePickers = builder.getByRole('combobox', { name: 'Поиск упражнения' });
  await expect(exercisePickers.nth(0)).toHaveValue('Тяга блока');
  await expect(exercisePickers.nth(1)).toHaveValue('');
  const moveExerciseDown = builder.getByRole('button', {
    name: 'Переместить упражнение 1 ниже',
  });
  await moveExerciseDown.focus();
  await moveExerciseDown.press('Enter');
  const exerciseRows = builder.locator('.program-exercise-row');
  await expect(exerciseRows.nth(0).getByRole('button', { name: 'Техника и детали' })).toHaveCount(
    0,
  );
  await expect(exerciseRows.nth(1).getByRole('button', { name: 'Техника и детали' })).toBeVisible();
  await expect(exercisePickers.nth(0)).toHaveValue('');
  await expect(exercisePickers.nth(1)).toHaveValue('Тяга блока');
  await builder.getByRole('button', { name: 'Удалить упражнение 1 из дня 1' }).click();

  await builder.getByRole('button', { name: 'Добавить день' }).click();
  const moveDayUp = builder.getByRole('button', { name: 'Переместить день 2 выше' });
  await moveDayUp.focus();
  await moveDayUp.press('Enter');
  await expect(builder.getByLabel('Название дня 1')).toHaveValue('Тренировка 2');
  await expect(builder.getByLabel('Название дня 2')).toHaveValue('Тренировка 1');
  await builder.getByRole('button', { name: 'Удалить день 1' }).click();
  await expect(builder.getByLabel('Название дня 1')).toHaveValue('Тренировка 1');

  const createRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname.endsWith('/programs/templates') &&
      request.method() === 'POST',
  );
  await builder.getByRole('button', { name: 'Создать программу' }).click();
  const payload = (await createRequest).postDataJSON() as {
    title: string;
    goal: string;
    level: string;
    duration_weeks: number;
    schedule_weekdays: number[];
    days: Array<{ exercises: Array<{ exercise_id: number }> }>;
  };
  expect(payload).toMatchObject({
    title: 'Моя программа',
    goal: 'maintenance',
    level: 'beginner',
    duration_weeks: 1,
  });
  expect(payload.schedule_weekdays).toHaveLength(1);
  expect(payload.days).toHaveLength(1);
  expect(payload.days[0]?.exercises).toEqual([expect.objectContaining({ exercise_id: 1 })]);
  await expect(builder.getByRole('link', { name: 'Перейти к тренировке' })).toBeVisible();
});

test('сенсорное поле даты сохраняет нативный пикер и показывает иконку календаря', async ({
  browser,
}) => {
  const context = await browser.newContext({
    baseURL: 'http://127.0.0.1:4173',
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();

  try {
    await mockApi(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await openAppDestination(page, 'Прогресс');
    const dateField = page.getByLabel('Дата');
    const dateControl = page.locator('.diary-date-control');
    await expect(dateField).toHaveAttribute('type', 'date');
    const fallbackIcon = await dateControl.evaluate((element) => {
      const style = getComputedStyle(element, '::after');
      return {
        content: style.content,
        height: style.height,
        mask: style.maskImage || style.getPropertyValue('-webkit-mask-image'),
        pointerEvents: style.pointerEvents,
        width: style.width,
      };
    });
    expect(fallbackIcon).toMatchObject({
      content: '""',
      height: '18px',
      pointerEvents: 'none',
      width: '18px',
    });
    expect(fallbackIcon.mask).toContain('svg');

    await dateControl.scrollIntoViewIfNeeded();
    const dateControlBox = await dateControl.boundingBox();
    expect(dateControlBox).not.toBeNull();
    await dateField.evaluate((element) => {
      element.addEventListener('click', () => element.setAttribute('data-picker-clicked', 'true'), {
        once: true,
      });
    });
    await dateField.click({
      position: { x: dateControlBox!.width - 14, y: dateControlBox!.height / 2 },
    });
    await expect(dateField).toHaveAttribute('data-picker-clicked', 'true');
  } finally {
    await context.close();
  }
});

test('Root открывает минимальный operational workspace', async ({ page }) => {
  await mockApi(page);
  await page.goto('/admin');
  await page.getByRole('button', { name: 'Админ' }).click();
  await expect(
    page.getByRole('heading', { name: 'Операции поддержки и безопасности' }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Админ-панель' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByRole('link', { name: 'Тренер', exact: true })).toHaveCount(0);
  await expect(page.getByText('Введите идентификатор')).toBeVisible();
  await expect(page.getByText('Заявки тренеров')).toHaveCount(0);
  await expect(page.getByText('Шаблоны программ')).toHaveCount(0);
});

test('поля даты остаются внутри анкеты клиента в кабинете тренера', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { withCoachClient: true });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await page.getByRole('button', { name: /Тестовый клиент/ }).click();
  await page.getByText('Профиль клиента', { exact: true }).click();

  const birthDateField = page.getByLabel('Дата рождения');
  const birthDateBox = await birthDateField.boundingBox();
  const birthDateControlBox = await page.locator('.coach-client-birth-date-control').boundingBox();
  expect(birthDateBox).not.toBeNull();
  expect(birthDateControlBox).not.toBeNull();
  expect(birthDateBox!.x).toBeGreaterThanOrEqual(birthDateControlBox!.x);
  expect(birthDateBox!.x + birthDateBox!.width).toBeLessThanOrEqual(
    birthDateControlBox!.x + birthDateControlBox!.width,
  );

  await page.getByText('Тренировки, прогресс и замеры', { exact: true }).click();

  const dateField = page.getByLabel('Дата', { exact: true });
  const dateBox = await dateField.boundingBox();
  await expect(dateField).toHaveCSS('text-align', 'center');
  const dateControlBox = await page.locator('.diary-date-control').boundingBox();
  const diaryGridBox = await page.locator('.diary-form-grid').boundingBox();
  expect(dateBox).not.toBeNull();
  expect(dateControlBox).not.toBeNull();
  expect(diaryGridBox).not.toBeNull();
  expect(dateControlBox!.x).toBeGreaterThanOrEqual(diaryGridBox!.x);
  expect(dateControlBox!.x + dateControlBox!.width).toBeLessThanOrEqual(
    diaryGridBox!.x + diaryGridBox!.width,
  );
  expect(dateBox!.x).toBeGreaterThanOrEqual(dateControlBox!.x);
  expect(dateBox!.x + dateBox!.width).toBeLessThanOrEqual(
    dateControlBox!.x + dateControlBox!.width,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test('тренер открывает кабинет', async ({ page }) => {
  await mockApi(page);
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();
  await expect(page.getByRole('heading', { name: 'Кабинет тренера' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Тренер', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page.getByRole('link', { name: 'Админ-панель' })).toHaveCount(0);
  await expect(page.getByText('Клиентов пока нет')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Добавьте первого клиента' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Пригласить первого клиента' })).toBeVisible();
});

test('тренер быстро переходит между программой клиента и каталогом', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { withCoachClient: true, withCoachProgram: true });
  await page.goto('/coach');
  await page.getByRole('button', { name: 'Тренер' }).click();

  await page.getByRole('tab', { name: 'Назначенные программы' }).click();
  await openCard(page, 'Программы клиентов');
  await expect(page.getByText('План клиента на четыре недели')).toBeVisible();
  await page.getByRole('button', { name: 'Открыть клиента' }).click();

  await expect(page.getByText('Текущая программа клиента')).toBeVisible();
  await expect(page.locator('.coach-client-program > div > strong')).toHaveText(
    'План клиента на четыре недели',
  );
  await page.getByRole('button', { name: 'Добавить упражнение' }).first().click();

  await expect(page.getByRole('heading', { name: 'Упражнения', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'В программу' }).click();
  const assignment = page.getByRole('dialog', { name: /Тяга блока/ });
  const assignmentContext = assignment.locator('.assignment-context select');
  await expect(assignmentContext.nth(0)).toHaveValue('2');
  await expect(assignmentContext.nth(1)).toHaveValue('701');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
