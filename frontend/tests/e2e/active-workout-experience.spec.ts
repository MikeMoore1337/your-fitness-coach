import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { activeWorkoutRestStorageKey } from '../../src/shared/userScopedStorage';
import { emptyHydrationDay } from './fixtures/platform-api';
import { expectSelectedChoice } from './fixtures/selected-state';
import {
  expectTouchTargets,
  installTelegramHarness,
  setDocumentVisibility,
  setNetworkOffline,
  TelegramHarness,
} from './fixtures/mobile-tma';

const mediaThumbnailUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.jpg';
const mediaAnimationUrl = '/static/exercise-guides/gymvisual/bench-press-0025-EIeI8Vf.gif';
const replacementMediaThumbnailUrl =
  '/static/exercise-guides/gymvisual/dumbbell-bench-press-0289-SpYC0Kp.jpg';

test.use({
  serviceWorkers: 'block',
  video: process.env.ALLURE_RESULTS_DIR ? 'retain-on-failure' : 'on',
});

const CAPTURE_980_AFTER = process.env.CAPTURE_980_AFTER === '1';
const ISSUE_980_AFTER_DIR = resolve(
  process.cwd(),
  '..',
  'docs',
  'ux',
  'final-issues-acceptance',
  'evidence',
  '980-completed-set-20261013',
  'after',
);
const CAPTURE_1162_VISUALS = process.env.CAPTURE_1162_VISUALS === '1';
const ISSUE_1162_CAPTURE_PHASE = process.env.CAPTURE_1162_PHASE ?? 'after';
const ISSUE_1162_CAPTURE_DIR = resolve(
  process.env.CAPTURE_1162_DIR ??
    resolve(
      process.cwd(),
      '..',
      '.artifacts',
      'tasks',
      '1162',
      'evidence',
      ISSUE_1162_CAPTURE_PHASE,
    ),
);
const ISSUE_996_AFTER_DIR = resolve(
  process.env.YFC_ISSUE_996_AFTER_DIR ??
    resolve(process.cwd(), '..', '.artifacts', 'tasks', '996', 'evidence', 'after'),
);

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
  longWorkout = false,
  exerciseTitleOverride: string | null = null,
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
  let nextPatchBarrier: Promise<void> | null = null;
  let workoutReadBarrier: Promise<void> | null = null;
  let workoutReadCount = 0;
  let workoutReadResponseCount = 0;
  const workoutReadSnapshots: boolean[] = [];
  const patches: Array<{
    setId: number;
    method: string;
    endpoint: string;
    body: Record<string, unknown>;
    receivedAt: number;
    respondedAt?: number;
    status?: number;
    response?: unknown;
  }> = [];
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
        exercise_title: replacementApplied
          ? 'Жим гантелей лёжа'
          : (exerciseTitleOverride ?? 'Жим штанги лёжа'),
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        source_template_exercise_id: 71,
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
      ...(longWorkout
        ? Array.from({ length: 5 }, (_, exerciseIndex) => ({
            id: 110 + exerciseIndex,
            exercise_id: 11,
            exercise_title: `Дополнительное упражнение ${exerciseIndex + 1}`,
            metric_type: 'strength',
            sort_order: 3 + exerciseIndex,
            prescribed_sets: 4,
            prescribed_reps: '10',
            rest_seconds: 90,
            sets: Array.from({ length: 4 }, (_, setIndex) => ({
              ...sets.get(203)!,
              id: 500 + exerciseIndex * 4 + setIndex,
              set_number: setIndex + 1,
            })),
          }))
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
      workoutReadCount += 1;
      const snapshotCompleted = sets.get(202)?.is_completed ?? false;
      workoutReadSnapshots.push(snapshotCompleted);
      const snapshot = workout();
      if (workoutReadBarrier) await workoutReadBarrier;
      await route.fulfill({ json: snapshot });
      workoutReadResponseCount += 1;
      return;
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
          status: 'unlogged',
          status_is_explicit: false,
        },
      });
    }
    if (path.endsWith('/nutrition/hydration')) {
      return route.fulfill({ json: emptyHydrationDay(today) });
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
            media_thumbnail_url:
              '/static/exercise-guides/gymvisual/dumbbell-bench-press-0289-SpYC0Kp.jpg',
            media_thumbnail_sources: [
              {
                url: '/static/exercise-guides/gymvisual/dumbbell-bench-press-0289-SpYC0Kp.jpg',
                mime_type: 'image/jpeg',
                width: 180,
                height: 180,
                byte_size: 8103,
              },
            ],
            score: 0.96,
            reason_keys: ['same_movement_pattern', 'same_primary_muscle'],
          },
          {
            exercise_id: 14,
            title: 'Жим в тренажёре от груди',
            equipment_ids: ['machine'],
            media_thumbnail_url: null,
            media_thumbnail_sources: [],
            score: 0.8,
            reason_keys: ['same_movement_pattern'],
          },
          {
            exercise_id: 15,
            title: 'Отжимания от пола',
            equipment_ids: ['bodyweight'],
            media_thumbnail_url: null,
            media_thumbnail_sources: [],
            score: 0.7,
            reason_keys: ['same_primary_muscle'],
          },
          {
            exercise_id: 16,
            title: 'Жим в тренажёре Смита',
            equipment_ids: ['machine', 'bench'],
            media_thumbnail_url: null,
            media_thumbnail_sources: [],
            score: 0.6,
            reason_keys: ['same_movement_pattern'],
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
      const setId = Number(setMatch[1]);
      const body = request.postDataJSON() as Partial<SetState> & {
        expected_version: number;
        mutation_id: string;
      };
      const patch: (typeof patches)[number] = {
        setId,
        method: request.method(),
        endpoint: path,
        body,
        receivedAt: Date.now(),
      };
      patches.push(patch);
      const respond = (status: number, response: unknown) => {
        Object.assign(patch, { status, response, respondedAt: Date.now() });
        return route.fulfill({ status, json: response });
      };
      const barrier = nextPatchBarrier;
      nextPatchBarrier = null;
      if (barrier) await barrier;
      if (failSetPatch) {
        return respond(503, { detail: 'Сервис временно недоступен' });
      }
      const current = sets.get(setId)!;
      if (body.expected_version !== current.version) {
        return respond(409, {
          detail: {
            code: 'workout_set_version_conflict',
            current: { id: setId, ...current },
          },
        });
      }
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
      return respond(200, { id: setId, set_number: setId === 204 ? 1 : setId - 200, ...next });
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
    patches,
    readWorkout: workout,
    readSet: (setId: number) => sets.get(setId)!,
    addFourthSet() {
      sets.set(301, {
        ...sets.get(203)!,
        actual_reps: null,
        actual_weight: null,
        is_completed: false,
      });
    },
    setRole(setId: number, role: SetState['planned_role']) {
      sets.get(setId)!.planned_role = role;
    },
    holdNextPatch() {
      let release!: () => void;
      nextPatchBarrier = new Promise<void>((resolve) => {
        release = resolve;
      });
      return release;
    },
    holdWorkoutReads() {
      let release!: () => void;
      workoutReadBarrier = new Promise<void>((resolve) => {
        release = () => {
          workoutReadBarrier = null;
          resolve();
        };
      });
      return release;
    },
    workoutReadCount: () => workoutReadCount,
    workoutReadResponseCount: () => workoutReadResponseCount,
    workoutReadSnapshots: () => [...workoutReadSnapshots],
    failSetPatch(value: boolean) {
      failSetPatch = value;
    },
    cardioCompleted,
  };
}

async function mockSetHistory(page: Page, server: Awaited<ReturnType<typeof mockActiveWorkout>>) {
  let hasHistory = true;
  let requests = 0;
  await page.route('**/api/v1/workouts/42/set-history', async (route) => {
    requests += 1;
    const exercise = server.readWorkout().exercises[0]!;
    return route.fulfill({
      json: {
        workout_id: 42,
        user_program_id: 4,
        program_revision_number: 2,
        sets: exercise.sets.map((set) => ({
          set_id: set.id,
          set_number: set.set_number,
          set_version: set.version,
          workout_exercise_id: exercise.id,
          exercise_id: exercise.exercise_id,
          source_template_exercise_id: 71,
          previous_today: null,
          history_status: hasHistory ? 'matched' : 'no_matching_set',
          previous_workout: hasHistory
            ? {
                set_id: set.id + 1000,
                set_number: set.set_number,
                set_version: 1,
                workout_id: 41,
                workout_exercise_id: 100,
                completed_at: '2026-10-23T12:00:00',
                performed_on: '2026-10-23',
                actual_weight: [160, 180, 200, 190][set.set_number - 1],
                actual_reps: 8,
              }
            : null,
        })),
      },
    });
  });
  return {
    withoutHistory() {
      hasHistory = false;
    },
    requests: () => requests,
  };
}

function completedActions(row: Locator) {
  return row.locator('.active-workout-set__completed-actions');
}

async function captureIssue1162State(page: Page, info: TestInfo, theme: string, state: string) {
  if (!CAPTURE_1162_VISUALS) return;
  await mkdir(ISSUE_1162_CAPTURE_DIR, { recursive: true });
  const width = page.viewportSize()?.width ?? 'unknown';
  await page.screenshot({
    path: resolve(ISSUE_1162_CAPTURE_DIR, `${info.project.name}-${width}-${theme}-${state}.png`),
    fullPage: false,
  });
}

async function activeWorkoutQueueLength(page: Page) {
  return page.evaluate(() => {
    const stored = localStorage.getItem('fit_active_workout_v1_user_7_workout_42');
    return stored ? ((JSON.parse(stored) as { queue?: unknown[] }).queue?.length ?? 0) : 0;
  });
}

test.describe('#1097 rest clock typography and v2 compact layout', () => {
  for (const theme of ['dark', 'light'] as const) {
    test(`planned and measured clocks preserve hierarchy and fit the top row in ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 393, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const server = await mockActiveWorkout(page, true, 'approved_animated', false, null, true);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('40');
      await first.getByLabel(/^Повторы,/).fill('10');
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(true);

      const panel = page.locator('.active-workout-rest');
      await expect(panel.locator('.active-workout-rest__actual-value')).toBeVisible();
      await expect(panel.locator('.active-workout-rest__actual-value span')).toHaveText('ФАКТ');
      await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();

      for (const width of [320, 360, 393, 430, 1440]) {
        await page.setViewportSize({ width, height: 844 });
        const result = await panel.evaluate((element) => {
          const planned = element.querySelector<HTMLElement>('.active-workout-rest__time strong')!;
          const actual = element.querySelector<HTMLElement>(
            '.active-workout-rest__actual-value strong',
          )!;
          const status = element.querySelector<HTMLElement>('.active-workout-rest__status')!;
          const actualBlock = element.querySelector<HTMLElement>('.active-workout-rest__actual')!;
          const stop = element.querySelector<HTMLElement>('.active-workout-rest__stop')!;
          const original = actual.textContent;
          // Exercise an hour-long measurement without waiting an hour or altering the journal.
          actual.textContent = '1:07:08';
          const timerSize = getComputedStyle(planned).fontSize;
          const actualSize = getComputedStyle(actual).fontSize;
          const actualFits = actual.scrollWidth <= actual.clientWidth + 1;
          const geometry = {
            timerSize,
            actualSize,
            actualFits,
            plannedRight: planned.getBoundingClientRect().right,
            statusLeft: status.getBoundingClientRect().left,
            actualLeft: actualBlock.getBoundingClientRect().left,
            actualRight: actualBlock.getBoundingClientRect().right,
            stopRight: stop.getBoundingClientRect().right,
            panelRight: element.getBoundingClientRect().right,
            panelWidth: element.getBoundingClientRect().width,
            documentOverflow:
              document.documentElement.scrollWidth - document.documentElement.clientWidth,
            actions: Array.from(
              element.querySelectorAll<HTMLElement>('.active-workout-rest__actions button'),
            ).map((button) => button.getBoundingClientRect().width),
          };
          actual.textContent = original;
          return geometry;
        });
        expect(
          parseFloat(result.timerSize),
          `${width}px ${theme}: planned clock hierarchy`,
        ).toBeGreaterThanOrEqual(parseFloat(result.actualSize));
        expect(result.actualFits, `${width}px ${theme}: full hour format visible`).toBe(true);
        expect(
          result.actualLeft - result.plannedRight,
          `${width}px ${theme}: clock separation`,
        ).toBeGreaterThanOrEqual(15);
        expect(result.actualRight).toBeLessThanOrEqual(result.statusLeft + 1);
        expect(result.stopRight).toBeLessThanOrEqual(result.panelRight + 1);
        expect(result.actualRight).toBeLessThanOrEqual(result.panelRight + 1);
        expect(result.documentOverflow).toBeLessThanOrEqual(1);
        expect(result.actions).toHaveLength(4);
        expect(result.actions.every((buttonWidth) => buttonWidth >= 44)).toBe(true);
        await panel.screenshot({
          path: test.info().outputPath(`rest-clock-${theme}-${width}.png`),
          animations: 'disabled',
        });
      }
    });
  }
});

async function settleViewport(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        let previous = window.scrollY;
        let stableFrames = 0;
        let frames = 0;
        const observe = () => {
          const current = window.scrollY;
          stableFrames = Math.abs(current - previous) <= 0.5 ? stableFrames + 1 : 0;
          previous = current;
          frames += 1;
          if (stableFrames >= 3 || frames >= 60) resolve();
          else requestAnimationFrame(observe);
        };
        requestAnimationFrame(observe);
      }),
  );
}

async function stableScrollY(page: Page) {
  await settleViewport(page);
  return page.evaluate(() => window.scrollY);
}

async function expectScrollYStable(page: Page, before: number, tolerance = 1) {
  const after = await stableScrollY(page);
  expect(Math.abs(after - before)).toBeLessThanOrEqual(tolerance);
}

async function focusWithPointer(field: Locator) {
  await field.evaluate((input) => {
    const box = input.getBoundingClientRect();
    const pointer = {
      bubbles: true,
      cancelable: true,
      clientX: box.left + box.width / 2,
      clientY: box.top + box.height / 2,
      pointerId: 1,
      pointerType: 'touch',
      isPrimary: true,
    };
    input.dispatchEvent(new PointerEvent('pointerdown', pointer));
    (input as HTMLElement).focus();
    input.dispatchEvent(new PointerEvent('pointerup', pointer));
  });
}

type Issue1099Frame = {
  time: number;
  scrollY: number;
  viewportTop: number;
  viewportHeight: number;
  panelTop: number | null;
  panelBottom: number | null;
  panelRelativeTop: number | null;
  activeTop: number | null;
  activeBottom: number | null;
  activeControlsTop: number | null;
  cssViewportOffsetTop: number;
  restClearance: string;
  activeScrollMargin: string;
};

type Issue1099Probe = {
  frames: Issue1099Frame[];
  scrollEvents: Array<{ source: string; scrollY: number; viewportTop: number }>;
  scrollCalls: Array<{ method: string; top: number; time: number }>;
};

type Issue1099Surface = 'browser' | 'pwa' | 'telegram';

async function prepareIssue1099KeyboardCase(
  page: Page,
  surface: Issue1099Surface = 'browser',
  options: { verifyPwaServiceWorker?: boolean; withRest?: boolean } = {},
) {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  if (surface === 'pwa') {
    await page.addInitScript(() => {
      const nativeMatchMedia = window.matchMedia.bind(window);
      window.matchMedia = (query: string) => {
        const result = nativeMatchMedia(query);
        if (query === '(display-mode: standalone)') {
          Object.defineProperty(result, 'matches', { configurable: true, value: true });
        }
        return result;
      };
      Object.defineProperty(navigator, 'standalone', {
        configurable: true,
        value: true,
      });
    });
  }
  if (surface === 'telegram') {
    await installTelegramHarness(page, {
      platform: 'ios',
      colorScheme: 'dark',
      viewportHeight: 844,
      viewportStableHeight: 844,
    });
  }
  await page.addInitScript(() => {
    const viewport = new EventTarget() as EventTarget & {
      height: number;
      width: number;
      offsetTop: number;
    };
    Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
    Object.defineProperty(viewport, 'pageTop', { get: () => scrollY + viewport.offsetTop });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    const calls: Array<{ method: string; top: number; time: number }> = [];
    const lifecycle: Array<{
      source: string;
      time: number;
      height: number;
      offsetTop: number;
      innerHeight: number;
    }> = [];
    const recordLifecycle = (source: string) =>
      lifecycle.push({
        source,
        time: performance.now(),
        height: viewport.height,
        offsetTop: viewport.offsetTop,
        innerHeight,
      });
    viewport.addEventListener('resize', () => recordLifecycle('visualViewport.resize'));
    viewport.addEventListener('scroll', () => recordLifecycle('visualViewport.scroll'));
    window.addEventListener('resize', () => recordLifecycle('window.resize'));
    Object.assign(window, { __yfc1099ScrollCalls: calls, __yfc1099Lifecycle: lifecycle });
    Object.assign(window, { __yfc1099NativeScrollTo: window.scrollTo.bind(window) });
    for (const method of ['scrollBy', 'scrollTo'] as const) {
      const original = window[method].bind(window);
      window[method] = (options?: ScrollToOptions | number, y?: number) => {
        const top = typeof options === 'number' ? (y ?? 0) : (options?.top ?? window.scrollY);
        recordLifecycle(`${method}(${top})`);
        calls.push({ method, top, time: performance.now() });
        if (typeof options === 'number') original(options, y ?? 0);
        else original(options);
        if (method === 'scrollBy') {
          (window as Window & { __yfc1099ScrollFeedback?: () => void }).__yfc1099ScrollFeedback?.();
        }
      };
    }
  });
  const server = await mockActiveWorkout(page, false, 'approved_animated', false, null, true);
  await page.goto(surface === 'telegram' ? '/app?tgWebAppPlatform=ios' : '/app');
  if (surface === 'pwa' && options.verifyPwaServiceWorker !== false) {
    await page.waitForFunction(async () => {
      const registration = await navigator.serviceWorker.getRegistration('/');
      return Boolean(registration?.active);
    });
    if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller)))) {
      await page.reload();
    }
    await page.waitForFunction(() => {
      const controller = navigator.serviceWorker.controller;
      return Boolean(controller?.scriptURL.endsWith('/sw.js'));
    });
  }
  if (surface !== 'telegram') {
    await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('40');
  await first.getByLabel(/^Повторы,/).fill('10');
  if (options.withRest !== false) {
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect.poll(() => server.readSet(201).is_completed).toBe(true);
    await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  }

  const row = page.locator('[data-workout-set-id="202"]');
  const weight = row.getByLabel(/^Вес,/);
  const reps = row.getByLabel(/^Повторы,/);
  await page.evaluate(() => {
    const viewport = window.visualViewport as EventTarget & { height: number; offsetTop: number };
    Object.assign(viewport, { height: 420, offsetTop: 0 });
    viewport.dispatchEvent(new Event('resize'));
  });
  return { server, row, weight, reps };
}

async function startIssue1099FrameProbe(page: Page) {
  await page.evaluate(() => {
    const win = window as Window & {
      __yfc1099FrameProbe?: {
        frames: Issue1099Frame[];
        scrollEvents: Array<{ source: string; scrollY: number; viewportTop: number }>;
        running: boolean;
      };
    };
    const probe = {
      frames: [],
      scrollEvents: [],
      running: true,
    } as {
      frames: Issue1099Frame[];
      scrollEvents: Array<{ source: string; scrollY: number; viewportTop: number }>;
      running: boolean;
    };
    const viewport = window.visualViewport;
    const readFrame = () => {
      const panel = document.querySelector<HTMLElement>('.active-workout-rest');
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const panelBox = panel?.getBoundingClientRect();
      const activeBox = active?.getBoundingClientRect();
      const controlsBox = active
        ?.closest<HTMLElement>('.active-workout-set__controls')
        ?.getBoundingClientRect();
      const viewportTop = viewport?.offsetTop ?? 0;
      const safeTop =
        Number.parseFloat(
          getComputedStyle(document.documentElement).getPropertyValue('--yfc-layout-safe-top'),
        ) || 0;
      probe.frames.push({
        time: performance.now(),
        scrollY: window.scrollY,
        viewportTop,
        viewportHeight: viewport?.height ?? window.innerHeight,
        panelTop: panelBox?.top ?? null,
        panelBottom: panelBox?.bottom ?? null,
        panelRelativeTop: panelBox ? panelBox.top - viewportTop - safeTop : null,
        activeTop: activeBox?.top ?? null,
        activeBottom: activeBox?.bottom ?? null,
        activeControlsTop: controlsBox?.top ?? null,
        cssViewportOffsetTop:
          Number.parseFloat(
            getComputedStyle(document.documentElement).getPropertyValue(
              '--yfc-visual-viewport-offset-top',
            ),
          ) || 0,
        restClearance: getComputedStyle(
          document.querySelector<HTMLElement>('.active-workout') ?? document.documentElement,
        ).getPropertyValue('--yfc-active-workout-rest-clearance'),
        activeScrollMargin: active ? getComputedStyle(active).scrollMarginBlockStart : '',
      });
      if (probe.running) requestAnimationFrame(readFrame);
    };
    const recordScroll = (source: string) =>
      probe.scrollEvents.push({
        source,
        scrollY: window.scrollY,
        viewportTop: window.visualViewport?.offsetTop ?? 0,
      });
    window.addEventListener('scroll', () => recordScroll('window'), { passive: true });
    viewport?.addEventListener('scroll', () => recordScroll('visualViewport'), { passive: true });
    win.__yfc1099FrameProbe = probe;
    requestAnimationFrame(readFrame);
  });
}

async function stopIssue1099FrameProbe(page: Page): Promise<Issue1099Probe> {
  return page.evaluate(() => {
    const win = window as Window & {
      __yfc1099FrameProbe?: {
        frames: Issue1099Frame[];
        scrollEvents: Array<{ source: string; scrollY: number; viewportTop: number }>;
        running: boolean;
      };
      __yfc1099ScrollCalls?: Array<{ method: string; top: number; time: number }>;
    };
    const probe = win.__yfc1099FrameProbe;
    if (!probe) throw new Error('Issue #1099 frame probe was not installed');
    probe.running = false;
    return {
      frames: probe.frames,
      scrollEvents: probe.scrollEvents,
      scrollCalls: win.__yfc1099ScrollCalls ?? [],
    };
  });
}

test('#1099 scenario A keeps input geometry stable after initial keyboard correction', async ({
  page,
}, info) => {
  const { server, row, weight, reps } = await prepareIssue1099KeyboardCase(page);
  await weight.focus();
  await settleViewport(page);
  const initialScrollY = await page.evaluate(() => window.scrollY);
  const initialCalls = await page.evaluate(
    () => (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls ?? [],
  );
  await page.evaluate(() => {
    (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
  });
  await startIssue1099FrameProbe(page);

  for (const [weightValue, repsValue] of [
    ['50', '12'],
    ['55', '11'],
    ['50', '12'],
  ] as const) {
    await weight.focus();
    await weight.fill('');
    await weight.pressSequentially(weightValue);
    await expect.poll(() => server.readSet(202).actual_weight).toBe(Number(weightValue));
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
    await reps.focus();
    await reps.fill('');
    await reps.pressSequentially(repsValue);
    await expect.poll(() => server.readSet(202).actual_reps).toBe(Number(repsValue));
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  }

  const probe = await stopIssue1099FrameProbe(page);
  const report = { initialScrollY, initialCalls, ...probe };
  await writeFile(
    info.outputPath('issue-1099-input-geometry.json'),
    JSON.stringify(report, null, 2),
  );
  await info.attach('issue-1099-input-geometry.json', {
    body: JSON.stringify(report, null, 2),
    contentType: 'application/json',
  });
  await page.screenshot({
    path: info.outputPath('issue-1099-input.png'),
    animations: 'disabled',
  });

  expect(await weight.inputValue()).toBe('50');
  expect(await reps.inputValue()).toBe('12');
  expect(probe.scrollCalls).toEqual([]);
  const inputFrames = probe.frames.filter(
    (
      frame,
    ): frame is Issue1099Frame & {
      activeTop: number;
      activeBottom: number;
      activeControlsTop: number;
      panelBottom: number;
    } =>
      frame.activeTop !== null &&
      frame.activeBottom !== null &&
      frame.activeControlsTop !== null &&
      frame.panelBottom !== null,
  );
  expect(inputFrames.length).toBeGreaterThan(0);
  const inputScrollYs = inputFrames.map((frame) => frame.scrollY);
  expect(Math.max(...inputScrollYs) - Math.min(...inputScrollYs)).toBeLessThanOrEqual(1);
  expect(Math.min(...inputFrames.map((frame) => frame.activeControlsTop))).toBeGreaterThanOrEqual(
    Math.max(...inputFrames.map((frame) => frame.panelBottom)) - 1,
  );
  expect(
    Math.max(
      ...inputFrames.map(
        (frame) => frame.activeBottom - (frame.viewportTop + frame.viewportHeight),
      ),
    ),
  ).toBeLessThanOrEqual(1);
  expect(server.readSet(202).is_completed).toBe(false);
  expect(
    Math.abs((await page.evaluate(() => window.scrollY)) - initialScrollY),
  ).toBeLessThanOrEqual(1);
  expect(row).toBeVisible();
});

async function verifyIssue1099RestSwipe(page: Page, info: TestInfo, surface: 'browser' | 'pwa') {
  test.skip(test.info().project.name !== 'chromium', 'CDP provides deterministic touch drag input');
  const { server, row, reps } = await prepareIssue1099KeyboardCase(page, surface, {
    verifyPwaServiceWorker: false,
  });
  await reps.fill('12');
  await expect.poll(() => server.readSet(202).actual_reps).toBe(12);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  await reps.focus();
  await settleViewport(page);
  const rowBox = (await row.boundingBox())!;
  const swipeX = rowBox.x + 5;
  const swipeY = Math.min(620, Math.max(160, rowBox.y + rowBox.height - 20));
  const touch = await page.context().newCDPSession(page);
  await touch.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
  await page.evaluate(() => {
    (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
  });
  await startIssue1099FrameProbe(page);
  const patchCountBeforeGesture = server.patches.length;

  const swipe = async (deltaY: number) => {
    await touch.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ id: 1, x: swipeX, y: swipeY }],
    });
    for (let step = 1; step <= 10; step += 1) {
      await touch.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ id: 1, x: swipeX, y: swipeY + (deltaY * step) / 10 }],
      });
      if (step === 3 || step === 6 || step === 9) {
        await page.evaluate(
          (offsetTop) => {
            const viewport = window.visualViewport as EventTarget & { offsetTop: number };
            viewport.offsetTop = offsetTop;
            viewport.dispatchEvent(new Event('scroll'));
          },
          step === 3 ? 2 : step === 6 ? 7 : 3,
        );
      }
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      );
    }
    await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await settleViewport(page);
  };

  const before = await page.evaluate(() => window.scrollY);
  await swipe(-180);
  const middle = await page.evaluate(() => window.scrollY);
  await swipe(180);
  const after = await page.evaluate(() => window.scrollY);
  const probe = await stopIssue1099FrameProbe(page);
  const report = { before, middle, after, ...probe };
  await writeFile(
    info.outputPath('issue-1099-rest-swipe-geometry.json'),
    JSON.stringify(report, null, 2),
  );
  await info.attach('issue-1099-rest-swipe-geometry.json', {
    body: JSON.stringify(report, null, 2),
    contentType: 'application/json',
  });
  await page.screenshot({
    path: info.outputPath('issue-1099-rest-swipe.png'),
    animations: 'disabled',
  });

  expect(Math.abs(middle - before)).toBeGreaterThan(50);
  expect(Math.abs(after - middle)).toBeGreaterThan(50);
  expect(probe.scrollCalls).toEqual([]);
  const panelPositions = probe.frames
    .map((frame) => frame.panelRelativeTop)
    .filter((position): position is number => position !== null);
  expect(panelPositions.length).toBeGreaterThan(0);
  expect(Math.max(...panelPositions) - Math.min(...panelPositions)).toBeLessThanOrEqual(1);
  expect(
    await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLButtonElement>('.active-workout-rest button')).map(
        (button) => {
          const box = button.getBoundingClientRect();
          const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
          return Boolean(hit && (hit === button || button.contains(hit)));
        },
      ),
    ),
  ).toEqual([true, true, true, true, true, true]);
  expect(await reps.inputValue()).toBe('12');
  expect(server.readSet(202).is_completed).toBe(false);
  expect(server.patches).toHaveLength(patchCountBeforeGesture);
}

for (const surface of ['browser', 'pwa'] as const) {
  test(`#1099 scenario B keeps the rest panel stable during a real touch swipe in ${surface}`, async ({
    page,
  }, info) => {
    await verifyIssue1099RestSwipe(page, info, surface);
  });
}

