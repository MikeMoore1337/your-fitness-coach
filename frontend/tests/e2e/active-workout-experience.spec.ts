import { expect, test, type Locator, type Page } from '@playwright/test';
import { expectTouchTargets } from './fixtures/mobile-tma';

const mediaThumbnailUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';
const mediaAnimationUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif';

test.use({ serviceWorkers: 'block', video: 'on' });

const captureLandingProductProofs =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_LANDING_PRODUCT_PROOFS === '1';
const captureTask520VisualPackage =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TASK_520_VISUALS === '1';

type SetState = {
  actual_reps: number | null;
  actual_weight: number | null;
  duration_minutes?: number | null;
  distance_km?: number | null;
  average_heart_rate_bpm?: number | null;
  heart_rate_zone?: number | null;
  rir: '0' | '1' | '2' | '3' | '4+' | null;
  set_kind: 'warmup' | 'working' | 'drop' | null;
  reached_failure: boolean | null;
  is_completed: boolean;
  version: number;
  planned_role?:
    | 'warmup'
    | 'working'
    | 'top'
    | 'backoff'
    | 'drop'
    | 'activation'
    | 'mini_set'
    | 'cluster_member'
    | null;
  planned_group_id?: number | null;
  planned_group_kind?:
    | 'sequence'
    | 'superset'
    | 'rest_pause'
    | 'myo_reps'
    | 'cluster'
    | 'drop_chain'
    | 'circuit'
    | null;
};

