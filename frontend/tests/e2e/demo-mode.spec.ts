import { resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import { demoFixture } from './fixtures/demo-session';
import type { DemoScenario, DemoSessionSnapshot } from '../../src/features/demo/demoApi';
import {
  expectDockWithinViewport,
  expectElementsWithinHorizontalViewport,
  expectNoHorizontalOverflow,
} from './fixtures/mobile-tma';
import { expectUiAuditClean, UI_AUDIT_VIEWPORTS } from './fixtures/ui-audit';

const DEMO_VIEWPORTS = [
  ...UI_AUDIT_VIEWPORTS.map((viewport) => ({
    ...viewport,
    mobile: viewport.width <= 900,
  })),
  { name: 'desktop-1366', width: 1366, height: 768, mobile: false },
] as const;

const TASK_274_EVIDENCE_DIR = process.env.TASK_274_EVIDENCE_DIR;
const TASK_278_EVIDENCE_DIR = process.env.TASK_278_EVIDENCE_DIR;
const TASK_291_EVIDENCE_DIR = process.env.TASK_291_EVIDENCE_DIR;
const TASK_293_EVIDENCE_DIR = process.env.TASK_293_EVIDENCE_DIR;
const TASK_293_THEME =
  process.env.TASK_293_THEME === 'light' || process.env.TASK_293_THEME === 'dark'
    ? process.env.TASK_293_THEME
    : undefined;
const TASK_293_VIEWPORT = /^\d+x\d+$/.test(process.env.TASK_293_VIEWPORT ?? '')
  ? process.env.TASK_293_VIEWPORT
  : undefined;
const TASK_293_VARIANT = `${TASK_293_VIEWPORT ?? 'default'}-${TASK_293_THEME ?? 'light'}`;
const TASK_278_THEME =
  process.env.TASK_278_THEME === 'light' || process.env.TASK_278_THEME === 'dark'
    ? process.env.TASK_278_THEME
    : undefined;

async function captureEvidence(page: Page, fileName: string): Promise<void> {
  if (!TASK_274_EVIDENCE_DIR) return;
  await page.screenshot({ path: resolve(TASK_274_EVIDENCE_DIR, fileName), fullPage: true });
}

async function captureTask278Evidence(page: Page, fileName: string): Promise<void> {
  if (!TASK_278_EVIDENCE_DIR) return;
  await page.screenshot({ path: resolve(TASK_278_EVIDENCE_DIR, fileName), fullPage: true });
}

async function captureTask291Evidence(page: Page, fileName: string): Promise<void> {
  if (!TASK_291_EVIDENCE_DIR) return;
  await page.screenshot({ path: resolve(TASK_291_EVIDENCE_DIR, fileName), fullPage: true });
}

async function captureTask293Evidence(page: Page, fileName: string): Promise<void> {
  if (!TASK_293_EVIDENCE_DIR) return;
  await page.screenshot({ path: resolve(TASK_293_EVIDENCE_DIR, fileName), fullPage: true });
}

async function assertBottomNavigationGeometry(page: Page, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 844 });
  const geometry = await page.evaluate(() => {
    const navigation = document.querySelector<HTMLElement>('#appBottomNav');
    const content = document.querySelector<HTMLElement>('#appContent');
    if (!navigation || !content) throw new Error('Expected app bottom navigation and content');

    const scrollElement = document.scrollingElement ?? document.documentElement;
    const actions = Array.from(
      content.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'),
    ).filter((element) => element.offsetParent !== null);
    const lastAction = actions.at(-1);
    const previousScrollBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = 'auto';
    scrollElement.scrollTop = scrollElement.scrollHeight;
    document.documentElement.style.scrollBehavior = previousScrollBehavior;

    const navigationRect = navigation.getBoundingClientRect();
    const lastActionRect = lastAction?.getBoundingClientRect() ?? null;
    const floatingAction = document.querySelector<HTMLElement>('.app-quick-add-trigger');
    const floatingActionRect = floatingAction?.getBoundingClientRect() ?? null;
    const overlaps = (left: DOMRect, right: DOMRect) =>
      left.left < right.right &&
      left.right > right.left &&
      left.top < right.bottom &&
      left.bottom > right.top;

    return {
      navigationHeight: navigationRect.height,
      navigationTop: navigationRect.top,
      navigationBottom: navigationRect.bottom,
      lastActionBottom: lastActionRect?.bottom ?? null,
      bodyPaddingBottom: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
      scrollHeight: scrollElement.scrollHeight,
      viewportHeight: window.innerHeight,
      viewportBottomGap: window.innerHeight - navigationRect.bottom,
      floatingActionOverlap: Boolean(
        floatingActionRect && overlaps(floatingActionRect, navigationRect),
      ),
    };
  });
  expect(geometry.navigationHeight).toBeGreaterThan(0);
  expect(geometry.navigationBottom).toBeLessThanOrEqual(geometry.viewportHeight);
  expect(geometry.viewportBottomGap).toBeGreaterThanOrEqual(0);
  expect(geometry.viewportBottomGap).toBeLessThanOrEqual(16);
  expect(geometry.bodyPaddingBottom).toBeGreaterThanOrEqual(geometry.navigationHeight);
  expect(geometry.scrollHeight).toBeGreaterThanOrEqual(geometry.viewportHeight);
  expect(geometry.lastActionBottom).not.toBeNull();
  expect(geometry.lastActionBottom ?? Number.POSITIVE_INFINITY).toBeLessThanOrEqual(
    geometry.navigationTop,
  );
  expect(geometry.floatingActionOverlap).toBe(false);
}

const today = () => new Date().toISOString().slice(0, 10);

function demoUser(snapshot: DemoSessionSnapshot) {
  const coach = snapshot.scenario === 'trainer';
  return {
    id: snapshot.scenario === 'trainer' ? 900000003 : 900000001,
    telegram_user_id: null,
    username: 'demo_user',
    first_name: 'Демо',
    last_name: null,
    photo_url: null,
    custom_avatar: null,
    is_coach: coach,
    is_admin: false,
    is_root: false,
    has_active_program: true,
    has_workout_history: true,
    has_food_history: true,
    auth_providers: [],
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
      kbju: {
        id: 70001,
        user_id: 900000001,
        telegram_user_id: null,
        effective_from: '2026-08-25',
        effective_to: null,
        source: 'calculated',
        created_at: '2026-08-25T10:00:00Z',
        note: null,
        superseded_by_id: null,
        sex: 'male',
        weight_kg: 77.1,
        height_cm: 180,
        age: 31,
        daily_routine: 'mixed',
        steps_range: 'from_7000_to_10000',
        strength_trainings_per_week: 4,
        strength_training_duration_minutes: 60,
        strength_training_type: 'regular',
        strength_rest: 'one_to_two',
        cardio_trainings: [],
        goal: 'muscle_gain',
        bmr: 1740,
        tdee: 2420,
        calories: 2150,
        protein_g: 145,
        fat_g: 70,
        carbs_g: 245,
        saved_at: '2026-08-25T10:00:00Z',
        created_by: null,
        assigned_by: null,
        daily_activity_level: 'moderate',
        cardio_trainings_per_week: 2,
        cardio_training_duration_minutes: 30,
        cardio_intensity: 'moderate',
      },
    },
    trainer: null,
  };
}