test.describe('#1099 standalone PWA keyboard path', () => {
  test.use({ serviceWorkers: 'block' });

  for (const placement of [
    'upper',
    'middle',
    'lower',
    'lower-then-upper-overlap',
    'upper-staged-no-rest',
    'upper-native-scroll-no-rest',
  ] as const) {
    test(`#1099 PWA keeps ${placement} input placement native-owned`, async ({ page }, info) => {
      const { server, weight, reps } = await prepareIssue1099KeyboardCase(page, 'pwa', {
        verifyPwaServiceWorker: false,
        withRest: !placement.endsWith('no-rest'),
      });
      if (placement.endsWith('no-rest')) {
        await page.setViewportSize({
          width: placement === 'upper-staged-no-rest' ? 360 : 430,
          height: 844,
        });
        await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
      }
      const readGeometry = () =>
        weight.evaluate((input) => {
          const viewport = window.visualViewport!;
          const field = input.getBoundingClientRect();
          const controls = input.closest('.active-workout-set__controls')!.getBoundingClientRect();
          const rest = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
          const dock = document.getElementById('appBottomNav')!.getBoundingClientRect();
          const measure = document.createElement('div');
          measure.style.cssText =
            'position:fixed;visibility:hidden;height:var(--yfc-layout-safe-top)';
          document.body.append(measure);
          const inset = measure.getBoundingClientRect().height;
          measure.remove();
          const dockVisible =
            getComputedStyle(document.getElementById('appBottomNav')!).visibility !== 'hidden';
          return {
            scrollY,
            offsetTop: viewport.offsetTop,
            pageTop: viewport.pageTop,
            height: viewport.height,
            fieldTop: field.top,
            fieldBottom: field.bottom,
            controlsTop: controls.top,
            controlsBottom: controls.bottom,
            restTop: rest?.top ?? null,
            restBottom: rest?.bottom ?? null,
            dockTop: dock.top,
            safeTop: Math.max(viewport.offsetTop + inset, rest?.bottom ?? 0),
            keyboardTop: viewport.offsetTop + viewport.height,
            safeBottom: Math.min(
              viewport.offsetTop + viewport.height,
              dockVisible ? dock.top : Infinity,
            ),
            scrollMarginBlock: getComputedStyle(input).scrollMarginBlock,
            scrollMarginBlockStart: getComputedStyle(input).scrollMarginBlockStart,
            scrollPaddingBlock: getComputedStyle(document.documentElement).scrollPaddingBlock,
          };
        });
      await weight.evaluate((input, position) => {
        (document.activeElement as HTMLElement)?.blur();
        const viewport = window.visualViewport as VisualViewport & {
          height: number;
          offsetTop: number;
        };
        Object.assign(viewport, { height: 844, offsetTop: 0 });
        viewport.dispatchEvent(new Event('resize'));
        viewport.dispatchEvent(new Event('scroll'));
        if (position.endsWith('no-rest')) {
          document.documentElement.style.setProperty('--yfc-layout-safe-top', '24px');
        }
        const fieldTop = position.startsWith('upper') ? 240 : position === 'middle' ? 420 : 650;
        window.scrollBy({ top: input.getBoundingClientRect().top - fieldTop, behavior: 'instant' });
      }, placement);
      await settleViewport(page);
      const beforeFocus = await readGeometry();
      await page.evaluate(() => {
        (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
      });
      // These viewport events model native iOS focus-pan, without an application scroll call.
      await weight.evaluate((input, position) => {
        input.focus({ preventScroll: true });
        const viewport = window.visualViewport as VisualViewport & {
          height: number;
          offsetTop: number;
        };
        Object.assign(viewport, {
          height: 420,
          offsetTop:
            position === 'upper'
              ? 100
              : position.startsWith('upper')
                ? input.getBoundingClientRect().top + 20
                : 150,
        });
        viewport.dispatchEvent(new Event('resize'));
        viewport.dispatchEvent(new Event('scroll'));
      }, placement);
      await settleViewport(page);
      if (placement === 'upper-staged-no-rest') {
        // Native focus animation can resume after a plateau, before the first typed digit.
        await page.evaluate(() => {
          const viewport = window.visualViewport as VisualViewport & { offsetTop: number };
          viewport.offsetTop += 40;
          viewport.dispatchEvent(new Event('scroll'));
        });
        await settleViewport(page);
      }
      if (placement === 'upper') {
        // iOS focus-pan may include native document scrolling as well as a
        // visualViewport offset. Model that native part explicitly when the
        // keyboard pan leaves the field behind the pinned rest panel.
        // Use the captured native method: app scroll calls must remain zero.
        await page.evaluate(() => {
          const input = document.activeElement as HTMLElement;
          const viewport = window.visualViewport!;
          const rest = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
          const safeTop = Math.max(viewport.offsetTop, rest?.bottom ?? viewport.offsetTop);
          const overlap = Math.max(0, safeTop - input.getBoundingClientRect().top);
          if (overlap > 0) {
            const nativeTop = Math.max(0, scrollY - overlap);
            (window as Window & { __yfc1099NativeScrollTo?: typeof window.scrollTo })
              .__yfc1099NativeScrollTo!({ top: nativeTop, behavior: 'instant' });
          }
        });
        await settleViewport(page);
      }
      if (placement === 'upper-native-scroll-no-rest') {
        // Model the native document-scroll part independently from application scroll calls.
        await page.evaluate(() => {
          (window as Window & { __yfc1099NativeScrollTo?: typeof window.scrollTo })
            .__yfc1099NativeScrollTo!({ top: scrollY + 40, behavior: 'instant' });
        });
        await settleViewport(page);
      }
      if (placement === 'lower' || placement === 'lower-then-upper-overlap') {
        // Model the native focus pan needed only for a field actually below the keyboard.
        await page.evaluate(() => {
          const input = document.activeElement as HTMLElement;
          const viewport = window.visualViewport!;
          const dock = document.getElementById('appBottomNav')!;
          const dockVisible = getComputedStyle(dock).visibility !== 'hidden';
          const safeBottom = Math.min(
            viewport.offsetTop + viewport.height,
            dockVisible ? dock.getBoundingClientRect().top : Infinity,
          );
          const delta = Math.max(0, input.getBoundingClientRect().bottom - safeBottom);
          if (delta > 0)
            (window as Window & { __yfc1099NativeScrollTo?: typeof window.scrollTo })
              .__yfc1099NativeScrollTo!({ top: scrollY + delta, behavior: 'instant' });
        });
        await settleViewport(page);
      }
      const afterFocus = await readGeometry();
      expect(afterFocus.scrollMarginBlock).toBe('0px');
      expect(afterFocus.scrollPaddingBlock).toBe('0px');
      const calls = await page.evaluate(
        () =>
          (window as Window & { __yfc1099ScrollCalls?: Issue1099Probe['scrollCalls'] })
            .__yfc1099ScrollCalls!,
      );
      const report = { placement, beforeFocus, afterFocus, calls };
      await writeFile(info.outputPath('focus-placement.json'), JSON.stringify(report, null, 2));
      await info.attach('focus-placement.json', {
        body: JSON.stringify(report, null, 2),
        contentType: 'application/json',
      });
      await page.screenshot({
        path: info.outputPath(`pwa-focus-${placement}.png`),
        animations: 'disabled',
      });
      if (!placement.endsWith('no-rest')) {
        expect(
          afterFocus.fieldTop,
          `#1099 ${placement} geometry: ${JSON.stringify(report)}`,
        ).toBeGreaterThanOrEqual(afterFocus.safeTop - 1);
        expect(afterFocus.fieldBottom).toBeLessThanOrEqual(afterFocus.safeBottom + 1);
      }
      // PWA focus placement must not compete with native focus-pan, even when the viewport
      // reports another intermediate position before the first digit is entered.
      expect(calls).toEqual([]);
      // Even before typing, viewport feedback must not scroll an already visible input.
      await page.evaluate(() => {
        const viewport = window.visualViewport as VisualViewport & { offsetTop: number };
        viewport.offsetTop += 2;
        viewport.dispatchEvent(new Event('scroll'));
      });
      await settleViewport(page);
      expect(
        await page.evaluate(
          () =>
            (
              window as Window & { __yfc1099ScrollCalls?: Issue1099Probe['scrollCalls'] }
            ).__yfc1099ScrollCalls!.filter((call) => call.method === 'scrollBy').length,
        ),
      ).toBe(0);

      await page.evaluate(() => {
        (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
      });
      const positionedY = await page.evaluate(() => scrollY);
      let typingY: number | undefined;
      for (const [field, value] of [
        [weight, '50'],
        [reps, '12'],
        [weight, '55'],
        [weight, '50'],
      ] as const) {
        await field.evaluate((input) => input.focus({ preventScroll: true }));
        await page.keyboard.press('ControlOrMeta+A');
        await page.keyboard.type(value);
        await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
        // Unchanged-height viewport noise and ACK must not restart placement while typing.
        await page.evaluate(() => {
          const viewport = window.visualViewport as VisualViewport & { offsetTop: number };
          viewport.offsetTop += 2;
          viewport.dispatchEvent(new Event('scroll'));
          viewport.dispatchEvent(new Event('resize'));
        });
        await settleViewport(page);
        if (typingY === undefined) typingY = await page.evaluate(() => scrollY);
        // The synthetic Chromium viewport can settle a native focus/caret pan by a few CSS pixels;
        // app scroll is asserted separately and must remain empty throughout this PWA sequence.
        else await expectScrollYStable(page, typingY, 4);
      }
      await expect.poll(() => server.readSet(202).actual_weight).toBe(50);
      await expect.poll(() => server.readSet(202).actual_reps).toBe(12);
      expect(server.readSet(202).is_completed).toBe(false);
      await writeFile(
        info.outputPath('typing-placement.json'),
        JSON.stringify(
          {
            positionedY,
            geometry: await readGeometry(),
            calls: await page.evaluate(
              () => (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls,
            ),
          },
          null,
          2,
        ),
      );
      await expectScrollYStable(page, typingY!, 4);
      expect(
        await page.evaluate(() =>
          (
            (window as Window & { __yfc1099ScrollCalls?: Issue1099Probe['scrollCalls'] })
              .__yfc1099ScrollCalls ?? []
          ).filter((call) => call.method === 'scrollBy'),
        ),
      ).toEqual([]);
      expect(
        await page.evaluate(
          (positionedY) =>
            (
              (window as Window & { __yfc1099ScrollCalls?: Issue1099Probe['scrollCalls'] })
                .__yfc1099ScrollCalls ?? []
            ).every((call) => call.method === 'scrollTo' && Math.abs(call.top - positionedY) <= 1),
          positionedY,
        ),
      ).toBe(true);
      await expect(weight).toBeFocused();
      await weight.evaluate((input) => {
        input.blur();
        const viewport = window.visualViewport as VisualViewport & {
          height: number;
          offsetTop: number;
        };
        Object.assign(viewport, { height: 844, offsetTop: 0 });
        viewport.dispatchEvent(new Event('resize'));
        viewport.dispatchEvent(new Event('scroll'));
      });
      await settleViewport(page);
      await expectScrollYStable(page, typingY!, 4);
      if (!placement.endsWith('no-rest')) {
        await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
      }
      await weight.evaluate((input) => {
        input.focus({ preventScroll: true });
        const viewport = window.visualViewport as VisualViewport & { height: number };
        viewport.height = 420;
        viewport.dispatchEvent(new Event('resize'));
      });
      await page.evaluate(() => {
        const input = document.activeElement as HTMLElement;
        const viewport = window.visualViewport!;
        const dock = document.getElementById('appBottomNav')!;
        const dockVisible = getComputedStyle(dock).visibility !== 'hidden';
        const safeBottom = Math.min(
          viewport.offsetTop + viewport.height,
          dockVisible ? dock.getBoundingClientRect().top : Infinity,
        );
        const delta = Math.max(0, input.getBoundingClientRect().bottom - safeBottom);
        if (delta > 0)
          (window as Window & { __yfc1099NativeScrollTo?: typeof window.scrollTo })
            .__yfc1099NativeScrollTo!({ top: scrollY + delta, behavior: 'instant' });
      });
      await settleViewport(page);
      const reopened = await readGeometry();
      expect(reopened.fieldTop).toBeGreaterThanOrEqual(reopened.safeTop - 1);
      expect(reopened.fieldBottom).toBeLessThanOrEqual(reopened.safeBottom + 1);
      await expect(weight).toHaveValue('50');
      await expect(reps).toHaveValue('12');
      await expect(weight).toBeFocused();
    });
  }

  test('#1099 PWA keeps input geometry stable during viewport pan events', async ({
    page,
  }, info) => {
    const { server, row, weight, reps } = await prepareIssue1099KeyboardCase(page, 'pwa', {
      verifyPwaServiceWorker: false,
    });
    await focusWithPointer(weight);
    // The mocked visual viewport cannot perform iOS's native focus pan.
    await weight.evaluate((input) => {
      const viewport = window.visualViewport!;
      const field = input.getBoundingClientRect();
      const rest = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
      const top = Math.max(viewport.offsetTop, rest?.bottom ?? 0) + 8;
      const bottom = viewport.offsetTop + viewport.height - 8;
      const delta = field.top < top ? field.top - top : Math.max(0, field.bottom - bottom);
      (window as Window & { __yfc1099NativeScrollTo?: typeof window.scrollTo })
        .__yfc1099NativeScrollTo!({
        top: window.scrollY + delta,
        behavior: 'instant',
      });
    });
    await settleViewport(page);
    await settleViewport(page);
    const initialScrollY = await page.evaluate(() => window.scrollY);
    const initialCalls = await page.evaluate(
      () => (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls ?? [],
    );
    await page.evaluate(() => {
      (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
    });
    await startIssue1099FrameProbe(page);

    const emitPwaViewportEvents = async (offsetTop: number) => {
      await page.evaluate((nextOffsetTop) => {
        const viewport = window.visualViewport as EventTarget & {
          offsetTop: number;
        };
        viewport.offsetTop = nextOffsetTop;
        viewport.dispatchEvent(new Event('scroll'));
        viewport.dispatchEvent(new Event('resize'));
        window.dispatchEvent(new Event('resize'));
      }, offsetTop);
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      );
    };

    for (const [weightValue, repsValue] of [
      ['50', '12'],
      ['55', '11'],
      ['50', '12'],
    ] as const) {
      await focusWithPointer(weight);
      await weight.fill('');
      await weight.pressSequentially(weightValue);
      await emitPwaViewportEvents(2);
      await expect.poll(() => server.readSet(202).actual_weight).toBe(Number(weightValue));
      await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
      await focusWithPointer(reps);
      await reps.fill('');
      await reps.pressSequentially(repsValue);
      await emitPwaViewportEvents(7);
      await expect.poll(() => server.readSet(202).actual_reps).toBe(Number(repsValue));
      await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
    }

    const probe = await stopIssue1099FrameProbe(page);
    const lifecycle = await page.evaluate(
      () =>
        (
          window as Window & {
            __yfc1099Lifecycle?: Array<Record<string, unknown>>;
          }
        ).__yfc1099Lifecycle ?? [],
    );
    const report = { initialScrollY, initialCalls, lifecycle, ...probe };
    await writeFile(
      info.outputPath('issue-1099-pwa-input-geometry.json'),
      JSON.stringify(report, null, 2),
    );
    await info.attach('issue-1099-pwa-input-geometry.json', {
      body: JSON.stringify(report, null, 2),
      contentType: 'application/json',
    });
    await page.screenshot({
      path: info.outputPath('issue-1099-pwa-before.png'),
      animations: 'disabled',
    });
    const inputFrames = probe.frames.filter(
      (
        frame,
      ): frame is Issue1099Frame & {
        activeTop: number;
        activeBottom: number;
        activeControlsTop: number;
        panelBottom: number;
      } =>
        frame.activeTop !== null &&
        frame.activeBottom !== null &&
        frame.activeControlsTop !== null &&
        frame.panelBottom !== null,
    );
    expect(await weight.inputValue()).toBe('50');
    expect(await reps.inputValue()).toBe('12');
    expect(
      lifecycle.filter((event) => event.source === 'visualViewport.scroll').length,
    ).toBeGreaterThan(0);
    expect(
      lifecycle.filter((event) => event.source === 'visualViewport.resize').length,
    ).toBeGreaterThan(0);
    expect(probe.scrollCalls.filter((call) => call.method === 'scrollBy')).toEqual([]);
    const focusRestores = probe.scrollCalls
      .filter((call) => call.method === 'scrollTo')
      .map((call) => Math.round(call.top));
    expect(new Set(focusRestores).size).toBeLessThanOrEqual(1);
    expect(inputFrames.length).toBeGreaterThan(0);
    expect(Math.min(...inputFrames.map((frame) => frame.activeTop))).toBeGreaterThanOrEqual(
      Math.max(...inputFrames.map((frame) => frame.panelBottom)) - 1,
    );
    expect(
      Math.max(
        ...inputFrames.map(
          (frame) => frame.activeBottom - (frame.viewportTop + frame.viewportHeight),
        ),
      ),
    ).toBeLessThanOrEqual(1);
    expect(server.readSet(202).is_completed).toBe(false);
    await expect(row).toBeVisible();
  });

  test('#1099 PWA does not scroll when a blurred input receives its ACK', async ({ page }) => {
    const { server, weight } = await prepareIssue1099KeyboardCase(page, 'pwa', {
      verifyPwaServiceWorker: false,
    });
    await weight.focus();
    const patchCount = server.patches.length;
    await page.evaluate(() => {
      (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
    });
    const release = server.holdNextPatch();
    await weight.fill('50');
    await expect.poll(() => server.patches.length).toBeGreaterThan(patchCount);
    await weight.blur();
    release();
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    expect(
      await page.evaluate(
        () => (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls,
      ),
    ).toEqual([]);
  });
});

test('#1099 TMA control keeps the same input sequence stable', async ({ page }) => {
  const { server, weight, reps } = await prepareIssue1099KeyboardCase(page, 'telegram');
  expect(await weight.evaluate((input) => getComputedStyle(input).scrollMarginBlockStart)).not.toBe(
    '0px',
  );
  await weight.focus();
  await settleViewport(page);
  const initialScrollY = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => {
    (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls!.length = 0;
  });
  for (const [weightValue, repsValue] of [
    ['50', '12'],
    ['55', '11'],
    ['50', '12'],
  ] as const) {
    await weight.focus();
    await weight.fill('');
    await weight.pressSequentially(weightValue);
    await expect.poll(() => server.readSet(202).actual_weight).toBe(Number(weightValue));
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
    await reps.focus();
    await reps.fill('');
    await reps.pressSequentially(repsValue);
    await expect.poll(() => server.readSet(202).actual_reps).toBe(Number(repsValue));
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  }
  expect(await weight.inputValue()).toBe('50');
  expect(await reps.inputValue()).toBe('12');
  expect(await page.evaluate(() => window.scrollY)).toBe(initialScrollY);
  expect(
    await page.evaluate(
      () => (window as Window & { __yfc1099ScrollCalls?: unknown[] }).__yfc1099ScrollCalls,
    ),
  ).toEqual([]);
});

test.describe('#1001 keyboard input stability', () => {
  test.use({
    isMobile: async ({ browserName }, provide) => provide(browserName !== 'firefox'),
    hasTouch: true,
    deviceScaleFactor: 3,
  });
  for (const width of [320, 360, 393, 430]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`autosave preserves focused fields at ${width}px ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({
          colorScheme: theme,
          reducedMotion: theme === 'dark' ? 'reduce' : 'no-preference',
        });
        await page.addInitScript((value) => {
          localStorage.setItem('app-theme', value);
          const viewport = new EventTarget();
          Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
          Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
        }, theme);
        const server = await mockActiveWorkout(page, true, 'approved_animated', false, null, true);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const first = page.locator('[data-workout-set-id="201"]');
        await first.getByLabel(/^Вес,/).fill('40');
        await first.getByLabel(/^Повторы,/).fill('10');
        await first.getByRole('button', { name: /^Завершить:/ }).click();
        await expect.poll(() => server.readSet(201).is_completed).toBe(true);
        await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
        await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
        const row = page.locator('[data-workout-set-id="202"]');
        const weight = row.getByLabel(/^Вес,/);
        const reps = row.getByLabel(/^Повторы,/);
        // Model an iOS keyboard without resizing the layout viewport.
        await page.evaluate(() => {
          Object.assign(window.visualViewport!, { height: 420 });
          window.visualViewport!.dispatchEvent(new Event('resize'));
        });
        await weight.focus();
        const assertFields = async () => {
          await expect
            .poll(() =>
              row.evaluate((element) => {
                const viewport = window.visualViewport!;
                const timer = document
                  .querySelector('.active-workout-rest')!
                  .getBoundingClientRect();
                const boxes = [...element.querySelectorAll('[data-workout-field]')].map((input) =>
                  input.getBoundingClientRect(),
                );
                return Math.max(
                  ...boxes.map((box) =>
                    Math.max(
                      Math.max(viewport.offsetTop, timer.bottom) - box.top,
                      box.bottom - viewport.offsetTop - viewport.height,
                    ),
                  ),
                );
              }),
            )
            .toBeLessThanOrEqual(0.5);
        };
        await assertFields();
        for (let index = 0; index < 3; index++) {
          await weight.focus();
          await weight.fill('');
          const weightScrollY = await stableScrollY(page);
          await weight.pressSequentially(index === 1 ? '6.5' : '5.5');
          await expect.poll(() => server.readSet(202).actual_weight).toBe(index === 1 ? 6.5 : 5.5);
          await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
          await expect(weight).toBeFocused();
          await assertFields();
          await expectScrollYStable(page, weightScrollY);
          await reps.focus();
          await reps.fill('');
          const repsScrollY = await stableScrollY(page);
          await reps.pressSequentially(index === 1 ? '11' : '12');
          await expect.poll(() => server.readSet(202).actual_reps).toBe(index === 1 ? 11 : 12);
          await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
          await expect(reps).toBeFocused();
          await assertFields();
          await expectScrollYStable(page, repsScrollY);
          await page.evaluate(
            (height) => {
              Object.assign(window.visualViewport!, { height });
              window.visualViewport!.dispatchEvent(new Event('resize'));
            },
            index === 1 ? 460 : 420,
          );
          await assertFields();
        }
        expect(server.readSet(202).is_completed).toBe(false);
        expect(server.readSet(203).actual_weight).toBeNull();
        await page.evaluate(() => {
          Object.assign(window.visualViewport!, { height: 844, offsetTop: 0 });
          window.visualViewport!.dispatchEvent(new Event('resize'));
          (document.activeElement as HTMLElement).blur();
        });
        await reps.focus();
        await page.evaluate(() => {
          Object.assign(window.visualViewport!, { height: 420, offsetTop: 20 });
          window.visualViewport!.dispatchEvent(new Event('resize'));
          window.visualViewport!.dispatchEvent(new Event('scroll'));
        });
        await assertFields();
        await page.evaluate(
          () =>
            new Promise<void>((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
            ),
        );
        await page.evaluate(() => window.scrollBy({ top: 40, behavior: 'instant' }));
        const manualScroll = await page.evaluate(() => scrollY);
        await reps.fill('13');
        await expect.poll(() => server.readSet(202).actual_reps).toBe(13);
        await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
        expect(await page.evaluate(() => scrollY)).toBe(manualScroll);
        await reps.fill('12');
        await expect.poll(() => server.readSet(202).actual_reps).toBe(12);
        await row.getByRole('button', { name: /^Завершить:/ }).click();
        await expect.poll(() => server.readSet(202).is_completed).toBe(true);
        await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
        await page.reload();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        await expect(row.getByLabel(/^Вес,/)).toHaveValue('5.5');
        await expect(row.getByLabel(/^Повторы,/)).toHaveValue('12');
        await first.getByRole('button', { name: 'Редактировать', exact: true }).click();
        await first.getByLabel(/^Вес,/).fill('41');
        await expect(first.getByLabel(/^Вес,/)).toBeFocused();
        expect(server.readSet(201).is_completed).toBe(true);
      });
    }
  }
});

test('#1099 keeps scroll stable after keyboard input and server ACK', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const viewport = new EventTarget() as EventTarget & {
      height: number;
      width: number;
      offsetTop: number;
    };
    Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    const calls: Array<{ method: string; top: number }> = [];
    Object.defineProperty(window, '__yfc1099ScrollCalls', {
      configurable: true,
      value: calls,
    });
    for (const method of ['scrollBy', 'scrollTo'] as const) {
      const original = window[method].bind(window);
      window[method] = (options?: ScrollToOptions | number, y?: number) => {
        const top = typeof options === 'number' ? (y ?? 0) : (options?.top ?? window.scrollY);
        calls.push({ method, top });
        if (typeof options === 'number') original(options, y ?? 0);
        else original(options);
      };
    }
  });
  const server = await mockActiveWorkout(page, false, 'approved_animated', false, null, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('40');
  await first.getByLabel(/^Повторы,/).fill('10');
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  const row = page.locator('[data-workout-set-id="202"]');
  const weight = row.getByLabel(/^Вес,/);
  const reps = row.getByLabel(/^Повторы,/);
  await page.evaluate(() => {
    const viewport = window.visualViewport as EventTarget & { height: number };
    viewport.height = 420;
    viewport.dispatchEvent(new Event('resize'));
  });
  await weight.focus();
  const initialScrollY = await stableScrollY(page);
  await page.evaluate(() => {
    (window as Window & { __yfc1099ScrollCalls?: Array<unknown> }).__yfc1099ScrollCalls!.length = 0;
  });
  await weight.pressSequentially('50');
  await expect.poll(() => server.readSet(202).actual_weight).toBe(50);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  await expect(weight).toBeFocused();
  await expectScrollYStable(page, initialScrollY);
  expect(
    await page.evaluate(
      () => (window as Window & { __yfc1099ScrollCalls?: Array<unknown> }).__yfc1099ScrollCalls,
    ),
  ).toEqual([]);

  await reps.focus();
  const repsScrollY = await stableScrollY(page);
  await page.evaluate(() => {
    (window as Window & { __yfc1099ScrollCalls?: Array<unknown> }).__yfc1099ScrollCalls!.length = 0;
  });
  await reps.pressSequentially('12');
  await expect.poll(() => server.readSet(202).actual_reps).toBe(12);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  await expect(reps).toBeFocused();
  await expectScrollYStable(page, repsScrollY);
  expect(
    await page.evaluate(
      () => (window as Window & { __yfc1099ScrollCalls?: Array<unknown> }).__yfc1099ScrollCalls,
    ),
  ).toEqual([]);
});

test('#1161 keeps a deliberate manual scroll after focused workout input', async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== 'chromium',
    'Chromium CDP provides the deterministic touch swipe input',
  );
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    localStorage.setItem('app-theme', 'dark');
    const viewport = new EventTarget() as EventTarget & {
      height: number;
      width: number;
      offsetTop: number;
    };
    Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
    const calls: string[] = [];
    Object.assign(window, { __yfc1161ScrollCalls: calls });
    for (const method of ['scrollBy', 'scrollTo'] as const) {
      const original = window[method].bind(window);
      window[method] = (options?: ScrollToOptions | number, y?: number) => {
        calls.push(method);
        if (typeof options === 'number') original(options, y ?? 0);
        else original(options);
      };
    }
  });
  const server = await mockActiveWorkout(page, false, 'approved_animated', false, null, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('40');
  await first.getByLabel(/^Повторы,/).fill('10');
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();

  const row = page.locator('[data-workout-set-id="202"]');
  const weight = row.getByLabel(/^Вес,/);
  const reps = row.getByLabel(/^Повторы,/);
  await weight.fill('85');
  await reps.fill('12');
  await expect.poll(() => server.readSet(202).actual_weight).toBe(85);
  await expect.poll(() => server.readSet(202).actual_reps).toBe(12);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  await page.evaluate(() => {
    const viewport = window.visualViewport as EventTarget & { height: number };
    viewport.height = 420;
    viewport.dispatchEvent(new Event('resize'));
  });
  await reps.focus();
  const before = await stableScrollY(page);
  await page.evaluate(() => {
    (window as Window & { __yfc1161ScrollCalls?: string[] }).__yfc1161ScrollCalls!.length = 0;
  });
  const patchCountBeforeGesture = server.patches.length;

  const rowBox = (await row.boundingBox())!;
  const swipeX = rowBox.x + 5;
  const swipeY = Math.min(620, Math.max(160, rowBox.y + rowBox.height - 20));
  const touch = await page.context().newCDPSession(page);
  await touch.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 });
  const swipe = async (deltaY: number) => {
    await touch.send('Input.dispatchTouchEvent', {
      type: 'touchStart',
      touchPoints: [{ id: 1, x: swipeX, y: swipeY }],
    });
    for (let step = 1; step <= 8; step += 1) {
      await touch.send('Input.dispatchTouchEvent', {
        type: 'touchMove',
        touchPoints: [{ id: 1, x: swipeX, y: swipeY + (deltaY * step) / 8 }],
      });
      if (step === 2) {
        await page.evaluate(
          (offsetTop) => {
            const viewport = window.visualViewport as EventTarget & { offsetTop: number };
            viewport.offsetTop = offsetTop;
            viewport.dispatchEvent(new Event('scroll'));
          },
          deltaY > 0 ? 1 : 2,
        );
      }
    }
    const duringGesture = await page.evaluate(() => window.scrollY);
    await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    return duringGesture;
  };

  const duringGesture = await swipe(180);

  const afterGesture = await stableScrollY(page);
  expect(Math.abs(duringGesture - before)).toBeGreaterThan(10);
  expect(Math.abs(afterGesture - before)).toBeGreaterThan(50);
  expect(
    await page.evaluate(
      () => (window as Window & { __yfc1161ScrollCalls?: string[] }).__yfc1161ScrollCalls,
    ),
  ).toEqual([]);
  expect(await reps.inputValue()).toBe('12');
  expect(server.patches).toHaveLength(patchCountBeforeGesture);
  expect(server.readSet(202).is_completed).toBe(false);

  const beforeReturn = await stableScrollY(page);
  const duringReturn = await swipe(-180);
  const afterReturn = await stableScrollY(page);
  expect(Math.abs(duringReturn - beforeReturn)).toBeGreaterThan(10);
  expect(Math.abs(afterReturn - beforeReturn)).toBeGreaterThan(50);
  expect(await reps.inputValue()).toBe('12');
});

type RestPanelProbe = {
  phase: string;
  scrollY: number;
  viewport: { top: number; bottom: number; height: number };
  safeTop: number;
  panel: { top: number; bottom: number; height: number; position: string };
  fullPanelVisible: boolean;
  nearViewportTop: boolean;
  buttonHits: boolean[];
  scrollEvents: Array<{ source: string; scrollY: number; viewportTop: number }>;
  scrollAncestors: Array<{
    tag: string;
    className: string;
    overflowY: string;
    position: string;
    transform: string;
    contain: string;
    scrollHeight: number;
    clientHeight: number;
  }>;
};

async function readRestPanelProbe(page: Page, phase: string): Promise<RestPanelProbe> {
  return page.evaluate((label) => {
    const panel = document.querySelector<HTMLElement>('.active-workout-rest');
    if (!panel) throw new Error('Active rest panel is missing');
    const visualViewport = window.visualViewport;
    const viewportTop = visualViewport?.offsetTop ?? 0;
    const viewportHeight = visualViewport?.height ?? window.innerHeight;
    const viewportBottom = viewportTop + viewportHeight;
    const panelBox = panel.getBoundingClientRect();
    const safeTop =
      Number.parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--yfc-layout-safe-top'),
      ) || 0;
    const scrollAncestors = [];
    let ancestor = panel.parentElement;
    while (ancestor) {
      const style = getComputedStyle(ancestor);
      if (
        ancestor.scrollHeight > ancestor.clientHeight ||
        ['auto', 'overlay', 'scroll'].includes(style.overflowY)
      ) {
        scrollAncestors.push({
          tag: ancestor.tagName,
          className: typeof ancestor.className === 'string' ? ancestor.className : '',
          overflowY: style.overflowY,
          position: style.position,
          transform: style.transform,
          contain: style.contain,
          scrollHeight: ancestor.scrollHeight,
          clientHeight: ancestor.clientHeight,
        });
      }
      ancestor = ancestor.parentElement;
    }
    const buttonHits = Array.from(panel.querySelectorAll<HTMLButtonElement>('button')).map(
      (button) => {
        const box = button.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return Boolean(hit && (hit === button || button.contains(hit)));
      },
    );
    const scrollEvents =
      (
        window as unknown as {
          __yfc1165ScrollEvents?: Array<{ source: string; scrollY: number; viewportTop: number }>;
        }
      ).__yfc1165ScrollEvents ?? [];
    return {
      phase: label,
      scrollY: window.scrollY,
      viewport: { top: viewportTop, bottom: viewportBottom, height: viewportHeight },
      safeTop,
      panel: {
        top: panelBox.top,
        bottom: panelBox.bottom,
        height: panelBox.height,
        position: getComputedStyle(panel).position,
      },
      fullPanelVisible:
        panelBox.top >= viewportTop + safeTop - 1 && panelBox.bottom <= viewportBottom + 1,
      nearViewportTop: panelBox.top <= viewportTop + safeTop + 3,
      buttonHits,
      scrollEvents: scrollEvents.slice(-20),
      scrollAncestors,
    };
  }, phase);
}

async function run1165GeometryCase(
  page: Page,
  width: number,
  theme: 'dark' | 'light',
  phase: string,
  info: {
    outputPath: (path: string) => string;
    attach: (name: string, options: { body: string; contentType: string }) => Promise<void>;
  },
) {
  await page.setViewportSize({ width, height: 844 });
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((value) => {
    localStorage.setItem('app-theme', value);
    const viewport = new EventTarget() as EventTarget & {
      height: number;
      width: number;
      offsetTop: number;
    };
    Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
  }, theme);
  const server = await mockActiveWorkout(page, false, 'approved_animated', false, null, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('40');
  await first.getByLabel(/^Повторы,/).fill('10');
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();

  const panel = page.locator('.active-workout-rest');
  const panelDocumentTop = await panel.evaluate(
    (element) => element.getBoundingClientRect().top + scrollY,
  );
  await page.evaluate(() => {
    const events: Array<{ source: string; scrollY: number; viewportTop: number }> = [];
    const record = (source: string) =>
      events.push({
        source,
        scrollY: window.scrollY,
        viewportTop: window.visualViewport?.offsetTop ?? 0,
      });
    window.addEventListener('scroll', () => record('window'), { passive: true });
    window.visualViewport?.addEventListener('scroll', () => record('visualViewport'), {
      passive: true,
    });
    Object.assign(window, { __yfc1165ScrollEvents: events });
  });
  const maxScroll = await page.evaluate(() => {
    const scrolling = document.scrollingElement ?? document.documentElement;
    return Math.max(0, scrolling.scrollHeight - window.innerHeight);
  });
  const scrollPoints = [
    Math.min(maxScroll, panelDocumentTop + 80),
    Math.min(maxScroll, Math.round(maxScroll * 0.55)),
    maxScroll,
  ];
  const probes: RestPanelProbe[] = [];
  for (const [index, top] of scrollPoints.entries()) {
    await page.evaluate((value) => window.scrollTo({ top: value, behavior: 'instant' }), top);
    await settleViewport(page);
    probes.push(await readRestPanelProbe(page, `scroll-${index}`));
    await page.screenshot({
      path: info.outputPath(`issue-1165-${phase}-${theme}-${width}-scroll-${index}.png`),
      fullPage: false,
      animations: 'disabled',
    });
  }

  await page.evaluate(() => {
    const viewport = window.visualViewport as EventTarget & { height: number; offsetTop: number };
    Object.assign(viewport, { height: 420, offsetTop: 20 });
    viewport.dispatchEvent(new Event('resize'));
    viewport.dispatchEvent(new Event('scroll'));
  });
  const nextWeight = page.locator('[data-workout-set-id="202"]').getByLabel(/^Вес,/);
  await nextWeight.focus();
  await settleViewport(page);
  probes.push(await readRestPanelProbe(page, 'keyboard'));
  await page.screenshot({
    path: info.outputPath(`issue-1165-${phase}-${theme}-${width}-keyboard.png`),
    fullPage: false,
    animations: 'disabled',
  });
  await info.attach(`issue-1165-${phase}-${theme}-${width}.json`, {
    body: JSON.stringify(probes, null, 2),
    contentType: 'application/json',
  });
  return probes;
}

for (const width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#1165 rest panel geometry at ${width}px ${theme}`, async ({ page }, info) => {
      const phase = process.env.YFC_1165_EVIDENCE_PHASE ?? 'after';
      const probes = await run1165GeometryCase(page, width, theme, phase, info);
      const failures = probes.flatMap((probe) => {
        const issues = [];
        if (!probe.fullPanelVisible) issues.push(`${probe.phase}: panel clipped by viewport`);
        if (probe.phase !== 'scroll-0' && !probe.nearViewportTop)
          issues.push(`${probe.phase}: panel is not pinned to viewport top`);
        if (probe.buttonHits.some((hit) => !hit))
          issues.push(`${probe.phase}: timer button hit test failed`);
        return issues;
      });
      expect(failures, JSON.stringify({ width, theme, probes }, null, 2)).toEqual([]);
    });
  }
}

// #1306: do not mistake a sticky end-of-scroll position for viewport stability.
// Check the panel on each animation frame while the workout itself actually moves.
for (const width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#1306 rest panel does not move during mobile scroll at ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => {
        localStorage.setItem('app-theme', value);
        const viewport = new EventTarget();
        Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
        Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
      }, theme);
      const server = await mockActiveWorkout(page, false, 'approved_animated', false, null, true);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('40');
      await first.getByLabel(/^Повторы,/).fill('10');
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(true);

      const panel = page.locator('.active-workout-rest');
      await expect(panel).toHaveCSS('position', 'fixed');
      await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();

      const probe = async () =>
        page.evaluate(async () => {
          const element = document.querySelector<HTMLElement>('.active-workout-rest');
          if (!element) throw new Error('Missing rest panel');
          const scrolling = document.scrollingElement ?? document.documentElement;
          const maxScroll = Math.max(0, scrolling.scrollHeight - innerHeight);
          const samples: Array<{ scrollY: number; top: number; left: number }> = [];
          for (const progress of [0, 0.3, 0.65, 1, 0.8, 0.45, 0.1, 0.95, 0.2]) {
            window.scrollTo({ top: Math.round(maxScroll * progress), behavior: 'instant' });
            await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
            const rect = element.getBoundingClientRect();
            samples.push({ scrollY: window.scrollY, top: rect.top, left: rect.left });
          }
          return samples;
        });

      for (const phase of ['running', 'collapsed']) {
        if (phase === 'collapsed') {
          await panel.getByRole('button', { name: 'Свернуть таймер' }).click();
          await expect(panel.getByRole('button', { name: 'Развернуть таймер' })).toBeVisible();
        }
        const samples = await probe();
        const tops = samples.map((sample) => sample.top);
        const lefts = samples.map((sample) => sample.left);
        const scrollPositions = samples.map((sample) => sample.scrollY);
        expect(
          Math.max(...scrollPositions) - Math.min(...scrollPositions),
          JSON.stringify({ width, theme, phase, samples }),
        ).toBeGreaterThan(100);
        expect(
          Math.max(...tops) - Math.min(...tops),
          JSON.stringify({ width, theme, phase, samples }),
        ).toBeLessThanOrEqual(1);
        expect(Math.max(...lefts) - Math.min(...lefts)).toBeLessThanOrEqual(1);
      }
    });
  }
}

test.describe('#1001 completion navigation', () => {
  test.use({
    isMobile: async ({ browserName }, provide) => provide(browserName !== 'firefox'),
    hasTouch: true,
  });
  for (const width of [320, 360, 393, 430]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`one accepted transition at ${width}px ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'no-preference' });
        await page.addInitScript((theme) => {
          localStorage.setItem('app-theme', theme);
          const viewport = new EventTarget();
          Object.assign(viewport, { height: 844, width: innerWidth, offsetTop: 0 });
          Object.defineProperty(window, 'visualViewport', { configurable: true, value: viewport });
          const calls: string[] = [];
          Object.assign(window, { completionScrolls: calls });
          for (const method of ['scrollBy', 'scrollTo'] as const) {
            const original = window[method].bind(window);
            window[method] = (options?: ScrollToOptions | number, y?: number) => {
              calls.push(method);
              if (typeof options === 'number') original(options, y ?? 0);
              else original(options);
            };
          }
          const original = Element.prototype.scrollIntoView;
          Element.prototype.scrollIntoView = function (options) {
            calls.push('scrollIntoView');
            original.call(this, options);
          };
        }, theme);
        const server = await mockActiveWorkout(page, true, 'approved_animated', false, null, true);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const currentSet = page.locator('.active-workout-set.is-current');
        await expect(currentSet).toHaveCount(1);
        await expect(currentSet).toHaveCSS('box-shadow', 'none');
        await expect(currentSet).toHaveCSS('border-width', '1px');
        await expect(currentSet).toHaveCSS('border-color', 'rgb(178, 245, 32)');
        for (const [id, nextId] of [
          [201, 202],
          [202, 203],
          [203, 204],
          [204, 500],
        ] as const) {
          const row = page.locator(`[data-workout-set-id="${id}"]`);
          const releaseAutosave = id === 203 ? server.holdNextPatch() : null;
          if (id === 204) await row.getByLabel(/^Длительность,/).fill('25');
          else {
            await row.getByLabel(/^Вес,/).fill('50');
            if (releaseAutosave) await expect.poll(() => server.patches.at(-1)?.setId).toBe(id);
            await row.getByLabel(/^Повторы,/).fill('15');
          }
          if (!releaseAutosave) await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
          if (id === 201) {
            const rir = row.getByRole('button', { name: /^2 —/ });
            await rir.scrollIntoViewIfNeeded();
            const box = (await rir.boundingBox())!;
            await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
            await page.mouse.down();
            const before = await page.evaluate(() => scrollY);
            await page.evaluate(() => {
              Object.assign(window.visualViewport!, { height: 420 });
              window.visualViewport!.dispatchEvent(new Event('resize'));
              return new Promise<void>((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
              );
            });
            expect(await page.evaluate(() => scrollY)).toBe(before);
            await page.mouse.up();
            await expect(rir).toHaveAttribute('aria-pressed', 'true');
            await expect.poll(() => server.readSet(id).rir).toBe('2');
            await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
          }
          if (id === 202) await setNetworkOffline(page, true);
          const patchCount = server.patches.length;
          const releaseCompletion = id === 201 ? server.holdNextPatch() : null;
          const release = releaseAutosave ?? releaseCompletion;
          await page.evaluate(
            (keyboard) => {
              Object.assign(window.visualViewport!, { height: keyboard ? 420 : 844, offsetTop: 0 });
              window.visualViewport!.dispatchEvent(new Event('resize'));
            },
            id === 202 || id === 203,
          );
          const done = row.locator('[data-workout-field="done"]');
          await done.scrollIntoViewIfNeeded();
          await page.evaluate(
            () =>
              new Promise<void>((resolve) =>
                requestAnimationFrame(() => {
                  (window as unknown as { completionScrolls: string[] }).completionScrolls.length =
                    0;
                  resolve();
                }),
              ),
          );
          await done.click();
          if (release) {
            try {
              if (releaseCompletion) {
                await expect.poll(() => server.patches.length).toBe(patchCount + 1);
                expect(server.patches.at(-1)?.body.is_completed).toBe(true);
              }
              expect(server.readSet(id).is_completed).toBe(false);
              await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
                'data-workout-set-id',
                String(id),
              );
              expect(
                await page.evaluate(
                  () => (window as unknown as { completionScrolls: string[] }).completionScrolls,
                ),
              ).toEqual([]);
            } finally {
              release();
            }
          }
          await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
            'data-workout-set-id',
            String(nextId),
          );
          if (id === 202 || id === 203) {
            await expect(page.locator('html')).toHaveAttribute(
              'data-yfc-workout-keyboard-closing',
              '',
            );
            await expect(page.locator('#appBottomNav')).toBeHidden();
          }
          const next = page.locator(`[data-workout-set-id="${nextId}"]`);
          await expect
            .poll(() =>
              next.evaluate((element) => {
                const viewport = window.visualViewport!;
                const timer = document
                  .querySelector('.active-workout-rest')
                  ?.getBoundingClientRect();
                const dock = document.getElementById('appBottomNav')?.getBoundingClientRect();
                const top = Math.max(viewport.offsetTop, timer?.bottom ?? 0);
                const bottom = Math.min(
                  viewport.offsetTop + viewport.height,
                  dock?.height ? dock.top : Infinity,
                );
                const controls = element
                  .querySelector('.active-workout-set__controls')!
                  .getBoundingClientRect();
                return Math.max(top - controls.top, controls.bottom - bottom);
              }),
            )
            .toBeLessThanOrEqual(1);
          if (id === 202) await setNetworkOffline(page, false);
          // Wait for the server to persist the offline completion before starting
          // the next held-autosave scenario. Queue length zero alone can precede
          // the server acknowledgement and lead to a stale current-set reload.
          await expect.poll(() => server.readSet(id).is_completed).toBe(true);
          await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
          await page.evaluate(() => {
            Object.assign(window.visualViewport!, { height: 844 });
            window.visualViewport!.dispatchEvent(new Event('resize'));
          });
          await expect(page.locator('html')).not.toHaveAttribute(
            'data-yfc-workout-keyboard-closing',
            '',
          );
          await expect(page.locator('#appBottomNav')).toBeVisible();
          await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
          await page.evaluate(
            () =>
              new Promise<void>((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
              ),
          );
          expect(
            await page.evaluate(
              () => (window as unknown as { completionScrolls: string[] }).completionScrolls,
            ),
          ).toEqual(['scrollBy']);
          expect(server.readSet(id)).toMatchObject(
            id === 204
              ? { is_completed: true, duration_minutes: 25 }
              : {
                  is_completed: true,
                  actual_weight: 50,
                  actual_reps: 15,
                  ...(id === 201 ? { rir: '2' } : {}),
                },
          );
          if (id !== 204) await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
        }
      });
    }
  }
});

test('does not restore a completed set after a stale reconnect refetch', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('40');
  await first.getByLabel(/^Повторы,/).fill('10');
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);

  const second = page.locator('[data-workout-set-id="202"]');
  await setNetworkOffline(page, true);
  await second.getByLabel(/^Вес,/).fill('50');
  await second.getByLabel(/^Повторы,/).fill('15');
  await second.getByRole('button', { name: /^Завершить:/ }).click();
  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '203');
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(1);

  const readsBeforeReconnect = server.workoutReadCount();
  const responsesBeforeReconnect = server.workoutReadResponseCount();
  const releasePatch = server.holdNextPatch();
  const releaseRead = server.holdWorkoutReads();
  try {
    await setNetworkOffline(page, false);
    await expect.poll(() => server.patches.some((patch) => patch.setId === 202)).toBe(true);
    expect(server.workoutReadCount()).toBe(readsBeforeReconnect);
    releasePatch();
    await expect.poll(() => server.readSet(202).is_completed).toBe(true);
    await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
    await expect.poll(() => server.workoutReadCount()).toBeGreaterThan(readsBeforeReconnect);
    expect(server.workoutReadSnapshots().at(-1)).toBe(true);
    releaseRead();
    await expect
      .poll(() => server.workoutReadResponseCount())
      .toBeGreaterThan(responsesBeforeReconnect);
    await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
      'data-workout-set-id',
      '203',
    );
  } finally {
    releasePatch();
    releaseRead();
  }

  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '203');
});

test('P1 completion waits for acceptance behind an in-flight autosave', async ({ page }, info) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 393, height: 844 });
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  const release = server.holdNextPatch();
  await first.getByLabel(/^Вес,/).fill('42.5');
  await expect.poll(() => server.patches.length).toBe(1);
  await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
  await first.getByRole('button', { name: /^2 —/ }).click();
  const completionButton = first.locator('[data-workout-field="done"]');
  const tapStartedAt = await page.evaluate(() => performance.now());
  await completionButton.dblclick();
  try {
    await expect(completionButton).toHaveText('Сохраняем…');
    await expect(completionButton).toBeDisabled();
    await expect(completionButton).toHaveAttribute('aria-busy', 'true');
    await expect(completionButton).toHaveAttribute('aria-label', /^Сохраняем…:/);
    await expect(completionButton).toHaveAttribute('aria-pressed', 'false');
    const feedbackAt = await page.evaluate(() => performance.now());
    expect(feedbackAt - tapStartedAt).toBeLessThan(1000);
    expect(server.patches).toHaveLength(1);
    expect(server.patches[0]?.body.is_completed).toBe(false);
    expect(server.patches[0]?.respondedAt).toBeUndefined();
    await page.screenshot({ path: info.outputPath('held-autosave.png') });
    await info.attach('held-autosave.json', {
      body: JSON.stringify(
        {
          tapToFeedbackMs: feedbackAt - tapStartedAt,
          patches: server.patches,
          server: server.readSet(201),
          currentSet: await page
            .locator('[aria-current="step"]')
            .getAttribute('data-workout-set-id'),
          timers: await page.getByRole('timer', { name: 'Отдых' }).count(),
          queue: await page.evaluate(() =>
            JSON.parse(localStorage.getItem('fit_active_workout_v1_user_7_workout_42') ?? '{}'),
          ),
        },
        null,
        2,
      ),
      contentType: 'application/json',
    });
    expect(server.readSet(201).is_completed).toBe(false);
    await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
  } finally {
    release();
  }
  await expect.poll(() => server.patches.length).toBe(3);
  expect(server.patches[0]?.body.is_completed).toBe(false);
  expect(server.patches[0]?.status).toBe(200);
  expect(server.patches[1]?.body.is_completed).toBe(true);
  expect(server.patches[1]?.body.expected_version).toBe(1);
  expect(server.patches[1]?.status).toBe(409);
  expect(server.patches[2]?.body.is_completed).toBe(true);
  expect(server.patches[2]?.body.expected_version).toBe(2);
  expect(server.patches[2]?.status).toBe(200);
  expect(server.patches[2]?.body.mutation_id).toBe(server.patches[1]?.body.mutation_id);
  expect(server.patches[1]?.receivedAt).toBeGreaterThanOrEqual(server.patches[0]?.respondedAt ?? 0);
  expect(server.patches[2]?.receivedAt).toBeGreaterThanOrEqual(server.patches[1]?.respondedAt ?? 0);
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '202');
  expect(server.readSet(201)).toMatchObject({ actual_weight: 42.5, actual_reps: 9, rir: '2' });
  await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
  await page.reload();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '202');
  await info.attach('completion-network.json', {
    body: JSON.stringify(server.patches, null, 2),
    contentType: 'application/json',
  });
});

for (const edit of ['weight', 'reps', 'rir', 'multiple'] as const) {
  test(`P1 immediate completion preserves ${edit} and survives a version conflict`, async ({
    page,
  }, info) => {
    await page.addInitScript(() => {
      const events: unknown[] = [];
      (window as unknown as { __p1DraftTrace: unknown[] }).__p1DraftTrace = events;
      for (const type of ['pointerdown', 'pointerup', 'click'])
        document.addEventListener(
          type,
          (event) => {
            const button = event.target instanceof Element ? event.target.closest('button') : null;
            events.push({
              type,
              target: event.target instanceof Element ? event.target.tagName : null,
              label: button?.getAttribute('aria-label'),
              pressed: button?.getAttribute('aria-pressed'),
              setId: button?.closest('[data-workout-set-id]')?.getAttribute('data-workout-set-id'),
              x: event instanceof MouseEvent ? event.clientX : null,
              y: event instanceof MouseEvent ? event.clientY : null,
              scrollY,
              time: performance.now(),
            });
          },
          true,
        );
      new MutationObserver((records) => {
        for (const record of records) {
          const target = record.target;
          if (
            target instanceof Element &&
            target.matches('button[aria-label^="2 —"]') &&
            target.closest('[data-workout-set-id="201"]')
          )
            events.push({
              type: 'selection',
              from: record.oldValue,
              to: target.getAttribute('aria-pressed'),
              time: performance.now(),
            });
        }
      }).observe(document, {
        subtree: true,
        attributes: true,
        attributeFilter: ['aria-pressed'],
        attributeOldValue: true,
      });
    });
    const server = await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const first = page.locator('[data-workout-set-id="201"]');
    if (edit === 'weight' || edit === 'multiple') await first.getByLabel(/^Вес,/).fill('42.5');
    if (edit === 'reps' || edit === 'multiple')
      await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
    if (edit === 'rir' || edit === 'multiple') {
      const choice = first.getByRole('button', { name: /^2 —/ });
      await choice.click();
      const selected = await choice.getAttribute('aria-pressed');
      if (selected !== 'true')
        await info.attach('selection-events.json', {
          body: JSON.stringify({
            patches: server.patches,
            events: await page.evaluate(
              () => (window as unknown as { __p1DraftTrace: unknown[] }).__p1DraftTrace,
            ),
          }),
          contentType: 'application/json',
        });
      expect(selected).toBe('true');
    }
    server.readSet(201).version += 1;
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
    await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
    await info.attach('completion-network.json', {
      body: JSON.stringify(
        {
          patches: server.patches,
          events: await page.evaluate(
            () => (window as unknown as { __p1DraftTrace: unknown[] }).__p1DraftTrace,
          ),
        },
        null,
        2,
      ),
      contentType: 'application/json',
    });
    expect(server.readSet(201)).toMatchObject({
      is_completed: true,
      actual_weight: edit === 'weight' || edit === 'multiple' ? 42.5 : null,
      actual_reps: edit === 'reps' || edit === 'multiple' ? 9 : null,
      rir: edit === 'rir' || edit === 'multiple' ? '2' : null,
    });
    expect(server.patches.some((patch) => patch.status === 409)).toBe(true);
    expect(
      server.patches.filter((patch) => patch.body.is_completed === true && patch.status === 200),
    ).toHaveLength(1);
  });
}

for (const theme of ['dark', 'light'] as const) {
  test(`P1 rejected completion does not start rest and retries without undoing the set ${theme}`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 360, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const first = page.locator('[data-workout-set-id="201"]');
    await first.getByLabel(/^Вес,/).fill('42.5');
    await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
    await first.getByRole('button', { name: /^2 —/ }).click();
    await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
    server.failSetPatch(true);
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.locator('.active-workout-sync')).toContainText('Требуется действие');
    await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
    await expect(first).toHaveAttribute('aria-current', 'step');
    expect(server.readSet(201).is_completed).toBe(false);
    await page.locator('.active-workout-sync').scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`completion-error-360-${theme}.png`) });
    server.failSetPatch(false);
    await first.getByRole('button', { name: /^Повторить сохранение:/ }).click();
    await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
    expect(server.readSet(201)).toMatchObject({
      is_completed: true,
      actual_weight: 42.5,
      actual_reps: 9,
      rir: '2',
    });
    expect(server.patches.slice(-2).every((patch) => patch.body.is_completed === true)).toBe(true);
    await info.attach('completion-network.json', {
      body: JSON.stringify(server.patches, null, 2),
      contentType: 'application/json',
    });
  });
}

for (const role of ['working', 'warmup', 'activation'] as const) {
  test(`P1 offline durable ${role} completion restores after reload and reconnect`, async ({
    page,
  }, info) => {
    const server = await mockActiveWorkout(page);
    server.setRole(201, role);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    // Keep the test shell available while restoring an offline queue on reload.
    await page.addInitScript(() =>
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false }),
    );
    await page.evaluate(() =>
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false }),
    );
    const first = page.locator('[data-workout-set-id="201"]');
    await first.getByLabel(/^Вес,/).fill('42.5');
    await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
    await first.getByRole('button', { name: /^2 —/ }).click();
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
      'data-workout-set-id',
      '202',
    );
    await expect(page.locator('.active-workout-sync')).toContainText('Сохранено на устройстве');
    await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(
      role === 'working' ? 1 : 0,
    );
    expect(server.patches).toHaveLength(0);
    await page.reload();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
      'data-workout-set-id',
      '202',
    );
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
      window.dispatchEvent(new Event('online'));
    });
    await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
    expect(server.readSet(201)).toMatchObject({
      is_completed: true,
      actual_weight: 42.5,
      actual_reps: 9,
      rir: '2',
    });
    await info.attach('completion-network.json', {
      body: JSON.stringify(server.patches, null, 2),
      contentType: 'application/json',
    });
  });
}

for (const width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`P1 completion evidence ${width}px ${theme}`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => {
        localStorage.setItem('app-theme', value);
        const rests: unknown[] = [];
        Object.assign(window, { __completionRests: rests });
        window.addEventListener('fit:rest', (event) =>
          rests.push({ time: Date.now(), detail: (event as CustomEvent).detail }),
        );
      }, theme);
      const server = await mockActiveWorkout(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('42.5');
      await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
      await first.getByRole('button', { name: /^2 —/ }).click();
      await page.screenshot({ path: info.outputPath(`completion-before-${width}-${theme}.png`) });
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
      await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
      await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
        'data-workout-set-id',
        '202',
      );
      expect(server.readSet(201)).toMatchObject({
        is_completed: true,
        actual_weight: 42.5,
        actual_reps: 9,
        rir: '2',
      });
      const rests = await page.evaluate(
        () => (window as unknown as { __completionRests: unknown[] }).__completionRests,
      );
      expect(rests).toHaveLength(1);
      const queue = await page.evaluate(() =>
        JSON.parse(localStorage.getItem('fit_active_workout_v1_user_7_workout_42') ?? '{}'),
      );
      expect(queue.queue).toEqual([]);
      await page.screenshot({ path: info.outputPath(`completion-after-${width}-${theme}.png`) });
      await info.attach('rest-dock-materials.json', {
        body: JSON.stringify(
          await page
            .locator('.active-workout-rest[data-glass], #appBottomNav')
            .evaluateAll((elements) =>
              elements.map((element) => {
                const style = getComputedStyle(element);
                return {
                  className: element.className,
                  variant: element.getAttribute('data-glass-variant'),
                  background: style.backgroundColor,
                  reflection: style.backgroundImage,
                  blur: style.backdropFilter,
                  webkitBlur: style.getPropertyValue('-webkit-backdrop-filter'),
                  border: style.borderColor,
                  shadow: style.boxShadow,
                  opacity: style.opacity,
                  materialOpacity: style.getPropertyValue('--glass-opacity'),
                  nestedBlur: [...element.querySelectorAll('[data-glass]')].map(
                    (child) => getComputedStyle(child).backdropFilter,
                  ),
                };
              }),
            ),
          null,
          2,
        ),
        contentType: 'application/json',
      });
      const completedPatch = server.patches.findIndex(
        (patch) => patch.status === 200 && patch.body.is_completed === true,
      );
      expect(completedPatch).toBeGreaterThanOrEqual(0);
      expect(
        server.patches
          .slice(completedPatch + 1)
          .filter((patch) => patch.setId === 201 && patch.body.is_completed === false),
      ).toEqual([]);
      await page.reload();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
        'data-workout-set-id',
        '202',
      );
      await page.screenshot({ path: info.outputPath(`completion-reload-${width}-${theme}.png`) });
      await info.attach('completion-network.json', {
        body: JSON.stringify(
          { patches: server.patches, rests, queue, server: server.readSet(201), currentSet: 202 },
          null,
          2,
        ),
        contentType: 'application/json',
      });
    });
  }
}

test('P1 sequential completions reach the final workout set without duplicate timers', async ({
  page,
}) => {
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  for (const id of [201, 202, 203]) {
    const row = page.locator(`[data-workout-set-id="${id}"]`);
    await expect(row).toHaveAttribute('aria-current', 'step');
    await row.getByLabel(/^Вес,/).fill('40');
    await row.getByRole('spinbutton', { name: /^Повторы,/ }).fill('8');
    await row.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
    expect(server.readSet(id).is_completed).toBe(true);
    await page.getByRole('button', { name: 'Пропустить', exact: true }).click();
    await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
    await expect(page.getByRole('status').filter({ hasText: 'Отдых пропущен' })).toBeVisible();
  }
  await expect(page.locator('[aria-current="step"]')).toHaveCount(0);
  expect(
    server.patches.filter((patch) => patch.body.is_completed === true && patch.status === 200),
  ).toHaveLength(3);
  await expect(
    page.getByRole('button', { name: 'Завершить тренировку', exact: true }),
  ).toBeVisible();
});

test('P1 completion preserves rest when navigation unmounts the pending workout', async ({
  page,
}) => {
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('42.5');
  await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
  await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
  const release = server.holdNextPatch();
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect
    .poll(() => server.patches.some((patch) => patch.body.is_completed === true))
    .toBe(true);
  await page.locator('#appBottomNav').getByRole('link', { name: 'План', exact: true }).click();
  release();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect
    .poll(() =>
      page.evaluate(() =>
        Number(localStorage.getItem('fit_active_workout_rest_v1_user_7_workout_42')),
      ),
    )
    .toBeGreaterThan(0);
  await page.locator('#appBottomNav').getByRole('link', { name: 'Сегодня', exact: true }).click();
  const resume = page.getByRole('button', { name: 'Продолжить тренировку' });
  if (await resume.isVisible()) await resume.click();
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '202');
});

test('P1 lock and resume completion starts the measured rest panel', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const current = page.locator('[data-workout-set-id="201"]');
  await current.getByLabel(/^Вес,/).fill('40');
  await current.getByLabel(/^Повторы,/).fill('8');
  await setDocumentVisibility(page, 'hidden');
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  await setDocumentVisibility(page, 'visible');
  await page.evaluate(() => window.dispatchEvent(new Event('pageshow')));

  await Promise.all([
    waitForCompletedSetPatch(page, 201),
    current.getByRole('button', { name: /^Завершить:/ }).click(),
  ]);
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.locator('.active-workout-rest__actual-value strong')).toHaveText('0:00');
  await expect(page.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
});

for (const theme of ['dark', 'light'] as const) {
  test(`P1 storage rejection keeps fields and current set without rest ${theme}`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 360, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const first = page.locator('[data-workout-set-id="201"]');
    await first.getByLabel(/^Вес,/).fill('42.5');
    await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
    await first.getByRole('button', { name: /^2 —/ }).click();
    await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
    await setNetworkOffline(page, true);
    await page.evaluate(() => {
      const write = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key.startsWith('fit_active_workout_v1_'))
          throw new DOMException('Quota', 'QuotaExceededError');
        return write.call(this, key, value);
      };
    });
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.locator('.active-workout-sync')).toContainText('Требуется действие');
    await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
    await expect(first).toHaveAttribute('aria-current', 'step');
    await expect(first.getByLabel(/^Вес,/)).toHaveValue('42.5');
    await expect(first.getByRole('spinbutton', { name: /^Повторы,/ })).toHaveValue('9');
    expect(server.readSet(201).is_completed).toBe(false);
    await page.locator('.active-workout-sync').scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`completion-storage-error-360-${theme}.png`) });
  });
}

test('P1 late workout read cannot revert a confirmed completion', async ({ page }, info) => {
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('42.5');
  await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
  await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
  const stale = await page.evaluate(async () => (await fetch('/api/v1/workouts/today')).json());
  let release!: () => void;
  let requested!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  const started = new Promise<void>((resolve) => {
    requested = resolve;
  });
  await page.route(
    '**/api/v1/workouts/today',
    async (route) => {
      requested();
      await barrier;
      await route.fulfill({ json: stale });
    },
    { times: 1 },
  );
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await started;
  const staleResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/workouts/today'),
  );
  try {
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
      'data-workout-set-id',
      '202',
    );
  } finally {
    release();
  }
  await (await staleResponse).finished();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  await expect(page.locator('[aria-current="step"]')).toHaveAttribute('data-workout-set-id', '202');
  expect(server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  await info.attach('late-read.json', {
    body: JSON.stringify({ stale, patches: server.patches, server: server.readSet(201) }),
    contentType: 'application/json',
  });
});

test('P1 combined API and storage failure never claims durable completion', async ({ page }) => {
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('42.5');
  await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
  await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
  server.failSetPatch(true);
  await page.evaluate(() => {
    const write = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key.startsWith('fit_active_workout_v1_'))
        throw new DOMException('Quota', 'QuotaExceededError');
      return write.call(this, key, value);
    };
  });
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect(page.locator('.active-workout-sync')).toContainText('Требуется действие');
  await expect(first.locator('.active-workout-set__complete-label')).toHaveText(/Не сохранено/);
  await expect(page.locator('.active-workout-sync')).toContainText('Не закрывайте приложение');
  await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
  await expect(first.getByLabel(/^Вес,/)).toHaveValue('42.5');
  await expect(first.getByRole('spinbutton', { name: /^Повторы,/ })).toHaveValue('9');
  expect(server.readSet(201).is_completed).toBe(false);
});

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
      mediaHeight: mediaRect.height,
      techniqueLeft: techniqueRect.left,
      techniqueRight: techniqueRect.right,
      techniqueWidth: techniqueRect.width,
      imageHeight: imageRect.height,
      mediaBorderTop: getComputedStyle(media).borderTopWidth,
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
  expect(
    Math.abs((geometry?.mediaWidth ?? 0) - (geometry?.mediaHeight ?? 0)),
    `${label}: main media surface must remain square`,
  ).toBeLessThanOrEqual(1);
  expect(
    geometry?.imageHeight ?? 0,
    `${label}: rendered image must fill the square media wrapper`,
  ).toBeGreaterThanOrEqual((geometry?.mediaHeight ?? 0) - tolerance);
  expect(geometry?.mediaBorderTop, `${label}: main media has no visible frame`).toBe('0px');
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

async function openIssue996Replacement(
  page: Page,
  options: {
    width?: number;
    theme?: 'dark' | 'light';
    candidateMedia?: 'catalog' | 'broken';
  } = {},
) {
  const { width = 393, theme = 'dark', candidateMedia = 'catalog' } = options;
  await page.setViewportSize({ width, height: 844 });
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem('app-theme', selectedTheme);
  }, theme);
  await page.addInitScript(() => {
    const viewport = new EventTarget() as EventTarget & {
      height: number;
      width: number;
      offsetTop: number;
      setHeight: (height: number) => void;
    };
    let height = 844;
    Object.defineProperties(viewport, {
      height: { configurable: true, get: () => height },
      width: { configurable: true, get: () => innerWidth },
      offsetTop: { configurable: true, get: () => 0 },
      setHeight: {
        configurable: true,
        value: (nextHeight: number) => {
          height = nextHeight;
        },
      },
    });
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: viewport,
    });
  });
  await mockActiveWorkout(page);
  if (candidateMedia === 'catalog') {
    await page.route(
      new RegExp(`${replacementMediaThumbnailUrl.replaceAll('.', '\\.')}(?:\\?.*)?$`),
      (route) =>
        route.fulfill({
          path: '../backend/assets/exercise-guides/gymvisual/dumbbell-bench-press-0289-SpYC0Kp.jpg',
          contentType: 'image/jpeg',
        }),
    );
  } else {
    await page.route(
      new RegExp(`${replacementMediaThumbnailUrl.replaceAll('.', '\\.')}(?:\\?.*)?$`),
      (route) => route.abort(),
    );
  }
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first()
    .getByRole('button', { name: 'Заменить только в этой тренировке' })
    .click();
  const dialog = page.getByRole('dialog', {
    name: 'Заменить только в этой тренировке',
    exact: true,
  });
  await dialog.getByRole('checkbox', { name: 'Гантели', exact: true }).check();
  await dialog.getByRole('checkbox', { name: 'Скамья', exact: true }).check();
  await expect(dialog.getByRole('radio', { name: /Жим гантелей лёжа/ })).toBeVisible();
  return dialog;
}

async function readIssue996FooterGeometry(dialog: Locator) {
  return dialog.evaluate((element) => {
    const footer = element.querySelector<HTMLElement>('.workout-adaptation-dialog__footer')!;
    const choiceRow = footer.querySelector<HTMLElement>('.workout-adaptation-dialog__choice-row')!;
    const getRect = (node: Element | null) => {
      if (!(node instanceof HTMLElement)) return null;
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
        clientWidth: node.clientWidth,
        scrollWidth: node.scrollWidth,
        minHeight: Number.parseFloat(style.minHeight) || 0,
        whiteSpace: style.whiteSpace,
      };
    };
    const footerChildren = [...footer.children].map((child) => ({
      tag: child.tagName,
      buttons:
        child instanceof HTMLButtonElement
          ? [child.textContent?.trim()]
          : [...child.querySelectorAll('button')].map((button) => button.textContent?.trim()),
    }));
    return {
      footer: getRect(footer)!,
      choiceRow: getRect(choiceRow)!,
      choiceButtons: [...choiceRow.querySelectorAll('button')].map(getRect),
      applyButton: getRect(
        [...footer.children].find(
          (child) => child instanceof HTMLButtonElement && child.classList.contains('ui-button'),
        ) ?? null,
      ),
      footerChildren,
      documentWidth: {
        client: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      },
      viewportHeight: window.innerHeight,
      footerPaddingBottom: Number.parseFloat(getComputedStyle(footer).paddingBottom) || 0,
    };
  });
}

async function assertIssue996FooterGeometry(dialog: Locator, afterPreview = false) {
  const geometry = await readIssue996FooterGeometry(dialog);
  const [previewButton, cancelButton] = geometry.choiceButtons;
  expect(geometry.choiceButtons).toHaveLength(2);
  expect(previewButton).not.toBeNull();
  expect(cancelButton).not.toBeNull();
  expect(Math.abs(previewButton!.top - cancelButton!.top)).toBeLessThanOrEqual(1);
  expect(Math.abs(previewButton!.bottom - cancelButton!.bottom)).toBeLessThanOrEqual(1);
  expect(previewButton!.left).toBeLessThan(cancelButton!.left);
  expect(Math.abs(previewButton!.width - cancelButton!.width)).toBeLessThanOrEqual(1);
  expect(previewButton!.height).toBeGreaterThanOrEqual(44);
  expect(cancelButton!.height).toBeGreaterThanOrEqual(44);
  expect(previewButton!.whiteSpace).toBe('nowrap');
  expect(cancelButton!.whiteSpace).toBe('nowrap');
  expect(previewButton!.scrollWidth).toBeLessThanOrEqual(previewButton!.clientWidth + 1);
  expect(cancelButton!.scrollWidth).toBeLessThanOrEqual(cancelButton!.clientWidth + 1);
  expect(previewButton!.right).toBeLessThanOrEqual(cancelButton!.left + 1);
  expect(geometry.choiceRow.scrollWidth).toBeLessThanOrEqual(geometry.choiceRow.clientWidth + 1);
  expect(geometry.footer.scrollWidth).toBeLessThanOrEqual(geometry.footer.clientWidth + 1);
  expect(geometry.documentWidth.scroll).toBeLessThanOrEqual(geometry.documentWidth.client + 1);
  expect(geometry.footerPaddingBottom).toBeGreaterThan(0);
  expect(geometry.footer.bottom).toBeLessThanOrEqual(geometry.viewportHeight + 1);
  expect(geometry.footerChildren[0]).toEqual({
    tag: 'DIV',
    buttons: [afterPreview ? 'Обновить изменения' : 'Показать изменения', 'Отмена'],
  });
  if (afterPreview) {
    expect(geometry.applyButton).not.toBeNull();
    expect(geometry.applyButton!.height).toBeGreaterThanOrEqual(44);
    expect(geometry.applyButton!.whiteSpace).toBe('nowrap');
    expect(geometry.applyButton!.scrollWidth).toBeLessThanOrEqual(
      geometry.applyButton!.clientWidth + 1,
    );
    expect(geometry.applyButton!.top).toBeGreaterThanOrEqual(geometry.choiceRow.bottom - 1);
    expect(geometry.footerChildren[1]).toEqual({
      tag: 'BUTTON',
      buttons: ['Применить только сегодня'],
    });
  } else {
    expect(geometry.applyButton).toBeNull();
    expect(geometry.footerChildren).toHaveLength(1);
  }
}

test('#1202 searches verified replacements without applying one', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await mockActiveWorkout(page);
  await page.route('**/workouts/42/exercises/101/alternatives?*', (route) =>
    route.fulfill({
      json: [
        {
          exercise_id: 13,
          title: 'Жим гантелей лёжа',
          aliases: ['dumbbell bench press'],
          equipment_ids: ['dumbbell', 'bench'],
        },
        { exercise_id: 14, title: 'Жим в тренажёре', aliases: [], equipment_ids: ['machine'] },
        { exercise_id: 15, title: 'Отжимания', aliases: [], equipment_ids: ['bodyweight'] },
        { exercise_id: 16, title: 'Жим Смита', aliases: [], equipment_ids: ['machine'] },
      ],
    }),
  );
  const writes: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().includes('/adaptations/'))
      writes.push(request.url());
  });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page
    .getByRole('button', { name: 'Заменить только в этой тренировке', exact: true })
    .first()
    .click();
  const dialog = page.getByRole('dialog', { name: 'Заменить только в этой тренировке' });
  await dialog.getByRole('checkbox', { name: 'Гантели' }).check();
  await dialog.getByRole('checkbox', { name: 'Скамья' }).check();
  await dialog.getByRole('button', { name: 'Все подходящие' }).click();
  const search = dialog.getByRole('searchbox', { name: 'Поиск по полному ответу сервиса' });
  await search.focus();
  await search.fill('dumbell bench press');
  await expect(dialog.getByRole('radio', { name: /Жим гантелей лёжа/ })).toBeVisible();
  await expect(dialog.getByRole('radio', { name: /Жим Смита/ })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
    true,
  );
  expect(writes).toEqual([]);
});

test('V9-01 replaces only an untouched active exercise and survives refresh', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
  await expect(summary.getByRole('button', { name: 'Что делать сейчас?' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );

  const exercise = page
    .locator('.active-workout-exercise')
    .filter({ hasText: 'Жим штанги лёжа' })
    .first();
  const replacement = exercise.getByRole('button', {
    name: 'Заменить только в этой тренировке',
  });
  await expect(replacement).toBeVisible();
  for (const mobileWidth of [320, 360, 393, 430]) {
    await page.setViewportSize({ width: mobileWidth, height: 844 });
    const { triggerWidth, actionsWidth, pageWidth } = await replacement.evaluate((button) => {
      const trigger = button.getBoundingClientRect();
      const actions = button.closest('.active-workout-exercise__head-actions');
      return {
        triggerWidth: trigger.width,
        actionsWidth: actions?.getBoundingClientRect().width ?? 0,
        pageWidth: document.documentElement.scrollWidth,
      };
    });
    expect(actionsWidth).toBeGreaterThan(0);
    expect(triggerWidth, `Replacement button width at ${mobileWidth}px`).toBeGreaterThanOrEqual(
      actionsWidth - 1,
    );
    expect(pageWidth, `Horizontal overflow at ${mobileWidth}px`).toBeLessThanOrEqual(
      mobileWidth + 1,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await replacement.click();
  await expect(
    page.getByRole('heading', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
  await page.getByRole('checkbox', { name: 'Гантели' }).check();
  await page.getByRole('checkbox', { name: 'Скамья' }).check();
  await page.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();
  await page.getByRole('button', { name: 'Показать изменения' }).click();
  await expect(page.getByRole('heading', { name: 'Что изменится' })).toBeVisible();
  await page.getByRole('button', { name: 'Применить только сегодня' }).click();
  await expect(page.getByText('Изменения применены только к сегодняшней тренировке')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();
  const replacedSummary = page.getByRole('region', { name: 'Что делать сейчас?' });
  await expect(replacedSummary.getByRole('button', { name: 'Что делать сейчас?' })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await expect(replacedSummary.locator('.active-session-summary__details')).toBeHidden();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('button', { name: 'Продолжить тренировку' })).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await expect(page.getByRole('heading', { name: 'Жим гантелей лёжа' })).toBeVisible();
});

for (const width of [360, 393, 430]) {
  for (const theme of ['light', 'dark'] as const) {
    for (const platform of ['browser', 'telegram'] as const) {
      test(`#860 replacement feedback stays visible at ${width}px ${theme} ${platform}`, async ({
        page,
      }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        if (platform === 'telegram') await installMockedTelegram(page);
        await page.addInitScript((selectedTheme) => {
          localStorage.setItem('app-theme', selectedTheme);
          if (window.Telegram?.WebApp) window.Telegram.WebApp.colorScheme = selectedTheme;
        }, theme);
        await mockActiveWorkout(page);
        await page.route('**/workouts/42/exercises/101/alternatives?*', async (route) => {
          if (route.request().url().includes('dumbbell')) return route.fallback();
          await route.fulfill({ json: [] });
        });
        let failPreview = true;
        await page.route('**/workouts/42/adaptations/preview', async (route) => {
          if (!failPreview) return route.fallback();
          failPreview = false;
          await route.fulfill({ status: 503, json: { detail: 'Временная ошибка сервера' } });
        });
        let failApply = true;
        await page.route('**/workouts/42/adaptations/apply', async (route) => {
          if (!failApply) return route.fallback();
          failApply = false;
          await route.fulfill({ status: 409, json: { detail: 'Тренировка изменилась' } });
        });
        const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
        page.on('request', (request) => {
          if (request.method() === 'POST' && /\/(adaptations|programs)\//.test(request.url())) {
            writes.push({ path: new URL(request.url()).pathname, body: request.postDataJSON() });
          }
        });
        await page.goto(platform === 'telegram' ? '/app?tgWebAppPlatform=ios' : '/app');
        if (platform === 'browser') await page.getByRole('button', { name: 'Клиент' }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const replacementButton = page
          .getByRole('button', { name: 'Заменить только в этой тренировке', exact: true })
          .first();
        const replacementGeometry = await replacementButton.evaluate((button) => {
          const row = button.closest('.active-workout-exercise__head-actions');
          const buttonRect = button.getBoundingClientRect();
          const rowRect = row?.getBoundingClientRect();
          return {
            buttonWidth: buttonRect.width,
            rowWidth: rowRect?.width ?? 0,
            pageWidth: document.documentElement.scrollWidth,
            viewportWidth: innerWidth,
          };
        });
        expect(replacementGeometry.rowWidth).toBeGreaterThan(0);
        expect(replacementGeometry.buttonWidth).toBeGreaterThanOrEqual(
          replacementGeometry.rowWidth - 1,
        );
        expect(replacementGeometry.pageWidth).toBeLessThanOrEqual(
          replacementGeometry.viewportWidth + 1,
        );
        await replacementButton.click();
        const dialog = page.getByRole('dialog', {
          name: 'Заменить только в этой тренировке',
          exact: true,
        });
        await dialog.getByRole('checkbox', { name: 'Тросовый блок', exact: true }).check();
        await dialog.getByRole('checkbox', { name: 'Тренажёры', exact: true }).check();
        await expect(
          dialog.getByText(/Для выбранного оборудования нет проверенной замены/),
        ).toBeVisible();
        await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
        const error = dialog.getByRole('alert');
        await expect(error).toContainText('Для выбранного оборудования нет проверенной замены.');
        await expect(error).toBeFocused();
        await expect(error).toBeInViewport();
        expect(writes).toHaveLength(0);
        await page.screenshot({ path: testInfo.outputPath('no-compatible-visible.png') });

        await dialog.getByRole('checkbox', { name: 'Гантели', exact: true }).check();
        await dialog.getByRole('checkbox', { name: 'Скамья', exact: true }).check();
        await dialog.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();
        await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
        await expect(error).toContainText('Сервис временно недоступен. Попробуйте ещё раз.');
        await expect(error).toBeFocused();
        await expect(error).toBeInViewport();
        await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
        const previewHeading = dialog.getByRole('heading', { name: 'Что изменится', exact: true });
        await expect(previewHeading).toBeFocused();
        await expect(previewHeading).toBeInViewport();
        expect(writes.every((request) => request.path.endsWith('/adaptations/preview'))).toBe(true);
        expect(writes.at(-1)?.body).toEqual({
          reason: 'replace_exercise',
          target_workout_exercise_id: 101,
          replacement_exercise_id: 13,
          available_equipment_ids: ['cable', 'machine', 'dumbbell', 'bench'],
        });
        await page.screenshot({ path: testInfo.outputPath('preview-visible.png') });
        await dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }).click();
        await expect(error).toContainText('Состав тренировки изменился');
        await expect(error).toBeInViewport();
        await expect(
          dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }),
        ).toHaveCount(0);
        await dialog.getByRole('button', { name: 'Обновить изменения', exact: true }).click();
        await expect(previewHeading).toBeFocused();
        await dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }).click();
        await expect(
          page
            .locator('.active-workout-exercise')
            .filter({ hasText: 'Жим гантелей лёжа' })
            .getByRole('heading', { name: 'Жим гантелей лёжа', exact: true }),
        ).toBeVisible();
        expect(
          writes.filter((request) => request.path.endsWith('/adaptations/apply')),
        ).toHaveLength(2);
        expect(writes.some((request) => request.path.includes('/programs/'))).toBe(false);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
          ),
        ).toBe(true);
        await testInfo.attach('synthetic-network.json', {
          body: JSON.stringify(writes, null, 2),
          contentType: 'application/json',
        });
      });
    }
  }
}

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
  await page.getByRole('button', { name: 'Применить только сегодня' }).click();
  await expect(
    page.locator('.active-workout-exercise').getByRole('heading', { name: 'Жим гантелей лёжа' }),
  ).toBeVisible();
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
  await page.getByRole('button', { name: 'Применить только сегодня' }).click();
  await expect(
    page
      .locator('.active-workout-exercise')
      .filter({ hasText: 'Жим гантелей лёжа' })
      .first()
      .getByRole('heading', { name: 'Жим гантелей лёжа', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
});

for (const [theme, width] of [
  ['dark', 320],
  ['light', 320],
  ['dark', 360],
  ['light', 360],
  ['dark', 393],
  ['light', 393],
  ['dark', 430],
  ['light', 430],
  ['dark', 1440],
  ['light', 1440],
] as const) {
  test(`#996 real AFTER ${theme} ${width}px`, async ({ page }) => {
    await mkdir(ISSUE_996_AFTER_DIR, { recursive: true });
    const dialog = await openIssue996Replacement(page, { width, theme });
    const originalImage = dialog.locator('.adaptation-original-card img');
    const alternativeCard = dialog
      .locator('.adaptation-alternative-card')
      .filter({ hasText: 'Жим гантелей лёжа' });
    const alternativeImage = alternativeCard.locator('img');
    await expect(originalImage).toBeVisible();
    await expect(alternativeImage).toBeVisible();
    await expect(alternativeCard.locator('input[type="radio"]')).toHaveValue('13');
    await expect
      .poll(() =>
        originalImage.evaluate((image) => {
          const element = image as HTMLImageElement;
          return [element.complete, element.naturalWidth];
        }),
      )
      .toEqual([true, expect.any(Number)]);
    await expect
      .poll(() => originalImage.evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0);
    await expect
      .poll(() =>
        alternativeImage.evaluate((image) => {
          const element = image as HTMLImageElement;
          return [element.complete, element.naturalWidth];
        }),
      )
      .toEqual([true, expect.any(Number)]);
    await expect
      .poll(() => alternativeImage.evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0);
    await expect(
      dialog
        .locator('.adaptation-alternative-card')
        .filter({ hasText: 'Жим в тренажёре от груди' })
        .getByText('Нет фото', { exact: true }),
    ).toBeVisible();
    await assertIssue996FooterGeometry(dialog);
    if (width === 1440) {
      await dialog.getByRole('button', { name: 'Все подходящие' }).click();
      await expect(dialog.getByRole('searchbox')).toBeVisible();
    } else {
      await dialog
        .locator('.workout-adaptation-dialog__body')
        .evaluate((body) => body.scrollTo({ top: 0 }));
    }

    await page.screenshot({
      path: resolve(ISSUE_996_AFTER_DIR, `issue-996-after-${theme}-${width}.png`),
      fullPage: false,
    });
  });
}

for (const width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#996 footer geometry ${theme} ${width}px`, async ({ page }) => {
      const dialog = await openIssue996Replacement(page, { width, theme });
      await assertIssue996FooterGeometry(dialog);
      await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
      await expect(
        dialog.getByRole('heading', { name: 'Что изменится', exact: true }),
      ).toBeVisible();
      await assertIssue996FooterGeometry(dialog, true);
      await expect(
        page
          .locator('.active-workout-exercise')
          .getByRole('heading', { name: 'Жим штанги лёжа', exact: true }),
      ).toBeVisible();
    });
  }
}