async function mockActiveWorkout(
  page: Page,
  mixed = false,
  mediaState: 'approved_animated' | 'blocked' = 'approved_animated',
  targetStarted = false,
  setupMemoryBody: string | null = null,
) {
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  let finished = false;
  let replacementApplied = false;
  let warmupProposalApplied = false;
  let setupMemory = setupMemoryBody
    ? {
        id: 501,
        exercise_id: 11,
        body: setupMemoryBody,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    : null;
  let failSetPatch = false;
  let resolveCardioCompleted!: () => void;
  const cardioCompleted = new Promise<void>((resolve) => {
    resolveCardioCompleted = resolve;
  });
  const sets = new Map<number, SetState>([
    [
      201,
      {
        actual_reps: targetStarted ? 1 : null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: null,
        is_completed: false,
        version: 1,
        planned_role: 'top',
      },
    ],
    [
      202,
      {
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: null,
        is_completed: false,
        version: 1,
        planned_role: 'backoff',
      },
    ],
    [
      203,
      {
        actual_reps: null,
        actual_weight: null,
        rir: null,
        set_kind: 'working',
        reached_failure: null,
        is_completed: false,
        version: 1,
        planned_role: 'backoff',
      },
    ],
    ...(mixed
      ? ([
          [
            204,
            {
              actual_reps: null,
              actual_weight: null,
              duration_minutes: null,
              distance_km: null,
              average_heart_rate_bpm: null,
              heart_rate_zone: null,
              rir: null,
              set_kind: null,
              reached_failure: null,
              is_completed: false,
              version: 1,
            },
          ],
        ] as Array<[number, SetState]>)
      : []),
  ]);
  const workout = () => ({
    id: 42,
    scheduled_date: today,
    title: 'Силовая база',
    status: 'in_progress',
    day_number: 1,
    week_number: 1,
    started_at: new Date(Date.now() - 12 * 60_000).toISOString(),
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: replacementApplied ? 13 : 11,
        exercise_title: replacementApplied ? 'Жим гантелей лёжа' : 'Жим штанги лёжа',
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        notes: 'Сохраняйте устойчивое положение корпуса.',
        setup_memory: setupMemory,
        has_guide: true,
        media_state: mediaState,
        media_thumbnail_url: mediaState === 'approved_animated' ? mediaThumbnailUrl : null,
        media_animation_url: mediaState === 'approved_animated' ? mediaAnimationUrl : null,
        sets: [...sets]
          .filter(([id]) => id !== 204)
          .sort(([leftId, leftState], [rightId, rightState]) => {
            if (warmupProposalApplied) {
              const leftWarmup = leftState.set_kind === 'warmup';
              const rightWarmup = rightState.set_kind === 'warmup';
              if (leftWarmup !== rightWarmup) return leftWarmup ? -1 : 1;
            }
            return leftId - rightId;
          })
          .map(([id, state]) => ({
            id,
            set_number: id >= 301 ? id - 297 : id - 200,
            ...state,
          })),
      },
      ...(mixed
        ? [
            {
              id: 102,
              exercise_id: 12,
              exercise_title: 'Велотренажёр',
              metric_type: 'cardio',
              sort_order: 2,
              prescribed_sets: 1,
              prescribed_reps: '',
              prescribed_duration_minutes: 25,
              rest_seconds: 0,
              notes: 'Ровный разговорный темп.',
              has_guide: false,
              progression_guidance: null,
              sets: [{ id: 204, set_number: 1, ...sets.get(204)! }],
            },
          ]
        : []),
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
    if (path.endsWith('/auth/telegram/init')) {
      return route.fulfill({ json: { access_token: 'telegram-test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/public/articles') && request.method() === 'GET') {
      return route.fulfill({ json: [] });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({
        json: {
          id: 7,
          first_name: 'Тест',
          is_coach: false,
          is_admin: false,
          has_active_program: true,
          has_workout_history: true,
          onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
          profile: { full_name: 'Тестовый пользователь', timezone: 'Europe/Moscow' },
          trainer: null,
        },
      });
    }
    if (path.endsWith('/workouts/today')) {
      if (finished) {
        return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка завершена' } });
      }
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: {
          training: { last_completed_workout_on: finished ? today : null, next_workout: null },
          body: { latest_measurement: null, trends: [] },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
          },
        },
      });
    }
    if (path.endsWith('/nutrition/diary')) {
      return route.fulfill({
        json: {
          diary_date: today,
          timezone: 'Europe/Moscow',
          meals: [],
          totals: { energy_kcal: '0', protein_g: '0', fat_g: '0', carbs_g: '0', fiber_g: null },
          targets: null,
          remaining: null,
        },
      });
    }
    if (path.endsWith('/programs/exercises/11')) {
      return route.fulfill({
        json: {
          id: 11,
          title: 'Жим штанги лёжа',
          metric_type: 'strength',
          primary_muscle: 'Грудь',
          equipment: 'Штанга и скамья',
          primary_muscle_ids: ['chest'],
          secondary_muscle_ids: ['triceps'],
          equipment_ids: ['barbell', 'bench'],
          alternatives: [],
          difficulty_level: 'beginner',
          is_custom: false,
          is_personalized: false,
          has_guide: true,
          guide: {
            technique_steps: ['Сведите лопатки.', 'Опускайте штангу под контролем.'],
            breathing: 'Вдох при опускании, выдох после тяжёлой части подъёма.',
            common_mistakes: ['Отрыв таза от скамьи'],
            muscles: [
              {
                identifier: 'chest',
                name: 'Грудь',
                role_id: 'primary',
                role: 'Основная',
                function: 'Перемещает руку вперёд в фазе усилия.',
              },
            ],
            equipment: [
              { identifier: 'barbell', name: 'Штанга' },
              { identifier: 'bench', name: 'Скамья' },
            ],
            safety_notes: ['Используйте страховку при тяжёлых подходах.'],
            alternatives: [],
            media: [
              {
                type: 'animation',
                url: mediaAnimationUrl,
                poster: mediaThumbnailUrl,
                phase_id: 'movement',
                phase: 'Движение',
                alt: 'Жим штанги лёжа: движение',
                source_name: 'Gym visual',
                source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
                source_license: 'Owner-purchased GymVisual license',
                source_license_url: 'https://gymvisual.com/',
                asset_id: 'gymvisual:0025:EIeI8Vf',
                asset_version: 'gymvisual-7455efae',
                variant_key: 'movement',
                width: 180,
                height: 180,
                byte_size: 12000,
                sort_order: 0,
                sources: [
                  {
                    url: mediaAnimationUrl,
                    mime_type: 'image/gif',
                    width: 180,
                    height: 180,
                    byte_size: 12000,
                  },
                  {
                    url: mediaThumbnailUrl,
                    mime_type: 'image/jpeg',
                    width: 180,
                    height: 180,
                    byte_size: 9000,
                  },
                ],
              },
            ],
            images: [
              {
                phase: 'Движение',
                url: mediaAnimationUrl,
                alt: 'Жим штанги лёжа: движение',
              },
            ],
            media_reference: 'exercise-guides:bench-press',
            source_name: 'Gym visual',
            source_url: 'https://github.com/hasaneyldrm/exercises-dataset',
            source_license: 'Owner-purchased GymVisual license',
            source_license_url: 'https://gymvisual.com/',
          },
        },
      });
    }
    if (path.endsWith('/programs/exercises/11/history')) {
      const previousWorkout = {
        workout_id: 41,
        workout_title: 'Прошлая тренировка',
        performed_on: today,
        completed_at: new Date(Date.now() - 7 * 86_400_000).toISOString(),
      };
      return route.fulfill({
        json: {
          exercise_id: 11,
          exercise_title: 'Жим штанги лёжа',
          metric_type: 'strength',
          load_unit: 'kg',
          last_performed: previousWorkout,
          best_authoritative_load: { value_kg: 40, workout: previousWorkout, reps: 8 },
          estimated_1rm: {
            kind: 'estimated',
            formula: 'brzycki',
            value_kg: 50,
            workout: previousWorkout,
            reps: 8,
            load_kg: 40,
          },
          rep_prs: [],
          windows: [7, 30, 90].map((days) => ({
            days,
            period_start: today,
            period_end: today,
            performed_session_count: 0,
            completed_set_count: 0,
            authoritative_set_count: 0,
            reps_total: 0,
            best_authoritative_load_kg: null,
            estimated_1rm_kg: null,
          })),
          recent_sessions: [
            {
              workout: previousWorkout,
              workout_exercise_id: 101,
              prescribed_reps: '8–10',
              completed_set_count: 1,
              authoritative_set_count: 1,
              reps_total: 8,
              max_authoritative_load_kg: 40,
              best_set_volume_kg: 320,
              estimated_1rm_kg: 50,
              sets: [
                {
                  set_number: 1,
                  reps: 8,
                  load_kg: 40,
                  volume_kg: 320,
                  rir: '2',
                  set_kind: 'working',
                  planned_role: 'working',
                  analytics_bucket: 'working',
                  pr_eligible: true,
                },
              ],
            },
          ],
          progression: [],
          progression_events: [],
          history_truncated: false,
        },
      });
    }
    if (path.endsWith('/workouts/42/exercises/101/alternatives')) {
      return route.fulfill({
        json: [
          {
            exercise_id: 13,
            title: 'Жим гантелей лёжа',
            equipment_ids: ['dumbbell', 'bench'],
            score: 0.96,
            reason_keys: ['same_movement_pattern', 'same_primary_muscle'],
          },
        ],
      });
    }
    if (path.endsWith('/workouts/42/exercises/101/warmup-proposals/preview')) {
      return route.fulfill({
        json: {
          status: 'proposal',
          workout_id: 42,
          workout_exercise_id: 101,
          ruleset_version: 'warmup-proposal-v1',
          working_weight_kg: 80,
          rows: [
            { weight_kg: 32, reps: 8 },
            { weight_kg: 48, reps: 5 },
            { weight_kg: 60, reps: 3 },
          ],
          max_rows: 5,
          state_token: 'a'.repeat(64),
          proposal_token: 'b'.repeat(64),
          message: 'Предложение рассчитано от рабочего веса: 40%, 60% и 75%.',
        },
      });
    }
    const setupMemoryMatch = path.match(/\/me\/exercise-setup-memories\/(\d+)$/);
    if (setupMemoryMatch && Number(setupMemoryMatch[1]) === 11) {
      if (request.method() === 'GET') return route.fulfill({ json: setupMemory });
      if (request.method() === 'PUT') {
        const body = request.postDataJSON() as { body?: string; expected_version?: number | null };
        setupMemory = {
          id: setupMemory?.id ?? 501,
          exercise_id: 11,
          body: String(body.body ?? ''),
          version: (setupMemory?.version ?? 0) + 1,
          created_at: setupMemory?.created_at ?? new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        return route.fulfill({ json: setupMemory });
      }
      if (request.method() === 'DELETE') {
        setupMemory = null;
        return route.fulfill({ status: 204, body: '' });
      }
    }
    if (path.endsWith('/workouts/42/exercises/101/warmup-proposals/apply')) {
      const body = request.postDataJSON() as {
        rows?: Array<{ weight_kg: number; reps: number }>;
      };
      warmupProposalApplied = true;
      body.rows?.forEach((row, index) => {
        sets.set(301 + index, {
          actual_reps: row.reps,
          actual_weight: row.weight_kg,
          rir: null,
          set_kind: 'warmup',
          reached_failure: null,
          is_completed: false,
          version: 1,
          planned_role: 'warmup',
        });
      });
      return route.fulfill({
        json: {
          workout_id: 42,
          workout_exercise_id: 101,
          ruleset_version: 'warmup-proposal-v1',
          idempotent: false,
          materialized_set_ids: [...(body.rows ?? [])].map((_, index) => 301 + index),
          workout: workout(),
        },
      });
    }
    if (path.endsWith('/workouts/42/adaptations/preview')) {
      const body = request.postDataJSON() as { reason?: string } | null;
      if (body?.reason === 'pain_or_injury') {
        return route.fulfill({
          json: {
            status: 'safety_stop',
            workout_id: 42,
            reason: 'pain_or_injury',
            ruleset_version: 'workout-adaptation-v2',
            original_estimated_minutes: 30,
            adapted_estimated_minutes: 30,
            time_budget_minutes: null,
            changes: [],
            original_exercises: [],
            adapted_exercises: [],
            warnings: [],
            message: 'При боли приложение не подбирает медицинскую замену.',
            preview_token: null,
          },
        });
      }
      return route.fulfill({
        json: {
          status: 'preview',
          workout_id: 42,
          reason: 'replace_exercise',
          ruleset_version: 'workout-adaptation-v2',
          original_estimated_minutes: 30,
          adapted_estimated_minutes: 31,
          time_budget_minutes: null,
          changes: [
            {
              kind: 'replaced',
              workout_exercise_id: 101,
              from_exercise_id: 11,
              from_title: 'Жим штанги лёжа',
              to_exercise_id: 13,
              to_title: 'Жим гантелей лёжа',
              transfer: 'compatible_with_load_reset',
              load_reset_required: true,
              reason_keys: ['same_movement_pattern', 'same_primary_muscle'],
            },
          ],
          original_exercises: [
            {
              workout_exercise_id: 101,
              exercise_id: 11,
              title: 'Жим штанги лёжа',
              equipment_ids: ['barbell', 'bench'],
              prescribed_sets: 3,
              prescribed_reps: '8–10',
              rest_seconds: 90,
              sort_order: 1,
              priority: 'core',
            },
          ],
          adapted_exercises: [
            {
              workout_exercise_id: 101,
              exercise_id: 13,
              title: 'Жим гантелей лёжа',
              equipment_ids: ['dumbbell', 'bench'],
              prescribed_sets: 3,
              prescribed_reps: '8–10',
              rest_seconds: 90,
              sort_order: 1,
              priority: 'core',
            },
          ],
          warnings: ['После замены рабочий вес потребуется подтвердить заново.'],
          message: 'Выбранная замена подходит по доступному оборудованию.',
          preview_token: 'task-520-preview-token',
        },
      });
    }
    if (path.endsWith('/workouts/42/adaptations/apply')) {
      replacementApplied = true;
      return route.fulfill({
        json: {
          adaptation_id: 9,
          applied_at: new Date().toISOString(),
          workout: workout(),
        },
      });
    }
    const setMatch = path.match(/\/workouts\/sets\/(\d+)$/);
    if (setMatch) {
      if (failSetPatch) {
        return route.fulfill({ status: 503, json: { detail: 'Сервис временно недоступен' } });
      }
      const setId = Number(setMatch[1]);
      const current = sets.get(setId)!;
      const body = request.postDataJSON() as Partial<SetState>;
      const next = {
        ...current,
        actual_reps: body.actual_reps ?? null,
        actual_weight: body.actual_weight ?? null,
        duration_minutes: body.duration_minutes ?? null,
        distance_km: body.distance_km ?? null,
        average_heart_rate_bpm: body.average_heart_rate_bpm ?? null,
        heart_rate_zone: body.heart_rate_zone ?? null,
        rir: body.rir ?? null,
        set_kind: body.set_kind ?? null,
        reached_failure: body.reached_failure ?? null,
        is_completed: body.is_completed ?? false,
        version: current.version + 1,
      };
      sets.set(setId, next);
      if (setId === 204 && next.is_completed) resolveCardioCompleted();
      return route.fulfill({
        json: { id: setId, set_number: setId === 204 ? 1 : setId - 200, ...next },
      });
    }
    if (path.endsWith('/workouts/42/finish')) {
      finished = true;
      return route.fulfill({ status: 204, body: '' });
    }
    return route.fulfill({ json: [] });
  });

  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.jpg(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg',
        contentType: 'image/jpeg',
      }),
  );
  await page.route(
    /\/static\/exercise-guides\/gymvisual\/bench-press-0025-EIeI8Vf\.gif(?:\?.*)?$/,
    (route) =>
      route.fulfill({
        path: '../backend/assets/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif',
        contentType: 'image/gif',
      }),
  );

  return {
    failSetPatch(value: boolean) {
      failSetPatch = value;
    },
    cardioCompleted,
  };
}