function workout(snapshot: DemoSessionSnapshot) {
  const state = snapshot.state.kind === 'self_training' ? snapshot.state : null;
  const completed = state?.completed_sets ?? 0;
  const status =
    state?.screen === 'active_workout'
      ? 'in_progress'
      : state?.screen === 'summary' || state?.screen === 'progress'
        ? 'completed'
        : 'planned';
  return {
    id: 50001,
    scheduled_date: today(),
    scheduled_time: '19:00:00',
    title: 'Верх тела · уверенный старт',
    status,
    day_number: new Date().getDay() || 7,
    week_number: 4,
    started_at: status === 'planned' ? null : '2026-09-15T17:00:00Z',
    completed_at: status === 'completed' ? '2026-09-15T17:46:00Z' : null,
    exercises: [
      {
        id: 61001,
        exercise_id: 1001,
        exercise_title: 'Жим гантелей лёжа с контролируемой паузой',
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: '10',
        prescribed_duration_minutes: null,
        rest_seconds: 90,
        notes: 'Сохраняйте контроль в нижней точке.',
        superset_group: null,
        superset_order: null,
        has_guide: false,
        progression_guidance: null,
        sets: [1, 2, 3].map((setNumber) => ({
          id: 60001 + setNumber,
          set_number: setNumber,
          actual_reps: setNumber <= completed ? 10 : null,
          actual_weight: setNumber <= completed ? 18 : null,
          duration_minutes: null,
          distance_km: null,
          average_heart_rate_bpm: null,
          heart_rate_zone: null,
          rir: setNumber <= completed ? '2' : null,
          set_kind: 'working',
          reached_failure: setNumber <= completed ? false : null,
          is_completed: setNumber <= completed,
          version: 1,
        })),
      },
    ],
    completion_summary:
      status === 'completed'
        ? {
            duration_seconds: 2760,
            performed_exercises: 1,
            completed_sets: completed,
            total_sets: 3,
            reps_total: completed * 10,
            reps_recorded_sets: completed,
            load_recorded_sets: completed,
            exercises: [],
            personal_records: [],
            next_workout: null,
            feedback: null,
            note: null,
          }
        : null,
  };
}

function progressSummary(snapshot: DemoSessionSnapshot) {
  const completed =
    snapshot.state.kind === 'self_training' &&
    ['summary', 'progress'].includes(snapshot.state.screen);
  const end = today();
  return {
    user_id: 900000001,
    period_days: 30,
    period_start: '2026-08-17',
    period_end: end,
    training: {
      planned_workouts: 12,
      completed_workouts: completed ? 12 : 11,
      skipped_workouts: 0,
      frequency_per_week: 3.2,
      volume_kg: completed ? 6840 : 6220,
      new_personal_records: completed ? 1 : 0,
      last_completed_workout_on: '2026-09-13',
      next_workout: {
        id: 50005,
        scheduled_date: '2026-09-17',
        scheduled_time: '19:00:00',
        title: 'Верх тела',
        status: 'planned',
      },
    },
    cardio: {
      completed_sessions: 6,
      planned_sessions: 8,
      frequency_per_week: 1.5,
      duration_minutes: 210,
      distance_km: 22.4,
      zone_duration: [{ zone: 2, duration_minutes: 142 }],
    },
    nutrition: {
      visible: true,
      logged_days: 5,
      complete_days: 4,
      incomplete_days: 1,
      fasted_days: 0,
      unlogged_days: 25,
      adherence_evaluated_days: 6,
      average_calories: 2010,
      target_calories: 2150,
      average_protein_g: 132,
      target_protein_g: 145,
      target_effective_on: '2026-08-25',
    },
    body: {
      latest_measurement:
        snapshot.scenario === 'trainer'
          ? {
              measured_on: today(),
              weight_kg: 77.1,
              custom_measurements: [
                {
                  definition_id: 93001,
                  label: 'Талия',
                  unit: 'cm',
                  value: 84,
                  measured_on: today(),
                  archived: false,
                },
              ],
            }
          : null,
      trends: [],
      priority: { mode: 'balanced', muscle_group_ids: [] },
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
      overall_percent: 82,
      included_components: ['workouts'],
      workouts: {
        status: 'available',
        percent: 92,
        achieved: 11,
        evaluated: 12,
        weight: 0.4,
        reason: null,
      },
      cardio: {
        status: 'available',
        percent: 75,
        achieved: 6,
        evaluated: 8,
        weight: 0.2,
        reason: null,
      },
      calories: {
        status: 'available',
        percent: 78,
        achieved: 5,
        evaluated: 6,
        weight: 0.2,
        reason: null,
      },
      protein: {
        status: 'available',
        percent: 81,
        achieved: 5,
        evaluated: 6,
        weight: 0.2,
        reason: null,
      },
    },
    data_sufficiency: {
      ruleset_version: 'data-sufficiency-v1',
      workout_logging: {
        status: 'sufficient',
        counters: { available: 1 },
        reason_keys: ['thresholds_met'],
      },
      working_sets: {
        status: 'sufficient',
        counters: { available: 1 },
        reason_keys: ['thresholds_met'],
      },
      rir_coverage: {
        status: 'limited',
        counters: { available: 1 },
        reason_keys: ['too_few_rir_observations'],
      },
      nutrition_coverage: {
        status: 'sufficient',
        counters: { available: 1 },
        reason_keys: ['thresholds_met'],
      },
      weight_trend: {
        status: 'sufficient',
        counters: { available: 1 },
        reason_keys: ['thresholds_met'],
      },
      anthropometry: {
        status: 'insufficient',
        counters: { available: 0 },
        reason_keys: ['no_anthropometry_measurements'],
      },
      schedule_adherence: {
        status: 'sufficient',
        counters: { available: 1 },
        reason_keys: ['thresholds_met'],
      },
      confirm_energy_mismatch: false,
    },
  };
}