test('#996 preserves the selected list, search focus and preview/cancel boundary', async ({
  page,
}) => {
  const dialog = await openIssue996Replacement(page, { width: 393, theme: 'dark' });
  await dialog.getByRole('button', { name: 'Все подходящие', exact: true }).click();
  const search = dialog.getByRole('searchbox', { name: 'Поиск по полному ответу сервиса' });
  await search.fill('Смита');
  await expect(search).toHaveValue('Смита');
  await expect(search).toBeFocused();
  await expect(dialog.getByRole('radio', { name: /Жим в тренажёре Смита/ })).toBeVisible();
  await expect(dialog.getByRole('radio', { name: /Жим гантелей лёжа/ })).toHaveCount(0);
  await search.fill('');
  await dialog.getByRole('button', { name: 'Тренажёры', exact: true }).click();
  await expect(dialog.getByRole('radio', { name: /Жим в тренажёре от груди/ })).toBeVisible();
  await expect(dialog.getByRole('radio', { name: /Жим гантелей лёжа/ })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Тренажёры', exact: true }).click();
  await dialog.getByRole('radio', { name: /Жим гантелей лёжа/ }).check();

  await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
  await expect(dialog.getByRole('heading', { name: 'Что изменится', exact: true })).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator('.active-workout-exercise')
      .getByRole('heading', { name: 'Жим штанги лёжа', exact: true }),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'Отмена', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Заменить только в этой тренировке' }),
  ).toBeVisible();
});