function waitForCompletedSetPatch(page: Page, setId: number) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    if (
      response.request().method() !== 'PATCH' ||
      !url.pathname.endsWith(`/workouts/sets/${setId}`) ||
      !response.ok()
    ) {
      return false;
    }
    try {
      return response.request().postDataJSON()?.is_completed === true;
    } catch {
      return false;
    }
  });
}

function waitForSetPatch(page: Page, setId: number) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      response.request().method() === 'PATCH' &&
      url.pathname.endsWith(`/workouts/sets/${setId}`) &&
      response.ok()
    );
  });
}

async function clickDetailsSummary(summary: Locator) {
  await summary.evaluate((element) =>
    element.scrollIntoView({ block: 'center', inline: 'nearest' }),
  );
  await summary.click();
}

async function expectClearOfBottomDock(target: Locator, label: string) {
  await target.scrollIntoViewIfNeeded();
  const geometry = await target.evaluate((element) => {
    const dock = document.querySelector<HTMLElement>('#appBottomNav');
    const targetRect = element.getBoundingClientRect();
    const dockRect = dock?.getBoundingClientRect();
    const dockStyle = dock ? getComputedStyle(dock) : null;
    const dockVisible = Boolean(
      dockRect &&
      dockRect.width > 0 &&
      dockRect.height > 0 &&
      dockStyle?.display !== 'none' &&
      dockStyle?.visibility !== 'hidden',
    );
    return {
      dockTop: dockRect ? Math.round(dockRect.top) : null,
      dockVisible,
      targetBottom: Math.round(targetRect.bottom),
      targetHeight: Math.round(targetRect.height),
    };
  });

  expect(geometry.targetHeight, `${label} must be in the viewport`).toBeGreaterThan(0);
  if (geometry.dockVisible) {
    expect(
      geometry.targetBottom,
      `${label} bottom ${geometry.targetBottom}px must stay above dock top ${geometry.dockTop}px with 8px clearance`,
    ).toBeLessThanOrEqual((geometry.dockTop ?? 0) - 8);
  }
}

async function expectRealMediaFullWidth(page: Page, label: string) {
  const geometry = await page.evaluate(() => {
    const media = document.querySelector<HTMLElement>(
      '.active-workout-exercise__media:not(.active-workout-exercise__media--blocked)',
    );
    const technique = document.querySelector<HTMLElement>(
      '.active-workout-exercise__head .exercise-guide-trigger',
    );
    const image = media?.querySelector<HTMLImageElement>('img');
    if (!media || !technique || !image) return null;

    const mediaRect = media.getBoundingClientRect();
    const techniqueRect = technique.getBoundingClientRect();
    const imageRect = image.getBoundingClientRect();
    const techniqueStyle = getComputedStyle(technique);
    const actions = technique.parentElement as HTMLElement | null;
    const actionsRect = actions?.getBoundingClientRect();
    const actionsStyle = actions ? getComputedStyle(actions) : null;
    return {
      imageWidth: imageRect.width,
      mediaLeft: mediaRect.left,
      mediaRight: mediaRect.right,
      mediaWidth: mediaRect.width,
      techniqueLeft: techniqueRect.left,
      techniqueRight: techniqueRect.right,
      techniqueWidth: techniqueRect.width,
      techniqueCssWidth: techniqueStyle.width,
      techniqueFlex: techniqueStyle.flex,
      actionsWidth: actionsRect?.width ?? null,
      actionsDisplay: actionsStyle?.display ?? null,
      actionsFlexWrap: actionsStyle?.flexWrap ?? null,
      actionsGap: actionsStyle?.gap ?? null,
    };
  });

  expect(geometry, `${label}: real media geometry must be measurable`).not.toBeNull();
  const tolerance = 2;
  expect(
    Math.abs((geometry?.mediaLeft ?? 0) - (geometry?.techniqueLeft ?? 0)),
    `${label}: media and Technique left edges must align`,
  ).toBeLessThanOrEqual(tolerance);
  expect(
    Math.abs((geometry?.mediaRight ?? 0) - (geometry?.techniqueRight ?? 0)),
    `${label}: media and Technique right edges must align ${JSON.stringify(geometry)}`,
  ).toBeLessThanOrEqual(tolerance);
  expect(
    geometry?.mediaWidth ?? 0,
    `${label}: media wrapper must fill the workout content column`,
  ).toBeGreaterThanOrEqual((geometry?.techniqueWidth ?? 0) - tolerance);
  expect(
    geometry?.imageWidth ?? 0,
    `${label}: rendered image must fill the media wrapper`,
  ).toBeGreaterThanOrEqual((geometry?.mediaWidth ?? 0) - tolerance);
}