function nutritionDay(snapshot: DemoSessionSnapshot) {
  const state = snapshot.state.kind === 'nutrition' ? snapshot.state : null;
  const added = Boolean(state?.item_added);
  const entry = {
    id: 80101,
    diary_date: today(),
    meal_type: 'breakfast',
    food_id: null,
    recipe_id: null,
    entry_kind: 'quick_add',
    logged_at: '09:00:00',
    food_name: 'Овсяная каша с бананом и греческим йогуртом',
    food_brand: null,
    amount: 1,
    amount_unit: 'serving',
    weight_g: null,
    nutrition_basis_kind: null,
    nutrition_basis_amount: null,
    nutrition_basis_unit: null,
    serving_amount: 1,
    serving_unit: 'порция',
    serving_weight_g: 320,
    nutrition: { energy_kcal: 428, protein_g: 24, fat_g: 10, carbs_g: 56, fiber_g: 8 },
    created_at: '2026-09-15T09:00:00Z',
    updated_at: '2026-09-15T09:00:00Z',
  };
  const calories = state?.calories ?? 1160;
  const protein = state?.protein_g ?? 82;
  const meals = ['breakfast', 'lunch', 'dinner', 'snacks'].map((meal_type) => ({
    meal_type,
    entries: meal_type === 'breakfast' && added ? [entry] : [],
    totals: {
      energy_kcal: meal_type === 'breakfast' && added ? 428 : 0,
      protein_g: meal_type === 'breakfast' && added ? 24 : 0,
      fat_g: meal_type === 'breakfast' && added ? 10 : 0,
      carbs_g: meal_type === 'breakfast' && added ? 56 : 0,
      fiber_g: meal_type === 'breakfast' && added ? 8 : 0,
    },
  }));
  return {
    diary_date: today(),
    timezone: 'Europe/Moscow',
    meals,
    totals: { energy_kcal: calories, protein_g: protein, fat_g: 48, carbs_g: 180, fiber_g: 22 },
    targets: { energy_kcal: 2150, protein_g: 145, fat_g: 70, carbs_g: 245 },
    remaining: {
      energy_kcal: Math.max(0, 2150 - calories),
      protein_g: Math.max(0, 145 - protein),
      fat_g: 22,
      carbs_g: 65,
    },
    status: added ? 'complete' : 'incomplete',
    status_is_explicit: false,
  };
}

function hydrationDay(snapshot: DemoSessionSnapshot) {
  const entries =
    (snapshot as DemoSessionSnapshot & { hydration?: Array<Record<string, unknown>> }).hydration ??
    [];
  return {
    diary_date: today(),
    timezone: 'Europe/Moscow',
    total_ml: 1350 + entries.reduce((sum, item) => sum + Number(item.volume_ml ?? 0), 0),
    goal: {
      id: 90001,
      enabled: true,
      target_ml: 2200,
      source: 'manual',
      method_version: 'demo-v1',
      reference_scope: 'demo',
      sex: 'male',
      adult_confirmed: true,
      effective_from: '2026-08-25',
      effective_to: null,
      created_at: '2026-08-25T10:00:00Z',
    },
    progress_percent: 61.4,
    entries,
    presets: [
      { id: 90101, label: 'Стакан', volume_ml: 250, beverage_type: 'water', is_default: true },
      { id: 90102, label: 'Бутылка', volume_ml: 500, beverage_type: 'water', is_default: false },
    ],
    last_logged_at: '2026-09-15T09:00:00Z',
    reminder_suppression_key: null,
    action_url: '/api/v1/nutrition/hydration/entries',
    original_estimated_minutes: 0,
    adapted_estimated_minutes: 0,
    time_budget_minutes: null,
    changes: [],
    original_exercises: [],
    adapted_exercises: [],
    warnings: [],
    message: 'Данные гидратации доступны только в текущей демо-сессии.',
    preview_token: null,
  };
}

function foodItem() {
  return {
    id: 80001,
    name: 'Овсяная каша с бананом и греческим йогуртом',
    brand: null,
    barcode: null,
    energy_kcal_per_100g: 134,
    protein_g_per_100g: 7.5,
    fat_g_per_100g: 3.2,
    carbs_g_per_100g: 18.1,
    fiber_g_per_100g: 2.4,
    nutrition_basis_kind: 'per_100_g',
    nutrition_basis_amount: 100,
    nutrition_basis_unit: 'g',
    canonical_facts: null,
    nutrition_provenance: null,
    catalog_quality: 'verified',
    provenance: 'internal',
    trust_level: 'verified',
    canonical_complete: true,
    standard_serving_amount: 320,
    standard_serving_unit: 'g',
    standard_serving_weight_g: 320,
    food_type: 'system',
    is_favorite: false,
    last_used_at: '2026-09-15T09:00:00Z',
    created_at: '2026-09-15T09:00:00Z',
    updated_at: '2026-09-15T09:00:00Z',
  };
}

function client(slug: 'alexey' | 'maria' | 'ivan') {
  const names = { alexey: 'Алексей', maria: 'Мария', ivan: 'Иван' };
  return {
    id: { alexey: 51001, maria: 51002, ivan: 51003 }[slug],
    invite_id: null,
    telegram_user_id: null,
    username: slug,
    full_name: names[slug],
    birth_date: null,
    goal: 'muscle_gain',
    level: 'intermediate',
    height_cm: 180,
    weight_kg: 77,
    workouts_per_week: 4,
    cardio_trainings_per_week: 2,
    resting_heart_rate: null,
    body_priority: { mode: 'balanced', muscle_group_ids: [] },
    training_preferences: null,
    timezone: 'Europe/Moscow',
    kbju: null,
    status: 'active',
  };
}

function pendingClient() {
  return {
    id: null,
    invite_id: 54001,
    telegram_user_id: null,
    username: null,
    full_name: 'Елена · ожидает подтверждения',
    status: 'pending',
  };
}

function assignedProgram(slug: 'alexey' | 'maria') {
  const names = { alexey: 'Алексей', maria: 'Мария' };
  const ids = { alexey: 51001, maria: 51002 };
  return {
    id: slug === 'alexey' ? 97001 : 97002,
    client_id: ids[slug],
    client_telegram_user_id: null,
    client_username: slug,
    client_full_name: names[slug],
    template_id: null,
    title: 'Сила и устойчивость',
    goal: 'muscle_gain',
    level: 'intermediate',
    assigned_at: '2026-08-25T10:00:00Z',
    is_active: true,
    status: 'active',
    start_date: '2026-08-25',
    duration_weeks: 8,
    schedule_weekdays: [1, 3, 5],
    completed_at: null,
    workouts_total: 24,
    workouts_completed: 12,
    next_workout_date: today(),
    current_revision_number: 1,
  };
}