test('#996 keeps a failed catalog image selectable with the missing-media fallback', async ({
  page,
}) => {
  const dialog = await openIssue996Replacement(page, {
    width: 393,
    theme: 'light',
    candidateMedia: 'broken',
  });
  const card = dialog
    .locator('.adaptation-alternative-card')
    .filter({ hasText: 'Жим гантелей лёжа' });
  await expect(card.getByText('Нет фото', { exact: true })).toBeVisible();
  await expect(card.getByRole('radio')).toHaveValue('13');
  await expect(card.getByRole('radio')).toBeChecked();
  await assertIssue996FooterGeometry(dialog);
});

test('#996 keeps the open sheet offline without preview or local mutation', async ({ page }) => {
  const dialog = await openIssue996Replacement(page, { width: 393, theme: 'dark' });
  await page.context().setOffline(true);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    window.dispatchEvent(new Event('offline'));
  });
  await expect(dialog.getByText(/Замена требует подключения/)).toBeVisible();
  await expect(
    dialog.getByRole('button', { name: 'Показать изменения', exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }),
  ).toHaveCount(0);
  await page.context().setOffline(false);
});

for (const [theme, state] of [
  ['dark', 'preview'],
  ['light', 'preview'],
  ['dark', 'error'],
  ['light', 'error'],
  ['dark', 'offline'],
  ['light', 'offline'],
  ['dark', 'conflict'],
  ['light', 'conflict'],
  ['dark', 'keyboard-modeled'],
  ['light', 'keyboard-modeled'],
] as const) {
  test(`#996 real AFTER ${state} ${theme} 393px`, async ({ page }) => {
    await mkdir(ISSUE_996_AFTER_DIR, { recursive: true });
    const dialog = await openIssue996Replacement(page, { width: 393, theme });
    if (state === 'error') {
      await page.route('**/workouts/42/adaptations/preview', (route) =>
        route.fulfill({ status: 503, json: { detail: 'Временная ошибка сервера' } }),
      );
      await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
      await expect(dialog.getByRole('alert')).toContainText(
        'Сервис временно недоступен. Попробуйте ещё раз.',
      );
    } else if (state === 'offline') {
      await page.context().setOffline(true);
      await page.evaluate(() => {
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
        window.dispatchEvent(new Event('offline'));
      });
      await expect(dialog.getByText(/Замена требует подключения/)).toBeVisible();
    } else if (state === 'conflict') {
      await page.route('**/workouts/42/adaptations/apply', (route) =>
        route.fulfill({ status: 409, json: { detail: 'Тренировка изменилась' } }),
      );
      await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
      await expect(
        dialog.getByRole('heading', { name: 'Что изменится', exact: true }),
      ).toBeVisible();
      await dialog.getByRole('button', { name: 'Применить только сегодня', exact: true }).click();
      await expect(dialog.getByRole('alert')).toContainText('Состав тренировки изменился');
    } else if (state === 'keyboard-modeled') {
      await dialog.getByRole('button', { name: 'Все подходящие', exact: true }).click();
      const search = dialog.getByRole('searchbox', { name: 'Поиск по полному ответу сервиса' });
      await search.fill('Смита');
      await expect(search).toBeFocused();
      await page.evaluate(() => {
        (
          window.visualViewport as VisualViewport & { setHeight: (height: number) => void }
        ).setHeight(420);
        window.visualViewport!.dispatchEvent(new Event('resize'));
      });
      await expect(search).toBeFocused();
      await expect(search).toHaveValue('Смита');
    } else {
      await dialog.getByRole('button', { name: 'Показать изменения', exact: true }).click();
      await expect(
        dialog.getByRole('heading', { name: 'Что изменится', exact: true }),
      ).toBeVisible();
      await assertIssue996FooterGeometry(dialog, true);
    }
    await page.screenshot({
      path: resolve(ISSUE_996_AFTER_DIR, `issue-996-after-${state}-${theme}-393.png`),
      fullPage: false,
    });
    await page.context().setOffline(false);
  });
}

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

  const summary = page.getByRole('region', { name: 'Что делать сейчас?' });
  await summary.getByRole('button', { name: 'Что делать сейчас?' }).click();
  await summary.getByRole('button', { name: 'Боль или травма во время тренировки' }).click();
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
    currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('80'),
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
    currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('80'),
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
    currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('80'),
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
  const resetInventory = calculator.getByRole('button', { name: 'Сбросить' });
  // Stop the ongoing smooth scroll before targeting a control moved by the result reflow.
  await resetInventory.evaluate((element) =>
    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }),
  );
  await resetInventory.click();
  await expect(calculator.getByRole('status')).toContainText('Точный результат');
  await expect(currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('');
  await expect(currentSet.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
  ).toBe(true);
  await page.context().setOffline(false);
});

for (const theme of ['light', 'dark'] as const) {
  test(`V12 #1273 keeps plate reset separate from instructions at 320-430px in ${theme}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

    const currentSet = page.locator('[data-workout-set-id="201"]');
    await clickDetailsSummary(currentSet.getByText('Разминка и блины', { exact: true }));
    const inventory = currentSet.locator('.active-workout-plate-inventory');
    const hint = inventory.locator(':scope > p');
    const reset = inventory.getByRole('button', { name: 'Сбросить' });
    const count = inventory.getByLabel('Количество блинов 25 кг на сторону');
    const originalCount = await count.inputValue();
    await count.fill(originalCount === '0' ? '1' : '0');
    await expect(count).not.toHaveValue(originalCount);

    // Enlarged text must still take up its own row rather than overlap the control.
    await hint.evaluate((element) => {
      element.style.fontSize = '1.25rem';
    });
    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      await expect(hint).toBeVisible();
      await expect(reset).toBeVisible();
      const rects = await inventory.evaluate((fieldset) => {
        const paragraph = fieldset.querySelector(':scope > p');
        const button = fieldset.querySelector('.active-workout-plate-inventory__reset button');
        if (!paragraph || !button) throw new Error('Plate inventory elements missing');
        const helpRect = paragraph.getBoundingClientRect();
        const resetRect = button.getBoundingClientRect();
        return {
          helpBottom: helpRect.bottom,
          resetTop: resetRect.top,
          resetRight: resetRect.right,
          viewportRight: window.innerWidth,
          fieldsetRight: fieldset.getBoundingClientRect().right,
        };
      });
      expect(rects.resetTop).toBeGreaterThanOrEqual(rects.helpBottom);
      expect(rects.resetRight).toBeLessThanOrEqual(rects.fieldsetRight + 1);
      expect(rects.resetRight).toBeLessThanOrEqual(rects.viewportRight + 1);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      ).toBe(true);
      if (width === 393) {
        await test.info().attach(`1273-after-${theme}-393px`, {
          body: await page.screenshot(),
          contentType: 'image/png',
        });
      }
    }

    await reset.click();
    await expect(count).toHaveValue(originalCount);
    await expect(currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('');
    await expect(currentSet.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('');
    await expect(currentSet).toHaveAttribute('aria-current', 'step');
  });
}

for (const theme of ['light', 'dark'] as const) {
  test(`V12 #1272 orders inputs and persists RIR in ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

    const first = page.locator('[data-workout-set-id="201"]');
    const weight = first.getByLabel('Вес, Жим штанги лёжа, подход 1');
    const reps = first.getByLabel('Повторы, Жим штанги лёжа, подход 1');
    const rir = first.locator('.active-workout-set__rir-row .active-workout-rir');
    const done = first.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' });
    await expect(rir).toBeVisible();
    expect(server.readSet(201).rir).toBeNull();

    const ordering = await first.evaluate((row) => {
      const fields = [
        row.querySelector('[data-workout-field="weight"]'),
        row.querySelector('[data-workout-field="reps"]'),
        row.querySelector('.active-workout-set__rir-row button'),
        row.querySelector('[data-workout-field="done"]'),
      ];
      if (fields.some((field) => !field)) throw new Error('Missing workout controls');
      const following = Node.DOCUMENT_POSITION_FOLLOWING;
      return fields.slice(0, -1).every((field, index) => {
        const next = fields[index + 1]!;
        return Boolean(field!.compareDocumentPosition(next) & following);
      });
    });
    expect(ordering).toBe(true);

    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      await expect(weight).toBeVisible();
      await expect(reps).toBeVisible();
      await expect(rir).toBeVisible();
      await expect(done).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true);
    }

    await weight.fill('42.5');
    await reps.fill('8');
    await reps.press('Enter');
    const choices = rir.locator('button');
    await expect(choices).toHaveCount(5);
    await expect(choices.first()).toBeFocused();
    await expect(choices.nth(4)).toHaveText('4+');
    await choices.nth(4).focus();
    await page.keyboard.press('Tab');
    await expect(done).toBeFocused();

    await expect
      .poll(() => server.readSet(201))
      .toMatchObject({ actual_weight: 42.5, actual_reps: 8 });
    await choices.nth(4).scrollIntoViewIfNeeded();
    const topBeforeRir = await first.evaluate(
      (element) => element.getBoundingClientRect().top + scrollY,
    );
    const scrollBeforeRir = await stableScrollY(page);
    await choices.nth(4).click();
    await expect(choices.nth(4)).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => server.readSet(201).rir).toBe('4+');
    expect(await first.evaluate((element) => element.getBoundingClientRect().top + scrollY)).toBe(
      topBeforeRir,
    );
    await expectScrollYStable(page, scrollBeforeRir);
    await choices.nth(4).click();
    await expect.poll(() => server.readSet(201).rir).toBeNull();
    await choices.first().click();
    await expect.poll(() => server.readSet(201).rir).toBe('0');

    await done.click();
    await expect.poll(() => server.readSet(201).is_completed).toBe(true);
    expect(server.readSet(201)).toMatchObject({ actual_weight: 42.5, actual_reps: 8, rir: '0' });
    const nextSet = page.locator('[data-workout-set-id="202"]');
    await expect(nextSet).toHaveAttribute('aria-current', 'step');
  });
}

for (const value of [null, '0', '1', '2', '3', '4+'] as const) {
  test(`#1272 completes a set with RIR ${value ?? 'null'}`, async ({ page }) => {
    const server = await mockActiveWorkout(page);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент', exact: true }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

    const set = page.locator('[data-workout-set-id="201"]');
    await set.getByLabel(/^Вес,/).fill('42.5');
    await set.getByLabel(/^Повторы,/).fill('8');
    if (value !== null) {
      await set
        .locator('.active-workout-set__rir-row')
        .getByRole('button', { name: new RegExp(`^${value.replace('+', '\\+')} —`) })
        .click();
    }
    await set.getByRole('button', { name: /^Завершить:/ }).click();
    await expect.poll(() => server.readSet(201).is_completed).toBe(true);
    expect(server.readSet(201)).toMatchObject({
      actual_weight: 42.5,
      actual_reps: 8,
      rir: value,
    });
  });
}

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
  await page
    .getByRole('region', { name: 'Что делать сейчас?' })
    .getByRole('button', { name: 'Что делать сейчас?' })
    .click();

  const exercise = page.locator('.active-workout-exercise').filter({ hasText: 'Жим штанги лёжа' });
  const setupMemory = exercise.getByTestId('exercise-setup-memory-11');
  await expect(setupMemory.getByRole('button', { name: 'Добавить настройку' })).toBeVisible();
  await setupMemory.getByRole('button', { name: 'Добавить настройку' }).click();
  await setupMemory.getByRole('textbox', { name: 'Что важно настроить' }).fill('Сиденье 4');
  await setupMemory.getByRole('button', { name: 'Сохранить настройку' }).click();
  await expect(setupMemory.getByText('Сиденье 4')).toBeVisible();
  await expect(setupMemory.getByRole('button', { name: 'Изменить настройку' })).toBeVisible();

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  await page
    .getByRole('region', { name: 'Что делать сейчас?' })
    .getByRole('button', { name: 'Что делать сейчас?' })
    .click();
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
  await page
    .getByRole('region', { name: 'Что делать сейчас?' })
    .getByRole('button', { name: 'Что делать сейчас?' })
    .click();

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
  await page
    .getByRole('region', { name: 'Что делать сейчас?' })
    .getByRole('button', { name: 'Что делать сейчас?' })
    .click();

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
  const server = await mockActiveWorkout(page);
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
  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  const firstDone = firstSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 1',
  });
  await firstDone.scrollIntoViewIfNeeded();
  await Promise.all([waitForCompletedSetPatch(page, 201), firstDone.dblclick()]);

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await expect(secondSet).toHaveAttribute('aria-current', 'step');
  await expect(secondSet.getByText('Облегчённый подход', { exact: true })).toBeVisible();
  await expect(secondSet.locator('.active-workout-set__history')).toContainText('40 кг × 8');
  await secondSet.getByLabel('Вес, Жим штанги лёжа, подход 2').fill('35');
  await expect.poll(() => secondSetPatchBodies.length).toBeGreaterThan(0);
  const patchesBeforePrefill = secondSetPatchBodies.length;
  await secondSet.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }).click();
  await expect.poll(() => secondSetPatchBodies.length).toBe(patchesBeforePrefill);
  await expect(secondSet.getByLabel('Вес, Жим штанги лёжа, подход 2')).toHaveValue('35');
  await expect(
    secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }),
  ).toHaveValue('8');
  await expect(
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }),
  ).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  const restPanel = page.getByRole('complementary', { name: 'Отдых между подходами' });
  await expect(restPanel).not.toContainText('Жим штанги лёжа');
  await expect(restPanel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
  await expect(secondSet).toHaveAttribute('aria-current', 'step');

  await secondSet.getByText('Дополнительно').click();
  await secondSet.getByLabel('Вид подхода').selectOption('drop');
  await secondSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
  await secondSet.getByLabel('Вес, Жим штанги лёжа, подход 2').fill('35');
  await secondSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 2' }).fill('9');
  await Promise.all([
    waitForCompletedSetPatch(page, 202),
    secondSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click(),
  ]);

  const thirdSet = page.locator('[data-workout-set-id="203"]');
  await expect(thirdSet).toHaveAttribute('aria-current', 'step');
  await thirdSet.getByRole('button', { name: /^4\+ —/ }).click();
  await thirdSet.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }).click();
  const thirdDone = thirdSet.getByRole('button', {
    name: 'Завершить: Жим штанги лёжа, подход 3',
  });
  await thirdDone.evaluate((element) =>
    element.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }),
  );
  await expect(thirdDone).toBeVisible();
  await Promise.all([waitForCompletedSetPatch(page, 203), thirdDone.click()]);
  expect(server.readSet(203)).toMatchObject({ is_completed: true, rir: '4+' });

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

type Issue1164Theme = 'light' | 'dark';

const issue1164Viewports = [
  { width: 320, height: 800 },
  { width: 360, height: 800 },
  { width: 393, height: 844 },
  { width: 430, height: 932 },
] as const;

async function runIssue1164SpacingScenario(
  page: Page,
  theme: Issue1164Theme,
  viewport: (typeof issue1164Viewports)[number],
) {
  await page.setViewportSize(viewport);
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const capture = process.env.YFC_ISSUE_1164_CAPTURE === '1';
  const directory = resolve(
    process.cwd(),
    '..',
    '.artifacts',
    'tasks',
    '1164',
    'evidence',
    process.env.YFC_ISSUE_1164_CAPTURE_PHASE ?? 'after',
    `${theme}-${viewport.width}`,
  );
  const captureState = async (name: string, locator: Locator, fullPage = false) => {
    if (!capture) return;
    await mkdir(directory, { recursive: true });
    await locator.screenshot({ path: resolve(directory, `${name}-card.png`) });
    if (fullPage)
      await page.screenshot({ path: resolve(directory, `${name}-page.png`), fullPage: true });
  };

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await expect(firstSet).toHaveAttribute('aria-current', 'step');
  await captureState('01-first-set-initial', firstSet);
  await firstSet.getByLabel(/Вес,/).fill('40');
  await firstSet.getByRole('spinbutton', { name: /Повторы,/ }).fill('8');
  await Promise.all([
    waitForCompletedSetPatch(page, 201),
    firstSet.getByRole('button', { name: /^Завершить:/ }).click(),
  ]);

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await expect(secondSet).toHaveAttribute('aria-current', 'step');
  await expect(secondSet.locator('.active-workout-set__history')).toContainText('40 кг × 8');
  await expect(secondSet.locator('.active-workout-set__context')).toContainText('8–10 повторений');
  await expect(secondSet.locator('.active-workout-set__context')).toContainText('Отдых 90 с');
  await expect(page.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
  await captureState('02-rest-prefill-visible', secondSet, true);

  const measure = async () =>
    page.evaluate(() => {
      const row = document.querySelector<HTMLElement>('[data-workout-set-id="202"]');
      const previous = row?.querySelector<HTMLElement>('.active-workout-set__history');
      const prefill = row?.querySelector<HTMLElement>('.active-workout-set__prefill-actions');
      const context = row?.querySelector<HTMLElement>('.active-workout-set__context');
      const controls = row?.querySelector<HTMLElement>('.active-workout-set__controls');
      if (!row || !previous || !prefill || !context || !controls) return null;
      const prefillStyle = getComputedStyle(prefill);
      return {
        rowHeight: row.getBoundingClientRect().height,
        prefillHeight: prefill.getBoundingClientRect().height,
        prefillVisibility: prefillStyle.visibility,
        contextGap: context.getBoundingClientRect().top - previous.getBoundingClientRect().bottom,
        prefillAfterControlsGap:
          prefill.getBoundingClientRect().top - controls.getBoundingClientRect().bottom,
      };
    });

  const beforePrefill = await measure();
  expect(beforePrefill).not.toBeNull();
  expect(beforePrefill!.prefillHeight).toBeGreaterThanOrEqual(44);
  expect(beforePrefill!.prefillVisibility).toBe('visible');
  expect(beforePrefill!.contextGap).toBeLessThanOrEqual(24);
  expect(beforePrefill!.prefillAfterControlsGap).toBeGreaterThanOrEqual(-1);

  await secondSet.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }).click();
  await expect(
    secondSet.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }),
  ).toBeDisabled();
  const afterPrefill = await measure();
  expect(afterPrefill).not.toBeNull();
  expect(afterPrefill!.prefillHeight).toBe(beforePrefill!.prefillHeight);
  expect(afterPrefill!.prefillVisibility).toBe('visible');
  expect(afterPrefill!.contextGap).toBeLessThanOrEqual(24);
  await captureState('03-rest-prefill-dismissed', secondSet, true);

  await secondSet.getByText('Дополнительно', { exact: true }).click();
  await expect(secondSet.getByLabel('Вид подхода')).toBeVisible();
  expect((await measure())?.contextGap).toBeLessThanOrEqual(24);
  await captureState('04-advanced-open', secondSet, true);
  await secondSet.getByText('Дополнительно', { exact: true }).click();
  await expect(secondSet.getByLabel('Вид подхода')).not.toBeVisible();

  // #1318: keep the focus outline inside both inputs without shifting the label.
  const weight = secondSet.getByLabel(/Вес,/);
  const repetitions = secondSet.getByRole('spinbutton', { name: /Повторы,/ });
  for (const field of [weight, repetitions]) {
    await field.focus();
    await expect(field).toBeFocused();
    await expect(field).toHaveCSS('outline-width', '3px');
    await expect(field).toHaveCSS('outline-offset', '-4px');
    const distance = await field.evaluate((input) => {
      const caption = input.closest('label')!.querySelector('span')!;
      return input.getBoundingClientRect().top - caption.getBoundingClientRect().bottom;
    });
    expect(distance).toBeGreaterThanOrEqual(0);
  }
  await weight.focus();
  await expectClearOfBottomDock(weight, `${theme} ${viewport.width}px weight`);
  await expectClearOfBottomDock(
    secondSet.getByRole('button', { name: /^Завершить:/ }),
    `${theme} ${viewport.width}px completion`,
  );
  const focusedPrefill = await measure();
  expect(focusedPrefill?.prefillHeight).toBe(beforePrefill!.prefillHeight);
  expect(focusedPrefill?.prefillVisibility).toBe('visible');
  await weight.blur();
  await expect(weight).not.toBeFocused();
  const afterBlur = await measure();
  expect(afterBlur?.prefillHeight).toBe(beforePrefill!.prefillHeight);
  if (capture) {
    await mkdir(directory, { recursive: true });
    await writeFile(
      resolve(directory, 'geometry.json'),
      JSON.stringify({ beforePrefill, afterPrefill, focusedPrefill, afterBlur }, null, 2),
    );
  }
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);

  await page.getByRole('button', { name: 'Свернуть таймер' }).click();
  await expect(page.getByRole('button', { name: 'Развернуть таймер' })).toBeVisible();
  expect((await measure())?.contextGap).toBeLessThanOrEqual(24);
  await captureState('05-rest-collapsed', secondSet, true);

  await page.getByRole('button', { name: 'Развернуть таймер' }).click();
  await page.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
  await expect(page.getByRole('button', { name: 'Скрыть' })).toBeVisible();
  expect((await measure())?.contextGap).toBeLessThanOrEqual(24);
  await captureState('06-rest-completed', secondSet, true);
}