async function resetPageScroll(page: Page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.querySelector<HTMLElement>('#appContent')?.scrollTo(0, 0);
  });
}

async function installMockedTelegram(page: Page) {
  await page.addInitScript(() => {
    const handlers = new Map<string, Set<() => void>>();
    const backState = { hide: 0, show: 0 };
    const backButton = {
      show() {
        backState.show += 1;
      },
      hide() {
        backState.hide += 1;
      },
      setText() {},
      enable() {},
      disable() {},
      onClick() {},
      offClick() {},
    };
    const telegram = {
      initData: 'signed-test-data',
      initDataUnsafe: {},
      isActive: true,
      viewportHeight: 560,
      viewportStableHeight: 844,
      safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
      colorScheme: 'dark' as const,
      themeParams: {},
      BackButton: backButton,
      ready() {},
      expand() {},
      onEvent(event: string, callback: () => void) {
        const callbacks = handlers.get(event) ?? new Set<() => void>();
        callbacks.add(callback);
        handlers.set(event, callbacks);
      },
      offEvent(event: string, callback: () => void) {
        handlers.get(event)?.delete(callback);
      },
    };
    Object.assign(window, {
      Telegram: { WebApp: telegram },
      __backButtonState: backState,
    });
  });
}

test('V9-01 replaces only an untouched active exercise and survives refresh', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first();
  await expect(
    exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
  await exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }).click();
  await expect(
    page.getByRole('heading', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
  await page.getByRole('checkbox', { name: 'Гантели' }).check();
  await page.getByRole('checkbox', { name: 'Скамья' }).check();
  await page.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();
  await page.getByRole('button', { name: 'Показать изменения' }).click();
  await expect(page.getByRole('heading', { name: 'Что изменится' })).toBeVisible();
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page.getByText('Изменения применены только к сегодняшней тренировке')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('button', { name: 'Продолжить тренировку' })).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();
});

test('V9-01 replaces an untouched active exercise in mocked TMA', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installMockedTelegram(page);
  await mockActiveWorkout(page);
  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first();
  await expect(
    exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
  await exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }).click();
  await page.getByRole('checkbox', { name: 'Гантели' }).check();
  await page.getByRole('checkbox', { name: 'Скамья' }).check();
  await page.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();
  await page.getByRole('button', { name: 'Показать изменения' }).click();
  await expect(page.getByRole('heading', { name: 'Что изменится' })).toBeVisible();
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-01 desktop smoke keeps replacement scoped to the current workout', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first();
  await expect(
    exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
  await exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }).click();
  await page.getByRole('checkbox', { name: 'Гантели' }).check();
  await page.getByRole('checkbox', { name: 'Скамья' }).check();
  await page.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();
  await page.getByRole('button', { name: 'Показать изменения' }).click();
  await page.getByRole('button', { name: 'Применить' }).click();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-01 does not offer replacement after the target has actual data', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, false, 'approved_animated', true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first();
  await expect(
    exercise.getByRole('button', { name: 'Заменить только в этой тренировке' }),
  ).toHaveCount(0);
});