function timeline() {
  return [
    {
      id: 50011,
      scheduled_date: '2026-09-13',
      scheduled_time: '19:00:00',
      title: 'Ноги и корпус',
      status: 'completed',
      completed_at: '2026-09-13T17:46:00Z',
      completed_sets: 18,
      volume_kg: 6480,
      completion_feedback: 'as_expected',
      completion_note: null,
      exercises: [
        {
          workout_exercise_id: 62001,
          exercise_id: 1001,
          exercise_title: 'Присед со штангой',
          notes: 'Контролируйте глубину и темп.',
          superset_group: null,
          superset_order: null,
          sets: [1, 2, 3].map((set_number) => ({
            set_number,
            actual_reps: 10,
            actual_weight: 80,
            rir: '2',
            set_kind: 'working',
            reached_failure: false,
            is_completed: true,
          })),
        },
      ],
    },
  ];
}

function transport(snapshot: DemoSessionSnapshot, path: string, method: string, body: unknown) {
  if (path === '/api/v1/me') return demoUser(snapshot);
  if (path === '/api/v1/workouts/today') return workout(snapshot);
  if (path === '/api/v1/workouts/week' || path === '/api/v1/workouts/schedule')
    return [
      {
        id: 50001,
        scheduled_date: today(),
        scheduled_time: '19:00:00',
        title: 'Верх тела · уверенный старт',
        status:
          snapshot.state.kind === 'self_training' && snapshot.state.screen === 'active_workout'
            ? 'in_progress'
            : 'planned',
        day_number: new Date().getDay() || 7,
        week_number: 4,
      },
    ];
  if (path.startsWith('/api/v1/workouts/cardio')) return [];
  if (path.startsWith('/api/v1/workouts/progress/summary')) return progressSummary(snapshot);
  if (path.startsWith('/api/v1/workouts/progress/training-analytics'))
    return {
      period_days: 30,
      period_start: '2026-08-17',
      period_end: today(),
      exercise_history_limit: 20,
      completed_set_count: 54,
      reps_total: 620,
      reps_recorded_sets: 54,
      external_load_volume_kg: 24680,
      volume_recorded_sets: 54,
      exercises: [],
      rir: {
        completed_set_count: 54,
        recorded_set_count: 42,
        missing_set_count: 12,
        distribution: [{ value: '2', completed_set_count: 20 }],
      },
      primary_muscle_exposure: [],
      secondary_muscle_exposure: [],
      completed_sets_without_muscle_metadata: 0,
      data_sufficiency: {},
    };
  if (path.startsWith('/api/v1/workouts/progress/nutrition-report'))
    return {
      period: 'days_30',
      period_start: '2026-08-17',
      period_end: today(),
      timezone: 'Europe/Moscow',
      summary: {
        logged_days: 5,
        eligible_days: 30,
        coverage_percent: 16.7,
        complete_days: 4,
        incomplete_days: 1,
        fasted_days: 0,
        missing_days: 25,
        current_day_status: 'incomplete',
        calories: { average: 2010, minimum: 1900, maximum: 2100, sample_days: 5 },
        protein_g: { average: 132, minimum: 100, maximum: 150, sample_days: 5 },
        fat_g: { average: 68, minimum: 60, maximum: 75, sample_days: 5 },
        carbs_g: { average: 230, minimum: 200, maximum: 250, sample_days: 5 },
        calorie_comparison: {
          average_actual: 2010,
          average_target: 2150,
          average_deviation: -140,
          evaluated_days: 5,
        },
        protein_comparison: {
          average_actual: 132,
          average_target: 145,
          average_deviation: -13,
          evaluated_days: 5,
        },
        fat_comparison: {
          average_actual: 68,
          average_target: 70,
          average_deviation: -2,
          evaluated_days: 5,
        },
        carbs_comparison: {
          average_actual: 230,
          average_target: 245,
          average_deviation: -15,
          evaluated_days: 5,
        },
        days_within_calorie_tolerance: 4,
        calorie_tolerance_evaluated_days: 5,
        days_meeting_protein_target: 2,
        protein_target_evaluated_days: 5,
      },
      daily: [],
      target_changes: [],
      hydration: {
        total_ml: 10800,
        average_ml: 2160,
        logged_days: 5,
        eligible_days: 5,
        coverage_percent: 100,
        days_meeting_goal: 3,
        goal_evaluated_days: 5,
        trend_ml: 120,
      },
    };
  if (path === '/api/v1/workouts/progress')
    return {
      workouts_total: 32,
      workouts_completed: 12,
      workouts_skipped: 1,
      workouts_missed: 0,
      adherence_percent: 82,
      current_streak: 3,
      weight_change_kg: -0.7,
      weights: [],
      weekly_volume: [],
      personal_records: [],
    };
  if (path === '/api/v1/workouts/diary') return [];
  if (/^\/api\/v1\/workouts\/\d+\/comments$/.test(path)) return [];
  if (path.startsWith('/api/v1/workouts/history')) return timeline();
  if (path.startsWith('/api/v1/check-ins/weekly/current'))
    return {
      status: 'not_submitted',
      week_start: '2026-09-14',
      week_end: '2026-09-20',
      submitted_on: null,
      training_load: null,
      recovery: null,
      hunger: null,
      adherence_difficulty: null,
      note: null,
    };
  if (path.startsWith('/api/v1/check-ins/daily'))
    return {
      local_date: today(),
      status: 'not_submitted',
      energy: null,
      sleep_quality: null,
      stress: null,
      soreness: null,
      note: null,
    };
  if (path.startsWith('/api/v1/check-ins/weekly')) return { items: [], total: 0 };
  if (path.startsWith('/api/v1/nutrition/diary') && method === 'GET') return nutritionDay(snapshot);
  if (path.startsWith('/api/v1/nutrition/hydration') && method === 'GET')
    return hydrationDay(snapshot);
  if (path.startsWith('/api/v1/nutrition/foods/'))
    return {
      items: [foodItem()],
      total: 1,
      limit: 20,
      offset: 0,
      external_items: [],
      provider_status: 'not_needed',
      provider_statuses: [],
    };
  if (path === '/api/v1/nutrition/targets/current') return demoUser(snapshot).profile.kbju;
  if (path.startsWith('/api/v1/nutrition/targets/history'))
    return { items: [demoUser(snapshot).profile.kbju], total: 1, limit: 20, offset: 0 };
  if (path.startsWith('/api/v1/nutrition/recipes'))
    return { items: [], total: 0, limit: 20, offset: 0 };
  if (path === '/api/v1/programs/exercises') return [];
  if (path.endsWith('/programs/templates/mine'))
    return [
      {
        id: 40001,
        title: 'Силовая база',
        slug: 'demo-strength-base',
        goal: 'muscle_gain',
        level: 'intermediate',
        split_type: 'upper_lower',
        owner_user_id: 900000001,
        owner_telegram_user_id: null,
        owner_full_name: 'Демо-профиль',
        created_by_user_id: 900000001,
        is_public: false,
        is_example: false,
        is_assigned_to_current_user: true,
        is_active_for_current_user: true,
        can_edit: false,
        assigned_by_user_id: null,
        assigned_by_full_name: null,
        assigned_program_id: 41001,
        assigned_program_status: 'active',
        assigned_program_start_date: '2026-08-25',
        assigned_program_duration_weeks: 8,
        current_revision_number: 1,
        default_duration_weeks: 8,
        days: [],
      },
    ];
  if (path.endsWith('/programs/templates/hidden')) return [];
  if (path === '/api/v1/coach/clients')
    return [...(['alexey', 'maria', 'ivan'] as const).map(client), pendingClient()];
  if (path === '/api/v1/coach/assigned-programs')
    return (['alexey', 'maria'] as const).map(assignedProgram);
  if (path.startsWith('/api/v1/coach/attention'))
    return {
      items: [
        {
          key: 'without_program:51003:51003',
          kind: 'without_program',
          client: { id: 51003, name: 'Иван' },
          title: 'Нет активной программы',
          reason: 'Назначьте следующий рабочий план клиента.',
          source_kind: 'client',
          source_id: 51003,
          source_state: 'active',
          action: 'assign_program',
          destination: '/coach?client_id=51003',
          created_at: '2026-09-15T10:00:00Z',
        },
      ],
      total: 1,
      generated_at: '2026-09-15T10:00:00Z',
    };
  if (path.startsWith('/api/v1/coach/client-summaries'))
    return {
      items: (['alexey', 'maria', 'ivan'] as const).map((slug) => ({
        ...progressSummary(snapshot),
        user_id: client(slug).id,
        client_name: client(slug).full_name,
      })),
      total: 3,
      limit: 100,
      offset: 0,
    };
  if (/^\/api\/v1\/coach\/clients\/\d+\/analytics$/.test(path)) {
    return {
      workouts_total: 32,
      workouts_completed: 8,
      workouts_skipped: 1,
      workouts_missed: 0,
      adherence_percent: 88,
      current_streak: 3,
      weight_change_kg: -0.7,
      weights: [
        { measured_on: '2026-08-18', weight_kg: 77.8 },
        { measured_on: today(), weight_kg: 77.1 },
      ],
      weekly_volume: [
        { week_start: '2026-08-25', completed_workouts: 2, volume_kg: 5920 },
        { week_start: '2026-09-01', completed_workouts: 2, volume_kg: 6220 },
        { week_start: '2026-09-08', completed_workouts: 3, volume_kg: 6480 },
      ],
      personal_records: [],
    };
  }
  if (/^\/api\/v1\/coach\/clients\/\d+\/workouts\/\d+\/comments$/.test(path) && method === 'GET')
    return [];
  if (/^\/api\/v1\/coach\/clients\/\d+\/workouts/.test(path) && method === 'GET') return timeline();
  if (path.startsWith('/api/v1/coach/clients/') && method === 'GET') return [];
  if (path === '/api/v1/me/profile/body-priority-options') return { items: [] };
  if (path === '/api/v1/me/trainer-capability')
    return {
      is_active: snapshot.scenario === 'trainer',
      activated_now: false,
      active_client_count: 3,
      pending_invite_count: 0,
      can_disable: false,
      terms_version: 'demo-v1',
    };
  if (path === '/api/v1/me/exports/current')
    return {
      status: 'none',
      export_id: null,
      created_at: null,
      completed_at: null,
      expires_at: null,
      filename: null,
      content_size_bytes: null,
      error_code: null,
    };
  if (path.startsWith('/api/v1/notifications'))
    return path.endsWith('/settings')
      ? {
          workout_reminders_enabled: true,
          weekly_check_in_reminders_enabled: true,
          measurement_reminders_enabled: true,
          meal_reminders_enabled: false,
          hydration_reminders_enabled: true,
          movement_reminders_enabled: false,
          telegram_enabled: false,
          telegram_linked: false,
          reminder_hour: 19,
          quiet_hours_start: '23:00:00',
          quiet_hours_end: '07:00:00',
        }
      : [];
  if (path === '/api/v1/ai-coach/status')
    return { ui_enabled: false, generic_available: false, personal_available: false };
  if (method === 'GET') return [];
  if (path === '/api/v1/workouts/50001/start' && method === 'POST') {
    if (snapshot.state.kind === 'self_training') snapshot.state.screen = 'active_workout';
    return workout(snapshot);
  }
  if (path === '/api/v1/workouts/50001/finish' && method === 'POST') {
    if (snapshot.state.kind === 'self_training') {
      snapshot.state.screen = 'summary';
      snapshot.state.duration_minutes = 46;
      snapshot.state.total_volume_kg = 6840;
      snapshot.cabinet.meaningful_action_completed = true;
    }
    return workout(snapshot);
  }
  const setMatch = path.match(/^\/api\/v1\/workouts\/sets\/(\d+)$/);
  if (setMatch && method === 'PATCH') {
    const setNumber = Number(setMatch[1]) - 60001;
    const values = (body ?? {}) as {
      actual_reps?: number;
      actual_weight?: number;
      is_completed?: boolean;
    };
    if (snapshot.state.kind === 'self_training' && values.is_completed)
      snapshot.state.completed_sets = Math.max(snapshot.state.completed_sets, setNumber);
    return {
      id: Number(setMatch[1]),
      set_number: setNumber,
      actual_reps: values.actual_reps ?? 10,
      actual_weight: values.actual_weight ?? 18,
      duration_minutes: null,
      distance_km: null,
      average_heart_rate_bpm: null,
      heart_rate_zone: null,
      rir: '2',
      set_kind: 'working',
      reached_failure: false,
      is_completed: values.is_completed ?? true,
      version: 2,
    };
  }
  if (path === '/api/v1/nutrition/diary/entries' && method === 'POST') {
    if (snapshot.state.kind !== 'nutrition') return {};
    snapshot.state.item_added = true;
    snapshot.cabinet.meaningful_action_completed = true;
    const breakfast = nutritionDay(snapshot).meals.find((meal) => meal.meal_type === 'breakfast');
    if (!breakfast?.entries[0]) throw new Error('Demo nutrition fixture did not create an entry');
    return breakfast.entries[0];
  }
  if (path === '/api/v1/nutrition/hydration/entries' && method === 'POST') {
    const values = (body ?? {}) as { volume_ml?: number; beverage_type?: string };
    const entry = {
      id: 90200,
      volume_ml: values.volume_ml ?? 250,
      beverage_type: values.beverage_type ?? 'water',
      occurred_at: '2026-09-15T10:00:00Z',
      diary_date: today(),
      timezone: 'Europe/Moscow',
      source: 'manual',
      created_at: '2026-09-15T10:00:00Z',
      updated_at: '2026-09-15T10:00:00Z',
    };
    (snapshot as DemoSessionSnapshot & { hydration?: Array<Record<string, unknown>> }).hydration = [
      entry,
    ];
    return entry;
  }
  if (/^\/api\/v1\/coach\/clients\/\d+\/workouts\/\d+\/comments$/.test(path) && method === 'POST') {
    const values = (body ?? {}) as { body?: string; workout_exercise_id?: number | null };
    return {
      id: 99001,
      trainer_author_id: 900000003,
      client_user_id: 51002,
      workout_id: 50011,
      workout_exercise_id: values.workout_exercise_id ?? null,
      body: values.body ?? '',
      body_format: 'plain_text',
      created_at: '2026-09-15T10:00:00Z',
      updated_at: null,
      revisions: [],
    };
  }
  return {};
}