for (const issue1164Theme of ['light', 'dark'] as const) {
  for (const issue1164Viewport of issue1164Viewports) {
    test(`#1164 active set spacing ${issue1164Theme} ${issue1164Viewport.width}px`, async ({
      page,
    }) => {
      await runIssue1164SpacingScenario(page, issue1164Theme, issue1164Viewport);
    });
  }
}

test('active workout keeps the current exercise primary and exposes keyboard handoff', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const currentSet = page.locator('[data-workout-set-id="201"]');
  const weight = currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1');
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
  const rirOptions = currentSet.locator('.active-workout-set__rir-row button');
  await expect(rirOptions.first()).toBeFocused();
  await rirOptions.last().focus();
  await page.keyboard.press('Tab');
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
      const weight = currentSet.getByLabel('Вес, Жим штанги лёжа, подход 1');
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

for (const width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`resting active workout keeps the next set clear of the dock at ${width}px ${theme}`, async ({
      browser,
      baseURL,
    }, testInfo) => {
      const context = await browser.newContext({
        baseURL,
        viewport: { width, height: 844 },
        isMobile: true,
        hasTouch: true,
        serviceWorkers: 'block',
      });
      const page = await context.newPage();
      try {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        const server = await mockActiveWorkout(page);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

        const firstSet = page.locator('[data-workout-set-id="201"]');
        await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
        await firstSet.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
        await Promise.all([
          waitForCompletedSetPatch(page, 201),
          firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click(),
        ]);
        const currentSet = page.locator('[data-workout-set-id="202"]');
        await currentSet.getByLabel('Вес, Жим штанги лёжа, подход 2').fill('42.5');
        await currentSet.getByLabel('Повторы, Жим штанги лёжа, подход 2').fill('9');
        await currentSet.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
        await expect
          .poll(() => server.readSet(202))
          .toMatchObject({
            actual_weight: 42.5,
            actual_reps: 9,
            rir: '2',
          });
        await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
        await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
        await expect(page.locator('.active-workout-rest')).toBeVisible();
        await expect(currentSet.locator('.active-workout-set__contextual-help')).toBeHidden();
        const controls = currentSet.locator('.active-workout-set__controls');
        const rirGaps = await controls.evaluate((element) => {
          const weight = element
            .querySelector('[data-workout-field="weight"]')!
            .getBoundingClientRect();
          const reps = element
            .querySelector('[data-workout-field="reps"]')!
            .getBoundingClientRect();
          const rir = element
            .querySelector('.active-workout-set__rir-row')!
            .getBoundingClientRect();
          const done = element
            .querySelector('[data-workout-field="done"]')!
            .getBoundingClientRect();
          return {
            above: rir.top - Math.max(weight.bottom, reps.bottom),
            below: done.top - rir.bottom,
          };
        });
        if (process.env.YFC_1272_CAPTURE_DIR) {
          await mkdir(process.env.YFC_1272_CAPTURE_DIR, { recursive: true });
          await controls.screenshot({
            path: resolve(
              process.env.YFC_1272_CAPTURE_DIR,
              `${testInfo.project.name}-${width}-${theme}-next.png`,
            ),
            animations: 'disabled',
            scale: 'css',
          });
        }
        expect(rirGaps.above, `${width}px: input to RIR`).toBeGreaterThanOrEqual(12);
        expect(rirGaps.above, `${width}px: input to RIR`).toBeLessThanOrEqual(16);
        expect(rirGaps.below, `${width}px: RIR to CTA`).toBeGreaterThanOrEqual(12);
        expect(rirGaps.below, `${width}px: RIR to CTA`).toBeLessThanOrEqual(16);
        await page.evaluate(
          () =>
            new Promise<void>((resolve) =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
            ),
        );
        const writes: string[] = [];
        page.on('request', (request) => {
          if (/\/workouts\/sets\//.test(request.url()) && request.method() !== 'GET') {
            writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
          }
        });
        const geometry = await page.evaluate(() => {
          const nav = document.querySelector<HTMLElement>('#appBottomNav')!;
          const nextSet = document.querySelector<HTMLElement>('[data-workout-set-id="203"]')!;
          const nextDone = nextSet.querySelector<HTMLElement>('[data-workout-field="done"]')!;
          const current = document.querySelector<HTMLElement>('[data-workout-set-id="202"]')!;
          const currentInput = current.querySelector<HTMLElement>('input')!;
          const currentDone = current.querySelector<HTMLElement>('[data-workout-field="done"]')!;
          const rest = document.querySelector<HTMLElement>('.active-workout-rest')!;
          const nextInteractive = Array.from(
            nextSet.querySelectorAll<HTMLElement>('input, button'),
          ).filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          });
          const activeNav =
            nav.querySelector<HTMLElement>('[aria-current="page"]') ??
            nav.querySelector<HTMLElement>('a, button')!;
          const nextDoneRect = nextDone.getBoundingClientRect();
          const currentDoneRect = currentDone.getBoundingClientRect();
          const currentInputRect = currentInput.getBoundingClientRect();
          const nextSetRect = nextSet.getBoundingClientRect();
          const navRect = nav.getBoundingClientRect();
          const activeNavRect = activeNav.getBoundingClientRect();
          const nextInteractiveBottom = Math.max(
            ...nextInteractive.map((element) => element.getBoundingClientRect().bottom),
          );
          const currentDockOverlap = Math.max(
            0,
            Math.min(currentDoneRect.bottom, navRect.bottom) -
              Math.max(currentDoneRect.top, navRect.top),
          );
          const nextDockOverlap = Math.max(
            0,
            Math.min(nextDoneRect.bottom, navRect.bottom) - Math.max(nextDoneRect.top, navRect.top),
          );
          const nextVisible = nextSetRect.top < innerHeight && nextSetRect.bottom > 0;
          const inputRestOverlap = Math.max(
            0,
            Math.min(currentInputRect.bottom, rest.getBoundingClientRect().bottom) -
              Math.max(currentInput.getBoundingClientRect().top, rest.getBoundingClientRect().top),
          );
          return {
            viewport: { width: innerWidth, height: innerHeight },
            scrollY,
            nav: navRect.toJSON(),
            rest: rest.getBoundingClientRect().toJSON(),
            currentSet: current.getBoundingClientRect().toJSON(),
            currentInput: currentInputRect.toJSON(),
            currentDone: currentDoneRect.toJSON(),
            nextSet: nextSetRect.toJSON(),
            nextDone: nextDoneRect.toJSON(),
            nextInteractiveBottom,
            currentDockOverlap,
            nextDockOverlap,
            nextVisible,
            inputRestOverlap,
            currentDoneHit:
              document
                .elementFromPoint(
                  currentDoneRect.left + currentDoneRect.width / 2,
                  currentDoneRect.top + currentDoneRect.height / 2,
                )
                ?.getAttribute('data-workout-field') ?? null,
            nextDoneHit: nextVisible
              ? (document
                  .elementFromPoint(
                    nextDoneRect.left + nextDoneRect.width / 2,
                    Math.min(nextDoneRect.bottom - 2, innerHeight - 2),
                  )
                  ?.getAttribute('data-workout-field') ?? null)
              : null,
            navHit: nav.contains(
              document.elementFromPoint(
                activeNavRect.left + activeNavRect.width / 2,
                activeNavRect.top + activeNavRect.height / 2,
              ),
            ),
            activeNav: activeNavRect.toJSON(),
            current: document
              .querySelector('[aria-current="step"]')
              ?.getAttribute('data-workout-set-id'),
          };
        });
        await page.screenshot({
          path: testInfo.outputPath(`resting-dock-${width}-${theme}.png`),
          animations: 'disabled',
        });
        const beforeUrl = page.url();
        const beforeSection = new URL(beforeUrl).searchParams.get('section') ?? 'today';
        await page.touchscreen.tap(
          geometry.activeNav.left + geometry.activeNav.width / 2,
          geometry.activeNav.top + geometry.activeNav.height / 2,
        );
        await expect(page.locator('[aria-current="step"]')).toHaveAttribute(
          'data-workout-set-id',
          '202',
        );
        await testInfo.attach(`resting-dock-${width}-${theme}.json`, {
          body: JSON.stringify({ geometry, writes }),
          contentType: 'application/json',
        });
        expect(geometry.currentDockOverlap, JSON.stringify(geometry)).toBe(0);
        expect(geometry.currentDone.bottom, JSON.stringify(geometry)).toBeLessThanOrEqual(
          geometry.nav.top - 8,
        );
        expect(geometry.currentDoneHit).toBe('done');
        if (geometry.nextVisible) {
          expect(geometry.nextDockOverlap, JSON.stringify(geometry)).toBe(0);
          expect(geometry.nextInteractiveBottom, JSON.stringify(geometry)).toBeLessThanOrEqual(
            geometry.nav.top - 8,
          );
          expect(geometry.nextDoneHit).toBe('done');
        }
        expect(geometry.inputRestOverlap, JSON.stringify(geometry)).toBe(0);
        expect(geometry.navHit).toBe(true);
        expect(geometry.current).toBe('202');
        expect(new URL(page.url()).searchParams.get('section') ?? 'today').toBe(beforeSection);
        expect(writes).toEqual([]);
      } finally {
        await context.close();
      }
    });
  }
}

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
  await cardio.getByLabel('Дистанция, Велотренажёр').fill('6.4');
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

  const cardioDone = cardio.locator('[data-workout-field="done"]');
  const releaseCardio = server.holdNextPatch();
  await cardioDone.click();
  try {
    await expect(cardioDone).toHaveText('Сохраняем…');
    await expect(cardioDone).toBeDisabled();
    await expect(cardioDone).toHaveAttribute('aria-busy', 'true');
    await expect(cardioDone).toHaveAttribute('aria-label', /^Сохраняем…:/);
    await expect(cardioDone).toHaveAttribute('aria-pressed', 'true');
  } finally {
    releaseCardio();
  }
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

test('#980 completed strength sets require an explicit edit or reopen action', async ({ page }) => {
  const server = await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('42.5');
  await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
  await first.getByRole('button', { name: /^2 —/ }).click();
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect(page.getByRole('button', { name: 'Пропустить', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Пропустить', exact: true }).click();
  await expect(
    first.getByRole('button', { name: 'Выполнен: Жим штанги лёжа, подход 1' }),
  ).toBeDisabled();
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toBeDisabled();
  await expect(first.getByRole('button', { name: 'Редактировать' })).toBeVisible();
  await expect(
    completedActions(first).getByRole('button', { name: 'Вернуть в работу' }),
  ).toBeVisible();

  await first.getByRole('button', { name: 'Редактировать' }).click();
  await expect(first.getByRole('button', { name: 'Отмена' })).toBeVisible();
  await expect(first.getByRole('button', { name: 'Сохранить' })).toBeVisible();
  await expect(first.getByRole('button', { name: 'Вернуть в работу' })).toHaveCount(0);
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toBeEnabled();
  const writesBeforeDraft = server.patches.length;
  await first.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('44');
  await first.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('10');
  await expect.poll(() => server.patches.length).toBe(writesBeforeDraft);
  await first.getByRole('button', { name: 'Отмена' }).click();
  await expect(completedActions(first)).toHaveCount(1);
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('42.5');
  await expect(first.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('9');
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toBeDisabled();
  expect(server.readSet(201)).toMatchObject({
    actual_weight: 42.5,
    actual_reps: 9,
    rir: '2',
    is_completed: true,
  });

  await first.getByRole('button', { name: 'Редактировать' }).click();
  await first.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('45');
  await first.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('10');
  await expect.poll(() => server.patches.length).toBe(writesBeforeDraft);
  await first.getByRole('button', { name: 'Сохранить' }).click();
  await expect.poll(() => server.readSet(201).actual_weight).toBe(45);
  await expect.poll(() => server.readSet(201).actual_reps).toBe(10);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  expect(server.readSet(201)).toMatchObject({ is_completed: true, rir: '2' });
  await expect(first.getByRole('button', { name: 'Редактировать' })).toBeVisible();
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toBeDisabled();

  const writesBeforeCancel = server.patches.length;
  const actions = completedActions(first);
  await actions.getByRole('button', { name: 'Вернуть в работу' }).click();
  await expect(page.getByRole('dialog')).toContainText('Сохранённые результаты останутся');
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect.poll(() => server.patches.length).toBe(writesBeforeCancel);
  expect(server.readSet(201)).toMatchObject({
    actual_weight: 45,
    actual_reps: 10,
    is_completed: true,
  });

  await actions.getByRole('button', { name: 'Вернуть в работу' }).click();
  await expect(page.getByRole('dialog')).toContainText('Статус изменится на');
  await page.getByRole('dialog').getByRole('button', { name: 'Вернуть в работу' }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(false);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  expect(server.readSet(201)).toMatchObject({ actual_weight: 45, actual_reps: 10 });
  await expect(first).toHaveAttribute('aria-current', 'step');
});

test('#980 completed cardio results keep their values through edit and reopen', async ({
  page,
}) => {
  const server = await mockActiveWorkout(page, true);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
  await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
  await cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }).fill('27');
  await cardio.getByLabel('Дистанция, Велотренажёр').fill('6.4');
  await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
  await expect.poll(() => server.readSet(204).is_completed).toBe(true);

  await expect(
    cardio.getByRole('button', { name: 'Кардио выполнено: Велотренажёр' }),
  ).toBeDisabled();
  await cardio.getByRole('button', { name: 'Редактировать' }).click();
  await expect(cardio.getByRole('button', { name: 'Отмена' })).toBeVisible();
  await expect(cardio.getByRole('button', { name: 'Вернуть в работу' })).toHaveCount(0);
  const writesBeforeDraft = server.patches.length;
  await cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }).fill('30');
  await expect.poll(() => server.patches.length).toBe(writesBeforeDraft);
  await cardio.getByRole('button', { name: 'Отмена' }).click();
  await expect(completedActions(cardio)).toHaveCount(1);
  await expect(cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' })).toHaveValue(
    '27',
  );
  expect(server.readSet(204)).toMatchObject({ duration_minutes: 27, is_completed: true });

  await cardio.getByRole('button', { name: 'Редактировать' }).click();
  await cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }).fill('30');
  await cardio.getByRole('button', { name: 'Сохранить' }).click();
  await expect.poll(() => server.readSet(204).duration_minutes).toBe(30);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  expect(server.readSet(204).is_completed).toBe(true);
  await expect(cardio.getByRole('button', { name: 'Редактировать' })).toBeVisible();
  await expect(
    cardio.getByRole('spinbutton', { name: 'Длительность, Велотренажёр' }),
  ).toBeDisabled();

  const actions = completedActions(cardio);
  await actions.getByRole('button', { name: 'Вернуть в работу' }).click();
  await expect(page.getByRole('dialog')).toContainText('Сохранённые результаты останутся');
  await page.getByRole('dialog').getByRole('button', { name: 'Вернуть в работу' }).click();
  await expect.poll(() => server.readSet(204).is_completed).toBe(false);
  await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
  expect(server.readSet(204)).toMatchObject({ duration_minutes: 30, distance_km: 6.4 });
});

for (const theme of ['dark', 'light'] as const) {
  test(`#980 guide text has readable contrast in every interactive state ${theme}`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await mockActiveWorkout(page, true);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const guide = page
      .locator('.active-workout-exercise')
      .filter({ hasText: 'Велотренажёр' })
      .getByRole('button', { name: 'Подробнее', exact: true });
    await expect(guide).toBeVisible();
    await guide.scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    const samples = [];
    for (const state of ['default', 'hover', 'pressed', 'focus'] as const) {
      if (state === 'hover') await guide.hover();
      if (state === 'pressed') await page.mouse.down();
      if (state === 'focus') {
        await page.mouse.move(0, 0);
        await page.mouse.up();
        await page.keyboard.press('Tab');
        await guide.focus();
        await expect(guide).toBeFocused();
      }
      if (state === 'hover' || state === 'pressed')
        await expect(guide).toHaveCSS('color', 'rgb(9, 11, 11)');
      if (state === 'default')
        expect(await guide.evaluate((element) => element.matches(':hover'))).toBe(false);
      if (state !== 'default') {
        const pseudo =
          state === 'pressed' ? ':active' : state === 'focus' ? ':focus-visible' : ':hover';
        await expect
          .poll(() => guide.evaluate((element, selector) => element.matches(selector), pseudo))
          .toBe(true);
      }
      const sample = await guide.evaluate((element) => {
        const label = element.querySelector('span');
        if (!label) throw new Error('Missing guide label');
        const foreground = getComputedStyle(label).color;
        const background = getComputedStyle(element).backgroundColor;
        const luminance = (color: string) => {
          const channels = color
            .match(/[\d.]+/g)!
            .slice(0, 3)
            .map(Number)
            .map((value) => {
              const normalized = value / 255;
              return normalized <= 0.04045
                ? normalized / 12.92
                : ((normalized + 0.055) / 1.055) ** 2.4;
            });
          return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722;
        };
        const a = luminance(foreground),
          b = luminance(background);
        return {
          foreground,
          background,
          buttonColor: getComputedStyle(element).color,
          labelTransition: getComputedStyle(label).transition,
          contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
        };
      });
      samples.push({ state, ...sample });
      expect
        .soft(sample.contrast, `${state} guide label contrast ${JSON.stringify(sample)}`)
        .toBeGreaterThanOrEqual(4.5);
      if (CAPTURE_980_AFTER && state === 'hover') {
        await mkdir(ISSUE_980_AFTER_DIR, { recursive: true });
        await page.screenshot({
          path: resolve(ISSUE_980_AFTER_DIR, `${info.project.name}-${theme}-guide-hover.png`),
        });
      }
    }
    await info.attach('guide-computed-colors.json', {
      body: JSON.stringify(samples, null, 2),
      contentType: 'application/json',
    });
    if (CAPTURE_980_AFTER)
      await writeFile(
        resolve(ISSUE_980_AFTER_DIR, `${info.project.name}-${theme}-guide-colors.json`),
        JSON.stringify(samples, null, 2),
      );
  });
}

test.describe('#980 completed set visual candidate', () => {
  for (const theme of ['dark', 'light'] as const) {
    test(`${theme} completed set keeps explicit actions visible`, async ({ page }, info) => {
      const captureWidth = Number(process.env.CAPTURE_980_WIDTH ?? 390);
      await page.setViewportSize({ width: captureWidth, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const server = await mockActiveWorkout(page, true);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('42.5');
      await first.getByRole('spinbutton', { name: /^Повторы,/ }).fill('9');
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(true);
      const rest = page.locator('.active-workout-rest');
      await expect(rest).toBeVisible();
      await expect(first.getByRole('button', { name: 'Редактировать' })).toBeVisible();
      await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('42.5');
      await expect(first.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('9');
      await first.evaluate((element) => {
        element.scrollIntoView({ block: 'center', behavior: 'instant' });
      });
      const geometry = await page.evaluate(() => {
        const panel = document.querySelector<HTMLElement>('.active-workout-rest');
        const row = document.querySelector<HTMLElement>('[data-workout-set-id="201"]');
        const edit = row?.querySelector<HTMLElement>('[data-workout-action="edit-completed"]');
        if (!panel || !row || !edit) return null;
        const panelBox = panel.getBoundingClientRect();
        const rowBox = row.getBoundingClientRect();
        const editBox = edit.getBoundingClientRect();
        const overlaps = (a: DOMRect, b: DOMRect) =>
          a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        return {
          panel: panelBox.toJSON(),
          row: rowBox.toJSON(),
          edit: editBox.toJSON(),
          rowOverlapsPanel: overlaps(rowBox, panelBox),
          editOverlapsPanel: overlaps(editBox, panelBox),
        };
      });
      expect(geometry).not.toBeNull();
      expect(geometry?.rowOverlapsPanel).toBe(false);
      expect(geometry?.editOverlapsPanel).toBe(false);
      await info.attach('rest-panel-geometry.json', {
        body: JSON.stringify(geometry, null, 2),
        contentType: 'application/json',
      });

      if (CAPTURE_980_AFTER) {
        await mkdir(ISSUE_980_AFTER_DIR, { recursive: true });
        await page.screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-completed.png`,
          ),
          fullPage: false,
        });
      }

      await first.getByRole('button', { name: 'Редактировать' }).click();
      await expect(first.getByRole('button', { name: 'Сохранить' })).toBeVisible();
      await first.getByLabel('Вес, Жим штанги лёжа, подход 1').focus();
      await first.evaluate((element) => {
        element.scrollIntoView({ block: 'center', behavior: 'instant' });
      });
      if (CAPTURE_980_AFTER) {
        await page.screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-strength-editing.png`,
          ),
          fullPage: false,
        });
      }
      await first.getByRole('button', { name: 'Отмена' }).click();

      const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
      await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
      await cardio.getByLabel('Длительность, Велотренажёр').fill('27');
      await cardio.getByLabel('Дистанция, Велотренажёр').fill('6.4');
      await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
      await expect.poll(() => server.readSet(204).is_completed).toBe(true);
      await cardio.getByRole('button', { name: 'Редактировать' }).click();
      await cardio.getByLabel('Длительность, Велотренажёр').focus();
      await cardio.evaluate((element) => {
        element.scrollIntoView({ block: 'center', behavior: 'instant' });
      });
      if (CAPTURE_980_AFTER) {
        await page.screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-cardio-editing.png`,
          ),
          fullPage: false,
        });
      }
      await cardio.getByRole('button', { name: 'Отмена' }).click();

      if (CAPTURE_980_AFTER) {
        const rir = page
          .locator('[data-workout-set-id="202"] .active-workout-rir__options button')
          .first();
        await rir.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        await page.screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-rir-actions.png`,
          ),
          fullPage: false,
        });

        const finish = page.getByRole('button', { name: 'Завершить тренировку', exact: true });
        await finish.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        await page.screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-footer-actions.png`,
          ),
          fullPage: false,
        });
      }

      const actions = completedActions(first);
      await actions.getByRole('button', { name: 'Вернуть в работу' }).click();
      await expect(page.getByRole('dialog')).toContainText('Сохранённые результаты останутся');
      if (CAPTURE_980_AFTER) {
        await page.getByRole('dialog').screenshot({
          path: resolve(
            ISSUE_980_AFTER_DIR,
            `${info.project.name}-${captureWidth}-${theme}-confirm.png`,
          ),
        });
      }
      await page.getByRole('button', { name: 'Отмена' }).click();
    });
  }
});

for (const issue1162Width of [320, 360, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#1162 completed set actions stay compact and deliberate ${theme} ${issue1162Width}px`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width: issue1162Width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const server = await mockActiveWorkout(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент' }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

      const first = page.locator('[data-workout-set-id="201"]');
      const current = page.locator('[data-workout-set-id="202"]');
      await first.getByLabel(/^Вес,/).fill('42.5');
      await first.getByLabel(/^Повторы,/).fill('9');
      await first.getByRole('button', { name: /^2 —/ }).click();
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(true);
      await expect(page.getByRole('button', { name: 'Пропустить', exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Пропустить', exact: true }).click();

      await expect(current).toHaveAttribute('aria-current', 'step');
      await expect(first.getByText('Выполнен', { exact: true })).toBeVisible();
      await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('42.5');
      await expect(first.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('9');
      await expect(first.getByRole('button', { name: 'Редактировать' })).toBeVisible();
      await expect(first.getByRole('button', { name: 'Вернуть в работу' })).toBeVisible();
      await expect(first.getByRole('button', { name: 'Действия', exact: true })).toHaveCount(0);
      await expect(first.locator('.active-workout-set__more-actions')).toHaveCount(0);

      await first.scrollIntoViewIfNeeded();
      await captureIssue1162State(page, info, theme, '01-completed-actions');
      const closedLayout = await first.evaluate((row) => {
        const box = (selector: string) =>
          row.querySelector<HTMLElement>(selector)?.getBoundingClientRect();
        const rowBox = row.getBoundingClientRect();
        const actions = box('.active-workout-set__completed-actions');
        const edit = box('[data-workout-action="edit-completed"]');
        const restore = box('[data-workout-action="reopen-completed"]');
        const buttonsFit = [
          ...row.querySelectorAll<HTMLElement>(
            '[data-workout-action="edit-completed"], [data-workout-action="reopen-completed"]',
          ),
        ].map((button) => button.scrollWidth <= button.clientWidth + 1);
        return {
          row: rowBox.toJSON(),
          actions: actions?.toJSON() ?? null,
          edit: edit?.toJSON() ?? null,
          restore: restore?.toJSON() ?? null,
          buttonsFit,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
        };
      });
      expect(closedLayout.documentWidth).toBeLessThanOrEqual(closedLayout.viewportWidth + 1);
      expect(closedLayout.actions?.right).toBeLessThanOrEqual((closedLayout.row?.right ?? 0) + 1);
      expect(closedLayout.edit?.height).toBeGreaterThanOrEqual(44);
      expect(closedLayout.restore?.height).toBeGreaterThanOrEqual(44);
      expect(closedLayout.restore?.top).toBe(closedLayout.edit?.top);
      expect(closedLayout.restore?.left).toBeGreaterThanOrEqual(
        (closedLayout.edit?.right ?? 0) - 1,
      );
      expect(closedLayout.buttonsFit).toEqual([true, true]);
      expect(closedLayout.actions?.height).toBeLessThanOrEqual(52);

      // #1320: completed RIR/failure can be corrected without reopening the set.
      const writesBeforeMetadata = server.patches.length;
      await first.locator('.active-workout-set__advanced > summary').click();
      const completedRir = first.getByRole('button', { name: /^1 —/ });
      const completedFailure = first.getByRole('checkbox', { name: 'Подход до отказа' });
      await expect(completedRir).toBeEnabled();
      await expect(completedFailure).toBeEnabled();
      await completedRir.click();
      await expect.poll(() => server.readSet(201).rir).toBe('1');
      await completedRir.click();
      await expect.poll(() => server.readSet(201).rir).toBeNull();
      await first.getByRole('button', { name: /^2 —/ }).click();
      await expect.poll(() => server.readSet(201).rir).toBe('2');
      await completedFailure.check();
      await expect.poll(() => server.readSet(201).reached_failure).toBe(true);
      await completedFailure.uncheck();
      await expect.poll(() => server.readSet(201).reached_failure).toBe(false);
      await expect.poll(() => activeWorkoutQueueLength(page)).toBe(0);
      const metadataWrites = server.patches.slice(writesBeforeMetadata);
      expect(metadataWrites.length).toBeGreaterThanOrEqual(5);
      expect(metadataWrites.every((patch) => patch.body.is_completed === true)).toBe(true);
      expect(server.readSet(201).is_completed).toBe(true);
      await expect(first.getByText('Выполнен', { exact: true })).toBeVisible();
      await expect(current).toHaveAttribute('aria-current', 'step');
      await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);

      const actions = completedActions(first);
      await expect(actions.getByRole('button', { name: 'Вернуть в работу' })).toBeVisible();
      await expect(actions.getByRole('button', { name: 'Вернуть в работу' })).toHaveCount(1);

      const writesBeforeConfirm = server.patches.length;
      const restore = actions.getByRole('button', { name: 'Вернуть в работу' });
      await restore.click();
      await restore.dispatchEvent('click');
      await expect(page.getByRole('dialog')).toHaveCount(1);
      expect(server.patches.length).toBe(writesBeforeConfirm);
      await captureIssue1162State(page, info, theme, '02-reopen-confirmation');
      await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click();
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await expect.poll(() => server.patches.length).toBe(writesBeforeConfirm);
      expect(server.readSet(201).is_completed).toBe(true);

      const actionsAfterCancel = completedActions(first);
      await actionsAfterCancel.getByRole('button', { name: 'Вернуть в работу' }).click();
      await page.getByRole('dialog').getByRole('button', { name: 'Вернуть в работу' }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(false);
      await expect(page.getByRole('timer', { name: 'Отдых' })).toHaveCount(0);
      await expect(first).toHaveAttribute('aria-current', 'step');
      await expect(first.getByRole('button', { name: 'Редактировать' })).toHaveCount(0);
      await captureIssue1162State(page, info, theme, '03-returned-to-work');

      expect(
        server.patches.filter((patch) => patch.setId === 201 && patch.body.is_completed === false),
      ).toHaveLength(1);
    });
  }
}

test('#1162 long exercise titles keep completed actions inline at 320px', async ({ page }) => {
  const longTitle = 'Жим штанги лёжа с паузой и контролем траектории';
  const server = await mockActiveWorkout(
    page,
    false,
    'approved_animated',
    false,
    null,
    false,
    longTitle,
  );
  await page.setViewportSize({ width: 320, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), 'dark');
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('42.5');
  await first.getByLabel(/^Повторы,/).fill('9');
  await first.getByRole('button', { name: /^2 —/ }).click();
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect.poll(() => server.readSet(201).is_completed).toBe(true);
  await expect(page.getByRole('button', { name: 'Пропустить', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Пропустить', exact: true }).click();

  const layout = await first.evaluate((row) => {
    const box = (selector: string) =>
      row.querySelector<HTMLElement>(selector)?.getBoundingClientRect().toJSON() ?? null;
    const edit = box('[data-workout-action="edit-completed"]');
    const restore = box('[data-workout-action="reopen-completed"]');
    const buttons = [
      ...row.querySelectorAll<HTMLElement>(
        '[data-workout-action="edit-completed"], [data-workout-action="reopen-completed"]',
      ),
    ];
    return {
      title: row.closest('.active-workout-exercise')?.querySelector('h3')?.textContent,
      edit,
      restore,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      buttonsFit: buttons.map((button) => button.scrollWidth <= button.clientWidth + 1),
    };
  });
  expect(layout.title).toBe(longTitle);
  expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth + 1);
  expect(layout.edit?.height).toBeGreaterThanOrEqual(44);
  expect(layout.restore?.height).toBeGreaterThanOrEqual(44);
  expect(layout.restore?.top).toBe(layout.edit?.top);
  expect(layout.buttonsFit).toEqual([true, true]);
});

test.describe('#980 completed-set geometry regression', () => {
  for (const width of [320, 360, 390, 393, 430]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`keeps completed strength/cardio editing and lower actions inside ${width}px ${theme}`, async ({
        page,
      }, info) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        const server = await mockActiveWorkout(page, true);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент' }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

        const strength = page.locator('[data-workout-set-id="201"]');
        const strengthExercise = page
          .locator('.active-workout-exercise')
          .filter({ hasText: 'Жим штанги лёжа' })
          .first();
        await expect(strengthExercise.locator('.active-workout-history')).toBeVisible();
        const historyGap = await strengthExercise.evaluate((exercise) => {
          const history = exercise.querySelector<HTMLElement>('.active-workout-history');
          const sets = exercise.querySelector<HTMLElement>('.active-workout-exercise__sets');
          if (!history || !sets) return null;
          return sets.getBoundingClientRect().top - history.getBoundingClientRect().bottom;
        });
        expect(historyGap).not.toBeNull();
        expect(historyGap ?? 0).toBeGreaterThanOrEqual(8);

        await strength.getByLabel(/^Вес,/).fill('42.5');
        await strength.getByLabel(/^Повторы,/).fill('9');
        await strength.getByRole('button', { name: /^Завершить:/ }).click();
        await expect.poll(() => server.readSet(201).is_completed).toBe(true);
        await strength.getByRole('button', { name: 'Редактировать' }).click();
        const weight = strength.getByLabel('Вес, Жим штанги лёжа, подход 1');
        const reps = strength.getByLabel('Повторы, Жим штанги лёжа, подход 1');
        await weight.focus();
        await expect(weight).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(reps).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(weight).toBeFocused();

        const strengthGeometry = await page.evaluate(() => {
          const root = document.documentElement;
          const app = document.querySelector<HTMLElement>('#appContent');
          const exercise = document
            .querySelector<HTMLElement>('[data-workout-set-id="201"]')
            ?.closest('.active-workout-exercise');
          const row = document.querySelector<HTMLElement>('[data-workout-set-id="201"]');
          const input = row?.querySelector<HTMLInputElement>('[data-workout-field="weight"]');
          const controls = row?.querySelector<HTMLElement>('.active-workout-set__controls');
          const box = (element: Element | null | undefined) =>
            element?.getBoundingClientRect().toJSON() ?? null;
          return {
            viewport: { width: window.innerWidth, height: window.innerHeight },
            scroll: { x: window.scrollX, y: window.scrollY },
            documentWidth: { client: root.clientWidth, scroll: root.scrollWidth },
            safe: {
              left: getComputedStyle(root).getPropertyValue('--yfc-layout-safe-left').trim(),
              right: getComputedStyle(root).getPropertyValue('--yfc-layout-safe-right').trim(),
            },
            visualViewport: window.visualViewport
              ? {
                  width: window.visualViewport.width,
                  height: window.visualViewport.height,
                  offsetLeft: window.visualViewport.offsetLeft,
                  offsetTop: window.visualViewport.offsetTop,
                }
              : null,
            app: box(app),
            exercise: box(exercise),
            row: box(row),
            controls: box(controls),
            weight: box(input),
            weightStyle: input
              ? {
                  boxSizing: getComputedStyle(input).boxSizing,
                  minWidth: getComputedStyle(input).minWidth,
                  width: getComputedStyle(input).width,
                  paddingInline: getComputedStyle(input).paddingInline,
                }
              : null,
            active: document.activeElement === input,
          };
        });
        await info.attach('strength-edit-geometry.json', {
          body: JSON.stringify(strengthGeometry, null, 2),
          contentType: 'application/json',
        });
        expect(strengthGeometry.weight).not.toBeNull();
        expect(strengthGeometry.exercise).not.toBeNull();
        expect(strengthGeometry.weight?.left).toBeGreaterThanOrEqual(
          (strengthGeometry.exercise?.left ?? 0) - 0.5,
        );
        expect(strengthGeometry.weight?.right).toBeLessThanOrEqual(
          (strengthGeometry.exercise?.right ?? width) + 0.5,
        );
        expect(strengthGeometry.documentWidth.scroll).toBeLessThanOrEqual(width + 1);
        expect(strengthGeometry.weightStyle?.boxSizing).toBe('border-box');

        const summaryGeometry = await page.evaluate(() =>
          Array.from(
            document.querySelectorAll<HTMLElement>(
              '.active-workout-set__helpers > summary, .active-workout-set__advanced > summary',
            ),
          )
            .map((summary) => {
              const style = getComputedStyle(summary);
              const rect = summary.getBoundingClientRect();
              return {
                text: summary.textContent?.trim() ?? '',
                rect: rect.toJSON(),
                display: style.display,
                alignItems: style.alignItems,
                minHeight: parseFloat(style.minHeight),
                paddingTop: style.paddingTop,
                paddingBottom: style.paddingBottom,
              };
            })
            .filter((summary) => summary.rect.width > 0 && summary.rect.height > 0),
        );
        expect(summaryGeometry.length).toBeGreaterThan(0);
        for (const summary of summaryGeometry) {
          expect(summary.rect.height, summary.text).toBeGreaterThanOrEqual(44);
          expect(summary.minHeight, summary.text).toBeGreaterThanOrEqual(44);
          expect(summary.display, summary.text).toBe('flex');
          expect(summary.alignItems, summary.text).toBe('center');
          expect(summary.paddingTop, summary.text).toBe('0px');
          expect(summary.paddingBottom, summary.text).toBe('0px');
        }

        for (const summary of [
          strength.locator('.active-workout-set__advanced > summary').first(),
          page
            .locator('[data-workout-set-id="202"] .active-workout-set__helpers > summary')
            .first(),
        ]) {
          await expect(summary).toBeVisible();
          await summary.scrollIntoViewIfNeeded();
          const summaryGeometry = await summary.evaluate((element) => {
            const dock = document.querySelector<HTMLElement>('#appBottomNav');
            const target = element.getBoundingClientRect();
            const dockRect = dock?.getBoundingClientRect();
            const hit = document.elementFromPoint(
              target.left + target.width / 2,
              target.top + target.height / 2,
            );
            return {
              target: target.toJSON(),
              dock: dockRect?.toJSON() ?? null,
              hit: hit === element || Boolean(hit?.closest('summary') === element),
              overlap:
                Boolean(dockRect) && target.bottom > dockRect!.top && target.top < dockRect!.bottom,
            };
          });
          expect(summaryGeometry.overlap).toBe(false);
          expect(summaryGeometry.hit).toBe(true);
        }

        const current = page.locator('[data-workout-set-id="202"]');
        const rir = current.getByRole('button', { name: /^2 —/ });
        await rir.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        const rirGeometry = await page.evaluate(() => {
          const target = document.querySelector<HTMLElement>(
            '[data-workout-set-id="202"] .active-workout-rir__options button',
          );
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          const targetBox = target?.getBoundingClientRect();
          const dockBox = dock?.getBoundingClientRect();
          const point = targetBox
            ? document.elementFromPoint(
                targetBox.left + targetBox.width / 2,
                targetBox.top + targetBox.height / 2,
              )
            : null;
          return {
            target: targetBox?.toJSON() ?? null,
            dock: dockBox?.toJSON() ?? null,
            hit: point?.closest('.active-workout-rir__options') !== null,
            overlap:
              Boolean(targetBox && dockBox) &&
              targetBox!.bottom > dockBox!.top &&
              targetBox!.top < dockBox!.bottom,
          };
        });
        await info.attach('rir-dock-geometry.json', {
          body: JSON.stringify(rirGeometry, null, 2),
          contentType: 'application/json',
        });
        expect(rirGeometry.overlap).toBe(false);
        expect(rirGeometry.hit).toBe(true);

        const finish = page.getByRole('button', { name: 'Завершить тренировку', exact: true });
        await finish.scrollIntoViewIfNeeded();
        const finishGeometry = await page.evaluate(() => {
          const target = document.querySelector<HTMLElement>(
            'button[aria-label="Завершить тренировку"], button:not([aria-label])[type="button"]',
          );
          const finishButton = [...document.querySelectorAll<HTMLElement>('button')].find(
            (button) => button.textContent?.trim() === 'Завершить тренировку',
          );
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          const targetBox = (finishButton ?? target)?.getBoundingClientRect();
          const dockBox = dock?.getBoundingClientRect();
          const point = targetBox
            ? document.elementFromPoint(
                targetBox.left + targetBox.width / 2,
                targetBox.top + targetBox.height / 2,
              )
            : null;
          return {
            target: targetBox?.toJSON() ?? null,
            dock: dockBox?.toJSON() ?? null,
            hit:
              point === finishButton ||
              Boolean(finishButton && point?.closest('button') === finishButton),
            overlap:
              Boolean(targetBox && dockBox) &&
              targetBox!.bottom > dockBox!.top &&
              targetBox!.top < dockBox!.bottom,
          };
        });
        await info.attach('finish-dock-geometry.json', {
          body: JSON.stringify(finishGeometry, null, 2),
          contentType: 'application/json',
        });
        expect(finishGeometry.overlap).toBe(false);
        expect(finishGeometry.hit).toBe(true);

        const cardio = page.locator('.active-workout-exercise').filter({ hasText: 'Велотренажёр' });
        await cardio.getByRole('button', { name: 'Открыть упражнение' }).click();
        await cardio.getByLabel('Длительность, Велотренажёр').fill('27');
        await cardio.getByLabel('Дистанция, Велотренажёр').fill('6.4');
        await cardio.getByRole('button', { name: 'Завершить кардио: Велотренажёр' }).click();
        await expect.poll(() => server.readSet(204).is_completed).toBe(true);
        await cardio.getByRole('button', { name: 'Редактировать' }).click();
        const duration = cardio.getByLabel('Длительность, Велотренажёр');
        await duration.focus();
        await expect(duration).toBeFocused();
        const cardioGeometry = await duration.evaluate((input) => {
          const row = input.closest<HTMLElement>('[data-workout-set-id]');
          const exercise = row?.closest<HTMLElement>('.active-workout-exercise');
          return {
            input: input.getBoundingClientRect().toJSON(),
            row: row?.getBoundingClientRect().toJSON() ?? null,
            exercise: exercise?.getBoundingClientRect().toJSON() ?? null,
            viewport: { width: window.innerWidth, height: window.innerHeight },
          };
        });
        await info.attach('cardio-edit-geometry.json', {
          body: JSON.stringify(cardioGeometry, null, 2),
          contentType: 'application/json',
        });
        expect(cardioGeometry.input.left).toBeGreaterThanOrEqual(
          (cardioGeometry.exercise?.left ?? 0) - 0.5,
        );
        expect(cardioGeometry.input.right).toBeLessThanOrEqual(
          (cardioGeometry.exercise?.right ?? width) + 0.5,
        );

        const pulseSummary = cardio.locator('.active-workout-set__advanced > summary');
        await expect(pulseSummary).toHaveText('Пульс (необязательно)');
        await pulseSummary.scrollIntoViewIfNeeded();
        const pulseGeometry = await pulseSummary.evaluate((element) => {
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          const target = element.getBoundingClientRect();
          const dockRect = dock?.getBoundingClientRect();
          const hit = document.elementFromPoint(
            target.left + target.width / 2,
            target.top + target.height / 2,
          );
          return {
            target: target.toJSON(),
            dock: dockRect?.toJSON() ?? null,
            hit: hit === element || Boolean(hit?.closest('summary') === element),
            overlap:
              Boolean(dockRect) && target.bottom > dockRect!.top && target.top < dockRect!.bottom,
          };
        });
        expect(pulseGeometry.overlap).toBe(false);
        expect(pulseGeometry.hit).toBe(true);
      });
    }
  }
});

test.describe('#980 completed editing keyboard and safe-area regression', () => {
  for (const width of [320, 360, 390, 393, 430]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`keeps focused completed weight usable with modeled keyboard at ${width}px ${theme}`, async ({
        page,
      }, info) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await installMockedTelegram(page);
        await page.addInitScript((selectedTheme) => {
          localStorage.setItem('app-theme', selectedTheme);
          if (window.Telegram?.WebApp) window.Telegram.WebApp.colorScheme = selectedTheme;
        }, theme);
        const server = await mockActiveWorkout(page, true);
        await page.goto('/app?tgWebAppPlatform=ios');
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

        const strength = page.locator('[data-workout-set-id="201"]');
        await strength.getByLabel(/^Вес,/).fill('42.5');
        await strength.getByLabel(/^Повторы,/).fill('9');
        await strength.getByRole('button', { name: /^Завершить:/ }).click();
        await expect.poll(() => server.readSet(201).is_completed).toBe(true);
        await page.getByRole('button', { name: 'Пропустить', exact: true }).click();
        await strength.getByRole('button', { name: 'Редактировать' }).click();

        const weight = strength.getByLabel('Вес, Жим штанги лёжа, подход 1');
        const reps = strength.getByLabel('Повторы, Жим штанги лёжа, подход 1');
        await weight.focus();
        await expect(weight).toBeFocused();
        await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
        await page.keyboard.press('Tab');
        await expect(reps).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(weight).toBeFocused();

        const geometry = await page.evaluate(() => {
          const root = document.documentElement;
          const input = document.querySelector<HTMLInputElement>(
            '[data-workout-set-id="201"] [data-workout-field="weight"]',
          );
          const exercise = input?.closest<HTMLElement>('.active-workout-exercise');
          const dock = document.querySelector<HTMLElement>('#appBottomNav');
          const inputBox = input?.getBoundingClientRect();
          const exerciseBox = exercise?.getBoundingClientRect();
          const dockBox = dock?.getBoundingClientRect();
          const style = input ? getComputedStyle(input) : null;
          const dockStyle = dock ? getComputedStyle(dock) : null;
          return {
            viewport: { width: innerWidth, height: innerHeight },
            visualViewport: window.visualViewport
              ? {
                  width: window.visualViewport.width,
                  height: window.visualViewport.height,
                  offsetTop: window.visualViewport.offsetTop,
                }
              : null,
            keyboard: root.getAttribute('data-yfc-keyboard'),
            viewportHeight: getComputedStyle(root).getPropertyValue('--yfc-viewport-height').trim(),
            safeBottom: getComputedStyle(root).getPropertyValue('--yfc-layout-safe-bottom').trim(),
            documentWidth: { client: root.clientWidth, scroll: root.scrollWidth },
            input: inputBox?.toJSON() ?? null,
            exercise: exerciseBox?.toJSON() ?? null,
            dock: dockBox?.toJSON() ?? null,
            boxSizing: style?.boxSizing ?? null,
            dockVisible: Boolean(
              dockBox &&
              dockBox.width > 0 &&
              dockBox.height > 0 &&
              dockStyle?.display !== 'none' &&
              dockStyle?.visibility !== 'hidden',
            ),
          };
        });
        await info.attach('completed-weight-keyboard-geometry.json', {
          body: JSON.stringify(geometry, null, 2),
          contentType: 'application/json',
        });
        expect(geometry.keyboard).toBe('visible');
        expect(geometry.boxSizing).toBe('border-box');
        expect(geometry.input).not.toBeNull();
        expect(geometry.exercise).not.toBeNull();
        expect(geometry.input?.left ?? 0).toBeGreaterThanOrEqual(
          (geometry.exercise?.left ?? 0) - 0.5,
        );
        expect(geometry.input?.right ?? width).toBeLessThanOrEqual(
          (geometry.exercise?.right ?? width) + 0.5,
        );
        expect(geometry.documentWidth.scroll).toBeLessThanOrEqual(width + 1);
        expect(geometry.dockVisible).toBe(false);
      });
    }
  }
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
  const weight = page.getByLabel('Вес, Жим штанги лёжа, подход 1');
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
  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
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
  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  const timer = page.getByRole('timer', { name: 'Отдых' });
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
  await expect(timer).toHaveText('0:00');
  const panel = page.locator('.active-workout-rest');
  await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
  await expect(panel).toContainText('ФАКТ');
  await expect(panel).not.toHaveClass(/is-compact/);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as typeof window & { __restNotifications: string[] }).__restNotifications.length,
      ),
    )
    .toBe(1);
});