test('V9-01 keeps pain inside the safety-stop boundary', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  await page.getByRole('button', { name: 'Боль или травма во время тренировки' }).click();
  await page.getByRole('button', { name: 'Показать рекомендации' }).click();
  await expect(page.getByRole('heading', { name: 'Безопасность прежде всего' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Применить' })).toHaveCount(0);
});

test('V9-01 keeps replacement unavailable offline without local mutation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const replacement = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first()
    .getByRole('button', { name: 'Заменить только в этой тренировке' });
  await expect(replacement).toBeEnabled();
  await page.context().setOffline(true);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await expect(replacement).toBeDisabled();
  await expect(page.getByText(/Замена требует подключения к интернету/)).toBeVisible();
  await page.context().setOffline(false);
});

test('V9-02 keeps warm-up editable until confirmation and survives reload', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await Promise.all([
    waitForSetPatch(page, 201),
    currentSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('80'),
  ]);
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  const warmupEntry = currentSet.getByTestId('warmup-proposal-entry');
  await expect(warmupEntry.getByRole('button', { name: 'Подготовить разминку' })).toBeVisible();
  await warmupEntry.getByRole('button', { name: 'Подготовить разминку' }).click();
  expect(page.getByRole('button', { name: 'Добавить в тренировку' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Рассчитать предложение' }).click();
  await expect(page.getByRole('heading', { name: 'Проверьте подходы' })).toBeVisible();
  await expect(page.getByLabel('Вес разминки, подход 1')).toHaveValue('32');
  await page.getByLabel('Вес разминки, подход 1').fill('30');
  await page.getByRole('button', { name: 'Добавить подход' }).click();
  await expect(page.getByLabel('Вес разминки, подход 4')).toBeVisible();
  await page.getByRole('button', { name: 'Удалить подход разминки 4' }).click();
  await page.getByRole('button', { name: 'Добавить в тренировку' }).click();
  await expect(page.getByText('Разминочные подходы добавлены в эту тренировку')).toBeVisible();
  await expect(page.locator('[data-workout-set-id="301"]')).toHaveAttribute('aria-current', 'step');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);

  await page.reload({ waitUntil: 'domcontentloaded' });
  const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
  await expect(continueButton).toBeVisible();
  await continueButton.click();
  await expect(page.locator('[data-workout-set-id="301"]')).toHaveAttribute('aria-current', 'step');
  await expect(page.locator('[data-testid="warmup-proposal-entry"]')).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-02 is available in mocked TMA without mobile overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installMockedTelegram(page);
  await mockActiveWorkout(page);
  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await Promise.all([
    waitForSetPatch(page, 201),
    currentSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('80'),
  ]);
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  await expect(currentSet.getByRole('button', { name: 'Подготовить разминку' })).toBeVisible();
  await currentSet.getByRole('button', { name: 'Подготовить разминку' }).click();
  await page.getByRole('button', { name: 'Рассчитать предложение' }).click();
  await expect(page.getByRole('heading', { name: 'Проверьте подходы' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
  await page.getByRole('button', { name: 'Отмена' }).click();
  expect(page.getByRole('dialog')).toHaveCount(0);
});

test('V9-02 does not persist an unsaved proposal offline', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await Promise.all([
    waitForSetPatch(page, 201),
    currentSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('80'),
  ]);
  await page.context().setOffline(true);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  await expect(page.getByText('Разминка требует подключения. Ничего не сохранено.')).toBeVisible();
  await expect(currentSet.getByRole('button', { name: 'Подготовить разминку' })).toBeDisabled();
  expect(await page.locator('[data-workout-set-id="301"]').count()).toBe(0);
  await page.context().setOffline(false);
});

test('V9-03 calculates exact and nearest local loads without network or workout mutation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  const calculator = currentSet.locator('.active-workout-plate-calculator');
  await calculator.getByLabel('Целевой вес, кг').fill('80');
  await expect(calculator.getByRole('status')).toContainText('Точный результат');
  await expect(calculator.getByRole('status')).toContainText('Итог80 кг');
  await expect(calculator.getByRole('status')).toContainText('25 кг + 5 кг');

  const inventoryLabels = [25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.5].map(
    (weight) => `Количество блинов ${weight} кг на сторону`,
  );
  for (const label of inventoryLabels) {
    await calculator.getByLabel(label).fill('0');
  }
  await calculator.getByLabel('Количество блинов 10 кг на сторону').fill('1');
  await calculator.getByLabel('Количество блинов 5 кг на сторону').fill('1');
  await calculator.getByLabel('Целевой вес, кг').fill('35');
  await expect(calculator.getByRole('status')).toContainText('Ближайший доступный результат');
  await expect(calculator.getByRole('status')).toContainText('Итог30 кг');
  await expect(calculator.getByRole('status')).toContainText('Разница к цели: −5 кг');

  await calculator.getByLabel('Целевой вес, кг').fill('10');
  await expect(calculator.getByRole('alert')).toContainText('не может быть меньше веса грифа');

  await page.context().setOffline(true);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await calculator.getByLabel('Целевой вес, кг').fill('80');
  await calculator.getByRole('button', { name: 'Сбросить' }).click();
  await expect(calculator.getByRole('status')).toContainText('Точный результат');
  await expect(currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('');
  await expect(currentSet.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
  await page.context().setOffline(false);
});

test('V9-03 fits the supported 360, 390 and 430px Mobile Web widths', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  const calculator = currentSet.locator('.active-workout-plate-calculator');
  await calculator.getByLabel('Целевой вес, кг').fill('80');
  await expect(calculator.getByRole('status')).toContainText('Точный результат');

  for (const width of [360, 390, 430]) {
    await page.setViewportSize({ width, height: width === 360 ? 800 : width === 390 ? 844 : 932 });
    await expect(calculator).toBeVisible();
    await expectTouchTargets(calculator.locator('input, button'));
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
  }
});

test('V9-03 keeps the calculator keyboard-usable in mocked TMA dark reduced-motion mode', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installMockedTelegram(page);
  await mockActiveWorkout(page);
  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  const calculator = currentSet.locator('.active-workout-plate-calculator');
  await calculator.getByLabel('Целевой вес, кг').fill('80');
  await expect(calculator.getByRole('status')).toContainText('Точный результат');
  await calculator.getByLabel('Целевой вес, кг').focus();
  await expect(calculator.getByLabel('Целевой вес, кг')).toBeFocused();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  expect(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(
    true,
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-03 stays compact on desktop in dark reduced-motion mode', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
  const calculator = currentSet.locator('.active-workout-plate-calculator');
  await calculator.getByLabel('Целевой вес, кг').fill('80');
  await expect(calculator.getByRole('status')).toContainText('Точный результат');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-04 keeps a private setup memory through create, edit, delete and reload', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page.locator('.active-workout-exercise').filter({ hasText: 'Жим штанги лёжа' });
  const setupMemory = exercise.getByTestId('exercise-setup-memory-11');
  await expect(setupMemory.getByText('Личная настройка')).toBeVisible();
  await setupMemory.getByRole('button', { name: 'Добавить настройку' }).click();
  await setupMemory.getByRole('textbox', { name: 'Что важно настроить' }).fill('Сиденье 4');
  await setupMemory.getByRole('button', { name: 'Сохранить настройку' }).click();
  await expect(setupMemory.getByText('Сиденье 4')).toBeVisible();
  await expect(setupMemory.getByRole('button', { name: 'Изменить настройку' })).toBeVisible();

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const reloadedMemory = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .getByTestId('exercise-setup-memory-11');
  await expect(reloadedMemory.getByText('Сиденье 4')).toBeVisible();
  await reloadedMemory.getByRole('button', { name: 'Изменить настройку' }).click();
  await reloadedMemory.getByRole('textbox', { name: 'Что важно настроить' }).fill('Спинка 2');
  await reloadedMemory.getByRole('button', { name: 'Сохранить настройку' }).click();
  await expect(reloadedMemory.getByText('Спинка 2')).toBeVisible();
  await reloadedMemory.getByRole('button', { name: 'Изменить настройку' }).click();
  await reloadedMemory.getByRole('button', { name: 'Удалить' }).click();
  await expect(reloadedMemory.getByRole('button', { name: 'Добавить настройку' })).toBeVisible();
  await expect(reloadedMemory.getByText('Спинка 2')).not.toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

test('V9-04 fits Mobile Web and mocked TMA widths without moving the next-set action', async ({
  page,
}) => {
  await installMockedTelegram(page);
  await mockActiveWorkout(page, false, 'approved_animated', false, 'Скамья 30°');
  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const exercise = page.locator('.active-workout-exercise').filter({ hasText: 'Жим штанги лёжа' });
  const setupMemory = exercise.getByTestId('exercise-setup-memory-11');
  await expect(setupMemory.getByText('Скамья 30°')).toBeVisible();
  await expect(setupMemory.getByRole('button', { name: 'Изменить настройку' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');

  for (const width of [360, 390, 430]) {
    await page.setViewportSize({ width, height: width === 360 ? 800 : width === 390 ? 844 : 932 });
    await expect(setupMemory.getByText('Скамья 30°')).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
  }
  await expect(page.locator('[data-workout-set-id="201"]')).toHaveAttribute('aria-current', 'step');
});

test('V9-04 preserves a draft when the memory save is offline', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const setupMemory = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .getByTestId('exercise-setup-memory-11');
  await setupMemory.getByRole('button', { name: 'Добавить настройку' }).click();
  await setupMemory.getByRole('textbox', { name: 'Что важно настроить' }).fill('Узкий хват');
  await page.context().setOffline(true);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await expect(
    page.getByText('Нет сети · изменения подходов сохранятся как черновик'),
  ).toBeVisible();
  const saveSetupMemory = setupMemory.getByRole('button', { name: 'Сохранить настройку' });
  await saveSetupMemory.evaluate((element) =>
    element.scrollIntoView({ block: 'center', inline: 'nearest' }),
  );
  await saveSetupMemory.click();
  await expect(
    setupMemory.getByText('Черновик сохранён на устройстве. Сервер ещё не подтвердил сохранение.'),
  ).toBeVisible();
  await expect(setupMemory.getByRole('textbox', { name: 'Что важно настроить' })).toHaveValue(
    'Узкий хват',
  );
  await page.context().setOffline(false);
});

test('active workout keeps one obvious next action through logging, timer and finish', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 390, height: 844 });
  if (captureLandingProductProofs) {
    await page.addInitScript(() => {
      if (!localStorage.getItem('app-theme')) localStorage.setItem('app-theme', 'light');
    });
  }
  await page.addInitScript(() => {
    const events: unknown[] = [];
    Object.defineProperty(window, '__productAnalyticsEvents', { value: events, writable: false });
    window.addEventListener('yfc:product-event', (event) => {
      events.push((event as CustomEvent).detail);
    });
  });
  await mockActiveWorkout(page);
  const secondSetPatchBodies: unknown[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (request.method() === 'PATCH' && url.pathname.endsWith('/api/v1/workouts/sets/202')) {
      secondSetPatchBodies.push(request.postDataJSON());
    }
  });

  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  if (captureLandingProductProofs) {
    await expect(page.getByRole('heading', { name: 'Жим штанги лёжа' })).toBeVisible();
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-workout-mobile-light.png',
    });
    await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    const darkClientEntry = page.getByRole('button', { name: 'Клиент' });
    if (await darkClientEntry.isVisible()) await darkClientEntry.click();
    const darkWorkoutEntry = page.getByRole('button', { name: 'Продолжить тренировку' });
    await expect(darkWorkoutEntry).toBeVisible();
    await darkWorkoutEntry.click();
    await expect(page.getByRole('heading', { name: 'Жим штанги лёжа' })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    await page.screenshot({
      path: '../.artifacts/runtime/tests/product-proofs/landing-workout-mobile-dark.png',
    });
    return;
  }

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await expect(firstSet).toHaveAttribute('aria-current', 'step');
  await expect(firstSet.getByText('Тяжёлый подход', { exact: true })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Контекст упражнения' })).toContainText(
    '40 кг × 8',
  );
  await expect(page.getByRole('complementary', { name: 'Контекст упражнения' })).toContainText(
    'Расчётный максимум на 1 повтор',
  );
  await expect(firstSet.getByText('Повторы в запасе (RIR)', { exact: true })).toBeVisible();
  await clickDetailsSummary(firstSet.getByText('Разминка и блины', { exact: true }));
  await firstSet.getByLabel('Целевой вес, кг').fill('80');
  await expect(firstSet.locator('.active-workout-plate-result')).toContainText('На сторону:');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  const firstDone = firstSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 1',
  });
  await firstDone.scrollIntoViewIfNeeded();
  await Promise.all([waitForCompletedSetPatch(page, 201), firstDone.dblclick()]);

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await expect(secondSet).toHaveAttribute('aria-current', 'step');
  await expect(secondSet.getByText('Облегчённый подход', { exact: true })).toBeVisible();
  await expect(secondSet.getByText('Предыдущий подход: 40 кг × 8')).toBeVisible();
  await secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }).fill('35');
  await expect.poll(() => secondSetPatchBodies.length).toBeGreaterThan(0);
  const patchesBeforePrefill = secondSetPatchBodies.length;
  await secondSet.getByRole('button', { name: 'Подставить предыдущий результат' }).click();
  await expect.poll(() => secondSetPatchBodies.length).toBe(patchesBeforePrefill);
  await expect(
    secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }),
  ).toHaveValue('35');
  await expect(
    secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }),
  ).toHaveValue('8');
  await expect(
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }),
  ).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('timer').filter({ hasText: 'Отдых' })).toContainText(
    'Дальше: Жим штанги лёжа, подход 2',
  );

  await secondSet.getByText('Дополнительно').click();
  await secondSet.getByLabel('Вид подхода').selectOption('drop');
  await secondSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
  await secondSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 2' }).fill('35');
  await secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }).fill('9');
  await Promise.all([
    waitForCompletedSetPatch(page, 202),
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click(),
  ]);

  const thirdSet = page.locator('[data-workout-set-id="203"]');
  await expect(thirdSet).toHaveAttribute('aria-current', 'step');
  const thirdDone = thirdSet.getByRole('button', {
    name: 'Подставить и завершить',
  });
  await thirdDone.evaluate((element) =>
    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }),
  );
  await expect(thirdDone).toBeVisible();
  await Promise.all([waitForCompletedSetPatch(page, 203), thirdDone.click()]);

  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  const completedHeading = page.getByRole('heading', { name: 'Тренировка завершена' });
  await expect(completedHeading).toBeVisible();
  await completedHeading.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-62/mobile-web-390x844-light-workout-completed.png',
  });
  const analyticsEvents = await page.evaluate(
    () =>
      (
        window as typeof window & {
          __productAnalyticsEvents: Array<Record<string, unknown>>;
        }
      ).__productAnalyticsEvents,
  );
  expect(analyticsEvents).toContainEqual(
    expect.objectContaining({ name: 'workout_completed', surface: 'mobile_web' }),
  );
  expect(JSON.stringify(analyticsEvents)).not.toContain('actual_weight');
  expect(JSON.stringify(analyticsEvents)).not.toContain('actual_reps');
});