async function installDemoTransport(page: Page) {
  const sessions = new Map<string, DemoSessionSnapshot>();
  let counter = 0;
  await page.route('**/api/v1/demo/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/sessions') && request.method() === 'POST') {
      const scenario = (request.postDataJSON() as { scenario: DemoScenario }).scenario;
      const token = `demo-token-${String(++counter).padStart(32, '0')}`;
      const snapshot = demoFixture(scenario);
      sessions.set(token, snapshot);
      await route.fulfill({ status: 201, json: { ...snapshot, session_token: token } });
      return;
    }
    const token = request.headers()['x-demo-session'];
    const snapshot = token ? sessions.get(token) : undefined;
    if (!token || !snapshot) {
      await route.fulfill({
        status: 410,
        json: { detail: 'Демо-сессия истекла. Начните новый сценарий.' },
      });
      return;
    }
    if (url.pathname.endsWith('/sessions/current') && request.method() === 'GET') {
      await route.fulfill({ status: 200, json: snapshot });
      return;
    }
    if (url.pathname.endsWith('/reset') && request.method() === 'POST') {
      const next = demoFixture(snapshot.scenario);
      sessions.set(token, next);
      await route.fulfill({ status: 200, json: next });
      return;
    }
    if (url.pathname.endsWith('/transport') && request.method() === 'POST') {
      const payload = request.postDataJSON() as { path: string; method: string; body: unknown };
      const result = transport(snapshot, payload.path, payload.method, payload.body);
      await route.fulfill({ status: 200, json: result });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: 'Неизвестный demo endpoint' } });
  });
}