test('rest timer reaches its final state from the deadline without user events', async ({
  page,
}) => {
  const start = new Date('2026-09-09T12:00:00Z');
  await page.clock.install({ time: start });
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();

  const timer = page.getByRole('timer', { name: 'Отдых' });
  await expect(timer).toHaveText('1:30');
  await page.clock.runFor(90_000);

  // Policy C keeps the actual rest running beyond the planned countdown.
  await expect(timer).toHaveText('0:00');
  const panel = page.locator('.active-workout-rest');
  await expect(panel).toContainText('ФАКТ');
  await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
  await panel.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
  await expect(panel).toHaveClass(/is-compact/);
  await expect(panel).toContainText('Отдых завершён по отметке');
  await panel.getByRole('button', { name: 'Скрыть' }).click();
  await expect(panel.getByRole('button', { name: 'Новый отдых' })).toBeVisible();
});

test('policy C offers manual rest recovery after fifteen minutes away past the deadline', async ({
  page,
}) => {
  const start = new Date('2026-09-09T12:00:00Z');
  await page.clock.setFixedTime(start);
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const firstSet = page.locator('[data-workout-set-id="201"]');
  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  await expect(
    page.locator('.active-workout-rest').getByRole('button', { name: 'Стоп: завершить отдых' }),
  ).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.clock.setFixedTime(new Date(start.getTime() + 17 * 60_000));
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await page.getByRole('button', { name: 'Уточнить', exact: true }).click();
  const review = page.getByRole('group', { name: 'Уточнение фактического отдыха' });
  await expect(review).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Сколько отдыхали?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Стоп: завершить отдых' })).toHaveCount(0);
  await review.getByRole('textbox', { name: 'Фактическое время, минуты' }).fill('2,5');
  await review.getByRole('button', { name: 'Сохранить время' }).click();
  await expect(page.locator('.active-workout-rest')).toContainText(
    'Отдых сохранён по вашей отметке',
  );
  const journal = await page.evaluate(() =>
    Object.keys(localStorage)
      // Per-action ':op:<id>' records are objects, not session arrays.
      .filter((key) => key.endsWith(':measured:v1'))
      .flatMap((key) => JSON.parse(localStorage.getItem(key) || '[]')),
  );
  expect(journal[0]?.source).toBe('USER_CORRECTED');
  expect(journal[0]?.pending.at(-1)?.corrected_seconds).toBe(150);
});

test.describe('#914 rest timer pointer lifecycle', () => {
  test.use({
    hasTouch: true,
    isMobile: async ({ browserName }, run) => run(browserName !== 'firefox'),
  });

  async function prepare(page: Page, width: number, theme: 'dark' | 'light', telegram = false) {
    await page.setViewportSize({ width, height: 844 });
    await page.clock.setFixedTime(new Date('2026-10-10T12:00:00Z'));
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    if (telegram) {
      await installTelegramHarness(page, {
        platform: 'ios',
        colorScheme: theme,
        viewportHeight: 844,
        viewportStableHeight: 844,
        safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
      });
    }
    await mockActiveWorkout(page);
    await page.goto(telegram ? '/app?tgWebAppPlatform=ios' : '/app');
    if (!telegram) await page.getByRole('button', { name: 'Клиент', exact: true }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const previous = page.locator('[data-workout-set-id="201"]');
    await previous.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
    await previous.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
    await Promise.all([
      waitForCompletedSetPatch(page, 201),
      previous.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click(),
    ]);
    const current = page.locator('[data-workout-set-id="202"]');
    await expect(current).toHaveAttribute('aria-current', 'step');
    await current.getByLabel('Вес, Жим штанги лёжа, подход 2').fill('42.5');
    await current.getByLabel('Повторы, Жим штанги лёжа, подход 2').fill('9');
    await current.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
    await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
    await page.clock.setFixedTime(new Date('2026-10-10T12:00:02Z'));
    const writes: Array<{ method: string; path: string; completed: unknown }> = [];
    page.on('request', (request) => {
      if (/\/workouts\/sets\//.test(request.url()) && request.method() !== 'GET') {
        writes.push({
          method: request.method(),
          path: new URL(request.url()).pathname,
          completed: request.postDataJSON()?.is_completed,
        });
      }
    });
    await page.evaluate(() => {
      const events: unknown[] = [];
      Object.assign(window, { __restPointerEvidence: events });
      for (const type of [
        'pointerdown',
        'pointerup',
        'pointercancel',
        'touchstart',
        'touchend',
        'click',
      ]) {
        document.addEventListener(
          type,
          (event) => {
            const pointer = event as PointerEvent;
            const point = (event as TouchEvent).changedTouches?.[0] ?? pointer;
            const target = event.target instanceof Element ? event.target : null;
            events.push({
              type,
              pointerType: pointer.pointerType,
              target: target?.tagName,
              set: target?.closest('[data-workout-set-id]')?.getAttribute('data-workout-set-id'),
              hit: document.elementFromPoint(point.clientX, point.clientY)?.tagName,
              path: event
                .composedPath()
                .slice(0, 5)
                .map((item) => (item as Element).tagName),
              active: document
                .querySelector('[aria-current="step"]')
                ?.getAttribute('data-workout-set-id'),
            });
          },
          true,
        );
      }
    });
    return { current, previous, writes, panel: page.locator('.active-workout-rest') };
  }

  async function alignPrevious(page: Page, skip: boolean) {
    return page.evaluate((atSkip) => {
      const panel = document.querySelector<HTMLElement>('.active-workout-rest')!;
      const button = atSkip
        ? [...panel.querySelectorAll('button')].find(
            (control) => control.textContent === 'Пропустить',
          )!
        : panel.querySelector('button')!;
      const previous = document.querySelector<HTMLElement>(
        '[data-workout-set-id="201"] [data-workout-field="done"]',
      )!;
      const control = button.getBoundingClientRect();
      const targetY = atSkip ? control.y + control.height / 2 : control.bottom + 3;
      const old = previous.getBoundingClientRect();
      window.scrollBy({ top: old.y + old.height / 2 - targetY, behavior: 'instant' });
      const finalControl = button.getBoundingClientRect();
      const previousBox = previous.getBoundingClientRect();
      const x = Math.min(finalControl.x + finalControl.width / 2, previousBox.right - 2);
      const y = atSkip ? finalControl.y + finalControl.height / 2 : finalControl.bottom + 3;
      return {
        x,
        y,
        panel: panel.getBoundingClientRect().toJSON(),
        previous: previousBox.toJSON(),
      };
    }, skip);
  }

  async function unchanged(page: Page, context: Awaited<ReturnType<typeof prepare>>) {
    await expect(context.current).toHaveAttribute('aria-current', 'step');
    await expect(
      context.previous.getByRole('button', {
        name: 'Выполнен: Жим штанги лёжа, подход 1',
      }),
    ).toBeDisabled();
    await expect(context.previous.getByRole('button', { name: 'Редактировать' })).toBeVisible();
    const actions = completedActions(context.previous);
    await expect(actions.getByRole('button', { name: 'Вернуть в работу' })).toBeVisible();
    await expect(context.current.getByLabel('Вес, Жим штанги лёжа, подход 2')).toHaveValue('42.5');
    await expect(context.current.getByLabel('Повторы, Жим штанги лёжа, подход 2')).toHaveValue('9');
    await expect(
      context.current.getByRole('button', { name: '2 — ещё примерно 2 повтора' }),
    ).toHaveAttribute('aria-pressed', 'true');
    const stored = await page.evaluate(async () => (await fetch('/api/v1/workouts/today')).json());
    const sets = stored.exercises.flatMap((exercise: { sets: SetState[] }) => exercise.sets);
    expect(sets.find((set: SetState & { id: number }) => set.id === 201)?.is_completed).toBe(true);
    expect(context.writes).toEqual([]);
  }

  for (const width of [320, 360, 393, 430]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`five-item dock preserves the workout across quick add and navigation at ${width}px ${theme}`, async ({
        page,
      }, testInfo) => {
        const pageErrors: string[] = [];
        page.on('pageerror', (error) => pageErrors.push(error.message));
        const context = await prepare(page, width, theme);
        const mutations: string[] = [];
        page.on('request', (request) => {
          const route = new URL(request.url()).pathname;
          // Timer journaling may legitimately POST /rest-sessions on navigation.
          // This regression specifically forbids rewriting completed workout sets.
          if (/\/workouts\/sets\/\d+/.test(route) && request.method() !== 'GET') {
            mutations.push(`${request.method()} ${new URL(request.url()).pathname}`);
          }
        });
        const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
        const add = navigation.getByRole('button', { name: 'Быстро добавить', exact: true });
        await expect(
          navigation.locator('.app-bottom-nav__primary > a, .app-bottom-nav__primary > button'),
        ).toHaveText(['Сегодня', 'План', 'Питание', 'Прогресс', 'Добавить']);
        await expect(add).toBeVisible();
        await context.panel.getByRole('button', { name: '+30 сек' }).tap();
        await expect(context.panel.getByRole('timer')).toHaveText('1:58');
        await add.tap();
        const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
        await expect(sheet.getByRole('link')).toHaveCount(5);
        await sheet.getByRole('button', { name: 'Закрыть быстрые действия' }).tap();
        await expect(add).toBeFocused();
        await unchanged(page, context);
        await expectSelectedChoice(
          context.current.getByRole('button', { name: '2 — ещё примерно 2 повтора' }),
        );
        await expect(context.current).not.toHaveAttribute('data-yfc-choice');
        await page.screenshot({
          path: testInfo.outputPath(`navigation-workout-${width}-${theme}.png`),
        });
        await context.current
          .getByRole('button', { name: '2 — ещё примерно 2 повтора' })
          .scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath(`selection-rir-${width}-${theme}.png`) });
        await settleViewport(page);

        const nutritionLink = navigation.getByRole('link', { name: 'Питание', exact: true });
        const materialGeometry = await nutritionLink.evaluate((link) => {
          const dock = link.closest<HTMLElement>('#appBottomNav')!;
          const cta = document.querySelector<HTMLElement>(
            '[data-workout-set-id="202"] [data-workout-field="done"]',
          )!;
          const control = link.getBoundingClientRect();
          const targetY = control.y + control.height / 2;
          const old = cta.getBoundingClientRect();
          const scrollBefore = window.scrollY;
          window.scrollBy({ top: old.y + old.height / 2 - targetY, behavior: 'instant' });
          const style = getComputedStyle(dock);
          return {
            cta: cta.getBoundingClientRect().toJSON(),
            targetY,
            targetIsNavigation: dock.contains(
              document.elementFromPoint(control.x + control.width / 2, targetY),
            ),
            scrollBefore,
            scrollAfter: window.scrollY,
            background: style.backgroundColor,
            blur: style.backdropFilter,
            opacity: style.opacity,
          };
        });
        expect(materialGeometry.cta.top).toBeLessThan(materialGeometry.targetY);
        expect(materialGeometry.cta.bottom).toBeGreaterThan(materialGeometry.targetY);
        expect(materialGeometry.targetIsNavigation).toBe(true);
        await expect(context.panel).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath(`dock-over-cta-${width}-${theme}.png`) });
        await testInfo.attach('dock-over-cta.json', {
          body: JSON.stringify(materialGeometry),
          contentType: 'application/json',
        });
        await settleViewport(page);
        await expect
          .poll(() =>
            nutritionLink.evaluate((link) => {
              const rect = link.getBoundingClientRect();
              return link.contains(
                document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2),
              );
            }),
          )
          .toBe(true);
        await nutritionLink.tap();
        await expect(page).toHaveURL(/section=nutrition/);
        await expect(page.locator('.app-section--nutrition')).toBeVisible();
        await expect(
          navigation.getByRole('link', { name: 'Питание', exact: true }),
        ).toHaveAttribute('aria-current', 'page');
        await navigation.getByRole('link', { name: 'Сегодня', exact: true }).tap();
        const resume = page.getByRole('button', { name: 'Продолжить тренировку', exact: true });
        await expect(resume.or(context.current)).toBeVisible();
        if (await resume.isVisible()) await resume.tap();
        await expect(context.panel.getByRole('timer')).toHaveText('1:58');
        await unchanged(page, context);
        expect(mutations).toEqual([]);
        expect(pageErrors).toEqual([]);
        await testInfo.attach('navigation-mutations.json', {
          body: JSON.stringify({
            mutations,
            pageErrors,
            currentSet: 202,
            weight: 42.5,
            reps: 9,
            rir: 2,
            rest: '1:58',
          }),
          contentType: 'application/json',
        });
      });

      test(`painted padding blocks the 202→201 PATCH regression at ${width}px ${theme}`, async ({
        page,
      }, testInfo) => {
        const context = await prepare(page, width, theme);
        const point = await alignPrevious(page, false);
        expect(point.y).toBeLessThan(point.panel.bottom);
        expect(point.y).toBeGreaterThan(point.previous.top);
        expect(point.y).toBeLessThan(point.previous.bottom);
        await page.touchscreen.tap(point.x, point.y);
        await page.touchscreen.tap(point.x, point.y);
        await unchanged(page, context);
        await testInfo.attach('hit-testing.json', {
          body: JSON.stringify({
            point,
            writes: context.writes,
            events: await page.evaluate(
              () =>
                (window as typeof window & { __restPointerEvidence: unknown[] })
                  .__restPointerEvidence,
            ),
          }),
          contentType: 'application/json',
        });
      });

      test(`actions and skip preserve the current set at ${width}px ${theme}`, async ({
        page,
      }, testInfo) => {
        const context = await prepare(page, width, theme);
        await page.evaluate(() => {
          const row = document.querySelector('[data-workout-set-id="202"]')!;
          const panel = document.querySelector('.active-workout-rest')!;
          row.scrollIntoView({ block: 'start', behavior: 'instant' });
          window.scrollBy({ top: -panel.getBoundingClientRect().height - 16, behavior: 'instant' });
        });
        const field = context.current.getByLabel('Повторы, Жим штанги лёжа, подход 2');
        await field.evaluate((element) => (element as HTMLElement).focus({ preventScroll: true }));
        const beforeScroll = await page.evaluate(() => scrollY);
        await page.screenshot({ path: testInfo.outputPath('timer.png') });
        const deadline = () =>
          page.evaluate(
            (key) => JSON.parse(localStorage.getItem(key)!),
            activeWorkoutRestStorageKey(7, 42),
          );
        let expectedDeadline = await deadline();
        expect(expectedDeadline).toEqual(expect.any(Number));
        for (const extra of [30, 60]) {
          const button = context.panel.getByRole('button', { name: `+${extra} сек` });
          const box = (await button.boundingBox())!;
          expect(box.width).toBeGreaterThanOrEqual(44);
          expect(box.height).toBeGreaterThanOrEqual(44);
          const points: Array<[number, number]> = [
            [box.x + box.width / 2, box.y + box.height / 2],
            [box.x + 2, box.y + box.height / 2],
            [box.x + box.width - 2, box.y + box.height / 2],
            [box.x + box.width / 2, box.y + 2],
            [box.x + box.width / 2, box.y + box.height - 2],
          ];
          for (const [x, y] of points) {
            expect(
              await button.evaluate(
                (element, point) => element.contains(document.elementFromPoint(point.x, point.y)),
                { x, y },
              ),
            ).toBe(true);
            await page.touchscreen.tap(x, y);
            expectedDeadline += extra * 1000;
            expect(await deadline()).toBe(expectedDeadline);
          }
          await expect(field).toBeFocused();
          expect(await page.evaluate(() => scrollY)).toBe(beforeScroll);
          await unchanged(page, context);
          await page.screenshot({ path: testInfo.outputPath(`plus${extra}.png`) });
        }
        const point = await alignPrevious(page, true);
        const currentBeforeSkip = (await context.current.boundingBox())!;
        const skipScroll = await page.evaluate(() => scrollY);
        await page.clock.setFixedTime(new Date('2026-10-10T12:00:12Z'));
        await page.touchscreen.tap(point.x, point.y);
        await expect(field).toBeFocused();
        await unchanged(page, context);
        await expect(context.panel).toHaveClass(/is-compact/);
        await expect(context.panel).toContainText('Отдых пропущен · Подход 2 из 3');
        await expect(context.panel.getByRole('button', { name: 'Скрыть' })).toBeVisible();
        const currentAfterSkip = (await context.current.boundingBox())!;
        expect(Math.abs(currentAfterSkip.y - currentBeforeSkip.y)).toBeLessThan(1);
        await unchanged(page, context);
        await page.screenshot({ path: testInfo.outputPath('skip.png') });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
          true,
        );
        await testInfo.attach('timer-mutations.json', {
          body: JSON.stringify({
            writes: context.writes,
            active: 202,
            previousCompleted: true,
            weight: 42.5,
            reps: 9,
            rir: '2',
            expectedDeadline,
            beforeScroll,
            skipScroll,
            events: await page.evaluate(
              () =>
                (window as typeof window & { __restPointerEvidence: unknown[] })
                  .__restPointerEvidence,
            ),
          }),
          contentType: 'application/json',
        });
      });
    }
  }

  for (const width of [320, 393]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`TMA resume offline and keyboard retain the set at ${width}px ${theme}`, async ({
        page,
      }, testInfo) => {
        const context = await prepare(page, width, theme, true);
        const telegram = new TelegramHarness(page);
        await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
        await setDocumentVisibility(page, 'hidden');
        await telegram.setActive(false);
        await page.clock.setFixedTime(new Date('2026-10-10T12:01:07Z'));
        await setDocumentVisibility(page, 'visible');
        await telegram.setActive(true);
        await expect(context.panel.getByRole('timer')).toHaveText('0:23');
        await setNetworkOffline(page, true);
        const add60 = context.panel.getByRole('button', { name: '+60 сек' });
        await add60.scrollIntoViewIfNeeded();
        await add60.tap();
        await expect(context.panel.getByRole('timer')).toHaveText('1:23');
        await page.setViewportSize({ width, height: 480 });
        await telegram.setViewport(480, 844);
        const field = context.current.getByLabel('Вес, Жим штанги лёжа, подход 2');
        await field.evaluate((element) => {
          element.closest('label')!.scrollIntoView({ block: 'center', behavior: 'instant' });
          (element as HTMLElement).focus({ preventScroll: true });
        });
        const panelBox = (await context.panel.boundingBox())!;
        const fieldBox = (await field.boundingBox())!;
        expect(panelBox.y).toBeGreaterThanOrEqual(24);
        expect(fieldBox.y).toBeGreaterThanOrEqual(panelBox.y + panelBox.height);
        expect(fieldBox.y + fieldBox.height).toBeLessThanOrEqual(480 - 34);
        await expect(field).toBeFocused();
        await page.screenshot({ path: testInfo.outputPath('tma-keyboard.png') });
        await setNetworkOffline(page, false);
        await page.setViewportSize({ width, height: 844 });
        await telegram.setViewport(844, 844);
        await unchanged(page, context);
        await testInfo.attach('lifecycle-mutations.json', {
          body: JSON.stringify({
            writes: context.writes,
            backgroundSeconds: 65,
            offlineAdded: 60,
            remaining: '1:23',
            input: 'Browser touch and modeled Telegram/keyboard, not a physical iPhone',
          }),
          contentType: 'application/json',
        });
      });

      test(`Web reload restores the scoped timer and current set at ${width}px ${theme}`, async ({
        page,
      }) => {
        const context = await prepare(page, width, theme);
        await context.panel.getByRole('button', { name: '+60 сек' }).tap();
        await expect(context.panel.getByRole('timer')).toHaveText('2:28');
        await page.reload({ waitUntil: 'domcontentloaded' });
        const resume = page.getByRole('button', { name: 'Продолжить тренировку' });
        await Promise.race([
          resume.waitFor({ state: 'visible' }),
          context.current.waitFor({ state: 'visible' }),
        ]);
        if (await resume.isVisible()) await resume.click();
        await expect(context.panel.getByRole('timer')).toHaveText('2:28');
        await unchanged(page, context);
      });
    }
  }

  test('rapid skip alone blocks the 202→201 PATCH regression after the panel closes', async ({
    page,
  }, testInfo) => {
    const context = await prepare(page, 393, 'dark');
    const point = await alignPrevious(page, true);
    await page.touchscreen.tap(point.x, point.y);
    await page.touchscreen.tap(point.x, point.y);
    await page.clock.setFixedTime(new Date('2026-10-10T12:00:12Z'));
    await page.touchscreen.tap(point.x, point.y);
    await testInfo.attach('skip-alone-mutations.json', {
      body: JSON.stringify({ writes: context.writes, point }),
      contentType: 'application/json',
    });
    await expect(context.panel).toHaveClass(/is-compact/);
    await unchanged(page, context);
    // After rapid repeated taps, the terminal "Скрыть" action may already have
    // been hit at the former Skip coordinates. Both terminal states must retain
    // the explicit restart action without starting another interval.
    const restart = context.panel.getByRole('button', { name: 'Новый отдых' });
    await expect(restart).toBeVisible();
    const dismiss = context.panel.getByRole('button', { name: 'Скрыть' });
    if (await dismiss.isVisible()) await dismiss.click();
    await expect(restart).toBeVisible();
    const journal = await page.evaluate(() =>
      Object.keys(localStorage)
        .filter((key) => key.endsWith(':measured:v1'))
        .flatMap((key) => JSON.parse(localStorage.getItem(key) || '[]')),
    );
    expect(journal).toHaveLength(1);
    expect(journal[0]?.status).toBe('skipped');
    await unchanged(page, context);
  });

  test('pressed skip completes only after pointer release, including after plan expiry', async ({
    page,
  }) => {
    const context = await prepare(page, 360, 'dark');
    const point = await alignPrevious(page, true);
    await page.mouse.move(point.x, point.y);
    await page.mouse.down();
    await page.clock.setFixedTime(new Date('2026-10-10T12:01:40Z'));
    await page.evaluate(() => window.dispatchEvent(new Event('pageshow')));
    await expect(context.panel.getByRole('timer')).toHaveText('0:00');
    await page.mouse.up();
    // Under Policy C the plan ending does not complete the rest. Releasing an
    // already pressed Skip is an explicit user action, so it must be honored.
    await expect(context.panel).toHaveClass(/is-compact/);
    await expect(context.panel).toContainText('Отдых пропущен');
    await expect(context.panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toHaveCount(
      0,
    );
    await unchanged(page, context);
  });
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

  await firstSet.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
  await firstSet.getByRole('spinbutton', { name: 'Повторы, Жим штанги лёжа, подход 1' }).fill('8');
  await firstSet.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-light-rest.png`, fullPage: true });

  const secondSet = page.locator('[data-workout-set-id="202"]');
  await secondSet.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }).click();
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
    .getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' })
    .click();
  const remainingThirdSet = page.locator('[data-workout-set-id="203"]');
  const skipSecondRest = page.getByRole('button', { name: 'Пропустить' });
  if (await skipSecondRest.isVisible()) await skipSecondRest.click();
  await remainingThirdSet
    .getByRole('button', { name: 'Подставить предыдущий подход сегодня' })
    .click();
  await remainingThirdSet
    .getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 3' })
    .click();
  await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await page.screenshot({ path: `${packagePath}/mobile-light-completed.png`, fullPage: true });
});

for (const theme of ['light', 'dark'] as const) {
  for (const width of [320, 393, 430]) {
    test(`issue960-visual ${theme} ${width}px actual rest and recovery`, async ({ page }) => {
      test.skip(process.env.YFC_CAPTURE_960_AFTER !== '1', 'Run only for owner visual evidence');
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const started = new Date('2026-10-17T12:00:00Z');
      await page.clock.setFixedTime(started);
      await mockActiveWorkout(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const set = page.locator('[data-workout-set-id="201"]');
      await set.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
      await set.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
      await set.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
      const rest = page.locator('.active-workout-rest');
      await expect(rest.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
      await expect(rest).toContainText('ФАКТ');
      const folder = resolve(
        process.cwd(),
        '..',
        'docs',
        'ux',
        'issue-960-implementation',
        'visuals',
      );
      await mkdir(folder, { recursive: true });
      await page.screenshot({
        path: resolve(folder, `after-${theme}-${width}-actual.png`),
        animations: 'disabled',
      });
      await page.evaluate(() => {
        Object.defineProperty(document, 'visibilityState', {
          configurable: true,
          get: () => 'hidden',
        });
        document.dispatchEvent(new Event('visibilitychange'));
      });
      await page.clock.setFixedTime(new Date(started.getTime() + 17 * 60_000));
      await page.evaluate(() => {
        Object.defineProperty(document, 'visibilityState', {
          configurable: true,
          get: () => 'visible',
        });
        document.dispatchEvent(new Event('visibilitychange'));
      });
      await rest.getByRole('button', { name: 'Уточнить', exact: true }).click();
      const review = page.getByRole('group', { name: 'Уточнение фактического отдыха' });
      await expect(review).toBeVisible();
      await expect(page.getByRole('dialog', { name: 'Сколько отдыхали?' })).toBeVisible();
      await page.screenshot({
        path: resolve(folder, `after-${theme}-${width}-recovery.png`),
        animations: 'disabled',
      });
    });
  }
}

async function mockRestSessions(page: Page) {
  const intervals: Record<number, Record<string, unknown>> = {};
  let nextId = 900;
  let restartRequests = 0;
  let actionFailure: number | null = null;
  let actionBarrier: Promise<void> | null = null;
  await page.route('**/api/v1/workouts/42/rest-sessions', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await route.fulfill({ json: Object.values(intervals) });
      return;
    }
    const payload = request.postDataJSON();
    const id = nextId++;
    intervals[id] = {
      id,
      workout_id: 42,
      source_set_id: payload.source_set_id,
      started_at: payload.started_at,
      ended_at: null,
      planned_seconds: 90,
      adjusted_seconds: 90,
      measured_seconds: null,
      status: 'running',
      source: null,
      quality: 'normal',
      version: 1,
      start_mutation_id: payload.mutation_id,
    };
    await route.fulfill({ json: intervals[id] });
  });
  await page.route('**/api/v1/workouts/rest-sessions/*/actions', async (route) => {
    if (actionBarrier) await actionBarrier;
    if (actionFailure) {
      await route.fulfill({
        status: actionFailure,
        json: { detail: 'Controlled rest save failure' },
      });
      return;
    }
    const id = Number(new URL(route.request().url()).pathname.split('/').at(-2));
    const interval = intervals[id];
    const payload = route.request().postDataJSON();
    if (!interval) {
      await route.fulfill({ status: 404, json: { detail: 'Not found' } });
      return;
    }
    interval.version = Number(interval.version) + 1;
    if (payload.action === 'complete') {
      interval.status = 'completed';
      interval.ended_at = payload.ended_at;
      interval.measured_seconds = Math.max(
        0,
        payload.corrected_seconds ??
          Math.floor(
            (Date.parse(payload.ended_at) - Date.parse(String(interval.started_at))) / 1000,
          ),
      );
      interval.source = payload.corrected ? 'USER_CORRECTED' : 'USER_CONFIRMED';
    } else if (payload.action === 'skip') {
      interval.status = 'skipped';
      interval.ended_at = payload.occurred_at;
    } else {
      interval.adjusted_seconds =
        Number(interval.adjusted_seconds) + (payload.action === 'add30' ? 30 : 60);
    }
    await route.fulfill({ json: interval });
  });
  await page.route('**/api/v1/workouts/rest-sessions/*/restart', async (route) => {
    restartRequests += 1;
    const oldId = Number(new URL(route.request().url()).pathname.split('/').at(-2));
    const previous = intervals[oldId];
    if (!previous) {
      await route.fulfill({ status: 404, json: { detail: 'Not found' } });
      return;
    }
    const payload = route.request().postDataJSON();
    const id = nextId++;
    intervals[id] = {
      ...previous,
      id,
      started_at: payload.started_at,
      ended_at: null,
      adjusted_seconds: previous.planned_seconds,
      measured_seconds: null,
      status: 'running',
      source: null,
      version: 1,
      start_mutation_id: payload.mutation_id,
    };
    await route.fulfill({ json: intervals[id] });
  });
  return {
    intervals,
    restartCount: () => restartRequests,
    failActions(status: number | null) {
      actionFailure = status;
    },
    holdNextAction() {
      let release!: () => void;
      actionBarrier = new Promise<void>((resolve) => {
        release = resolve;
      });
      return () => {
        actionBarrier = null;
        release();
      };
    },
  };
}

for (const theme1166 of ['dark', 'light'] as const) {
  for (const width1166 of [320, 360, 393, 430, 1440]) {
    test(`issue1166 real AFTER ${theme1166} ${width1166}`, async ({ page }) => {
      await page.setViewportSize({ width: width1166, height: width1166 === 1440 ? 1000 : 844 });
      await page.emulateMedia({ colorScheme: theme1166, reducedMotion: 'reduce' });
      await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), theme1166);
      const server = await mockActiveWorkout(page);
      await mockRestSessions(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const current = page.locator('[data-workout-set-id="201"]');
      await current.getByLabel(/^Вес,/).fill('40');
      await current.getByLabel(/^Повторы,/).fill('8');
      await current.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(() => server.readSet(201).is_completed).toBe(true);
      const out = resolve(
        process.cwd(),
        '..',
        '.artifacts',
        'runtime',
        'tests',
        'playwright',
        'redesign-visual-1166',
      );
      await mkdir(out, { recursive: true });
      const shot = async (name: string) => {
        await page.screenshot({
          path: resolve(out, `${theme1166}-${width1166}-${name}.png`),
          animations: 'disabled',
        });
      };
      await expect(page.getByRole('button', { name: 'Свернуть таймер' })).toBeVisible();
      await shot('01-running');
      await page.getByRole('button', { name: 'Свернуть таймер' }).click();
      await expect(page.getByRole('button', { name: 'Развернуть таймер' })).toBeVisible();
      await shot('02-hidden');
      await page.getByRole('button', { name: 'Развернуть таймер' }).click();
      await shot('03-reopened');
      await page.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
      await expect(page.getByRole('button', { name: 'Новый отдых' })).toBeVisible();
      await shot('04-stopped');
      await page.getByRole('button', { name: 'Новый отдых' }).click();
      await expect(page.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
      await shot('05-restarted');
      expect(server.readSet(201).is_completed).toBe(true);
    });
  }
}
for (const theme of ['light', 'dark'] as const) {
  test(`Issue #1132 shows four corresponding sets and preserves the timer in ${theme}`, async ({
    page,
  }, info) => {
    test.slow();
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    server.addFourthSet();
    await mockRestSessions(page);
    Object.assign(server.readSet(201), { actual_weight: 40, actual_reps: 8, is_completed: true });
    await mockSetHistory(page, server);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const second = page.locator('[data-workout-set-id="202"]');
    await second.getByLabel('Вес, Жим штанги лёжа, подход 2').fill('45');
    await second.getByLabel('Повторы, Жим штанги лёжа, подход 2').fill('8');
    await second.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click();
    await expect(page.getByRole('complementary', { name: 'Отдых между подходами' })).toBeVisible();
    const third = page.locator('[data-workout-set-id="203"]');
    await expect(third).toHaveAttribute('aria-current', 'step');
    await expect(third.getByRole('group', { name: 'История подхода 3' })).toBeVisible();
    for (const [id, value] of [
      [201, 160],
      [202, 180],
      [203, 200],
      [301, 190],
    ]) {
      await expect(
        page.locator(`[data-workout-set-id="${id}"] .active-workout-set__history`),
      ).toContainText(`${value} кг × 8`);
    }
    await expect(third.locator('.active-workout-set__history')).toContainText('45 кг × 8');
    await expect(third.locator('.active-workout-set__history')).toContainText(
      'тип недели может отличаться',
    );
    for (const width of [320, 360, 393, 430, 1440]) {
      await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
      const layout = await third.evaluate((row) => {
        const history = row.querySelector('.active-workout-set__history')!.getBoundingClientRect();
        const controls = row
          .querySelector('.active-workout-set__controls')!
          .getBoundingClientRect();
        const buttons = [
          ...row.querySelectorAll<HTMLButtonElement>('.active-workout-set__prefill-actions button'),
        ].map((button) => button.getBoundingClientRect());
        return { history, controls, buttons, scrollWidth: document.documentElement.scrollWidth };
      });
      expect(layout.history.bottom).toBeLessThanOrEqual(layout.controls.top + 1);
      expect(layout.buttons).toHaveLength(2);
      expect(layout.buttons[0]!.bottom).toBeLessThanOrEqual(layout.buttons[1]!.top + 1);
      expect(layout.buttons.every((button) => button.height >= 44)).toBe(true);
      expect(layout.buttons.every((button) => button.height <= 60)).toBe(true);
      expect(layout.scrollWidth).toBeLessThanOrEqual(width + 1);
      for (const action of await third
        .locator('.active-workout-set__prefill-actions button')
        .all()) {
        await action.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        expect(
          await action.evaluate((element) => {
            const box = element.getBoundingClientRect();
            const hit = document.elementFromPoint(
              box.left + box.width / 2,
              box.top + box.height / 2,
            );
            return hit === element || element.contains(hit);
          }),
        ).toBe(true);
      }
      if (
        (process.env.YFC_1132_CAPTURE === '1' && info.project.name === 'chromium') ||
        (process.env.YFC_1132_WEBKIT_CAPTURE === '1' &&
          info.project.name === 'webkit' &&
          width === 393)
      ) {
        const directory = resolve(
          process.cwd(),
          '..',
          'docs',
          'ux-proposals',
          'issue-1132-v12',
          'after',
        );
        const prefix = info.project.name === 'webkit' ? 'webkit-' : '';
        await mkdir(directory, { recursive: true });
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
        await page.screenshot({
          path: resolve(directory, `${prefix}${theme}-${width}-four-sets.png`),
          fullPage: true,
          scale: 'css',
          animations: 'disabled',
        });
        if (width === 393) {
          await third.evaluate((element) => {
            window.scrollBy({
              top: element.getBoundingClientRect().top - 120,
              behavior: 'instant',
            });
          });
          await page.screenshot({
            path: resolve(directory, `${prefix}${theme}-393-active-viewport.png`),
            animations: 'disabled',
          });
        }
      }
    }
    const past = third.getByRole('button', { name: 'Подставить из прошлой тренировки' });
    await expect(past).toBeEnabled();
    const today = third.getByRole('button', { name: 'Подставить предыдущий подход сегодня' });
    await third.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 3' }).focus();
    await page.keyboard.press('Tab');
    await expect(today).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(past).toBeFocused();
    await third.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).click();
    await third.getByText('Дополнительно', { exact: true }).click();
    await third.getByLabel('Подход до отказа').check();
    await past.click();
    await expect(third.getByLabel('Вес, Жим штанги лёжа, подход 3')).toHaveValue('200');
    await expect(third.getByLabel('Повторы, Жим штанги лёжа, подход 3')).toHaveValue('8');
    await expect.poll(() => server.readSet(203).actual_weight).toBe(200);
    expect(server.readSet(203)).toMatchObject({
      actual_reps: 8,
      rir: '2',
      reached_failure: true,
      is_completed: false,
    });
  });

  test(`Issue #1132 keeps empty history and the first set usable in ${theme}`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    const history = await mockSetHistory(page, server);
    history.withoutHistory();
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const first = page.locator('[data-workout-set-id="201"]');
    await expect(first.locator('.active-workout-set__history')).toContainText(
      'Нет прошлого результата',
    );
    await expect(first.locator('.active-workout-set__history')).toContainText(
      'Нет завершённого подхода',
    );
    await expect(
      first.getByRole('button', { name: 'Подставить из прошлой тренировки' }),
    ).toBeDisabled();
    if (process.env.YFC_1132_CAPTURE === '1' && info.project.name === 'chromium') {
      const directory = resolve(
        process.cwd(),
        '..',
        'docs',
        'ux-proposals',
        'issue-1132-v12',
        'after',
      );
      await mkdir(directory, { recursive: true });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.screenshot({
        path: resolve(directory, `${theme}-393-no-history.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.screenshot({
        path: resolve(directory, `${theme}-1440-no-history.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await page.setViewportSize({ width: 393, height: 844 });
    }
    const input = first.getByLabel('Вес, Жим штанги лёжа, подход 1');
    await input.focus();
    await page.setViewportSize({ width: 393, height: 480 });
    await input.evaluate((element) =>
      element.scrollIntoView({ block: 'center', behavior: 'instant' }),
    );
    await expect(input).toBeFocused();
    expect(
      await input.evaluate((element) => {
        const box = element.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return box.top >= 0 && box.bottom <= window.innerHeight && hit === element;
      }),
    ).toBe(true);
    if (process.env.YFC_1132_KEYBOARD_CAPTURE === '1') {
      const prefix = info.project.name === 'webkit' ? 'webkit-' : '';
      await page.screenshot({
        path: resolve(
          process.cwd(),
          '..',
          'docs',
          'ux-proposals',
          'issue-1132-v12',
          'after',
          `${prefix}${theme}-393-keyboard-model.png`,
        ),
        animations: 'disabled',
      });
    }
  });

  test(`Issue #1132 allows the first set to use only its matching past result in ${theme}`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    await mockSetHistory(page, server);
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    const first = page.locator('[data-workout-set-id="201"]');
    const past = first.getByRole('button', { name: 'Подставить из прошлой тренировки' });
    await expect(past).toBeEnabled();
    await expect(
      first.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }),
    ).toBeDisabled();
    await expect(first.locator('.active-workout-set__history')).toContainText('160 кг × 8');
    if (process.env.YFC_1132_CAPTURE === '1' && info.project.name === 'chromium') {
      const directory = resolve(
        process.cwd(),
        '..',
        'docs',
        'ux-proposals',
        'issue-1132-v12',
        'after',
      );
      await mkdir(directory, { recursive: true });
      await first.evaluate((element) =>
        window.scrollBy({ top: element.getBoundingClientRect().top - 25, behavior: 'instant' }),
      );
      await page.screenshot({
        path: resolve(directory, `${theme}-393-first-viewport.png`),
        animations: 'disabled',
      });
    }
    await past.click();
    await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('160');
    await expect.poll(() => server.readSet(201).actual_weight).toBe(160);
    expect(server.readSet(201).is_completed).toBe(false);
  });
}