test('active workout keeps the current exercise primary and exposes keyboard handoff', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  const weight = currentSet.getByRole('spinbutton', {
    name: 'Вес, Жим штанги лёжа, подход 1',
  });
  const reps = currentSet.getByRole('spinbutton', {
    name: 'Повторы, Жим штанги лёжа, подход 1',
  });
  const done = currentSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 1',
  });
  await weight.focus();
  await weight.press('Enter');
  await expect(reps).toBeFocused();
  await reps.press('Enter');
  await expect(done).toBeFocused();

  const nextExercise = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await expect(nextExercise.getByRole('button', { name: 'Открыть упражнение' })).toBeVisible();
  await expect(nextExercise.locator('[id$="-details"][hidden]')).toHaveCount(1);
  await nextExercise.getByRole('button', { name: 'Открыть упражнение' }).click();
  await expect(
    nextExercise.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }),
  ).toBeVisible();
});

test('active workout checkpoint evidence covers light dark reduced and responsive states', async ({
  page,
}) => {
  const enterWorkout = async () => {
    const clientEntry = page.getByRole('button', { name: 'Клиент' });
    const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
    await Promise.race([
      clientEntry.waitFor({ state: 'visible', timeout: 5000 }),
      continueButton.waitFor({ state: 'visible', timeout: 5000 }),
    ]);
    if (await continueButton.isVisible()) {
      await continueButton.click();
      return;
    }
    await clientEntry.click();
    await expect(continueButton).toBeVisible();
    await continueButton.click();
  };

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await enterWorkout();
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await expectRealMediaFullWidth(page, '390px light animated');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-390x844-viewport.png',
  });

  await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await expectRealMediaFullWidth(page, '390px dark animated');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-dark-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-dark-390x844-viewport.png',
  });

  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'static-poster',
  );
  await expectRealMediaFullWidth(page, '390px dark reduced motion');
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-reduced-390x844.png',
    fullPage: true,
  });
  await resetPageScroll(page);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-reduced-390x844-viewport.png',
  });

  for (const viewport of [
    { width: 320, height: 800 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
    await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await enterWorkout();
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
    await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
      'data-media-mode',
      'animated',
    );
    await expectRealMediaFullWidth(page, `${viewport.width}px light animated`);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path: `../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-${viewport.width}x${viewport.height}.png`,
      fullPage: true,
    });
    await resetPageScroll(page);
    await page.screenshot({
      path: `../.artifacts/tasks/391/evidence/screenshots/active-workout-mobile-light-${viewport.width}x${viewport.height}-viewport.png`,
    });
  }
});

test('blocked exercise media stays compact and neutral in active workout', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, false, 'blocked');
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const media = page.locator('.active-workout-exercise__media--blocked').first();
  await expect(media).toContainText('Изображение пока недоступно');
  await expect(media).toContainText('Для этого упражнения нет проверенного визуального материала.');
  await expect(media.locator('img')).toHaveCount(0);
  const box = await media.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(150);
  expect(box?.height).toBeLessThan(220);
  const widthGeometry = await media.evaluate((element) => {
    const exercise = element.closest<HTMLElement>('.active-workout-exercise');
    if (!exercise) return null;
    const style = getComputedStyle(exercise);
    const contentWidth =
      exercise.getBoundingClientRect().width -
      parseFloat(style.paddingLeft) -
      parseFloat(style.paddingRight) -
      parseFloat(style.borderLeftWidth) -
      parseFloat(style.borderRightWidth);
    return {
      contentWidth,
      mediaWidth: element.getBoundingClientRect().width,
    };
  });
  expect(widthGeometry).not.toBeNull();
  expect(widthGeometry?.mediaWidth).toBeGreaterThanOrEqual((widthGeometry?.contentWidth ?? 0) - 1);
  await page.screenshot({
    path: '../.artifacts/tasks/391/evidence/screenshots/active-workout-blocked-mobile-390x844.png',
    fullPage: true,
  });
});