test('demo uses production today composition and persists one workout set through demo transport', async ({
  page,
}) => {
  const transportRequests: Array<{ pathname: string; method: string; demoSession: string }> = [];
  const transportPayloads: Array<{ path: string; method: string; body: unknown }> = [];
  const directProductionRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.endsWith('/transport')) {
      transportPayloads.push(
        request.postDataJSON() as { path: string; method: string; body: unknown },
      );
      transportRequests.push({
        pathname: url.pathname,
        method: request.method(),
        demoSession: request.headers()['x-demo-session'] ?? '',
      });
    }
    if (url.pathname.startsWith('/api/v1/workouts/')) directProductionRequests.push(url.pathname);
  });
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await installDemoTransport(page);
  if (TASK_278_THEME) {
    await page.emulateMedia({ colorScheme: TASK_278_THEME });
    await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), TASK_278_THEME);
  }
  await page.goto('/');
  await page
    .locator('.landing-hero__actions')
    .getByRole('link', { name: 'Попробовать демо', exact: true })
    .click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=today');
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
  if (TASK_278_THEME) {
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', TASK_278_THEME);
  }
  await expect(page.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
  await expect(page.locator('.demo-cabinet-primary')).toHaveCount(0);
  await page.getByRole('button', { name: 'Продолжить' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=plan');
  await expect(page.getByRole('heading', { name: 'План', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: 'Сегодня', exact: true }).first().click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await expect(
    page.getByRole('heading', { name: 'Верх тела · уверенный старт', level: 2 }),
  ).toBeVisible();
  await page
    .getByRole('spinbutton', { name: 'Вес, Жим гантелей лёжа с контролируемой паузой, подход 3' })
    .fill('19');
  await page
    .getByRole('spinbutton', {
      name: 'Повторы, Жим гантелей лёжа с контролируемой паузой, подход 3',
    })
    .fill('8');
  const setButton = page.getByRole('button', { name: /Завершить:.*подход 3/ });
  await setButton.click();
  await expect(page.locator('.active-workout-rest')).toBeVisible();
  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await expect
    .poll(() =>
      transportPayloads.some((payload) => {
        const body = payload.body;
        return (
          payload.path.startsWith('/api/v1/workouts/sets/') &&
          typeof body === 'object' &&
          body !== null &&
          'actual_weight' in body &&
          body.actual_weight === 19 &&
          'actual_reps' in body &&
          body.actual_reps === 8 &&
          'is_completed' in body &&
          body.is_completed === true
        );
      }),
    )
    .toBe(true);
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(page.getByRole('heading', { name: 'Тренировка завершена', level: 2 })).toBeVisible();
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 1280, height: 720 },
  ]) {
    await page.setViewportSize(viewport);
    await expectNoHorizontalOverflow(page);
    const geometry = await page.evaluate(() => {
      const check = document.querySelector('.workout-completion__check')?.getBoundingClientRect();
      const icon = document
        .querySelector('.workout-completion__check svg')
        ?.getBoundingClientRect();
      const title = document.getElementById('workout-completion-title')?.getBoundingClientRect();
      if (!check || !icon || !title) return null;
      return {
        checkLeft: check.left,
        checkTop: check.top,
        checkRight: check.right,
        checkBottom: check.bottom,
        iconLeft: icon.left,
        iconRight: icon.right,
        iconTop: icon.top,
        iconBottom: icon.bottom,
        titleLeft: title.left,
      };
    });
    expect(geometry).not.toBeNull();
    expect(geometry!.iconLeft).toBeGreaterThanOrEqual(geometry!.checkLeft - 1);
    expect(geometry!.iconRight).toBeLessThanOrEqual(geometry!.checkRight + 1);
    expect(geometry!.iconTop).toBeGreaterThanOrEqual(geometry!.checkTop - 1);
    expect(geometry!.iconBottom).toBeLessThanOrEqual(geometry!.checkBottom + 1);
    expect(geometry!.checkRight).toBeLessThanOrEqual(geometry!.titleLeft + 1);
    await captureTask278Evidence(
      page,
      `completion-${viewport.width}x${viewport.height}-${TASK_278_THEME ?? 'default'}.png`,
    );
  }
  await page.getByRole('button', { name: 'Продолжить' }).click();
  await expect(page).toHaveURL('/demo?cabinet=1&scenario=self_training&section=progress');
  await expect(page.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(page.getByText('Готово. Вы посмотрели основной сценарий')).toBeVisible();
  expect(transportRequests.length).toBeGreaterThan(0);
  expect(transportRequests.every((request) => request.method === 'POST')).toBe(true);
  expect(transportRequests.every((request) => Boolean(request.demoSession))).toBe(true);
  expect(directProductionRequests).toEqual([]);
});