test('Issue #1132 preserves history and explicit prefill in mocked Telegram Mini App', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await installTelegramHarness(page, {
    platform: 'ios',
    colorScheme: 'dark',
    safeAreaInset: { top: 20, right: 0, bottom: 16, left: 0 },
    contentSafeAreaInset: { top: 8, right: 0, bottom: 0, left: 0 },
  });
  const server = await mockActiveWorkout(page);
  await mockSetHistory(page, server);
  await page.goto('/app?tgWebAppPlatform=ios');
  await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  const past = first.getByRole('button', { name: 'Подставить из прошлой тренировки' });
  await expect(past).toBeEnabled();
  await expect(first.getByRole('group', { name: 'История подхода 1' })).toContainText('160 кг × 8');
  if (process.env.YFC_1132_CAPTURE === '1' && info.project.name === 'chromium') {
    const directory = resolve(
      process.cwd(),
      '..',
      'docs',
      'ux-proposals',
      'issue-1132-v12',
      'after',
    );
    await mkdir(directory, { recursive: true });
    await first.evaluate((element) =>
      window.scrollBy({ top: element.getBoundingClientRect().top - 10, behavior: 'instant' }),
    );
    await page.screenshot({
      path: resolve(directory, 'tma-mocked-dark-393-first.png'),
      animations: 'disabled',
    });
  }
  await past.click();
  await expect.poll(() => server.readSet(201).actual_weight).toBe(160);
  expect(server.readSet(201)).toMatchObject({ actual_reps: 8, is_completed: false });
});

test('Issue #1132 hides stale history offline and reloads it after reconnect', async ({ page }) => {
  const server = await mockActiveWorkout(page);
  const history = await mockSetHistory(page, server);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  const button = first.getByRole('button', { name: 'Подставить из прошлой тренировки' });
  await expect(button).toBeEnabled();
  await expect(first.locator('.active-workout-set__history')).toContainText('160 кг × 8');
  await setNetworkOffline(page, true);
  await expect(first.locator('.active-workout-set__history')).toContainText(
    'История недоступна без сети',
  );
  await expect(button).toBeDisabled();
  history.withoutHistory();
  const beforeReconnect = history.requests();
  await setNetworkOffline(page, false);
  await expect.poll(() => history.requests()).toBeGreaterThan(beforeReconnect);
  await expect(first.locator('.active-workout-set__history')).toContainText(
    'Нет прошлого результата',
  );
  await expect(button).toBeDisabled();
  await expect(first.getByLabel('Вес, Жим штанги лёжа, подход 1')).toHaveValue('');
});

test('Issue #1132 hides history during pending writes and reloads after a version conflict', async ({
  page,
}) => {
  const server = await mockActiveWorkout(page);
  await mockSetHistory(page, server);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const first = page.locator('[data-workout-set-id="201"]');
  const history = first.locator('.active-workout-set__history');
  const button = first.getByRole('button', { name: 'Подставить из прошлой тренировки' });
  await expect(button).toBeEnabled();
  const release = server.holdNextPatch();
  server.readSet(201).version += 1;
  const weight = first.getByLabel('Вес, Жим штанги лёжа, подход 1');
  await weight.fill('35');
  try {
    await expect.poll(() => server.patches.length).toBeGreaterThan(0);
    await expect(history).toContainText('Обновляем историю');
    await expect(button).toBeDisabled();
  } finally {
    release();
  }
  await expect.poll(() => server.patches.some((patch) => patch.status === 409)).toBe(true);
  await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
  await expect(button).toBeEnabled();
  await expect(weight).toHaveValue('35');
  await expect(first.getByLabel('Повторы, Жим штанги лёжа, подход 1')).toHaveValue('');
  expect(server.readSet(201).is_completed).toBe(false);
});

for (const theme of ['light', 'dark'] as const) {
  test(`Issue #1293 keeps active set order and helpers usable in ${theme}`, async ({
    page,
  }, testInfo) => {
    test.slow();
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const server = await mockActiveWorkout(page);
    Object.assign(server.readSet(201), { actual_weight: 40, actual_reps: 8, is_completed: true });
    await page.goto('/app');
    await page.getByRole('button', { name: 'Клиент' }).click();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();

    const row = page.locator('[data-workout-set-id="202"]');
    await expect(row).toHaveAttribute('aria-current', 'step');
    const weight = row.getByLabel('Вес, Жим штанги лёжа, подход 2');
    const reps = row.getByLabel('Повторы, Жим штанги лёжа, подход 2');
    const done = row.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' });
    const prefill = row.getByRole('button', { name: 'Подставить предыдущий подход сегодня' });
    const past = row.getByRole('button', { name: 'Подставить из прошлой тренировки' });
    const help = row.getByText('Что такое RIR?', { exact: true });
    const helpers = row.getByText('Разминка и блины', { exact: true });
    const advanced = row.getByText('Дополнительно', { exact: true });
    await expect(prefill).toBeVisible();
    await expect(past).toBeVisible();
    await expect(past).toBeDisabled();

    const order = await row.evaluate((element) => {
      const selectors = [
        '.active-workout-set__history',
        '.active-workout-set__context',
        '[data-workout-field="weight"]',
        '[data-workout-field="reps"]',
        '.active-workout-set__rir-row button',
        '[data-workout-field="done"]',
        '.active-workout-set__prefill-actions button:first-child',
        '.active-workout-set__prefill-actions button:last-child',
        '.active-workout-set__contextual-help summary',
        '.active-workout-set__helpers > summary',
        '.active-workout-set__advanced > summary',
      ];
      const nodes = selectors.map((selector) => element.querySelector(selector));
      if (nodes.some((node) => !node)) throw new Error('Active set element missing');
      return nodes
        .slice(0, -1)
        .every((node, index) =>
          Boolean(
            node!.compareDocumentPosition(nodes[index + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING,
          ),
        );
    });
    expect(order).toBe(true);

    const capture = async (state: string) => {
      if (process.env.YFC_1293_CAPTURE !== '1' || testInfo.project.name !== 'chromium') return;
      const directory = resolve(
        process.cwd(),
        '..',
        '.artifacts',
        'tasks',
        '1293',
        'evidence',
        'after',
      );
      await mkdir(directory, { recursive: true });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
      await page.screenshot({
        path: resolve(directory, `${theme}-${page.viewportSize()!.width}-${state}.png`),
        fullPage: true,
      });
    };

    for (const width of [320, 360, 393, 430]) {
      await page.setViewportSize({ width, height: 844 });
      const geometry = await row.evaluate((element) => {
        const selectors = [
          '.active-workout-set__history',
          '.active-workout-set__context',
          '.active-workout-set__controls',
          '.active-workout-set__prefill-actions',
          '.active-workout-set__contextual-help',
          '.active-workout-set__helpers',
          '.active-workout-set__advanced',
        ];
        const regions = selectors.map((selector) => element.querySelector(selector));
        const input = element.querySelector('[data-workout-field="weight"]')?.parentElement;
        const rirRow = element.querySelector('.active-workout-set__rir-row');
        const completion = element.querySelector('[data-workout-field="done"]');
        if (regions.some((region) => !region) || !input || !rirRow || !completion) {
          throw new Error('Active set geometry missing');
        }
        const boxes = regions.map((region) => region!.getBoundingClientRect());
        return {
          inOrder: boxes
            .slice(0, -1)
            .every((box, index) => boxes[index + 1]!.top >= box.bottom - 1),
          rowGap: Number.parseFloat(
            getComputedStyle(element.querySelector('.active-workout-set__controls')!).rowGap,
          ),
          beforeRir: rirRow.getBoundingClientRect().top - input.getBoundingClientRect().bottom,
          afterRir: completion.getBoundingClientRect().top - rirRow.getBoundingClientRect().bottom,
          scrollWidth: document.documentElement.scrollWidth,
        };
      });
      expect(geometry.inOrder).toBe(true);
      // #1272 keeps the RIR row separated from inputs and completion at every width.
      expect(geometry.rowGap).toBeGreaterThanOrEqual(11);
      expect(geometry.beforeRir).toBeGreaterThanOrEqual(geometry.rowGap - 1);
      expect(geometry.afterRir).toBeGreaterThanOrEqual(geometry.rowGap - 1);
      expect(geometry.scrollWidth).toBeLessThanOrEqual(width + 1);
    }
    await page.setViewportSize({ width: 1280, height: 1000 });
    await capture('prefill-collapsed');
    await page.setViewportSize({ width: 393, height: 844 });
    await capture('prefill-collapsed');

    await done.focus();
    for (const next of [prefill, help, helpers, advanced]) {
      await page.keyboard.press('Tab');
      await expect(next).toBeFocused();
    }

    const openWithoutJump = async (summary: Locator) => {
      await summary.evaluate((element) =>
        element.scrollIntoView({ block: 'center', behavior: 'instant' }),
      );
      const before = await page.evaluate(() => window.scrollY);
      await summary.click();
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      );
      expect(Math.abs((await page.evaluate(() => window.scrollY)) - before)).toBeLessThanOrEqual(2);
    };
    await openWithoutJump(help);
    await expect(row.locator('.active-workout-set__contextual-help details')).toHaveAttribute(
      'open',
      '',
    );
    await expect(row.getByRole('link', { name: 'Подробнее на сайте' })).toHaveAttribute(
      'href',
      /\/knowledge\/training\/repetitions-in-reserve/,
    );
    await openWithoutJump(helpers);
    await expect(row.locator('.active-workout-set__helpers')).toHaveAttribute('open', '');
    await row.getByLabel('Целевой вес, кг').fill('80');
    await expect(row.locator('.active-workout-plate-result')).toContainText('25 кг + 5 кг');
    const inventory = row.locator('.active-workout-plate-inventory');
    const overlap = await inventory.evaluate((element) => {
      const hint = element.querySelector(':scope > p')!.getBoundingClientRect();
      const reset = element
        .querySelector('.active-workout-plate-inventory__reset button')!
        .getBoundingClientRect();
      return (
        reset.top < hint.bottom &&
        reset.bottom > hint.top &&
        reset.left < hint.right &&
        reset.right > hint.left
      );
    });
    expect(overlap).toBe(false);
    expect(server.readSet(202).is_completed).toBe(false);
    await capture('prefill-open');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await capture('prefill-open');
    await page.setViewportSize({ width: 393, height: 844 });

    await prefill.click();
    await expect(weight).toHaveValue('40');
    await expect(reps).toHaveValue('8');
    await expect(prefill).toBeDisabled();
    await expect(past).toBeDisabled();
    const gap = await row.evaluate((element) => {
      const controls = element
        .querySelector('.active-workout-set__controls')!
        .getBoundingClientRect();
      const helpBox = element
        .querySelector('.active-workout-set__contextual-help')!
        .getBoundingClientRect();
      const actions = element
        .querySelector('.active-workout-set__prefill-actions')!
        .getBoundingClientRect();
      return {
        afterControls: actions.top - controls.bottom,
        beforeHelp: helpBox.top - actions.bottom,
      };
    });
    expect(gap.afterControls).toBeGreaterThanOrEqual(0);
    expect(gap.beforeHelp).toBeGreaterThanOrEqual(0);
    expect(gap.beforeHelp).toBeLessThanOrEqual(24);
    const selectedRir = row.getByRole('button', { name: '2 — ещё примерно 2 повтора' });
    await selectedRir.click();
    await expect.poll(() => server.readSet(202).rir).toBe('2');
    const count = inventory.getByLabel('Количество блинов 25 кг на сторону');
    const originalCount = await count.inputValue();
    await count.fill(originalCount === '0' ? '1' : '0');
    await inventory.getByRole('button', { name: 'Сбросить' }).click();
    await expect(count).toHaveValue(originalCount);
    await expect(weight).toHaveValue('40');
    await expect(reps).toHaveValue('8');
    await expect(selectedRir).toHaveAttribute('aria-pressed', 'true');
    expect(server.readSet(202).is_completed).toBe(false);
    await capture('no-prefill-open');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await capture('no-prefill-open');
    await page.setViewportSize({ width: 393, height: 844 });
    await row.getByRole('button', { name: 'Подготовить разминку' }).click();
    await page.getByRole('button', { name: 'Рассчитать предложение' }).click();
    await expect(page.getByRole('heading', { name: 'Проверьте подходы' })).toBeVisible();
    await page.getByRole('button', { name: 'Отмена' }).click();
    await advanced.click();
    await expect(row.getByLabel('Вид подхода')).toBeVisible();
    await row.getByLabel('Вид подхода').selectOption('drop');
    await expect.poll(() => server.readSet(202).set_kind).toBe('drop');
    await row.getByLabel('Вид подхода').selectOption('working');
    await expect.poll(() => server.readSet(202).set_kind).toBe('working');
    await advanced.click();
    await helpers.click();
    await help.click();
    await capture('no-prefill-collapsed');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await capture('no-prefill-collapsed');
    await page.setViewportSize({ width: 393, height: 844 });
    await done.click();
    await expect.poll(() => server.readSet(202).is_completed).toBe(true);
    expect(server.readSet(202)).toMatchObject({ actual_weight: 40, actual_reps: 8, rir: '2' });
  });
}

test('Issue #1293 disables prefill without a previous result', async ({ page }) => {
  await mockActiveWorkout(page);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const row = page.locator('[data-workout-set-id="201"]');
  await expect(row).toHaveAttribute('aria-current', 'step');
  await expect(
    row.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }),
  ).toBeDisabled();
  await expect(
    row.getByRole('button', { name: 'Подставить из прошлой тренировки' }),
  ).toBeDisabled();
  for (const width of [320, 360, 393, 430]) {
    await page.setViewportSize({ width, height: 844 });
    const spacing = await row.evaluate((element) => {
      const input = element.querySelector('[data-workout-field="weight"]')!.parentElement!;
      const rir = element.querySelector('.active-workout-set__rir-row')!;
      const done = element.querySelector('[data-workout-field="done"]')!;
      return {
        rowGap: Number.parseFloat(
          getComputedStyle(element.querySelector('.active-workout-set__controls')!).rowGap,
        ),
        beforeRir: rir.getBoundingClientRect().top - input.getBoundingClientRect().bottom,
        afterRir: done.getBoundingClientRect().top - rir.getBoundingClientRect().bottom,
        scrollWidth: document.documentElement.scrollWidth,
      };
    });
    expect(spacing.rowGap).toBeGreaterThanOrEqual(11);
    expect(spacing.beforeRir).toBeGreaterThanOrEqual(11);
    expect(spacing.afterRir).toBeGreaterThanOrEqual(11);
    expect(spacing.scrollWidth).toBeLessThanOrEqual(width + 1);
  }
  const done = row.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' });
  await done.focus();
  for (const label of ['Что такое RIR?', 'Разминка и блины', 'Дополнительно']) {
    await page.keyboard.press('Tab');
    await expect(row.getByText(label, { exact: true })).toBeFocused();
  }
});

test('Issue #1293 keeps explicit completion and optional RIR', async ({ page }) => {
  const server = await mockActiveWorkout(page);
  Object.assign(server.readSet(201), { actual_weight: 40, actual_reps: 8, is_completed: true });
  await page.goto('/app');
  await page.getByRole('button', { name: 'Клиент' }).click();
  await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
  const row = page.locator('[data-workout-set-id="202"]');
  await row.getByRole('button', { name: '4+ — осталось много сил' }).click();
  await expect.poll(() => server.readSet(202).rir).toBe('4+');
  await row.getByRole('button', { name: 'Подставить предыдущий подход сегодня' }).click();
  expect(server.readSet(202).is_completed).toBe(false);
  await row.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' }).click();
  await expect.poll(() => server.readSet(202).is_completed).toBe(true);
  expect(server.readSet(202)).toMatchObject({ actual_weight: 40, actual_reps: 8, rir: '4+' });
});

async function readRestJournal(page: Page) {
  return page.evaluate(() =>
    Object.keys(localStorage)
      .filter((key) => key.endsWith(':measured:v1'))
      .flatMap((key) => JSON.parse(localStorage.getItem(key) || '[]')),
  );
}