test('active workout actionable controls clear the mobile bottom dock', async ({
  browser,
  baseURL,
}) => {
  for (const viewport of [
    { width: 320, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    const context = await browser.newContext({
      baseURL,
      viewport,
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    try {
      await mockActiveWorkout(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

      await expect(page.locator('#appBottomNav')).toBeVisible();
      const currentSet = page.locator('[data-workout-set-id="201"]');
      const weight = currentSet.getByRole('spinbutton', {
        name: 'Вес, Жим штанги лёжа, подход 1',
      });
      const reps = currentSet.getByRole('spinbutton', {
        name: 'Повторы, Жим штанги лёжа, подход 1',
      });
      const done = currentSet.getByRole('button', {
        name: 'Завершить: Жим штанги лёжа, подход 1',
      });
      await expectClearOfBottomDock(weight, `${viewport.width}px focused input`);
      await weight.focus();
      await expectClearOfBottomDock(weight, `${viewport.width}px focused input`);
      await expectClearOfBottomDock(done, `${viewport.width}px complete CTA`);

      await weight.fill('40');
      await reps.fill('8');
      await Promise.all([waitForCompletedSetPatch(page, 201), done.dblclick()]);
      const rest = page.locator('.active-workout-rest');
      await expect(rest).toBeVisible();
      await expectClearOfBottomDock(
        rest.getByRole('button', { name: '+30 сек' }),
        `${viewport.width}px rest timer control`,
      );
    } finally {
      await context.close();
    }
  }
});

test('active workout has touch-size controls and no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const exercise = page.locator('.active-workout-exercise').first();
  await expect(exercise.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'src',
    mediaAnimationUrl,
  );
  await expect(exercise.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'animated',
  );
  await exercise.locator('.active-workout-exercise__media img').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/active-workout-inline-mobile-390x844.png',
  });
  await expect(exercise).toHaveCSS('border-radius', '0px');
  await expect(exercise).toHaveCSS('border-top-color', 'rgb(208, 208, 208)');
  await expect(exercise).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
  const guideButton = page.getByRole('button', { name: 'Техника' });
  await expect(guideButton).toHaveText('Техника');
  await guideButton.click();
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  const guideImages = page.locator('.exercise-guide-image img');
  await expect(guideImages).toHaveCount(1);
  await expect(guideImages.first()).toHaveAttribute('data-media-mode', 'animation');
  await guideImages.first().scrollIntoViewIfNeeded();
  await expect
    .poll(() => guideImages.nth(0).evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  await expect(page.locator('.exercise-guide-image video')).toHaveCount(0);
  await page.screenshot({
    path: '../.artifacts/tasks/390/evidence/screenshots/active-workout-mobile-390x844.png',
  });
  await page.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  for (const viewport of [
    { width: 1280, height: 900 },
    { width: 768, height: 900 },
    { width: 430, height: 932 },
    { width: 390, height: 844 },
    { width: 360, height: 800 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    const box = await page
      .getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' })
      .boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    if (viewport.width <= 430) {
      const focusHeader = page.locator('.today-workout-focus__header');
      await expect(focusHeader.locator(':scope > div > span')).toBeHidden();
      await expect(focusHeader.locator(':scope > span')).toBeHidden();
      await expect(focusHeader.getByText('Текущая тренировка')).toBeVisible();
    }
  }
});

test('touch Mobile Web keeps mixed controls usable with hover none', async ({
  browser,
  baseURL,
}) => {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 430, height: 932 },
    hasTouch: true,
    isMobile: true,
    colorScheme: 'light',
    reducedMotion: 'reduce',
  });
  const page = await context.newPage();
  try {
    await mockActiveWorkout(page, true);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    expect(await page.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
    expect(await page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
    await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
      'data-media-mode',
      'static-poster',
    );
    const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
    await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
    const done = cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' });
    expect((await done.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
  } finally {
    await context.close();
  }
});

test('mixed workout keeps cardio type-aware, compact and stable during input', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.setViewportSize({ width: 390, height: 844 });
  const server = await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
  await expect(cardio.getByRole('heading', { name: 'Велотренажёр' })).toBeVisible();
  await expect(cardio.getByText('План: 25 мин')).toBeVisible();
  await expect(cardio.getByText(/Рабочие подходы|Повторы|Отдых, сек/)).toHaveCount(0);
  await expect(cardio.getByRole('spinbutton', { name: /Вес/ })).toHaveCount(0);

  await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
  await expect(cardio.getByRole('alert')).toHaveText('Укажите длительность кардио.');
  await cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }).fill('27');
  await cardio.getByRole('spinbutton', { name: 'Дистанция, Велотренажёр' }).fill('6.4');
  const pulse = cardio.getByText('Пульс (необязательно)');
  await pulse.click();
  await cardio.getByRole('spinbutton', { name: 'Средний пульс, уд/мин' }).fill('138');
  await cardio.getByRole('combobox', { name: 'Зона пульса' }).selectOption('3');
  await expect(cardio.locator('details')).toHaveAttribute('open', '');
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-119/mobile-web-390x844-dark-mixed-workout.png',
    fullPage: true,
  });

  await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
  await server.cardioCompleted;
  await expect
    .poll(() =>
      page.evaluate(() => {
        const stored = localStorage.getItem('fit_active_workout_v1_user_7_workout_42');
        if (!stored) return -1;
        return (JSON.parse(stored) as { queue: unknown[] }).queue.length;
      }),
    )
    .toBe(0);
  await page.reload();
  const clientEntry = page.getByRole('button', { name: 'Клиент' });
  if (await clientEntry.isVisible()) await clientEntry.click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(cardio.getByRole('button', { name: 'Кардио сохранено' })).toBeVisible();
  await expect(cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' })).toHaveCount(
    0,
  );
  await cardio.getByRole('button', { name: 'Кардио сохранено' }).click();
  await expect(cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' })).toHaveValue(
    '27',
  );

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
  await page.reload();
  const desktopClientEntry = page.getByRole('button', { name: 'Клиент' });
  if (await desktopClientEntry.isVisible()) await desktopClientEntry.click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const desktopCardio = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Велотренажёр' });
  await desktopCardio.getByRole('button', { name: 'Кардио сохранено' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: '../.artifacts/runtime/tests/screenshots/task-119/desktop-web-1280x900-light-mixed-workout.png',
    fullPage: true,
  });
});