test('nutrition and coach scenarios render shared production surfaces with local mutations', async ({
  browser,
}) => {
  const nutritionContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const nutritionPage = await nutritionContext.newPage();
  await installDemoTransport(nutritionPage);
  await nutritionPage.goto('/demo?cabinet=1&scenario=nutrition&section=nutrition');
  await expect(nutritionPage.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();
  await expect(nutritionPage.getByRole('button', { name: 'Быстрый ввод' })).toBeVisible();
  await nutritionPage.getByRole('button', { name: 'Быстрый ввод' }).click();
  await expect(nutritionPage.getByRole('dialog')).toBeVisible();
  await nutritionPage.getByRole('spinbutton', { name: 'Калории' }).fill('420');
  await nutritionPage.getByRole('button', { name: 'Сохранить Quick Add' }).click();
  await expect(
    nutritionPage.getByText('Овсяная каша с бананом и греческим йогуртом'),
  ).toBeVisible();
  await nutritionPage.getByRole('button', { name: 'Продолжить' }).click();
  await expect(nutritionPage).toHaveURL('/demo?cabinet=1&scenario=nutrition&section=progress');
  await expect(nutritionPage.getByRole('heading', { name: 'Прогресс', exact: true })).toBeVisible();
  await expect(nutritionPage.getByText('Готово. Вы посмотрели основной сценарий')).toBeVisible();
  await nutritionContext.close();

  const planContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const planPage = await planContext.newPage();
  await installDemoTransport(planPage);
  await planPage.goto('/demo?cabinet=1&scenario=self_training&section=plan');
  await expect(planPage.getByText(/Управление программой недоступно/)).toBeVisible();
  await expect(planPage.locator('fieldset.demo-capability-fieldset')).toHaveAttribute(
    'disabled',
    '',
  );
  await expect(planPage.getByRole('link', { name: 'Управление программой' })).toHaveCount(0);
  await captureEvidence(planPage, 'disabled-plan-390x844-light.png');
  await planContext.close();

  const trainerContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const trainerPage = await trainerContext.newPage();
  await installDemoTransport(trainerPage);
  await trainerPage.goto('/demo?cabinet=1&scenario=trainer&section=trainer');
  await expect(trainerPage.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await expect(
    trainerPage.getByRole('button', { name: 'Пригласить клиента' }).first(),
  ).toBeDisabled();
  for (const width of [320, 360, 390, 430]) {
    await assertBottomNavigationGeometry(trainerPage, width);
    await captureTask291Evidence(trainerPage, `demo-trainer-navigation-${width}-light.png`);
  }
  await captureTask291Evidence(trainerPage, 'demo-trainer-mobile-light.png');
  await trainerPage.getByRole('button', { name: 'Клиенты', exact: true }).click();
  await expect(trainerPage.getByRole('button', { name: /^Алексей/ })).toBeVisible();
  await trainerPage.getByRole('button', { name: /^Алексей/ }).click();
  await captureTask291Evidence(trainerPage, 'demo-trainer-mobile-client-light.png');
  await trainerPage.setViewportSize({ width: 1440, height: 900 });
  await trainerPage.getByRole('button', { name: 'Сегодня', exact: true }).click();
  await expect(trainerPage.getByRole('heading', { name: 'Что требует действия?' })).toBeVisible();
  await captureTask291Evidence(trainerPage, 'demo-trainer-desktop-light.png');
  await trainerPage.getByRole('button', { name: 'Клиенты', exact: true }).click();
  await trainerPage.getByRole('button', { name: /^Алексей/ }).click();
  await trainerPage.getByLabel('Данные клиента').getByRole('link', { name: 'Прогресс' }).click();
  const progressDisclosure = trainerPage.locator('details#coach-client-progress');
  if ((await progressDisclosure.getAttribute('open')) === null) {
    await progressDisclosure.locator(':scope > summary').click();
  }
  await expect(progressDisclosure).toHaveAttribute('open', '');
  await expect(trainerPage.getByText('Лента тренировок')).toBeVisible();
  const workoutTitle = trainerPage.getByText('Ноги и корпус', { exact: true }).last();
  await expect(workoutTitle).toBeVisible();
  await workoutTitle.click();
  await trainerPage.getByText('Комментарий тренера', { exact: true }).click();
  await trainerPage.getByLabel('Комментарий', { exact: true }).fill('Хороший контроль темпа.');
  await trainerPage.getByRole('button', { name: 'Отправить комментарий' }).click();
  await expect(trainerPage.getByText('Хороший контроль темпа.')).toBeVisible();
  await trainerContext.close();
});

test('trainer demo follows the connected Today-to-Today route', async ({ page }) => {
  if (TASK_293_VIEWPORT) {
    const [width = 390, height = 844] = TASK_293_VIEWPORT.split('x').map(Number);
    await page.setViewportSize({ width, height });
  }
  if (TASK_293_THEME) {
    await page.emulateMedia({ colorScheme: TASK_293_THEME, reducedMotion: 'reduce' });
    await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), TASK_293_THEME);
  }
  await installDemoTransport(page);
  await page.goto('/demo?cabinet=1&scenario=trainer&section=trainer');
  await expect(page.getByRole('heading', { name: 'Сегодня', level: 1 })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Требует внимания' })).toBeVisible();
  await captureTask293Evidence(page, `${TASK_293_VARIANT}-trainer-demo-start.png`);

  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  const attentionAction = page.getByRole('link', { name: 'Назначить программу', exact: true });
  await attentionAction.click();
  await expect(page).toHaveURL(/client_id=51003/);
  await expect(page.getByRole('heading', { name: 'Иван', level: 2 })).toBeVisible();
  await captureTask293Evidence(page, `${TASK_293_VARIANT}-trainer-demo-client.png`);

  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('link', { name: 'Последние события', exact: true }).click();
  await page
    .getByLabel('Данные клиента')
    .getByRole('link', { name: 'Прогресс', exact: true })
    .click();

  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await expect(page).toHaveURL(/section=trainer.*demo_step=operations/);
  await expect(page.getByRole('heading', { name: 'Сегодня', level: 1 })).toBeVisible();
  await captureTask293Evidence(page, `${TASK_293_VARIANT}-trainer-demo-operations.png`);

  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('button', { name: /Задачи клиентов/ }).click();
  await expect(page.locator('#coach-tasks-title')).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await expect(page.locator('#coach-tasks-title')).toBeFocused();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await expect(page).toHaveURL(/section=trainer.*demo_step=return/);
  await expect(page.getByRole('heading', { name: 'Сегодня', level: 1 })).toBeVisible();
  await expect(page.getByText('Основной сценарий завершён')).toBeVisible();
  await captureTask293Evidence(page, `${TASK_293_VARIANT}-trainer-demo-complete.png`);
});

test('demo exposes deterministic loading and error states without leaving the boundary', async ({
  browser,
}) => {
  const loadingContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    serviceWorkers: 'block',
  });
  const loadingPage = await loadingContext.newPage();
  await installDemoTransport(loadingPage);
  let pendingSessionRoute: import('@playwright/test').Route | null = null;
  await loadingPage.route('**/api/v1/demo/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      pendingSessionRoute = route;
      return;
    }
    await route.fallback();
  });
  await loadingPage.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await expect(loadingPage.locator('[data-demo-state="loading"]')).toBeVisible();
  await expect(loadingPage.getByText('Готовим демо-кабинет…')).toBeVisible();
  await captureEvidence(loadingPage, 'loading-390x844-light.png');
  await expect.poll(() => pendingSessionRoute).not.toBeNull();
  await pendingSessionRoute!.abort();
  await expect(loadingPage.locator('[data-demo-state="error"]')).toBeVisible();
  await captureEvidence(loadingPage, 'error-aborted-390x844-light.png');
  await loadingContext.close();

  const errorContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    serviceWorkers: 'block',
  });
  const errorPage = await errorContext.newPage();
  await installDemoTransport(errorPage);
  await errorPage.route('**/api/v1/demo/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 503, json: { detail: 'Демо временно недоступно.' } });
      return;
    }
    await route.fallback();
  });
  await errorPage.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await expect(errorPage.locator('[data-demo-state="error"]')).toBeVisible();
  await expect(errorPage.getByText('Демо временно недоступно.')).toBeVisible();
  await expect(errorPage.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
  await captureEvidence(errorPage, 'error-503-390x844-light.png');
  await errorContext.close();
});