test.describe('#1292 compact rest panel', () => {
  test.use({ hasTouch: true });

  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 360, 393, 430, 1440]) {
      test(`omitted rest, geometry and restart at ${width}px ${theme}`, async ({
        page,
        browserName,
      }) => {
        const start = new Date('2026-10-10T12:00:00Z');
        const height = width === 1440 ? 900 : 844;
        await page.setViewportSize({ width, height });
        await page.clock.setFixedTime(start);
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        const server = await mockActiveWorkout(page);
        const restApi = await mockRestSessions(page);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const first = page.locator('[data-workout-set-id="201"]');
        await first.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
        await first.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
        await first.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
        const panel = page.getByRole('complementary', { name: 'Отдых между подходами' });
        await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
        await expect.poll(() => Object.values(restApi.intervals).length).toBe(1);
        const current = page.locator('[data-workout-set-id="202"]');
        const weight = current.getByLabel('Вес, Жим штанги лёжа, подход 2');
        await weight.fill('42.5');
        await current.getByLabel('Повторы, Жим штанги лёжа, подход 2').fill('9');
        await expect.poll(() => server.readSet(202).actual_weight).toBe(42.5);
        await expect.poll(() => server.readSet(202).actual_reps).toBe(9);
        await expect(page.locator('.active-workout-sync')).toContainText('Синхронизировано');
        const currentBefore = structuredClone(server.readSet(202));
        await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
        if (width < 681) await expect(page.locator('#appBottomNav')).toBeVisible();
        await current.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );

        const shot = async (state: string) => {
          if (process.env.CAPTURE_1292_VISUALS !== '1') return;
          const folder = resolve(
            process.cwd(),
            '..',
            '.artifacts',
            'tasks',
            '1292',
            'evidence',
            'after',
          );
          await mkdir(folder, { recursive: true });
          await page.screenshot({
            path: resolve(folder, `${browserName}-${theme}-${width}-${state}.png`),
            animations: 'disabled',
          });
          if (state !== 'modeled-keyboard') {
            await panel.screenshot({
              path: resolve(folder, `${browserName}-${theme}-${width}-${state}-panel.png`),
              animations: 'disabled',
            });
          }
        };
        await shot('running');
        await panel.getByRole('button', { name: 'Свернуть таймер' }).click();
        await expect(panel.getByRole('button', { name: 'Развернуть таймер' })).toBeVisible();
        await shot('collapsed');
        await panel.getByRole('button', { name: 'Развернуть таймер' }).click();
        await page.evaluate(() => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            get: () => 'hidden',
          });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await page.clock.setFixedTime(new Date(start.getTime() + 17 * 60_000));
        await page.evaluate(() => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            get: () => 'visible',
          });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await panel.getByRole('button', { name: 'Уточнить', exact: true }).click();
        await page
          .getByRole('group', { name: 'Уточнение фактического отдыха' })
          .getByRole('button', { name: 'Не учитывать', exact: true })
          .click();
        const summary = panel.locator('.active-workout-rest__complete-summary');
        await expect(summary).toHaveText('Отдых не учитывается');
        const restart = panel.getByRole('button', { name: 'Новый отдых' });
        const dismiss = panel.getByRole('button', { name: 'Скрыть' });
        await expect(restart).toHaveClass(/ui-button--primary/);
        await expect(dismiss).toHaveClass(/ui-button--secondary/);
        await expect.poll(() => restApi.intervals[900]?.status).toBe('skipped');
        await expect.poll(async () => (await readRestJournal(page))[0]?.pending.length).toBe(0);
        const previous = (await readRestJournal(page))[0];
        const previousRemote = structuredClone(restApi.intervals[900]);
        await current.evaluate((element) =>
          element.scrollIntoView({ block: 'center', behavior: 'instant' }),
        );
        await current.evaluate((element) => {
          const panelBottom = document
            .querySelector('.active-workout-rest')!
            .getBoundingClientRect().bottom;
          window.scrollBy({
            top: element.getBoundingClientRect().top - panelBottom - 12,
            behavior: 'instant',
          });
        });
        const geometry = await panel.evaluate((element) => {
          const box = (node: Element) => {
            const r = node.getBoundingClientRect();
            return {
              left: r.left,
              top: r.top,
              right: r.right,
              bottom: r.bottom,
              width: r.width,
              height: r.height,
            };
          };
          const status = element.querySelector('.active-workout-rest__complete-summary')!;
          const copy = status.querySelector<HTMLElement>('.active-workout-rest__complete-copy')!;
          const actions = Array.from(
            element.querySelectorAll('.active-workout-rest__complete-actions button'),
          );
          return {
            panel: box(element),
            status: box(status),
            buttons: actions.map(box),
            hits: actions.map((button) => {
              const r = button.getBoundingClientRect();
              return button.contains(
                document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2),
              );
            }),
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            textScrollWidth: copy.scrollWidth,
            textClientWidth: copy.clientWidth,
            textScrollHeight: copy.scrollHeight,
            textClientHeight: copy.clientHeight,
          };
        });
        expect(geometry.buttons).toHaveLength(2);
        expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
        expect(geometry.textScrollWidth).toBeLessThanOrEqual(geometry.textClientWidth + 1);
        expect(geometry.textScrollHeight).toBeLessThanOrEqual(geometry.textClientHeight + 1);
        expect(geometry.status.right).toBeLessThanOrEqual(geometry.buttons[0]!.left);
        expect(geometry.panel.height).toBeLessThanOrEqual(66);
        expect(geometry.buttons[0]!.right).toBeLessThanOrEqual(geometry.buttons[1]!.left);
        if (width < 681) {
          expect(geometry.status.left - geometry.panel.left).toBeCloseTo(11, 0);
          expect(geometry.panel.right - geometry.buttons[1]!.right).toBeCloseTo(11, 0);
        }
        for (const button of geometry.buttons) {
          expect(button.width).toBeGreaterThanOrEqual(44);
          expect(button.height).toBeGreaterThanOrEqual(44);
          expect(button.left).toBeGreaterThanOrEqual(geometry.panel.left);
          expect(button.right).toBeLessThanOrEqual(geometry.panel.right);
        }
        expect(geometry.hits).toEqual([true, true]);
        if (width < 681) {
          const dock = await page.locator('#appBottomNav').boundingBox();
          expect(dock).not.toBeNull();
          expect(geometry.panel.bottom).toBeLessThanOrEqual(dock!.y);
          const field = await weight.boundingBox();
          const done = await current
            .getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 2' })
            .boundingBox();
          expect(field).not.toBeNull();
          expect(done).not.toBeNull();
          expect(field!.y).toBeGreaterThanOrEqual(geometry.panel.bottom);
          expect(done!.y + done!.height).toBeLessThanOrEqual(dock!.y);
        }
        await shot('omitted');
        if (width === 320 && theme === 'dark') {
          await page.evaluate(() => {
            document.documentElement.style.fontSize = '200%';
          });
          const scaled = await panel.evaluate((element) => {
            const p = element.getBoundingClientRect();
            return Array.from(
              element.querySelectorAll('.active-workout-rest__complete-actions button'),
            ).map((button) => {
              const r = button.getBoundingClientRect();
              return {
                left: r.left,
                right: r.right,
                top: r.top,
                bottom: r.bottom,
                panelLeft: p.left,
                panelRight: p.right,
                scrollWidth: button.scrollWidth,
                clientWidth: button.clientWidth,
              };
            });
          });
          for (const button of scaled) {
            expect(button.left).toBeGreaterThanOrEqual(button.panelLeft);
            expect(button.right).toBeLessThanOrEqual(button.panelRight);
            expect(button.scrollWidth).toBeLessThanOrEqual(button.clientWidth);
          }
          expect(scaled).toHaveLength(2);
          expect(scaled[0]!.right <= scaled[1]!.left || scaled[0]!.bottom <= scaled[1]!.top).toBe(
            true,
          );
          await shot('large-text');
          await page.evaluate(() => {
            document.documentElement.style.fontSize = '';
          });
        }
        await page.evaluate(() => window.scrollBy({ top: 200, behavior: 'instant' }));
        await expect(panel).toBeInViewport();
        const sticky = await panel.boundingBox();
        expect(sticky).not.toBeNull();
        expect(sticky!.y).toBeGreaterThanOrEqual(-1);
        expect(sticky!.y).toBeLessThanOrEqual(1);
        if (width < 681) {
          await page.setViewportSize({ width, height: 480 });
          await weight.evaluate((element) =>
            element.scrollIntoView({ block: 'center', behavior: 'instant' }),
          );
          await weight.focus();
          await expect(weight).toBeFocused();
          await expect(page.locator('#appBottomNav')).toBeHidden();
          await settleViewport(page);
          await expect
            .poll(() =>
              weight.evaluate((element) => {
                const field = element.getBoundingClientRect();
                const panelBottom = document
                  .querySelector('.active-workout-rest')!
                  .getBoundingClientRect().bottom;
                return Math.min(field.top - panelBottom, window.innerHeight - field.bottom);
              }),
            )
            .toBeGreaterThanOrEqual(0);
          await shot('modeled-keyboard');
          await page.setViewportSize({ width, height });
        }
        await expect(weight).toHaveValue('42.5');
        await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
        if (width < 681) await expect(page.locator('#appBottomNav')).toBeVisible();
        await dismiss.click();
        await expect(summary).toHaveCount(0);
        await expect(panel.getByRole('timer')).toHaveCount(0);
        expect(restApi.restartCount()).toBe(0);
        expect(await readRestJournal(page)).toEqual([previous]);
        await shot('dismissed');

        await restart.dblclick();
        await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
        await expect.poll(() => restApi.restartCount()).toBe(1);
        await expect.poll(async () => (await readRestJournal(page)).length).toBe(2);
        const records = await readRestJournal(page);
        expect(records[0]).toEqual(previous);
        expect(records[1]).toMatchObject({
          status: 'running',
          restart_of_start_mutation_id: previous.start_mutation_id,
        });
        expect(restApi.intervals[900]).toEqual(previousRemote);
        expect(Object.values(restApi.intervals)).toHaveLength(2);
        expect(server.readSet(202)).toEqual(currentBefore);
        await shot('restarted');
      });
    }
  }

  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 1440]) {
      test(`expiry, corrected fact and skipped rest at ${width}px ${theme}`, async ({
        page,
        browserName,
      }) => {
        const start = new Date('2026-10-10T12:00:00Z');
        await page.setViewportSize({ width, height: width === 1440 ? 900 : 844 });
        await page.clock.setFixedTime(start);
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await mockActiveWorkout(page);
        const restApi = await mockRestSessions(page);
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const panel = page.getByRole('complementary', { name: 'Отдых между подходами' });
        const shot = async (state: string) => {
          if (process.env.CAPTURE_1292_VISUALS !== '1') return;
          const folder = resolve(
            process.cwd(),
            '..',
            '.artifacts',
            'tasks',
            '1292',
            'evidence',
            'after',
          );
          await mkdir(folder, { recursive: true });
          await page.screenshot({
            path: resolve(folder, `${browserName}-${theme}-${width}-${state}.png`),
            animations: 'disabled',
          });
          await panel.screenshot({
            path: resolve(folder, `${browserName}-${theme}-${width}-${state}-panel.png`),
            animations: 'disabled',
          });
        };

        await page.evaluate(() =>
          window.dispatchEvent(
            new CustomEvent('fit:rest', {
              detail: { workoutId: 42, seconds: 90, deadline: Date.now() - 1 },
            }),
          ),
        );
        await expect(panel.locator('.active-workout-rest__complete-summary')).toContainText(
          'Отдых завершён',
        );
        await expect(panel.getByRole('button', { name: 'Новый отдых' })).toHaveCount(0);
        const single = await panel.evaluate((element) => {
          const p = element.getBoundingClientRect();
          const summary = element.querySelector('.active-workout-rest__complete-summary')!;
          const status = summary.getBoundingClientRect();
          const copy = summary.querySelector<HTMLElement>('.active-workout-rest__complete-copy')!;
          const button = element
            .querySelector('.active-workout-rest__complete-actions button')!
            .getBoundingClientRect();
          return {
            panelLeft: p.left,
            panelRight: p.right,
            statusRight: status.right,
            buttonLeft: button.left,
            buttonRight: button.right,
            buttonWidth: button.width,
            buttonHeight: button.height,
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            textScrollWidth: copy.scrollWidth,
            textClientWidth: copy.clientWidth,
            textScrollHeight: copy.scrollHeight,
            textClientHeight: copy.clientHeight,
          };
        });
        expect(single.statusRight).toBeLessThanOrEqual(single.buttonLeft);
        expect(single.buttonLeft).toBeGreaterThanOrEqual(single.panelLeft);
        expect(single.buttonRight).toBeLessThanOrEqual(single.panelRight);
        expect(single.buttonWidth).toBeGreaterThanOrEqual(44);
        expect(single.buttonHeight).toBeGreaterThanOrEqual(44);
        expect(single.scrollWidth).toBeLessThanOrEqual(single.clientWidth);
        expect(single.textScrollWidth).toBeLessThanOrEqual(single.textClientWidth + 1);
        expect(single.textScrollHeight).toBeLessThanOrEqual(single.textClientHeight + 1);
        await shot('without-restart');
        await panel.getByRole('button', { name: 'Скрыть' }).click();
        await expect(panel).toHaveCount(0);
        expect(await readRestJournal(page)).toHaveLength(0);

        const first = page.locator('[data-workout-set-id="201"]');
        await first.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
        await first.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
        await first.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
        await expect(panel.getByRole('timer', { name: 'Отдых' })).toBeVisible();
        await expect.poll(() => Object.values(restApi.intervals).length).toBe(1);
        await page.clock.setFixedTime(new Date(start.getTime() + 100_000));
        await page.evaluate(() => window.dispatchEvent(new Event('pageshow')));
        await expect(panel.getByRole('timer', { name: 'Отдых' })).toHaveText('0:00');
        await expect(panel.getByRole('button', { name: 'Стоп: завершить отдых' })).toBeVisible();
        await shot('expired-running');
        await page.evaluate(() => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            get: () => 'hidden',
          });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await page.clock.setFixedTime(new Date(start.getTime() + 18 * 60_000));
        await page.evaluate(() => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            get: () => 'visible',
          });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await panel.getByRole('button', { name: 'Уточнить', exact: true }).click();
        const recovery = page.getByRole('group', { name: 'Уточнение фактического отдыха' });
        await recovery.getByRole('textbox', { name: 'Фактическое время, минуты' }).fill('2,5');
        await recovery.getByRole('button', { name: 'Сохранить время' }).click();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toContainText(
          'ФАКТ 2:30',
        );
        await expect.poll(() => restApi.intervals[900]?.status).toBe('completed');
        await expect.poll(async () => (await readRestJournal(page))[0]?.pending.length).toBe(0);
        const corrected = (await readRestJournal(page))[0];
        expect(corrected).toMatchObject({ measured_seconds: 150, source: 'USER_CORRECTED' });
        await shot('corrected');

        await panel.getByRole('button', { name: 'Новый отдых' }).click();
        await expect.poll(() => restApi.restartCount()).toBe(1);
        await panel.getByRole('button', { name: 'Пропустить' }).click();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toContainText(
          'Отдых пропущен',
        );
        await shot('skipped');
        await expect.poll(async () => (await readRestJournal(page))[1]?.pending.length).toBe(0);
        await panel.getByRole('button', { name: 'Новый отдых' }).click();
        await expect.poll(() => restApi.restartCount()).toBe(2);
        await panel.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toContainText(
          'Отдых завершён',
        );
        expect((await readRestJournal(page))[0]).toEqual(corrected);
        expect(await readRestJournal(page)).toHaveLength(3);
        await shot('completed');
      });
    }
  }

  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 393]) {
      test(`TMA safe area and keyboard at ${width}px ${theme}`, async ({ page, browserName }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await installTelegramHarness(page, {
          platform: 'ios',
          colorScheme: theme,
          viewportHeight: 844,
          viewportStableHeight: 844,
          safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
        });
        const server = await mockActiveWorkout(page);
        await mockRestSessions(page);
        await page.goto('/app?tgWebAppPlatform=ios');
        await expect(page.locator('html')).toHaveAttribute('data-yfc-layout-surface', 'telegram');
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const first = page.locator('[data-workout-set-id="201"]');
        await first.getByLabel('Вес, Жим штанги лёжа, подход 1').fill('40');
        await first.getByLabel('Повторы, Жим штанги лёжа, подход 1').fill('8');
        await first.getByRole('button', { name: 'Завершить: Жим штанги лёжа, подход 1' }).click();
        await expect.poll(() => server.readSet(201).is_completed).toBe(true);
        const panel = page.getByRole('complementary', { name: 'Отдых между подходами' });
        await panel.getByRole('button', { name: 'Пропустить' }).click();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toContainText(
          'Отдых пропущен',
        );
        await page.evaluate(() => window.scrollBy({ top: 200, behavior: 'instant' }));
        await settleViewport(page);
        const panelBox = await panel.boundingBox();
        const dock = await page.locator('#appBottomNav').boundingBox();
        expect(panelBox).not.toBeNull();
        expect(dock).not.toBeNull();
        expect(panelBox!.y).toBeGreaterThanOrEqual(23);
        expect(panelBox!.y).toBeLessThanOrEqual(27);
        expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(dock!.y);
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
          ),
        ).toBe(true);
        const capture = async (state: string) => {
          if (process.env.CAPTURE_1292_VISUALS !== '1') return;
          const folder = resolve(
            process.cwd(),
            '..',
            '.artifacts',
            'tasks',
            '1292',
            'evidence',
            'after',
          );
          await mkdir(folder, { recursive: true });
          await page.screenshot({
            path: resolve(folder, `${browserName}-${theme}-${width}-${state}.png`),
            animations: 'disabled',
          });
          if (state !== 'tma-keyboard') {
            await panel.screenshot({
              path: resolve(folder, `${browserName}-${theme}-${width}-${state}-panel.png`),
              animations: 'disabled',
            });
          }
        };
        await capture('tma-skipped');

        await page.setViewportSize({ width, height: 480 });
        await new TelegramHarness(page).setViewport(480, 844);
        const field = page
          .locator('[data-workout-set-id="202"]')
          .getByLabel('Вес, Жим штанги лёжа, подход 2');
        await field.evaluate((element) => {
          element.closest('label')!.scrollIntoView({ block: 'center', behavior: 'instant' });
          (element as HTMLElement).focus({ preventScroll: true });
        });
        await expect(field).toBeFocused();
        await expect(page.locator('#appBottomNav')).toBeHidden();
        await settleViewport(page);
        await expect
          .poll(() =>
            field.evaluate((element) => {
              const fieldBox = element.getBoundingClientRect();
              const restBox = document
                .querySelector('.active-workout-rest')!
                .getBoundingClientRect();
              return Math.min(fieldBox.top - restBox.bottom, 480 - 34 - fieldBox.bottom);
            }),
          )
          .toBeGreaterThanOrEqual(0);
        const keyboardPanel = await panel.boundingBox();
        expect(keyboardPanel).not.toBeNull();
        expect(keyboardPanel!.y).toBeGreaterThanOrEqual(23);
        expect(keyboardPanel!.y).toBeLessThanOrEqual(27);
        await capture('tma-keyboard');
      });
    }
  }
});

test.describe('#1338 v2 compact timer', () => {
  test.use({ hasTouch: true });

  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 360, 393, 430, 1120, 1440]) {
      test('review states ' + theme + ' ' + width + 'px', async ({ page, browserName }, info) => {
        const start = new Date('2026-10-10T12:00:00Z');
        await page.setViewportSize({
          width,
          height: width === 1440 ? 1000 : width === 1120 ? 960 : 844,
        });
        await page.clock.install({ time: start });
        await page.clock.setFixedTime(start);
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        const server = await mockActiveWorkout(page);
        const restApi = await mockRestSessions(page);
        Object.assign(server.readSet(201), { actual_weight: 40, actual_reps: 8, rir: '1' });
        Object.assign(server.readSet(202), { actual_weight: 42.5, actual_reps: 9, rir: '2' });
        await page.goto('/app');
        await page.getByRole('button', { name: 'Клиент', exact: true }).click();
        await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
        const panel = page.getByRole('complementary', { name: 'Отдых между подходами' });
        await expect(panel).toHaveCount(0);
        expect(await readRestJournal(page)).toHaveLength(0);
        await page
          .locator('[data-workout-set-id="201"]')
          .getByRole('button', { name: /^Завершить:/ })
          .click();
        await expect.poll(() => server.readSet(201).is_completed).toBe(true);
        await expect.poll(async () => (await readRestJournal(page))[0]?.server_id).toBe(900);
        const previousSet = structuredClone(server.readSet(201));
        const nextSet = structuredClone(server.readSet(202));
        const neighbor = structuredClone(server.readSet(203));
        const heights: Record<string, number> = {};
        const capture = async (state: string, expectedHeight: number) => {
          await expect
            .poll(async () => (await panel.boundingBox())?.height, { message: state })
            .toBeCloseTo(expectedHeight, 0);
          const box = await panel.boundingBox();
          expect(box).not.toBeNull();
          await expect(panel).toBeInViewport();
          if (expectedHeight === 110) expect(box!.height).toBeLessThanOrEqual(118);
          heights[state] = box!.height;
          const geometry = await panel.evaluate((element) => {
            const p = element.getBoundingClientRect();
            return {
              overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
              controls: Array.from(element.querySelectorAll('button'))
                .filter((button) => button.getClientRects().length)
                .map((button) => {
                  const r = button.getBoundingClientRect();
                  return {
                    width: r.width,
                    height: r.height,
                    left: r.left - p.left,
                    right: p.right - r.right,
                  };
                }),
            };
          });
          expect(geometry.overflow).toBeLessThanOrEqual(1);
          expect(geometry.controls.length).toBeGreaterThan(0);
          for (const control of geometry.controls) {
            expect(control.width).toBeGreaterThanOrEqual(44);
            expect(control.height).toBeGreaterThanOrEqual(44);
            expect(control.left).toBeGreaterThanOrEqual(-1);
            expect(control.right).toBeGreaterThanOrEqual(-1);
          }
          if (state === 'completed' || state === 'skipped') {
            const terminal = await panel.evaluate((element) => {
              const mark = element.querySelector<HTMLElement>(
                '.active-workout-rest__complete-mark',
              )!;
              const copy = element.querySelector<HTMLElement>(
                '.active-workout-rest__complete-copy',
              )!;
              const markBox = mark.getBoundingClientRect();
              const copyBox = copy.getBoundingClientRect();
              const panelBox = element.getBoundingClientRect();
              const radius = getComputedStyle(mark).borderTopLeftRadius;
              return {
                width: markBox.width,
                height: markBox.height,
                radiusRatio: radius.endsWith('%')
                  ? parseFloat(radius) / 100
                  : parseFloat(radius) / Math.min(markBox.width, markBox.height),
                copyOffset: (copyBox.top + copyBox.bottom - panelBox.top - panelBox.bottom) / 2,
              };
            });
            expect(terminal.width, `${state}: circular mark width`).toBeCloseTo(terminal.height, 1);
            expect(terminal.radiusRatio, `${state}: circular mark radius`).toBeGreaterThanOrEqual(
              0.49,
            );
            if (state === 'skipped') {
              expect(
                Math.abs(terminal.copyOffset),
                'skipped text vertical center',
              ).toBeLessThanOrEqual(1);
            }
          }
          expect(server.readSet(201)).toEqual(previousSet);
          expect(server.readSet(202)).toEqual(nextSet);
          expect(server.readSet(203)).toEqual(neighbor);
          if (process.env.CAPTURE_1338_VISUALS === '1') {
            const folder = resolve(
              process.cwd(),
              '..',
              '.artifacts',
              'tasks',
              '1338',
              'evidence',
              'after',
            );
            await mkdir(folder, { recursive: true });
            await page.screenshot({
              path: resolve(folder, [browserName, theme, width, state].join('-') + '.png'),
              animations: 'disabled',
            });
          }
        };

        await expect(panel.locator('.active-workout-rest__actions button')).toHaveCount(4);
        await expect(panel.getByRole('timer')).toHaveText('1:30');
        await capture('active', 110);
        await panel.getByRole('button', { name: 'Свернуть таймер' }).click();
        await capture('collapsed-active', 60);
        await panel.getByRole('button', { name: 'Развернуть таймер' }).click();
        await panel.getByRole('button', { name: '+30 сек', exact: true }).click();
        await panel.getByRole('button', { name: '+60 сек', exact: true }).click();
        await expect(panel.getByRole('timer')).toHaveText('3:00');
        await expect.poll(() => restApi.intervals[900]?.adjusted_seconds).toBe(180);

        await page.clock.setFixedTime(new Date(start.getTime() + 200_000));
        await page.clock.runFor(1100);
        await expect(panel.getByRole('timer')).toHaveText('0:00');
        await expect(panel.getByLabel('Время по отметке пользователя')).toHaveText('3:20');
        await capture('expired', 110);
        const intervalId = (await readRestJournal(page))[0]!.start_mutation_id;
        await panel.getByRole('button', { name: 'Свернуть таймер' }).click();
        await capture('collapsed', 60);
        await page.clock.setFixedTime(new Date(start.getTime() + 210_000));
        await page.clock.runFor(1100);
        await expect(panel).toContainText('ФАКТ 3:30');
        await panel.getByRole('button', { name: 'Развернуть таймер' }).click();
        expect((await readRestJournal(page))[0]!.start_mutation_id).toBe(intervalId);
        await expect(panel.getByLabel('Время по отметке пользователя')).toHaveText('3:30');
        await panel.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
        await expect.poll(() => restApi.intervals[900]?.measured_seconds).toBe(210);
        await expect.poll(async () => (await readRestJournal(page))[0]?.pending.length).toBe(0);
        await capture('completed', 66);
        const completed = (await readRestJournal(page))[0];
        await panel.getByRole('button', { name: 'Скрыть', exact: true }).click();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toHaveCount(0);
        await expect
          .poll(
            async () => (await page.locator('.active-workout-rest-spacer').boundingBox())?.height,
          )
          .toBe(44);
        await capture('dismissed', 44);
        expect(await readRestJournal(page)).toEqual([completed]);

        await panel.getByRole('button', { name: 'Новый отдых', exact: true }).dblclick();
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await expect.poll(() => restApi.restartCount()).toBe(1);
        expect((await readRestJournal(page))[0]).toEqual(completed);
        await expect(panel.getByLabel('Время по отметке пользователя')).toHaveText('0:00');
        await capture('restarted', 110);
        await panel.getByRole('button', { name: 'Пропустить', exact: true }).click();
        await expect.poll(() => restApi.intervals[901]?.status).toBe('skipped');
        expect(restApi.intervals[901]!.measured_seconds).toBeNull();
        await capture('skipped', 66);

        await panel.getByRole('button', { name: 'Новый отдых', exact: true }).click();
        await expect.poll(() => restApi.restartCount()).toBe(2);
        await setDocumentVisibility(page, 'hidden');
        await page.clock.setFixedTime(new Date(start.getTime() + 23 * 60_000));
        await setDocumentVisibility(page, 'visible');
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await capture('review-required', 62);
        await panel.getByRole('button', { name: 'Уточнить', exact: true }).click();
        const dialog = page.getByRole('dialog', { name: 'Сколько отдыхали?', exact: true });
        const input = dialog.getByRole('textbox', {
          name: 'Фактическое время, минуты',
        });
        await expect(input).toBeFocused();
        await capture('recovery-dialog', 62);
        const unresolved = await readRestJournal(page);
        await page.keyboard.press('Escape');
        await expect(dialog).toHaveCount(0);
        expect(await readRestJournal(page)).toEqual(unresolved);
        await capture('review-required', 62);
        const reopen = panel.getByRole('button', { name: 'Уточнить', exact: true });
        await reopen.click();
        await expect(input).toBeFocused();
        await page.keyboard.press('Shift+Tab');
        await expect(dialog.locator('.active-workout-rest-dialog__close')).toBeFocused();
        await page.keyboard.press('Tab');
        await expect(input).toBeFocused();
        await input.fill('-1');
        await dialog.getByRole('button', { name: 'Сохранить время', exact: true }).click();
        await expect(input).toHaveAttribute('aria-invalid', 'true');
        expect(await readRestJournal(page)).toEqual(unresolved);
        await input.fill('2,5');
        await dialog.getByRole('button', { name: 'Сохранить время', exact: true }).click();
        await expect(dialog).toHaveCount(0);
        await expect.poll(() => restApi.intervals[902]?.measured_seconds).toBe(150);
        expect(restApi.intervals[902]!.source).toBe('USER_CORRECTED');
        await capture('corrected', 66);

        await panel.getByRole('button', { name: 'Новый отдых', exact: true }).click();
        await setDocumentVisibility(page, 'hidden');
        await page.clock.setFixedTime(new Date(start.getTime() + 45 * 60_000));
        await setDocumentVisibility(page, 'visible');
        await panel.getByRole('button', { name: 'Уточнить', exact: true }).click();
        await page
          .getByRole('dialog', { name: 'Сколько отдыхали?', exact: true })
          .getByRole('button', { name: 'Не учитывать', exact: true })
          .click();
        await expect.poll(() => restApi.intervals[903]?.status).toBe('skipped');
        expect(restApi.intervals[903]!.measured_seconds).toBeNull();
        await expect(panel.locator('.active-workout-rest__complete-summary')).toHaveText(
          'Отдых не учитывается',
        );
        await capture('omitted', 66);
        expect((await readRestJournal(page))[0]).toEqual(completed);

        if (width === 320 && theme === 'dark') {
          await panel.getByRole('button', { name: 'Новый отдых', exact: true }).click();
          await page.evaluate(() => {
            document.documentElement.style.fontSize = '200%';
          });
          const scaled = await panel.evaluate((element) => {
            const p = element.getBoundingClientRect();
            return Array.from(element.querySelectorAll('button'))
              .filter((button) => button.getClientRects().length)
              .map((button) => {
                const r = button.getBoundingClientRect();
                return (
                  r.left >= p.left && r.right <= p.right && button.scrollWidth <= button.clientWidth
                );
              });
          });
          expect(scaled.length).toBeGreaterThanOrEqual(6);
          expect(scaled.every(Boolean)).toBe(true);
          if (process.env.CAPTURE_1338_VISUALS === '1') {
            const folder = resolve(
              process.cwd(),
              '..',
              '.artifacts',
              'tasks',
              '1338',
              'evidence',
              'after',
            );
            await page.screenshot({
              path: resolve(folder, [browserName, theme, width, 'large-text'].join('-') + '.png'),
              animations: 'disabled',
            });
          }
        }
        await writeFile(
          info.outputPath('timer-heights.json'),
          JSON.stringify({ browserName, theme, width, heights }, null, 2),
        );
      });
    }

    test('sync pending offline error and 409 ' + theme, async ({ page, browserName }, info) => {
      await page.setViewportSize({ width: 393, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const server = await mockActiveWorkout(page);
      const restApi = await mockRestSessions(page);
      await page.goto('/app');
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('40');
      await first.getByLabel(/^Повторы,/).fill('8');
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect.poll(async () => (await readRestJournal(page))[0]?.server_id).toBe(900);
      const panel = page.getByRole('complementary', { name: 'Отдых между подходами' });
      const before = structuredClone(server.readSet(202));
      const capture = async (state: string) => {
        expect((await panel.boundingBox())!.height).toBe(110);
        expect(server.readSet(202)).toEqual(before);
        expect(
          await panel.evaluate((element) =>
            Array.from(element.querySelectorAll('button, [role="timer"]')).every((control) => {
              const r = control.getBoundingClientRect();
              return control.contains(
                document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2),
              );
            }),
          ),
          `${state}: clocks and actions are not covered by global notices`,
        ).toBe(true);
        if (process.env.CAPTURE_1338_VISUALS === '1') {
          const folder = resolve(
            process.cwd(),
            '..',
            '.artifacts',
            'tasks',
            '1338',
            'evidence',
            'after',
          );
          await mkdir(folder, { recursive: true });
          await page.screenshot({
            path: resolve(folder, [browserName, theme, 393, state].join('-') + '.png'),
            animations: 'disabled',
          });
        }
      };
      const release = restApi.holdNextAction();
      await panel.getByRole('button', { name: '+30 сек', exact: true }).click();
      await expect(panel.locator('.active-workout-rest__status')).toContainText('Сохраняется…');
      await capture('pending');
      release();
      await expect.poll(async () => (await readRestJournal(page))[0]?.pending.length).toBe(0);
      await setNetworkOffline(page, true);
      await panel.getByRole('button', { name: '+60 сек', exact: true }).click();
      await expect(panel.locator('.active-workout-rest__status')).toContainText('Нет сети');
      await expect(page.locator('.offline-status')).toBeHidden();
      const offline = (await readRestJournal(page))[0]!;
      expect(offline.pending).toHaveLength(1);
      await capture('offline');
      restApi.failActions(503);
      await setNetworkOffline(page, false);
      await expect(panel.locator('.active-workout-rest__status')).toContainText(
        'Ошибка сохранения',
      );
      await capture('error');
      const status = panel.getByRole('button', { name: /Состояние отдыха:/ });
      await status.click();
      const dialog = page.getByRole('dialog', { name: 'Сохранение отдыха' });
      await expect(dialog.getByRole('alert')).toContainText('устройстве');
      await page.keyboard.press('Escape');
      await expect(status).toBeFocused();
      restApi.failActions(409);
      await page.evaluate(() => window.dispatchEvent(new Event('online')));
      await expect(panel.locator('.active-workout-rest__status')).toContainText(
        'Конфликт сохранения',
      );
      expect((await readRestJournal(page))[0]).toMatchObject({
        start_mutation_id: offline.start_mutation_id,
        deadline: offline.deadline,
        pending: offline.pending,
      });
      await capture('conflict-409');
      restApi.failActions(null);
      await page.evaluate(() => window.dispatchEvent(new Event('online')));
      await expect.poll(async () => (await readRestJournal(page))[0]?.pending.length).toBe(0);
      await expect(panel.locator('.active-workout-rest__status')).toContainText('Отдых идёт');
      expect(restApi.intervals[900]!.adjusted_seconds).toBe(180);
      await capture('reconnected');
      await writeFile(
        info.outputPath('sync-verification.json'),
        JSON.stringify(
          { browserName, theme, pendingRetainedOn409: true, syncedAdjustedSeconds: 180 },
          null,
          2,
        ),
      );
    });
  }
});