test('TMA active workout keeps in-page back while native back stays hidden and keyboard nav restores', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const handlers = new Map<string, Set<() => void>>();
    const backState = { hide: 0, show: 0 };
    const backButton = {
      show() {
        backState.show += 1;
      },
      hide() {
        backState.hide += 1;
      },
      setText() {},
      enable() {},
      disable() {},
      onClick() {},
      offClick() {},
    };
    const telegram = {
      initData: 'signed-test-data',
      initDataUnsafe: {},
      isActive: true,
      viewportHeight: 560,
      viewportStableHeight: 844,
      safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
      colorScheme: 'dark' as const,
      themeParams: {},
      BackButton: backButton,
      ready() {},
      expand() {},
      onEvent(event: string, callback: () => void) {
        const callbacks = handlers.get(event) ?? new Set<() => void>();
        callbacks.add(callback);
        handlers.set(event, callbacks);
      },
      offEvent(event: string, callback: () => void) {
        handlers.get(event)?.delete(callback);
      },
    };
    Object.assign(window, {
      Telegram: { WebApp: telegram },
      __backButtonState: backState,
    });
  });
  await mockActiveWorkout(page, true);

  await page.goto('/app?tgWebAppPlatform=android');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  await expect(page.getByRole('button', { name: 'К сводке' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  expect(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--yfc-viewport-height').trim(),
    ),
  ).toBe('560px');
  expect(
    await page.evaluate(() =>
      getComputedStyle(document.documentElement)
        .getPropertyValue('--yfc-viewport-stable-height')
        .trim(),
    ),
  ).toBe('844px');
  const tmaCardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await tmaCardio.getByRole('button', { name: 'Открыть упражнение' }).click();
  await expect(
    tmaCardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }),
  ).toBeVisible();
  await expect(tmaCardio.getByRole('spinbutton', { name: /Вес/ })).toHaveCount(0);

  const navigation = page.locator('#appBottomNav');
  await expect(navigation).toBeVisible();
  const weight = page.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' });
  await weight.focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(navigation).toBeHidden();

  await page.getByRole('button', { name: 'К сводке' }).focus();
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'hidden');
  await expect(navigation).toBeVisible();
  await expect(page).toHaveURL(/\/app\?tgWebAppPlatform=android$/);
  const backState = await page.evaluate(
    () =>
      (
        window as unknown as Window & {
          __backButtonState: { hide: number; show: number };
        }
      ).__backButtonState,
  );
  expect(backState.hide).toBeGreaterThanOrEqual(1);
  expect(backState.show).toBe(0);
});

test('save failure stays compact, keeps controls open and retries explicitly', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const server = await mockActiveWorkout(page);
  server.failSetPatch(true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await expect(page.getByText('Требуется действие')).toBeVisible();
  await expect(
    firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }),
  ).toBeEnabled();

  server.failSetPatch(false);
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
});

test('rest timer reconciles its deadline after a simulated hidden-tab return', async ({ page }) => {
  const start = new Date('2026-09-09T12:00:00Z');
  await page.clock.setFixedTime(start);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const notifications: string[] = [];
    Object.defineProperty(window, '__restNotifications', { value: notifications });
    class TestNotification {
      static permission = 'granted';

      constructor(title: string) {
        notifications.push(title);
      }
    }
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: TestNotification,
    });
  });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  const timer = page.getByRole('timer').filter({ hasText: 'Отдых' });
  await expect(timer).toContainText('1:30');
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.setFixedTime(new Date(start.getTime() + 65_000));
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect(timer).toContainText('0:25');
  await page.clock.setFixedTime(new Date(start.getTime() + 100_000));
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await expect(timer).toHaveCount(0);
  await expect(page.locator('.active-workout-rest--complete')).toContainText('Отдых завершён');
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as typeof window & { __restNotifications: string[] }).__restNotifications.length,
      ),
    )
    .toBe(1);
});

test('Task 520 owner visual package covers friction-reduction states', async ({ page }) => {
  test.skip(!captureTask520VisualPackage, 'owner visual package capture is opt-in');
  const packagePath = '../.artifacts/tasks/520/deliverables/visual-package';
  const enterWorkout = async () => {
    const clientEntry = page.getByRole('button', { name: 'Клиент' });
    const continueButton = page.getByRole('button', { name: 'Продолжить тренировку' });
    await Promise.race([
      clientEntry.waitFor({ state: 'visible', timeout: 5000 }),
      continueButton.waitFor({ state: 'visible', timeout: 5000 }),
    ]);
    if (await continueButton.isVisible()) {
      await continueButton.click();
      return;
    }
    await clientEntry.click();
    await expect(continueButton).toBeVisible();
    await continueButton.click();
  };

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await enterWorkout();

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await expect(page.getByRole('complementary', { name: 'Контекст упражнения' })).toBeVisible();
  await page.screenshot({
    path: `${packagePath}/mobile-light-active-history-prefill.png`,
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Техника' }).first().click();
  await expect(page.getByRole('heading', { name: 'Техника выполнения' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-light-technique.png`, fullPage: true });
  await page.getByRole('button', { name: 'Закрыть карточку упражнения' }).click();

  await clickDetailsSummary(firstSet.getByText('Разминка и блины', { exact: true }));
  await firstSet.getByLabel('Вес снаряда, кг').fill('80');
  await expect(firstSet.getByRole('status')).toContainText('На сторону:');
  await page.screenshot({
    path: `${packagePath}/mobile-light-warmup-plate-helper.png`,
    fullPage: true,
  });

  await firstSet.getByRole('spinbutton', { name: 'Вес, Жим штанги лёжа, подход 1' }).fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  await expect(page.getByRole('timer').filter({ hasText: 'Отдых' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-light-rest.png`, fullPage: true });

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await secondSet.getByRole('button', { name: 'Подставить предыдущий результат' }).click();
  await page.screenshot({ path: `${packagePath}/mobile-light-prefilled-set.png`, fullPage: true });
  await secondSet.getByText('Дополнительно', { exact: true }).click();
  await secondSet.getByLabel('Вид подхода').selectOption('drop');
  await secondSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
  await page.screenshot({ path: `${packagePath}/mobile-light-advanced-set.png`, fullPage: true });

  const replacement = page.getByRole('button', { name: 'Заменить' }).first();
  await replacement.click();
  const adaptationDialog = page.getByRole('dialog', { name: 'Подстроить тренировку' });
  await expect(adaptationDialog).toBeVisible();
  await adaptationDialog.getByRole('checkbox', { name: 'Гантели' }).check();
  await adaptationDialog.getByRole('checkbox', { name: 'Скамья' }).check();
  const alternative = adaptationDialog.getByRole('radio', { name: /Жим гантелей лёжа/ });
  await expect(alternative).toBeVisible();
  await alternative.check();
  await adaptationDialog.getByRole('button', { name: 'Показать изменения' }).click();
  await expect(adaptationDialog.getByRole('heading', { name: 'Что изменится' })).toBeVisible();
  await expect(adaptationDialog.locator('.adaptation-preview')).toContainText('Жим гантелей лёжа');
  await adaptationDialog.locator('.adaptation-preview').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${packagePath}/mobile-light-substitution.png`, fullPage: true });

  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'dark' });
  await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.getByRole('heading', { name: 'Жим штанги лёжа' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-dark-active-workout.png`, fullPage: true });

  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await expect(page.locator('.active-workout-exercise__media img')).toHaveAttribute(
    'data-media-mode',
    'static-poster',
  );
  await page.screenshot({
    path: `${packagePath}/mobile-light-reduced-static-fallback.png`,
    fullPage: true,
  });

  await page.emulateMedia({ reducedMotion: 'no-preference', colorScheme: 'light' });
  await page.evaluate(() => localStorage.setItem('app-theme', 'light'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await enterWorkout();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await page.screenshot({
    path: `${packagePath}/desktop-light-active-workout.png`,
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  const skipRest = page.getByRole('button', { name: 'Пропустить' });
  if (await skipRest.isVisible()) await skipRest.click();
  const remainingSecondSet = page.locator('[data-workout-set-id="202"]');
  await remainingSecondSet
    .getByRole('button', { name: /Подставить и завершить|Завершить: Жим штанги лёжа, подход 2/ })
    .click();
  const remainingThirdSet = page.locator('[data-workout-set-id="203"]');
  const skipSecondRest = page.getByRole('button', { name: 'Пропустить' });
  if (await skipSecondRest.isVisible()) await skipSecondRest.click();
  await remainingThirdSet
    .getByRole('button', { name: /Подставить и завершить|Завершить: Жим штанги лёжа, подход 3/ })
    .click();
  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-light-completed.png`, fullPage: true });
});