test('demo reload, reset, expiry and isolated sessions preserve the session boundary', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await installDemoTransport(page);
  await page.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await expect(
    page.getByRole('heading', { name: 'Верх тела · уверенный старт', level: 2 }),
  ).toBeVisible();
  await page.getByRole('button', { name: /Завершить:.*подход 3/ }).click();
  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();

  await page.getByRole('button', { name: 'Начать заново', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();

  const expiredSession = async (route: import('@playwright/test').Route) => {
    await route.fulfill({
      status: 410,
      json: { detail: 'Демо-сессия истекла. Начните новый сценарий.' },
    });
  };
  await page.route('**/api/v1/demo/sessions/current', expiredSession);
  await page.reload();
  await expect(page.locator('[data-demo-state="error"]')).toBeVisible();
  await expect(page.getByText('Демо-сессия истекла. Начните новый сценарий.')).toBeVisible();
  await page.unroute('**/api/v1/demo/sessions/current', expiredSession);
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  await context.close();

  const firstContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const secondContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const firstPage = await firstContext.newPage();
  const secondPage = await secondContext.newPage();
  await installDemoTransport(firstPage);
  await installDemoTransport(secondPage);
  await firstPage.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await secondPage.goto('/demo?cabinet=1&scenario=self_training&section=today');
  await firstPage.getByRole('button', { name: 'Начать тренировку' }).click();
  await firstPage.getByRole('button', { name: /Завершить:.*подход 3/ }).click();
  await expect(firstPage.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await expect(secondPage.getByRole('button', { name: 'Начать тренировку' })).toBeVisible();
  await expect(secondPage.getByText('Все подходы отмечены — можно завершать.')).toHaveCount(0);
  await firstContext.close();
  await secondContext.close();
});

for (const viewport of DEMO_VIEWPORTS) {
  for (const colorScheme of ['light', 'dark'] as const) {
    test(`production composition keeps responsive geometry, utility and keyboard focus (${viewport.name} ${colorScheme})`, async ({
      browser,
    }) => {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        colorScheme,
        isMobile: viewport.mobile,
        hasTouch: viewport.mobile,
      });
      try {
        const page = await context.newPage();
        await installDemoTransport(page);
        await page.goto('/demo?cabinet=1&scenario=self_training&section=today');
        await expect(page.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
        await expect(page.locator('.app-bottom-nav')).toBeVisible();
        await expectNoHorizontalOverflow(page);
        await expectDockWithinViewport(page);
        await expectElementsWithinHorizontalViewport(
          page,
          '.demo-cabinet-boundary, .demo-route, .app-section',
        );
        await expectUiAuditClean(page, `demo today ${viewport.name} ${colorScheme} top`, {
          checkTouchTargets: viewport.mobile,
        });
        await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
        await expectUiAuditClean(page, `demo today ${viewport.name} ${colorScheme} bottom`, {
          checkTouchTargets: viewport.mobile,
        });
        await page.evaluate(() => window.scrollTo(0, 0));

        if (viewport.mobile) {
          const moreButton = page.getByRole('button', { name: 'Сценарии', exact: true });
          await moreButton.focus();
          await expect(moreButton).toBeFocused();
          await moreButton.press('Enter');
          await expect(page.locator('#appMorePanel')).toBeVisible();
          await expect(page.locator('#appMorePanel .app-more-panel__close')).toBeFocused();
          await page.keyboard.press('Escape');
          await expect(moreButton).toBeFocused();

          const safeArea = await page.evaluate(() => {
            document.documentElement.style.setProperty('--yfc-tg-safe-bottom', '24px');
            document.documentElement.style.setProperty('--yfc-tg-content-safe-bottom', '12px');
            return {
              safeBottom: document.documentElement.style.getPropertyValue('--yfc-tg-safe-bottom'),
              contentSafeBottom: document.documentElement.style.getPropertyValue(
                '--yfc-tg-content-safe-bottom',
              ),
            };
          });
          expect(safeArea).toEqual({ safeBottom: '24px', contentSafeBottom: '12px' });
        } else {
          await expect(page.locator('.app-bottom-nav__utility')).toBeVisible();
          await expect(
            page.locator('.app-bottom-nav__utility .app-bottom-nav__demo-exit'),
          ).toBeVisible();
        }
        await captureEvidence(page, `${viewport.name}-${colorScheme}-today.png`);
      } finally {
        await context.close();
      }
    });
  }
}
