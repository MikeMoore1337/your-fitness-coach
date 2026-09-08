/// <reference types="node" />

import type { Page, Route } from '@playwright/test';

type WorkoutStatus = 'planned' | 'in_progress' | 'completed' | 'none';
type ProgressionOutcome = 'consider_progressing' | 'hold' | 'review' | 'consider_reducing' | 'none';

export interface PlatformApiOptions {
  browserSession?: boolean;
  fixedDate?: string;
  workoutStatus?: WorkoutStatus;
  activeProgram?: boolean;
  weeklyReviewAvailable?: boolean;
  weeklyCalibration?: 'insufficient' | 'pending';
  nutritionTargetSource?: 'manual' | 'trainer';
  programHistory?: 'empty' | 'one' | 'many';
  progressionOutcome?: ProgressionOutcome;
  longExerciseName?: boolean;
  notificationState?: 'empty' | 'populated' | 'unlinked' | 'stale';
  accountExportState?: 'none' | 'ready' | 'expired' | 'error';
  authProviders?: string[];
  trainerActive?: boolean;
  measurementHistory?: 'none' | 'many';
  cardioState?: 'empty' | 'planned' | 'completed';
  avatarState?: 'default' | 'provider' | 'custom';
}

export interface PlatformApiController {
  setOffline(offline: boolean): void;
  failNextMeasurementSave(): void;
  measurementSaveCalls(): number;
  failNextCardioSave(): void;
  cardioSaveCalls(): number;
  authInitCalls(): number;
  meCalls(): number;
  trainerActivationCalls(): number;
  setPatchCalls(): number;
  finishCalls(): number;
  manualTargetSaves(): number;
  targetHistoryLength(): number;
  weeklyDecisionCalls(): string[];
  weeklyReviewSubmits(): number;
  nutritionReportPeriods(): string[];
  workoutValues(): { actualReps: number | null; actualWeight: number | null; completed: boolean };
  completionFeedback(): { feedback: string | null; note: string | null };
  adaptationApplyCalls(): number;
  setAdaptationApplyMode(mode: 'success' | 'conflict' | 'error'): void;
  accountExportCreates(): number;
  accountUnlinks(): string[];
  accountDeletes(): number;
  failNextAvatarUpload(): void;
  avatarUploads(): number;
  avatarDeletes(): number;
}

const zeroNutrition = {
  energy_kcal: '0.00',
  protein_g: '0.000',
  fat_g: '0.000',
  carbs_g: '0.000',
  fiber_g: null,
};

const oatmeal = {
  id: 7,
  name: 'Овсяная каша',
  brand: null,
  barcode: null,
  energy_kcal_per_100g: '360.00',
  protein_g_per_100g: '12.000',
  fat_g_per_100g: '6.000',
  carbs_g_per_100g: '62.000',
  fiber_g_per_100g: '8.000',
  standard_serving_amount: '1.000',
  standard_serving_unit: 'serving',
  standard_serving_weight_g: '50.000',
  food_type: 'system',
  is_favorite: true,
  last_used_at: '2030-01-09T07:00:00Z',
  created_at: '2030-01-01T07:00:00Z',
  updated_at: '2030-01-09T07:00:00Z',
};

export function emptyHydrationDay(diaryDate: string) {
  return {
    diary_date: diaryDate,
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
    action_url: `/app?section=nutrition&date=${diaryDate}&hydration=quick`,
  };
}

export const contextualReminderTemplates = [
  {
    template_key: 'meal_logging',
    version: 'v1',
    label: 'Записать приём пищи',
    purpose: 'Мягко напомнить добавить запись, когда выбранное окно ещё пусто.',
    schedule_kind: 'times',
    allowed_schedule: 'До трёх выбранных окон в выбранные дни недели.',
    quiet_hours_behavior: 'Окно внутри тихих часов пропускается без переноса на утро.',
    deep_link: 'Питание → быстрый ввод за выбранный приём пищи.',
    suppression: 'Пропускается, если в этом окне уже есть сохранённая запись питания.',
    neutral_copy: 'Можно записать приём пищи. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    times: ['08:00:00', '13:00:00', '19:00:00'],
    window_start: null,
    window_end: null,
    interval_minutes: null,
    max_per_day: 3,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
  {
    template_key: 'hydration',
    version: 'v1',
    label: 'Выпить воду',
    purpose: 'Напомнить отметить воду или другой напиток в дневнике.',
    schedule_kind: 'interval',
    allowed_schedule: 'Повтор в выбранном рабочем окне с ограничением числа напоминаний в день.',
    quiet_hours_behavior: 'Слоты внутри тихих часов пропускаются без catch-up серии.',
    deep_link: 'Питание → быстрый ввод воды за текущую дату.',
    suppression: 'Ближайший слот пропускается после недавней записи гидратации.',
    neutral_copy: 'Можно выпить воды. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    times: [],
    window_start: '09:00:00',
    window_end: '21:00:00',
    interval_minutes: 120,
    max_per_day: 6,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
  {
    template_key: 'movement_break',
    version: 'v1',
    label: 'Разминка / перерыв от сидения',
    purpose: 'Предложить короткий перерыв и немного подвигаться по расписанию.',
    schedule_kind: 'interval',
    allowed_schedule: 'Плановые слоты в выбранном рабочем окне; приложение не измеряет сидение.',
    quiet_hours_behavior: 'Слоты внутри тихих часов пропускаются без catch-up серии.',
    deep_link: 'Сегодня → контекст приложения для короткого перерыва.',
    suppression: 'Слот не переносится автоматически, если он был пропущен.',
    neutral_copy:
      'Пора сделать короткий перерыв и немного подвигаться. Подробности — в приложении.',
    default_enabled: false,
    enabled: false,
    weekdays: [0, 1, 2, 3, 4],
    times: [],
    window_start: '10:00:00',
    window_end: '18:00:00',
    interval_minutes: 120,
    max_per_day: 5,
    minimum_spacing_minutes: 120,
    telegram_linked: true,
    telegram_enabled: true,
    channel_note: 'Событие появится в приложении; в Telegram придёт нейтральный текст.',
  },
];

export async function installPlatformApi(
  page: Page,
  options: PlatformApiOptions = {},
): Promise<PlatformApiController> {
  const today =
    options.fixedDate ?? new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
  const todayDate = new Date(`${today}T12:00:00Z`);
  const contextDate = new Date(todayDate);
  const nextWorkoutDate = new Date(todayDate);
  nextWorkoutDate.setUTCDate(todayDate.getUTCDate() + 3);
  const nextWorkoutDay = nextWorkoutDate.toISOString().slice(0, 10);
  const contextIsCompleted = todayDate.getUTCDay() === 0;
  contextDate.setUTCDate(todayDate.getUTCDate() + (contextIsCompleted ? -1 : 1));
  const contextDay = contextDate.toISOString().slice(0, 10);
  let offline = false;
  let workoutStatus = options.workoutStatus ?? 'planned';
  const activeProgram = options.activeProgram ?? true;
  let authInitCalls = 0;
  let meCalls = 0;
  let trainerActivationCalls = 0;
  let trainerActive = options.trainerActive ?? false;
  let patchCalls = 0;
  let finishCalls = 0;
  let manualTargetSaves = 0;
  let weeklyReviewSubmits = 0;
  let accountExportCreates = 0;
  let accountDeletes = 0;
  let avatarState = options.avatarState ?? 'default';
  let failNextAvatarUpload = false;
  let avatarUploads = 0;
  let avatarDeletes = 0;
  let accountExportState = options.accountExportState ?? 'none';
  let authProviders = [...(options.authProviders ?? ['telegram'])];
  const accountUnlinks: string[] = [];
  let notificationsRead = false;
  const weeklyDecisions: string[] = [];
  const requestedNutritionReportPeriods: string[] = [];
  let setVersion = 1;
  let setValues = {
    actualReps: workoutStatus === 'completed' ? 8 : (null as number | null),
    actualWeight: workoutStatus === 'completed' ? 40 : (null as number | null),
    completed: workoutStatus === 'completed',
  };
  let nutritionEntries: Array<Record<string, unknown>> = [];
  let measurements: Array<{
    id: number;
    measured_on: string;
    weight_kg: number | null;
    chest_cm: number | null;
    waist_cm: number | null;
    hips_cm: number | null;
    biceps_cm: number | null;
    thigh_cm: number | null;
    note: string | null;
  }> =
    options.measurementHistory === 'many'
      ? [
          { daysAgo: 0, id: 101, weight: 80.9 },
          { daysAgo: 14, id: 102, weight: 81.6 },
          { daysAgo: 28, id: 103, weight: 82.4 },
          { daysAgo: 60, id: 104, weight: 83.3 },
        ].map(({ daysAgo, id, weight }) => {
          const measuredOn = new Date(todayDate);
          measuredOn.setUTCDate(measuredOn.getUTCDate() - daysAgo);
          return {
            id,
            measured_on: measuredOn.toISOString().slice(0, 10),
            weight_kg: weight,
            chest_cm: null,
            waist_cm: null,
            hips_cm: null,
            biceps_cm: null,
            thigh_cm: null,
            note: null,
          };
        })
      : [];
  let failNextMeasurementSave = false;
  let measurementSaveCalls = 0;
  let failNextCardioSave = false;
  let cardioSaveCalls = 0;
  let cardioSessions: Array<Record<string, unknown>> =
    options.cardioState && options.cardioState !== 'empty'
      ? [
          {
            id: 659,
            activity_type: 'walking',
            duration_minutes: 30,
            distance_km: null,
            average_heart_rate_bpm: null,
            heart_rate_zone: null,
            note: options.cardioState === 'planned' ? 'План на сегодня' : 'Фактический результат',
            scheduled_at: `${today}T09:00:00`,
            completed_at: options.cardioState === 'completed' ? `${today}T09:30:00` : null,
            status: options.cardioState,
            source: 'manual',
            created_at: `${today}T08:00:00`,
            updated_at: `${today}T09:30:00`,
          },
        ]
      : [];
  let completionFeedback: string | null = null;
  let completionNote: string | null = null;
  let adaptationApplyCalls = 0;
  let adaptationApplyMode: 'success' | 'conflict' | 'error' = 'success';
  const progressionOutcome = options.progressionOutcome ?? 'review';
  const providerAvatar =
    'data:image/svg+xml;charset=utf-8,' +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"><rect width="128" height="128" fill="#d8f799"/><circle cx="64" cy="48" r="24" fill="#43631f"/><path d="M22 122c4-31 20-46 42-46s38 15 42 46" fill="#43631f"/></svg>',
    );
  const customAvatarUpdatedAt = '2030-01-02T12:00:00Z';
  const currentUser = () => ({
    id: 7,
    telegram_user_id: authProviders.includes('telegram') ? 7007 : null,
    username: 'mobile_user',
    first_name: 'Анна',
    photo_url: avatarState === 'provider' || avatarState === 'custom' ? providerAvatar : null,
    custom_avatar:
      avatarState === 'custom'
        ? {
            content_type: 'image/webp',
            byte_size: 1084,
            width: 512,
            height: 512,
            updated_at: customAvatarUpdatedAt,
          }
        : null,
    is_coach: trainerActive,
    is_admin: false,
    has_active_program: activeProgram,
    has_workout_history: false,
    auth_providers: authProviders,
    onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
    profile: {
      full_name: 'Анна Петрова',
      timezone: 'Europe/Moscow',
      goal: 'maintenance',
      level: 'beginner',
      height_cm: 168,
      weight_kg: 67,
      workouts_per_week: 3,
      cardio_trainings_per_week: 1,
      kbju: currentTarget,
    },
    trainer: null,
  });
  const previousTargetDate = new Date(todayDate);
  previousTargetDate.setUTCDate(previousTargetDate.getUTCDate() - 30);
  const targetSource = options.nutritionTargetSource ?? 'manual';
  const targetAuthor =
    targetSource === 'trainer'
      ? { id: 11, telegram_user_id: 7011, full_name: 'Ирина Тренерова' }
      : { id: 7, telegram_user_id: 7007, full_name: 'Анна Петрова' };
  let currentTarget: Record<string, unknown> = {
    id: 2,
    user_id: 7,
    telegram_user_id: 7007,
    effective_from: today,
    effective_to: null,
    source: targetSource,
    created_at: `${today}T08:00:00`,
    note: 'Ориентир для текущего этапа',
    superseded_by_id: null,
    calories: 2100,
    protein_g: 140,
    fat_g: 70,
    carbs_g: 230,
    strength_rest: null,
    cardio_trainings: [],
    saved_at: `${today}T08:00:00`,
    created_by: targetAuthor,
    assigned_by: targetAuthor,
  };
  let targetHistory: Array<Record<string, unknown>> = [
    currentTarget,
    {
      ...currentTarget,
      id: 1,
      effective_from: previousTargetDate.toISOString().slice(0, 10),
      effective_to: today,
      source: 'calculated',
      note: 'Первичный расчёт',
      superseded_by_id: 2,
      calories: 2000,
      protein_g: 135,
      fat_g: 65,
      carbs_g: 219,
    },
  ];
  let calibrationStatus: 'insufficient' | 'pending' | 'accepted' | 'rejected' =
    options.weeklyCalibration ?? 'insufficient';
  const calibration = () => ({
    id: calibrationStatus === 'insufficient' ? null : 17,
    status: calibrationStatus,
    ruleset_version: 'adaptive-energy-v1',
    period_start: previousTargetDate.toISOString().slice(0, 10),
    period_end: today,
    sufficiency: {
      status: calibrationStatus === 'insufficient' ? 'insufficient' : 'sufficient',
      counters: {
        logged_day_count: calibrationStatus === 'insufficient' ? 3 : 24,
        eligible_day_count: 28,
        weight_point_count: calibrationStatus === 'insufficient' ? 0 : 6,
        first_window_weight_point_count: calibrationStatus === 'insufficient' ? 0 : 3,
        last_window_weight_point_count: calibrationStatus === 'insufficient' ? 0 : 3,
        required_logged_day_count: 21,
        required_window_weight_point_count: 3,
      },
      reason_keys:
        calibrationStatus === 'insufficient' ? ['too_few_logged_days'] : ['thresholds_met'],
    },
    average_intake_kcal: calibrationStatus === 'insufficient' ? null : 2300,
    smoothed_start_weight_kg: calibrationStatus === 'insufficient' ? null : 80,
    smoothed_end_weight_kg: calibrationStatus === 'insufficient' ? null : 80,
    estimated_expenditure_kcal: calibrationStatus === 'insufficient' ? null : 2300,
    estimate_low_kcal: calibrationStatus === 'insufficient' ? null : 2050,
    estimate_high_kcal: calibrationStatus === 'insufficient' ? null : 2550,
    goal: 'maintenance',
    current_target_calories: 2100,
    current_target_protein_g: 140,
    current_target_fat_g: 70,
    current_target_carbs_g: 230,
    proposed_target_calories: calibrationStatus === 'insufficient' ? null : 2300,
    proposed_target_protein_g: calibrationStatus === 'insufficient' ? null : 140,
    proposed_target_fat_g: calibrationStatus === 'insufficient' ? null : 70,
    proposed_target_carbs_g: calibrationStatus === 'insufficient' ? null : 280,
    proposed_effective_from: today,
    rationale:
      calibrationStatus === 'insufficient'
        ? ['Пока недостаточно заполненных дней питания и регулярных замеров массы для оценки.']
        : ['Среднее потребление по заполненным дням: 2300 ккал.', 'Тренд массы стабилен.'],
    created_at: `${today}T10:00:00`,
    decided_at:
      calibrationStatus === 'accepted' || calibrationStatus === 'rejected'
        ? `${today}T11:00:00`
        : null,
  });
  let weeklyExisting: Record<string, unknown> | null = options.weeklyReviewAvailable
    ? null
    : { id: 1, status: 'completed', summary: { adaptive_energy: null } };

  if (options.browserSession) {
    await page.addInitScript(() => sessionStorage.setItem('fit_access_token', 'e2e-browser-token'));
  }

  const progressionGuidance = () => {
    if (progressionOutcome === 'none') return null;
    const sessionCount = progressionOutcome === 'review' ? 0 : 2;
    const requiredSessionCount =
      progressionOutcome === 'hold' ? 3 : progressionOutcome === 'review' ? 2 : 2;
    const reps = progressionOutcome === 'consider_reducing' ? [6, 7] : [10, 10];
    const messages = {
      consider_progressing: 'Можно рассмотреть небольшое увеличение веса',
      hold: 'Пока оставьте текущую нагрузку',
      review: 'Данных недостаточно — сначала закрепите текущий диапазон повторений',
      consider_reducing: 'Можно рассмотреть небольшое снижение веса',
    } as const;
    return {
      ruleset_version: 'progression-guidance-v1',
      outcome: progressionOutcome,
      message: messages[progressionOutcome],
      detail:
        progressionOutcome === 'consider_progressing'
          ? 'Верхняя граница повторений стабильно достигнута. Доступный шаг оборудования учтён; решение остаётся за вами.'
          : progressionOutcome === 'consider_reducing'
            ? 'В двух сопоставимых тренировках рабочие подходы оставались ниже заданного диапазона. Это не оценка восстановления или перетренированности.'
            : progressionOutcome === 'hold'
              ? 'Последние результаты ещё не подтверждают устойчивое изменение нагрузки.'
              : 'Нужны полные сопоставимые рабочие подходы в текущем контексте программы.',
      suggested_increment:
        progressionOutcome === 'consider_progressing'
          ? 2.5
          : progressionOutcome === 'consider_reducing'
            ? -2.5
            : null,
      suggested_weight:
        progressionOutcome === 'consider_progressing'
          ? 42.5
          : progressionOutcome === 'consider_reducing'
            ? 37.5
            : null,
      load_unit: 'kg',
      evidence: {
        target_reps_min: 8,
        target_reps_max: 10,
        prescribed_sets: 1,
        comparable_session_count: sessionCount,
        required_session_count: requiredSessionCount,
        working_set_count: sessionCount,
        rir_recorded_set_count: progressionOutcome === 'consider_progressing' ? sessionCount : 0,
        reason_keys:
          progressionOutcome === 'consider_progressing'
            ? ['top_range_repeated', 'full_rir_coverage']
            : progressionOutcome === 'consider_reducing'
              ? ['below_range_two_sessions']
              : progressionOutcome === 'hold'
                ? ['need_one_more_stable_session']
                : ['too_few_comparable_sessions'],
        sessions: Array.from({ length: sessionCount }, (_, index) => ({
          workout_id: 30 + index,
          scheduled_date: new Date(todayDate.getTime() - (index + 1) * 7 * 86_400_000)
            .toISOString()
            .slice(0, 10),
          working_set_count: 1,
          load: 40,
          load_unit: 'kg',
          reps_min: reps[index],
          reps_max: reps[index],
          rir_recorded_set_count: progressionOutcome === 'consider_progressing' ? 1 : 0,
          rir_values:
            progressionOutcome === 'consider_progressing' ? [index === 0 ? '1' : '2'] : [],
          reached_failure: progressionOutcome === 'consider_reducing',
          completion_feedback: index === 0 ? 'as_expected' : null,
        })),
      },
    };
  };

  const workout = () => ({
    id: 42,
    scheduled_date: today,
    scheduled_time: '18:30:00',
    title: 'Силовая база',
    status: workoutStatus,
    day_number: 1,
    week_number: 1,
    started_at: workoutStatus === 'in_progress' ? `${today}T10:00:00` : null,
    completed_at: workoutStatus === 'completed' ? `${today}T11:00:00` : null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: options.longExerciseName
          ? 'Приседания со штангой с контролируемой паузой в нижней точке'
          : 'Приседания',
        sort_order: 1,
        prescribed_sets: 1,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        notes: null,
        has_guide: false,
        progression_guidance: progressionGuidance(),
        sets: [
          {
            id: 201,
            set_number: 1,
            actual_reps: setValues.actualReps,
            actual_weight: setValues.actualWeight,
            rir: null,
            set_kind: 'working',
            reached_failure: false,
            is_completed: setValues.completed,
            version: setVersion,
          },
        ],
      },
    ],
    completion_summary:
      workoutStatus === 'completed'
        ? {
            duration_seconds: 3600,
            performed_exercises: 1,
            completed_sets: setValues.completed ? 1 : 0,
            total_sets: 1,
            reps_total: setValues.actualReps,
            reps_recorded_sets: setValues.actualReps == null ? 0 : 1,
            load_recorded_sets: setValues.actualWeight == null ? 0 : 1,
            exercises: setValues.completed
              ? [
                  {
                    workout_exercise_id: 101,
                    exercise_id: 11,
                    exercise_title: 'Приседания',
                    completed_sets: 1,
                    reps_total: setValues.actualReps,
                    reps_recorded_sets: setValues.actualReps == null ? 0 : 1,
                    max_load_kg: setValues.actualWeight,
                    load_recorded_sets: setValues.actualWeight == null ? 0 : 1,
                  },
                ]
              : [],
            personal_records:
              setValues.completed && setValues.actualWeight != null
                ? [
                    {
                      exercise_id: 11,
                      exercise_title: 'Приседания',
                      kinds: ['max_load'],
                      max_load_kg: setValues.actualWeight,
                      best_set_volume_kg: null,
                    },
                  ]
                : [],
            next_workout: {
              id: 44,
              scheduled_date: nextWorkoutDay,
              scheduled_time: '09:00:00',
              title: 'Верх тела',
            },
            feedback: completionFeedback,
            note: completionNote,
          }
        : null,
  });

  const contextWorkout = {
    id: 43,
    scheduled_date: contextDay,
    scheduled_time: '09:00:00',
    title: 'Контекст недели',
    status: contextIsCompleted ? 'completed' : 'planned',
    day_number: 2,
    week_number: 1,
  };

  const shiftedDay = (days: number) => {
    const value = new Date(todayDate);
    value.setUTCDate(todayDate.getUTCDate() + days);
    return value.toISOString().slice(0, 10);
  };
  const programHistory = options.programHistory ?? null;
  const archivedBlock = {
    id: 300,
    user_program_id: 77,
    title: 'Вводный этап',
    start_date: shiftedDay(-42),
    end_date: shiftedDay(-29),
    duration_days: 14,
    purpose: 'Спокойно вернуться к регулярным тренировкам.',
    priority_muscle_ids: [],
    notes: null,
    is_deload: false,
    status: 'archived',
    created_by_user_id: 7,
    created_at: `${shiftedDay(-42)}T08:00:00`,
    updated_at: `${shiftedDay(-29)}T08:00:00`,
  };
  const completedBlock = {
    id: 301,
    user_program_id: 77,
    title: 'Техническая база',
    start_date: shiftedDay(-28),
    end_date: shiftedDay(-15),
    duration_days: 14,
    purpose: 'Закрепить технику основных движений.',
    priority_muscle_ids: [],
    notes: 'Без отказных повторов.',
    is_deload: false,
    status: 'completed',
    created_by_user_id: 7,
    created_at: `${shiftedDay(-28)}T08:00:00`,
    updated_at: `${shiftedDay(-15)}T08:00:00`,
  };
  const activeBlock = {
    id: 302,
    user_program_id: 77,
    title:
      'Устойчивый рабочий объём с постепенным усложнением основных движений без потери техники',
    start_date: shiftedDay(-14),
    end_date: shiftedDay(6),
    duration_days: 21,
    purpose:
      'Увеличить рабочий объём, сохраняя стабильную технику и понятный запас повторов в каждом подходе.',
    priority_muscle_ids: [],
    notes: 'Тренер скорректировал цель после уверенного выполнения предыдущего этапа.',
    is_deload: false,
    status: 'active',
    created_by_user_id: 11,
    created_at: `${shiftedDay(-14)}T08:00:00`,
    updated_at: `${shiftedDay(-2)}T12:00:00`,
  };
  const plannedBlock = {
    id: 303,
    user_program_id: 77,
    title: 'Облегчённая неделя перед следующим рабочим циклом',
    start_date: shiftedDay(7),
    end_date: shiftedDay(13),
    duration_days: 7,
    purpose: 'Снизить объём перед следующим этапом программы.',
    priority_muscle_ids: [],
    notes: null,
    is_deload: true,
    status: 'planned',
    created_by_user_id: 11,
    created_at: `${shiftedDay(-2)}T12:00:00`,
    updated_at: null,
  };
  const programBlocks =
    programHistory === 'empty'
      ? []
      : programHistory === 'one'
        ? [activeBlock]
        : [archivedBlock, completedBlock, activeBlock, plannedBlock];
  const programSnapshotWorkoutInitial = {
    id: 943,
    scheduled_date: contextDay,
    title: 'Контекст версии',
    status: 'completed',
    day_number: 2,
    week_number: 3,
    exercises: [
      {
        exercise_id: 11,
        sort_order: 1,
        prescribed_sets: 2,
        prescribed_reps: '10–12',
        rest_seconds: 75,
        notes: null,
        superset_group: null,
        superset_order: null,
      },
    ],
  };
  const programSnapshotWorkoutBefore = {
    ...programSnapshotWorkoutInitial,
    exercises: [
      {
        ...programSnapshotWorkoutInitial.exercises[0],
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
      },
    ],
  };
  const programSnapshotWorkout = {
    ...programSnapshotWorkoutBefore,
    exercises: [
      {
        ...programSnapshotWorkoutBefore.exercises[0],
        prescribed_sets: 4,
        prescribed_reps: '6–8',
        rest_seconds: 120,
      },
    ],
  };
  const activeBlockBefore = {
    ...activeBlock,
    purpose: 'Сохранять рабочий объём без изменения сложности.',
  };
  const currentRevisionNumber = programHistory === 'empty' ? 0 : programHistory === 'one' ? 2 : 4;
  const programRevisions =
    programHistory === 'empty'
      ? []
      : programHistory === 'one'
        ? [
            {
              id: 2,
              user_program_id: 77,
              revision_number: 2,
              changed_by_user_id: 7,
              actor_role: 'self',
              change_kind: 'block_created',
              reason: 'Разделить программу на понятные этапы',
              changed_fields: { block_id: 302, status: 'active' },
              snapshot: { training_blocks: [activeBlock], workouts: [programSnapshotWorkout] },
              created_at: `${shiftedDay(-14)}T08:00:00`,
            },
            {
              id: 1,
              user_program_id: 77,
              revision_number: 1,
              changed_by_user_id: 7,
              actor_role: 'self',
              change_kind: 'assigned',
              reason: null,
              changed_fields: {},
              snapshot: { training_blocks: [], workouts: [programSnapshotWorkout] },
              created_at: `${shiftedDay(-42)}T08:00:00`,
            },
          ]
        : [
            {
              id: 4,
              user_program_id: 77,
              revision_number: 4,
              changed_by_user_id: 11,
              actor_role: 'trainer',
              change_kind: 'block_updated',
              reason:
                'Пользователь уверенно выполняет план, поэтому этап уточнён без изменения исторических тренировок.',
              changed_fields: { block_id: 302, fields: ['purpose'] },
              snapshot: { training_blocks: programBlocks, workouts: [programSnapshotWorkout] },
              created_at: `${shiftedDay(-2)}T12:00:00`,
            },
            {
              id: 3,
              user_program_id: 77,
              revision_number: 3,
              changed_by_user_id: 11,
              actor_role: 'trainer',
              change_kind: 'plan_updated',
              reason: 'Уточнить объём тренировки для следующего шага программы',
              changed_fields: {
                operation: 'exercise_upserted',
                day_number: 2,
                exercise_id: 11,
                workouts_updated: 1,
              },
              snapshot: {
                training_blocks: [archivedBlock, completedBlock, activeBlockBefore, plannedBlock],
                workouts: [programSnapshotWorkoutBefore],
              },
              created_at: `${shiftedDay(-3)}T12:00:00`,
            },
            {
              id: 2,
              user_program_id: 77,
              revision_number: 2,
              changed_by_user_id: 7,
              actor_role: 'self',
              change_kind: 'block_status_changed',
              reason: 'Технический этап завершён по плану',
              changed_fields: { block_id: 301, fields: ['status'] },
              snapshot: {
                training_blocks: [archivedBlock, completedBlock, activeBlockBefore],
                workouts: [programSnapshotWorkoutInitial],
              },
              created_at: `${shiftedDay(-15)}T09:00:00`,
            },
            {
              id: 1,
              user_program_id: 77,
              revision_number: 1,
              changed_by_user_id: 7,
              actor_role: 'self',
              change_kind: 'assigned',
              reason: null,
              changed_fields: {},
              snapshot: { training_blocks: [], workouts: [programSnapshotWorkoutInitial] },
              created_at: `${shiftedDay(-42)}T08:00:00`,
            },
          ];
  const activeProgramTemplate = {
    id: 700,
    slug: 'strength-base-history',
    title: 'Силовая база: длинный цикл для устойчивого прогресса',
    goal: 'recomposition',
    level: 'intermediate',
    split_type: 'full_body',
    owner_user_id: 7,
    owner_telegram_user_id: 7007,
    owner_full_name: 'Анна Петрова',
    created_by_user_id: 7,
    is_public: false,
    is_example: false,
    can_edit: true,
    is_assigned_to_current_user: true,
    is_active_for_current_user: true,
    assigned_by_user_id: null,
    assigned_by_full_name: null,
    assigned_program_id: 77,
    assigned_program_status: 'active',
    assigned_program_start_date: shiftedDay(-42),
    assigned_program_duration_weeks: 10,
    current_revision_number: currentRevisionNumber,
    days: [{ id: 1, day_number: 1, title: 'Силовая', exercises: [] }],
  };

  const measurementTrends = (periodDays = 30) => {
    const cutoff = new Date(todayDate);
    cutoff.setUTCDate(cutoff.getUTCDate() - Math.max(periodDays - 1, 0));
    const cutoffDate = cutoff.toISOString().slice(0, 10);
    const metrics = [
      ['weight_kg', 'weight_kg'],
      ['chest_cm', 'chest_cm'],
      ['waist_cm', 'waist_cm'],
      ['hips_cm', 'hips_cm'],
      ['biceps_cm', 'biceps_cm'],
      ['thigh_cm', 'thigh_cm'],
    ] as const;
    return metrics.flatMap(([metric, field]) => {
      const points = measurements
        .filter((item) => item.measured_on >= cutoffDate && item[field] != null)
        .map((item) => ({ measured_on: item.measured_on, value: item[field] as number }))
        .sort((left, right) => left.measured_on.localeCompare(right.measured_on));
      const first = points[0];
      const latest = points.at(-1);
      if (!first || !latest) return [];
      const spanDays = Math.round(
        (Date.parse(`${latest.measured_on}T12:00:00Z`) -
          Date.parse(`${first.measured_on}T12:00:00Z`)) /
          86_400_000,
      );
      return [
        {
          metric,
          first_value: first.value,
          latest_value: latest.value,
          change: points.length > 1 ? latest.value - first.value : null,
          first_measured_on: first.measured_on,
          latest_measured_on: latest.measured_on,
          point_count: points.length,
          span_days: spanDays,
          interpretation_status:
            points.length === 1
              ? 'single_point'
              : points.length < 3
                ? 'insufficient_points'
                : spanDays < 14
                  ? 'insufficient_period'
                  : 'available',
          points,
        },
      ];
    });
  };

  const progressSummary = (periodDays = 30) => ({
    user_id: 7,
    period_days: periodDays,
    period_start: today,
    period_end: today,
    training: {
      planned_workouts: 1,
      completed_workouts: workoutStatus === 'completed' ? 1 : 0,
      skipped_workouts: 0,
      frequency_per_week: 0,
      volume_kg: 0,
      new_personal_records: 0,
      last_completed_workout_on: workoutStatus === 'completed' ? today : null,
      next_workout: null,
    },
    nutrition: {
      visible: true,
      logged_days: nutritionEntries.length ? 1 : 0,
      complete_days: 0,
      incomplete_days: nutritionEntries.length ? 1 : 0,
      fasted_days: 0,
      unlogged_days: nutritionEntries.length ? 28 : 29,
      adherence_evaluated_days: 0,
      average_calories: null,
      target_calories: 2100,
      average_protein_g: null,
      target_protein_g: 140,
      target_effective_on: today,
    },
    body: {
      latest_measurement: measurements[0] ?? null,
      trends: measurementTrends(periodDays),
      priority: { mode: 'balanced', muscle_group_ids: [] },
      guidance: {
        comparison_basis: 'self',
        minimum_points_for_interpretation: 3,
        minimum_span_days_for_interpretation: 14,
        consistency_tips: ['Снимайте замеры в похожее время суток.'],
        circumference_limitations: ['Окружность участка тела не показывает рост отдельной мышцы.'],
      },
    },
    cardio: {
      completed_sessions: cardioSessions.filter((session) => session.status === 'completed').length,
      planned_sessions: cardioSessions.filter((session) => session.status === 'planned').length,
      frequency_per_week: Number(
        (
          (cardioSessions.filter((session) => session.status === 'completed').length * 7) /
          30
        ).toFixed(1),
      ),
      duration_minutes: cardioSessions
        .filter((session) => session.status === 'completed')
        .reduce((total, session) => total + Number(session.duration_minutes), 0),
      distance_km: cardioSessions.some(
        (session) => session.status === 'completed' && session.distance_km != null,
      )
        ? cardioSessions
            .filter((session) => session.status === 'completed')
            .reduce((total, session) => total + Number(session.distance_km ?? 0), 0)
        : null,
      zone_duration: Object.entries(
        cardioSessions
          .filter((session) => session.status === 'completed' && session.heart_rate_zone != null)
          .reduce<Record<string, number>>((totals, session) => {
            const zone = String(session.heart_rate_zone);
            totals[zone] = (totals[zone] ?? 0) + Number(session.duration_minutes);
            return totals;
          }, {}),
      ).map(([zone, duration]) => ({ zone: Number(zone), duration_minutes: duration })),
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
      workout_logging: {
        status: workoutStatus === 'completed' ? 'sufficient' : 'insufficient',
        counters: {
          completed_workout_count: workoutStatus === 'completed' ? 1 : 0,
          prescribed_set_count: 1,
          logged_set_count: workoutStatus === 'completed' ? 1 : 0,
          coverage_percent: workoutStatus === 'completed' ? 100 : 0,
        },
        reason_keys: [workoutStatus === 'completed' ? 'thresholds_met' : 'no_completed_workouts'],
      },
      working_sets: {
        status: workoutStatus === 'completed' ? 'limited' : 'insufficient',
        counters: {
          workout_session_count: workoutStatus === 'completed' ? 1 : 0,
          working_set_count: workoutStatus === 'completed' ? 1 : 0,
          required_workout_session_count: 2,
          required_working_set_count: 6,
        },
        reason_keys: [workoutStatus === 'completed' ? 'too_few_working_sets' : 'no_working_sets'],
      },
      rir_coverage: {
        status: 'insufficient',
        counters: {
          working_set_count: workoutStatus === 'completed' ? 1 : 0,
          recorded_set_count: 0,
          required_recorded_set_count: 3,
          coverage_percent: 0,
          required_coverage_percent: 50,
        },
        reason_keys: ['no_rir_observations'],
      },
      nutrition_coverage: {
        status: nutritionEntries.length ? 'limited' : 'insufficient',
        counters: {
          logged_day_count: nutritionEntries.length ? 1 : 0,
          eligible_day_count: 29,
          required_logged_day_count: 7,
          coverage_percent: nutritionEntries.length ? 3.4 : 0,
        },
        reason_keys: [nutritionEntries.length ? 'below_required_coverage' : 'no_logged_days'],
      },
      weight_trend: {
        status:
          measurements.length >= 3
            ? 'sufficient'
            : measurements.length
              ? 'limited'
              : 'insufficient',
        counters: {
          point_count: measurements.length,
          span_days: measurementTrends(periodDays)[0]?.span_days ?? 0,
          required_point_count: 3,
          required_span_days: 14,
        },
        reason_keys: [
          measurements.length >= 3
            ? 'thresholds_met'
            : measurements.length
              ? 'too_few_points'
              : 'no_measurements',
        ],
      },
      anthropometry: {
        status: 'insufficient',
        counters: {
          measured_metric_count: 0,
          sufficient_metric_count: 0,
          maximum_point_count: 0,
          maximum_span_days: 0,
          required_point_count_per_metric: 3,
          required_span_days_per_metric: 14,
        },
        reason_keys: ['no_anthropometry_measurements'],
      },
      schedule_adherence: {
        status: 'insufficient',
        counters: { evaluable_workout_count: 0, required_evaluable_workout_count: 3 },
        reason_keys: ['no_evaluable_planned_workouts'],
      },
    },
  });

  const nutritionTotals = () => {
    const sums = nutritionEntries.reduce<{
      energy: number;
      protein: number;
      fat: number;
      carbs: number;
      fiber: number;
    }>(
      (totals, entry) => {
        const nutrition = entry.nutrition as Record<string, string | null | undefined>;
        totals.energy += Number(nutrition.energy_kcal ?? 0);
        totals.protein += Number(nutrition.protein_g ?? 0);
        totals.fat += Number(nutrition.fat_g ?? 0);
        totals.carbs += Number(nutrition.carbs_g ?? 0);
        totals.fiber += Number(nutrition.fiber_g ?? 0);
        return totals;
      },
      { energy: 0, protein: 0, fat: 0, carbs: 0, fiber: 0 },
    );
    return {
      energy_kcal: sums.energy.toFixed(2),
      protein_g: sums.protein.toFixed(3),
      fat_g: sums.fat.toFixed(3),
      carbs_g: sums.carbs.toFixed(3),
      fiber_g: nutritionEntries.length ? sums.fiber.toFixed(3) : null,
    };
  };

  const nutritionReport = (period = 'days_7') => {
    const dates = Array.from({ length: 7 }, (_, index) => {
      const value = new Date(todayDate);
      value.setUTCDate(todayDate.getUTCDate() - (6 - index));
      return value.toISOString().slice(0, 10);
    });
    const changeDate = dates[3]!;
    const statuses = [
      'complete',
      'missing',
      'complete',
      'missing',
      'fasted',
      'incomplete',
      'missing',
    ] as const;
    const daily = dates.map((diaryDate, index) => {
      const status = statuses[index]!;
      const targetCalories = diaryDate < changeDate ? 2100 : 1950;
      const targetProtein = diaryDate < changeDate ? 140 : 135;
      const logged = status === 'complete' || status === 'fasted';
      const calories =
        status === 'fasted'
          ? 0
          : status === 'complete'
            ? 2050 - index * 35
            : status === 'incomplete'
              ? 720
              : null;
      const protein =
        status === 'fasted'
          ? 0
          : status === 'complete'
            ? 145 - index * 2
            : status === 'incomplete'
              ? 48
              : null;
      const fat =
        status === 'fasted'
          ? 0
          : status === 'complete'
            ? 68 - index
            : status === 'incomplete'
              ? 25
              : null;
      const carbs =
        status === 'fasted'
          ? 0
          : status === 'complete'
            ? 210 - index * 3
            : status === 'incomplete'
              ? 82
              : null;
      return {
        diary_date: diaryDate,
        status,
        is_current_day: diaryDate === today,
        calories,
        protein_g: protein,
        fat_g: fat,
        carbs_g: carbs,
        target_calories: targetCalories,
        target_protein_g: targetProtein,
        target_fat_g: diaryDate < changeDate ? 70 : 65,
        target_carbs_g: diaryDate < changeDate ? 230 : 210,
        calorie_deviation: logged && calories != null ? calories - targetCalories : null,
        protein_deviation_g: logged && protein != null ? protein - targetProtein : null,
        fat_deviation_g: logged && fat != null ? fat - (diaryDate < changeDate ? 70 : 65) : null,
        carbs_deviation_g:
          logged && carbs != null ? carbs - (diaryDate < changeDate ? 230 : 210) : null,
        within_calorie_tolerance:
          logged && calories != null
            ? Math.abs(calories - targetCalories) <= targetCalories * 0.1
            : null,
        meets_protein_target: logged && protein != null ? protein >= targetProtein : null,
        target_changed: diaryDate === changeDate,
      };
    });
    return {
      period,
      period_start: dates[0],
      period_end: dates[6],
      timezone: 'Europe/Moscow',
      summary: {
        logged_days: 3,
        eligible_days: 7,
        coverage_percent: 42.9,
        complete_days: 2,
        incomplete_days: 1,
        fasted_days: 1,
        missing_days: 3,
        current_day_status: 'missing',
        calories: { average: 1342, minimum: 0, maximum: 2050, sample_days: 3 },
        protein_g: { average: 95, minimum: 0, maximum: 145, sample_days: 3 },
        fat_g: { average: 44, minimum: 0, maximum: 68, sample_days: 3 },
        carbs_g: { average: 137, minimum: 0, maximum: 210, sample_days: 3 },
        calorie_comparison: {
          average_actual: 1342,
          average_target: 2000,
          average_deviation: -658,
          evaluated_days: 3,
        },
        protein_comparison: {
          average_actual: 95,
          average_target: 136.7,
          average_deviation: -41.7,
          evaluated_days: 3,
        },
        fat_comparison: {
          average_actual: 44,
          average_target: 66.7,
          average_deviation: -22.7,
          evaluated_days: 3,
        },
        carbs_comparison: {
          average_actual: 137,
          average_target: 216.7,
          average_deviation: -79.7,
          evaluated_days: 3,
        },
        days_within_calorie_tolerance: 2,
        calorie_tolerance_evaluated_days: 3,
        days_meeting_protein_target: 1,
        protein_target_evaluated_days: 3,
      },
      daily,
      target_changes: [
        {
          effective_from: changeDate,
          source: 'adaptive',
          calories: 1950,
          protein_g: 135,
          fat_g: 65,
          carbs_g: 210,
        },
      ],
    };
  };

  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (offline && !path.endsWith('/public/config')) return route.abort('internetdisconnected');
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: {
          app_env: 'test',
          enable_dev_auth: true,
          enable_web_auth: false,
          enable_email_auth: false,
          telegram_bot_username: 'fit_test_bot',
          oauth_providers: authProviders.filter(
            (provider) => provider !== 'telegram' && provider !== 'password',
          ),
        },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/auth/telegram/init')) {
      authInitCalls += 1;
      return route.fulfill({
        json: { access_token: 'telegram-test-token', token_type: 'bearer' },
      });
    }
    if (path.endsWith('/auth/dev-login')) {
      return route.fulfill({ json: { access_token: 'dev-test-token', token_type: 'bearer' } });
    }
    if (path.endsWith('/ai-coach/status')) {
      return route.fulfill({
        json: { ui_enabled: false, generic_available: false, personal_available: false },
      });
    }
    if (path.endsWith('/me/trainer-capability')) {
      if (request.method() === 'POST') {
        trainerActivationCalls += 1;
        trainerActive = true;
      } else if (request.method() === 'DELETE') {
        trainerActive = false;
      }
      return route.fulfill({
        json: {
          is_active: trainerActive,
          activated_now: request.method() === 'POST',
          active_client_count: trainerActive ? 1 : 0,
          pending_invite_count: 0,
          can_disable: !trainerActive,
          terms_version: 'trainer-capability-v1',
        },
      });
    }
    if (path.endsWith('/me/exports/current') && request.method() === 'GET') {
      const ready = accountExportState === 'ready';
      return route.fulfill({
        json: {
          status: accountExportState,
          export_id: accountExportState === 'none' ? null : 'task-65-export',
          created_at: accountExportState === 'none' ? null : '2030-01-02T11:45:00',
          completed_at: accountExportState === 'none' ? null : '2030-01-02T11:45:05',
          expires_at: ready ? '2030-01-02T12:00:00' : null,
          filename: ready ? 'your-fitness-coach-data.zip' : null,
          content_size_bytes: ready ? 4096 : null,
          error_code: accountExportState === 'error' ? 'generation_failed' : null,
        },
      });
    }
    if (path.endsWith('/me/exports') && request.method() === 'POST') {
      accountExportCreates += 1;
      accountExportState = 'ready';
      return route.fulfill({
        status: 201,
        json: {
          status: 'ready',
          export_id: 'task-65-export',
          created_at: '2030-01-02T11:45:00',
          completed_at: '2030-01-02T11:45:05',
          expires_at: '2030-01-02T12:00:00',
          filename: 'your-fitness-coach-data.zip',
          content_size_bytes: 4096,
          error_code: null,
        },
      });
    }
    if (/\/me\/exports\/[^/]+\/download-link$/.test(path) && request.method() === 'POST') {
      return route.fulfill({
        json: {
          url: `${url.origin}/api/v1/me/exports/file/task-65-short-token`,
          filename: 'your-fitness-coach-data.zip',
          expires_at: '2030-01-02T11:47:00',
        },
      });
    }
    if (/\/me\/auth\/identities\/[^/]+$/.test(path) && request.method() === 'DELETE') {
      const provider = path.split('/').at(-1) ?? '';
      accountUnlinks.push(provider);
      authProviders = authProviders.filter((candidate) => candidate !== provider);
      return route.fulfill({ json: {} });
    }
    if (path.endsWith('/me/account') && request.method() === 'DELETE') {
      accountDeletes += 1;
      return route.fulfill({ status: 204 });
    }
    if (path.endsWith('/me/avatar') && request.method() === 'GET') {
      if (avatarState !== 'custom') {
        return route.fulfill({ status: 404, json: { detail: 'Custom avatar not found' } });
      }
      return route.fulfill({
        status: 200,
        contentType: 'image/webp',
        body: Buffer.from(
          'UklGRjQEAABXRUJQVlA4ICgEAADQGwCdASqAAIAAPjEYiUKiIaEWzjQAIAMEs4BqRSMgP/oMLs4xtiueO01Cnb/BX9P/gHbV/a8UIAO+un1nhB2pv8Tkpvxb/afwD+deQD4AeIB6Hn+T88/4B+gHkDTAP45/nvYk/Qf9R/VfyA9hfxL/0vcC/i38r/2H9m/w/uZ+oD9ZvYF/V4b0YSGupd7aYQHC7RGxfixSB86Po6wMWpXPiOwqPEQocFVovGF/jumXFt9kCeY72DgVVkgXqRDsoN7OaLbA6b55lMfm0A2Afnxg+WuQVwnAK5qWYcwVNYQ4RQMxg8fc1uAA/v0lEv/WV/+ZX/5lf75HgMgnRnESCAAfpIPOfGqGc4+DGdJlvJGfpF34XWYV3pL/g07R66uV0G7CXAkxCWPEAD9ibHI0VaXt02JPDARoH99l0/7AACo/7Vk3/js91Rzx8C1zMad8/rQGhB6w5IPcgJfT5iFWK+xF5/ilkNl0+OIwntYK7CyMBcV+omuj+ZR4ubvMv8ux7+sHidS2DA9sFH08nh5R82zn6skw+YB4ZVU3OAnG7j8WACgXAmnQ7GPAxjqNu0Zk9iY4OfDdod559qh7Onvw2MTuHSh/7gu+bSEy5/GxhIYvFWMZJ2unPvX3odo6GHl6Uk4wsKPL4iLxKVqLdN3+6NKwo3KrMfOONxVoWlOVty4WN8blGBoRBCdlDdbTwxbKw1jb9qW1I45aG87wMUiQooJ4jaD6BsckeBzmCNVcjDQniN5WNbg+bHfG/hEQV/2t3aG0OWiVe8TSFupD3yVBnAc2JcWYNxHpz4eJEfsUe21O+JljaqtHUjXuRnyXFnEwXAVa1LtFpSWT++zCv20SSTu4+M5IvVmd/xhjH6k1P7as3Be/os2YeaYXoi/Bopt8Mui346kCQ5fbVmDfJII6oBDpBNVFes5OqlcPfjKvSFsKFQhWC38vmslkAmV50P+e9jkV7Lp/C8br73Ynx4WvImahkZCndKigYjzazD6n4g0Pca37wG1/jZqHedohaSz+O+c91DVUy+lAr4BY1uqcs9zxxJ6DKzJuihFgSkWbxKlay5yxfVVjxjY2dJD2ZYGw+JwGe/szxNCuzjOqSf/miJ1rH35y53yIdBQLxBfR6GWEjuf4xnM9nP8Lg7o67VVGYweSEpWcu8RBYApOjSG5O3pzOuIKUVOO7weBwE9Hbkzi74Q1pALtUMAJdzCKSGs7TzbPIK9FYf+jw2sAIIDFYuuCUC519wquOTol44qxTGCypj0DhyUV+2SnwF2vM2cmnYl4p5PdurFRqqM3yOzI+bjl5h7wu8REg46LJ4UKUqvOP/KzjR/IyugC8aNqyuT6GXMB+Er9Tv1+prbI7wd3+aQvZuK134S6OtQcnpV6KcnBK5tW2R32Rc6Vq86Gby/RWv5+WVVeQYAAAA==',
          'base64',
        ),
      });
    }
    if (path.endsWith('/me/avatar') && request.method() === 'PUT') {
      avatarUploads += 1;
      if (failNextAvatarUpload) {
        failNextAvatarUpload = false;
        return route.fulfill({
          status: 422,
          json: { detail: 'Не удалось обработать изображение' },
        });
      }
      avatarState = 'custom';
      return route.fulfill({ json: currentUser() });
    }
    if (path.endsWith('/me/avatar') && request.method() === 'DELETE') {
      avatarDeletes += 1;
      avatarState =
        options.avatarState === 'provider' || options.avatarState === 'custom'
          ? 'provider'
          : 'default';
      return route.fulfill({ json: currentUser() });
    }
    if (path.endsWith('/me')) {
      meCalls += 1;
      return route.fulfill({ json: currentUser() });
    }
    if (path.endsWith('/coach/clients')) {
      return route.fulfill({
        json: [
          {
            id: 11,
            invite_id: null,
            telegram_user_id: 3011,
            username: 'anna_runner',
            full_name: 'Анна Петрова',
            goal: 'maintenance',
            level: 'intermediate',
            height_cm: 168,
            weight_kg: 62,
            workouts_per_week: 3,
            cardio_trainings_per_week: 1,
            timezone: 'Europe/Moscow',
            kbju: null,
            status: 'active',
          },
        ],
      });
    }
    if (path.endsWith('/coach/assigned-programs')) return route.fulfill({ json: [] });
    if (path.endsWith('/coach/client-summaries')) {
      return route.fulfill({ json: { items: [], total: 0, limit: 100, offset: 0 } });
    }
    if (path.endsWith('/coach/clients/11/analytics')) {
      return route.fulfill({
        json: {
          adherence_percent: null,
          workouts_completed: 0,
          workouts_skipped: 0,
          workouts_missed: 0,
          current_streak: 0,
          weight_change_kg: null,
          personal_records: [],
        },
      });
    }
    if (path.endsWith('/coach/clients/11/workouts')) return route.fulfill({ json: [] });
    if (programHistory && path.endsWith('/programs/templates/mine')) {
      return route.fulfill({ json: [activeProgramTemplate] });
    }
    if (programHistory && path.endsWith('/programs/templates/hidden')) {
      return route.fulfill({ json: [] });
    }
    if (programHistory && path.endsWith('/programs/assigned/77/blocks')) {
      return route.fulfill({ json: programBlocks });
    }
    if (programHistory && path.endsWith('/programs/assigned/77/revisions')) {
      return route.fulfill({ json: programRevisions });
    }
    if (programHistory && path.endsWith('/programs/exercises')) {
      return route.fulfill({
        json: [
          {
            id: 11,
            title: 'Присед со штангой',
            primary_muscle: 'Квадрицепс',
            equipment: 'Штанга',
            primary_muscle_ids: ['quadriceps'],
            secondary_muscle_ids: [],
            equipment_ids: ['barbell'],
            alternatives: [],
            difficulty_level: 'intermediate',
            edit_target_id: null,
            slug: 'barbell-squat',
            is_custom: false,
            is_personalized: false,
            created_by_user_id: null,
            source_exercise_id: null,
            has_guide: false,
            guide: null,
          },
        ],
      });
    }
    if (path.endsWith('/workouts/today')) {
      if (workoutStatus === 'none') {
        return route.fulfill({
          status: 404,
          json: { detail: 'На сегодня тренировка не назначена' },
        });
      }
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/week')) {
      if (!activeProgram) return route.fulfill({ json: [] });
      return route.fulfill({
        json: [...(workoutStatus === 'none' ? [] : [workout()]), contextWorkout],
      });
    }
    if (path.endsWith('/workouts/schedule')) {
      return route.fulfill({ json: contextIsCompleted ? [] : [contextWorkout] });
    }
    if (path.endsWith('/workouts/history')) {
      return route.fulfill({
        json: contextIsCompleted
          ? [
              {
                ...contextWorkout,
                started_at: `${contextDay}T08:00:00`,
                completed_at: `${contextDay}T09:00:00`,
                completed_sets: 1,
                volume_kg: 40,
                exercises: [],
                adaptations: [],
              },
            ]
          : [],
      });
    }
    if (path.endsWith('/workouts/history/summary')) {
      return route.fulfill({
        json: {
          workouts_completed: contextIsCompleted ? 1 : 0,
          completed_sets: contextIsCompleted ? 1 : 0,
          volume_kg: contextIsCompleted ? 40 : 0,
        },
      });
    }
    if (path.endsWith('/workouts/42/start')) {
      workoutStatus = 'in_progress';
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/42/adaptations/preview') && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        reason: string;
        time_budget_minutes?: number;
      };
      const safety = body.reason === 'pain_or_injury';
      return route.fulfill({
        json: {
          status: safety ? 'safety_stop' : 'preview',
          workout_id: 42,
          reason: body.reason,
          ruleset_version: 'workout-adaptation-v1',
          original_estimated_minutes: 56,
          adapted_estimated_minutes: safety ? 56 : 20,
          time_budget_minutes: body.time_budget_minutes ?? null,
          changes: safety
            ? []
            : [
                {
                  kind: 'removed',
                  workout_exercise_id: 102,
                  from_exercise_id: 12,
                  from_title: 'Разведение гантелей на наклонной скамье',
                  to_exercise_id: null,
                  to_title: null,
                },
              ],
          original_exercises: [],
          adapted_exercises: [],
          warnings: safety ? [] : ['Основные упражнения и их порядок сохранены.'],
          message: safety
            ? 'Приложение не подбирает медицинскую замену. Остановите упражнение и обратитесь к квалифицированному специалисту.'
            : 'Проверьте изменения перед применением. Будет изменена только эта тренировка.',
          preview_token: safety ? null : 'a'.repeat(64),
        },
      });
    }
    if (path.endsWith('/workouts/42/adaptations/apply') && request.method() === 'POST') {
      adaptationApplyCalls += 1;
      if (adaptationApplyMode === 'conflict') {
        return route.fulfill({
          status: 409,
          json: { detail: 'Тренировка или условия изменились. Сформируйте preview заново' },
        });
      }
      if (adaptationApplyMode === 'error') {
        return route.fulfill({ status: 503, json: { detail: 'Временная ошибка сервера' } });
      }
      return route.fulfill({
        json: {
          adaptation_id: 9,
          applied_at: `${today}T10:15:00`,
          workout: workout(),
        },
      });
    }
    if (path.endsWith('/workouts/42/finish')) {
      finishCalls += 1;
      if (!setValues.completed) {
        return route.fulfill({
          status: 409,
          json: { detail: 'Отметьте хотя бы один выполненный подход' },
        });
      }
      workoutStatus = 'completed';
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/42/completion-feedback') && request.method() === 'PUT') {
      const body = request.postDataJSON() as { feedback: string | null; note: string | null };
      completionFeedback = body.feedback;
      completionNote = body.note;
      return route.fulfill({ json: workout() });
    }
    if (path.endsWith('/workouts/sets/201')) {
      patchCalls += 1;
      const body = request.postDataJSON() as {
        actual_reps: number | null;
        actual_weight: number | null;
        is_completed: boolean;
      };
      setValues = {
        actualReps: body.actual_reps,
        actualWeight: body.actual_weight,
        completed: body.is_completed,
      };
      setVersion += 1;
      return route.fulfill({
        json: {
          id: 201,
          set_number: 1,
          actual_reps: setValues.actualReps,
          actual_weight: setValues.actualWeight,
          rir: null,
          set_kind: 'working',
          reached_failure: false,
          is_completed: setValues.completed,
          version: setVersion,
        },
      });
    }
    if (path.endsWith('/workouts/cardio') && request.method() === 'GET') {
      const dateFrom = url.searchParams.get('date_from');
      const dateTo = url.searchParams.get('date_to');
      const items = cardioSessions.filter((session) => {
        const date = String(session.scheduled_at).slice(0, 10);
        return (!dateFrom || date >= dateFrom) && (!dateTo || date <= dateTo);
      });
      return route.fulfill({ json: items });
    }
    if (path.endsWith('/workouts/cardio') && request.method() === 'POST') {
      cardioSaveCalls += 1;
      if (failNextCardioSave) {
        failNextCardioSave = false;
        return route.fulfill({ status: 503, json: { detail: 'Временная ошибка сохранения' } });
      }
      const body = request.postDataJSON() as Record<string, unknown>;
      const replay = cardioSessions.find(
        (session) => session.client_request_id === body.client_request_id,
      );
      if (replay) return route.fulfill({ status: 201, json: replay });
      const created = {
        ...body,
        id: 660 + cardioSessions.length,
        source: 'manual',
        completed_at: body.status === 'completed' ? body.scheduled_at : null,
        created_at: `${today}T12:00:00`,
        updated_at: `${today}T12:00:00`,
      };
      cardioSessions = [created, ...cardioSessions];
      return route.fulfill({ status: 201, json: created });
    }
    const cardioMatch = path.match(/\/workouts\/cardio\/(\d+)$/);
    if (cardioMatch && request.method() === 'PATCH') {
      cardioSaveCalls += 1;
      const id = Number(cardioMatch[1]);
      const body = request.postDataJSON() as Record<string, unknown>;
      const existing = cardioSessions.find((session) => session.id === id);
      if (!existing) return route.fulfill({ status: 404, json: { detail: 'Cardio not found' } });
      const updated = { ...existing, ...body, updated_at: `${today}T12:05:00` };
      cardioSessions = cardioSessions.map((session) => (session.id === id ? updated : session));
      return route.fulfill({ json: updated });
    }
    const completeCardioMatch = path.match(/\/workouts\/cardio\/(\d+)\/complete$/);
    if (completeCardioMatch && request.method() === 'POST') {
      const id = Number(completeCardioMatch[1]);
      const existing = cardioSessions.find((session) => session.id === id);
      if (!existing) return route.fulfill({ status: 404, json: { detail: 'Cardio not found' } });
      const updated = {
        ...existing,
        status: 'completed',
        completed_at: existing.completed_at ?? `${today}T12:05:00`,
        updated_at: `${today}T12:05:00`,
      };
      cardioSessions = cardioSessions.map((session) => (session.id === id ? updated : session));
      return route.fulfill({ json: updated });
    }
    if (cardioMatch && request.method() === 'DELETE') {
      const id = Number(cardioMatch[1]);
      cardioSessions = cardioSessions.filter((session) => session.id !== id);
      return route.fulfill({ status: 204, body: '' });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: progressSummary(Number(url.searchParams.get('period_days')) || 30),
      });
    }
    if (path.endsWith('/workouts/progress/training-analytics')) {
      const workingSets = progressSummary().data_sufficiency.working_sets;
      return route.fulfill({
        json: {
          period_days: Number(url.searchParams.get('period_days')) || 30,
          period_start: today,
          period_end: today,
          exercise_history_limit: 20,
          completed_set_count: workoutStatus === 'completed' ? 1 : 0,
          reps_total: workoutStatus === 'completed' ? 8 : 0,
          reps_recorded_sets: workoutStatus === 'completed' ? 1 : 0,
          external_load_volume_kg: workoutStatus === 'completed' ? 320 : 0,
          volume_recorded_sets: workoutStatus === 'completed' ? 1 : 0,
          exercises: [],
          rir: {
            completed_set_count: workoutStatus === 'completed' ? 1 : 0,
            recorded_set_count: 0,
            missing_set_count: workoutStatus === 'completed' ? 1 : 0,
            distribution: [],
          },
          primary_muscle_exposure: [],
          secondary_muscle_exposure: [],
          completed_sets_without_muscle_metadata: workoutStatus === 'completed' ? 1 : 0,
          data_sufficiency: {
            ruleset_version: 'data-sufficiency-v1',
            workout_logging: progressSummary().data_sufficiency.workout_logging,
            working_sets: workingSets,
            rir_coverage: progressSummary().data_sufficiency.rir_coverage,
          },
        },
      });
    }
    if (path.endsWith('/me/profile/body-priority-options')) {
      return route.fulfill({
        json: {
          items: [
            { id: 'back', name: 'Мышцы спины' },
            { id: 'glutes', name: 'Ягодичные мышцы' },
          ],
        },
      });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'GET') {
      return route.fulfill({ json: measurements });
    }
    if (path.endsWith('/workouts/diary') && request.method() === 'POST') {
      measurementSaveCalls += 1;
      if (failNextMeasurementSave) {
        failNextMeasurementSave = false;
        return route.fulfill({
          status: 503,
          json: { detail: 'Замер временно не удалось сохранить' },
        });
      }
      const body = request.postDataJSON() as Partial<(typeof measurements)[number]> & {
        measured_on: string;
      };
      const existing = measurements.find((item) => item.measured_on === body.measured_on);
      const saved = {
        id: existing?.id ?? measurements.length + 1,
        measured_on: body.measured_on,
        weight_kg: body.weight_kg ?? null,
        chest_cm: body.chest_cm ?? null,
        waist_cm: body.waist_cm ?? null,
        hips_cm: body.hips_cm ?? null,
        biceps_cm: body.biceps_cm ?? null,
        thigh_cm: body.thigh_cm ?? null,
        note: body.note ?? null,
      };
      measurements = [saved, ...measurements.filter((item) => item.id !== saved.id)];
      return route.fulfill({ json: saved });
    }
    if (/\/workouts\/diary\/\d+$/.test(path) && request.method() === 'DELETE') {
      const id = Number(path.split('/').at(-1));
      measurements = measurements.filter((item) => item.id !== id);
      return route.fulfill({ status: 204, body: '' });
    }
    if (path.endsWith('/workouts/progress/nutrition-report')) {
      const period = url.searchParams.get('period') ?? 'days_7';
      requestedNutritionReportPeriods.push(period);
      return route.fulfill({ json: nutritionReport(period) });
    }
    if (path.endsWith('/workouts/progress/nutrition-report.csv')) {
      return route.fulfill({
        body: '\ufeffrow_type,period_start,period_end\nsummary,' + today + ',' + today + '\n',
        contentType: 'text/csv; charset=utf-8',
        headers: { 'Content-Disposition': 'attachment; filename="nutrition-report.csv"' },
      });
    }
    if (path.endsWith('/check-ins/daily') && request.method() === 'GET') {
      return route.fulfill({
        json: {
          local_date: url.searchParams.get('local_date') ?? today,
          today,
          timezone: 'Europe/Moscow',
          record: null,
        },
      });
    }
    if (path.endsWith('/check-ins/weekly/current')) {
      return route.fulfill({
        json: {
          week_start: today,
          week_end: today,
          submitted_on: today,
          timezone: 'Europe/Moscow',
          existing: weeklyExisting,
          summary: {
            ruleset_version: 'weekly-review-summary-v2',
            period_start: today,
            period_end: today,
            goal: 'maintenance',
            training: { completed_workouts: 0, planned_workouts: 1, adherence: {} },
            nutrition: {
              logged_days: nutritionEntries.length ? 1 : 0,
              complete_days: 0,
              incomplete_days: nutritionEntries.length ? 1 : 0,
              fasted_days: 0,
              unlogged_days: nutritionEntries.length ? 0 : 1,
              average_calories: null,
              target_calories: 2100,
              average_protein_g: null,
              target_protein_g: 140,
              calories_adherence: {},
              protein_adherence: {},
              current_target: {
                effective_from: today,
                source: currentTarget.source,
                calories: currentTarget.calories,
                protein_g: currentTarget.protein_g,
                fat_g: currentTarget.fat_g,
                carbs_g: currentTarget.carbs_g,
              },
              suspicious_low_days: [],
            },
            progression: { new_personal_records: 0 },
            weight_trend: null,
            anthropometry_trends: [],
            body_priority: null,
            data_sufficiency: {
              weight_trend: {
                status: 'insufficient',
                counters: { point_count: 0 },
                reason_keys: ['no_measurements'],
              },
            },
            adaptive_energy: null,
          },
        },
      });
    }
    if (path.endsWith('/check-ins/weekly') && request.method() === 'GET') {
      return route.fulfill({
        json: {
          items: [
            {
              id: 1,
              user_id: 7,
              week_start: today,
              week_end: today,
              submitted_on: today,
              timezone: 'Europe/Moscow',
              status: 'completed',
              summary_version: 'weekly-review-summary-v2',
              summary: {
                training: { completed_workouts: 1, planned_workouts: 1 },
                adaptive_energy: null,
              },
              training_load: null,
              recovery: null,
              hunger: null,
              adherence_difficulty: null,
              note: null,
              created_at: `${today}T10:00:00`,
            },
          ],
          total: 1,
          limit: 4,
          offset: 0,
        },
      });
    }
    if (path.endsWith('/check-ins/weekly') && request.method() === 'POST') {
      weeklyReviewSubmits += 1;
      const body = request.postDataJSON() as { status: 'completed' | 'skipped' };
      weeklyExisting = {
        id: 2,
        status: body.status,
        summary: {
          adaptive_energy:
            body.status === 'completed'
              ? {
                  decision:
                    calibrationStatus === 'accepted'
                      ? 'accepted'
                      : calibrationStatus === 'rejected'
                        ? 'kept'
                        : calibrationStatus === 'pending'
                          ? 'deferred'
                          : 'not_available',
                  calibration: calibration(),
                }
              : null,
        },
      };
      return route.fulfill({ status: 201, json: weeklyExisting });
    }
    if (path.endsWith('/nutrition/energy-calibration/preview') && request.method() === 'POST') {
      return route.fulfill({ json: calibration() });
    }
    if (
      /\/nutrition\/energy-calibration\/17\/decision$/.test(path) &&
      request.method() === 'POST'
    ) {
      const decision = String(request.postDataJSON().decision);
      weeklyDecisions.push(decision);
      calibrationStatus = decision === 'accept' ? 'accepted' : 'rejected';
      if (decision === 'accept')
        currentTarget = { ...currentTarget, calories: 2300, source: 'adaptive' };
      return route.fulfill({ json: calibration() });
    }
    if (path.endsWith('/notifications/settings')) {
      const linked = options.notificationState !== 'unlinked';
      return route.fulfill({
        json: {
          workout_reminders_enabled: true,
          weekly_check_in_reminders_enabled: true,
          measurement_reminders_enabled: false,
          meal_reminders_enabled: false,
          hydration_reminders_enabled: false,
          movement_reminders_enabled: false,
          telegram_enabled: true,
          telegram_linked: linked,
          reminder_hour: 9,
          quiet_hours_start: '22:00:00',
          quiet_hours_end: '08:00:00',
        },
      });
    }
    if (path.endsWith('/notifications/templates')) {
      const linked = options.notificationState !== 'unlinked';
      return route.fulfill({
        json: contextualReminderTemplates.map((template) => ({
          ...template,
          telegram_linked: linked,
          channel_note: linked
            ? template.channel_note
            : 'В приложении доступно всегда; Telegram появится после связывания аккаунта.',
        })),
      });
    }
    if (/\/notifications\/templates\/(meal_logging|hydration|movement_break)$/.test(path)) {
      const templateKey = path.split('/').pop();
      const template = contextualReminderTemplates.find(
        (item) => item.template_key === templateKey,
      );
      return route.fulfill({ json: { ...template, ...request.postDataJSON() } });
    }
    if (path.endsWith('/notifications/read-all')) {
      notificationsRead = true;
      return route.fulfill({ json: { updated: 2 } });
    }
    if (/\/notifications\/\d+\/open$/.test(path)) {
      const stale = options.notificationState === 'stale';
      notificationsRead = true;
      return route.fulfill({
        json: {
          destination: stale
            ? '/app?section=profile#profile-notifications'
            : '/app?workout_id=43&comment_id=91&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
          stale,
          message: stale
            ? 'Связанный объект больше недоступен. Вы вернулись в центр уведомлений.'
            : null,
        },
      });
    }
    if (path.endsWith('/notifications') && request.method() === 'GET') {
      if (!options.notificationState || options.notificationState === 'empty') {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({
        json: [
          {
            id: 91,
            category: 'trainer_comment',
            event_kind: 'transactional',
            title: 'Комментарий тренера к тренировке',
            body: 'Сохраняйте контролируемый темп в эксцентрической фазе и не ускоряйте последний повтор длинного рабочего подхода.',
            created_at: `${today}T10:15:00`,
            scheduled_for: `${today}T10:15:00`,
            delivery_status: 'sent',
            sent_at: `${today}T10:15:05`,
            read_at: notificationsRead ? `${today}T10:20:00` : null,
            action_url:
              '/app?workout_id=43&comment_id=91&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
          },
          {
            id: 92,
            category: 'measurement_reminder',
            event_kind: 'reminder',
            title: 'Пора обновить замеры',
            body: 'Регулярные замеры помогают видеть фактическую динамику без оценочных выводов.',
            created_at: `${today}T08:00:00`,
            scheduled_for: `${today}T09:00:00`,
            delivery_status: 'queued',
            sent_at: null,
            read_at: notificationsRead ? `${today}T10:20:00` : null,
            action_url: '/app?section=progress',
          },
        ],
      });
    }
    if (/\/workouts\/\d+\/comments$/.test(path)) return route.fulfill({ json: [] });
    if (path.endsWith('/nutrition/targets/history') && request.method() === 'GET') {
      return route.fulfill({ json: { items: targetHistory } });
    }
    if (path.endsWith('/nutrition/targets/current') && request.method() === 'GET') {
      return route.fulfill({ json: currentTarget });
    }
    if (path.endsWith('/nutrition/targets/manual') && request.method() === 'POST') {
      manualTargetSaves += 1;
      const body = request.postDataJSON() as {
        calories: number;
        protein_g: number;
        fat_g: number;
        carbs_g: number;
        effective_from: string;
        note?: string | null;
      };
      const repeated =
        currentTarget.effective_from === body.effective_from &&
        currentTarget.calories === body.calories &&
        currentTarget.protein_g === body.protein_g &&
        currentTarget.fat_g === body.fat_g &&
        currentTarget.carbs_g === body.carbs_g &&
        currentTarget.note === (body.note || null);
      if (!repeated) {
        const id = Number(currentTarget.id) + 1;
        const closedCurrent = {
          ...currentTarget,
          effective_to: body.effective_from,
          superseded_by_id: id,
        };
        currentTarget = {
          ...currentTarget,
          ...body,
          id,
          source: 'manual',
          effective_to: null,
          superseded_by_id: null,
          created_at: `${today}T10:00:00`,
          saved_at: `${today}T10:00:00`,
        };
        targetHistory = [currentTarget, closedCurrent, ...targetHistory.slice(1)];
      }
      return route.fulfill({ json: currentTarget });
    }
    if (path.endsWith('/nutrition/hydration') && request.method() === 'GET') {
      return route.fulfill({
        json: emptyHydrationDay(url.searchParams.get('diary_date') || today),
      });
    }
    if (path.endsWith('/nutrition/diary') && request.method() === 'GET') {
      const totals = nutritionTotals();
      return route.fulfill({
        json: {
          diary_date: url.searchParams.get('diary_date') || today,
          timezone: 'Europe/Moscow',
          meals: [
            { meal_type: 'breakfast', entries: nutritionEntries, totals },
            { meal_type: 'lunch', entries: [], totals: zeroNutrition },
            { meal_type: 'dinner', entries: [], totals: zeroNutrition },
            { meal_type: 'snacks', entries: [], totals: zeroNutrition },
          ],
          totals,
          targets: {
            energy_kcal: '2100.00',
            protein_g: '140.000',
            fat_g: '70.000',
            carbs_g: '230.000',
          },
          remaining: {
            energy_kcal: String(2100 - Number(totals.energy_kcal)),
            protein_g: String(140 - Number(totals.protein_g)),
            fat_g: String(70 - Number(totals.fat_g)),
            carbs_g: String(230 - Number(totals.carbs_g)),
          },
          status: nutritionEntries.length ? 'incomplete' : 'unlogged',
          status_is_explicit: false,
        },
      });
    }
    if (path.endsWith('/nutrition/foods/recent') || path.endsWith('/nutrition/foods/favorites')) {
      return route.fulfill({ json: { items: [oatmeal], total: 1, limit: 12, offset: 0 } });
    }
    if (path.endsWith('/nutrition/foods/barcode/3017620422003')) {
      return route.fulfill({
        json: {
          barcode: '3017620422003',
          status: 'found',
          provider_status: 'not_requested',
          local_item: { ...oatmeal, barcode: '3017620422003' },
          external_item: null,
        },
      });
    }
    if (path.endsWith('/nutrition/diary/entries') && request.method() === 'POST') {
      const body = request.postDataJSON() as {
        diary_date: string;
        meal_type: string;
        logged_at?: string | null;
        quick_add?: {
          name?: string | null;
          energy_kcal: number;
          protein_g?: number | null;
          fat_g?: number | null;
          carbs_g?: number | null;
        };
      };
      const isQuick = Boolean(body.quick_add);
      const entry = {
        id: 21 + nutritionEntries.length,
        diary_date: body.diary_date,
        meal_type: body.meal_type,
        food_id: isQuick ? null : oatmeal.id,
        recipe_id: null,
        entry_kind: isQuick ? 'quick_add' : 'food',
        logged_at: body.logged_at ?? null,
        food_name: body.quick_add?.name || (isQuick ? 'Быстрый ввод' : oatmeal.name),
        food_brand: null,
        amount: '1.000',
        amount_unit: 'serving',
        weight_g: '50.000',
        serving_amount: '1.000',
        serving_unit: 'serving',
        serving_weight_g: '50.000',
        nutrition: isQuick
          ? {
              energy_kcal: String(body.quick_add?.energy_kcal ?? 0),
              protein_g:
                body.quick_add?.protein_g == null ? null : String(body.quick_add.protein_g),
              fat_g: body.quick_add?.fat_g == null ? null : String(body.quick_add.fat_g),
              carbs_g: body.quick_add?.carbs_g == null ? null : String(body.quick_add.carbs_g),
              fiber_g: null,
            }
          : {
              energy_kcal: '180.00',
              protein_g: '6.000',
              fat_g: '3.000',
              carbs_g: '31.000',
              fiber_g: '4.000',
            },
        created_at: `${today}T07:00:00Z`,
        updated_at: `${today}T07:00:00Z`,
      };
      nutritionEntries = [...nutritionEntries, entry];
      return route.fulfill({ status: 201, json: entry });
    }
    if (path.endsWith('/nutrition/diary/copy/product') && request.method() === 'POST') {
      const source = nutritionEntries.find(
        (entry) => entry.id === request.postDataJSON().source_entry_id,
      );
      if (!source) return route.fulfill({ status: 404, json: { detail: 'Entry not found' } });
      const copied = {
        ...source,
        id: 21 + nutritionEntries.length,
        created_at: `${today}T08:00:00Z`,
        updated_at: `${today}T08:00:00Z`,
      };
      nutritionEntries = [...nutritionEntries, copied];
      return route.fulfill({
        status: 201,
        json: { copy_scope: 'product', replayed: false, entries: [copied] },
      });
    }
    return route.fulfill({
      status: 404,
      json: { detail: `Not available in platform smoke: ${path}` },
    });
  });

  return {
    setOffline(value) {
      offline = value;
    },
    failNextMeasurementSave() {
      failNextMeasurementSave = true;
    },
    measurementSaveCalls() {
      return measurementSaveCalls;
    },
    failNextCardioSave() {
      failNextCardioSave = true;
    },
    cardioSaveCalls() {
      return cardioSaveCalls;
    },
    authInitCalls() {
      return authInitCalls;
    },
    meCalls() {
      return meCalls;
    },
    trainerActivationCalls() {
      return trainerActivationCalls;
    },
    setPatchCalls() {
      return patchCalls;
    },
    finishCalls() {
      return finishCalls;
    },
    manualTargetSaves() {
      return manualTargetSaves;
    },
    targetHistoryLength() {
      return targetHistory.length;
    },
    weeklyDecisionCalls() {
      return [...weeklyDecisions];
    },
    weeklyReviewSubmits() {
      return weeklyReviewSubmits;
    },
    nutritionReportPeriods() {
      return [...requestedNutritionReportPeriods];
    },
    workoutValues() {
      return { ...setValues };
    },
    completionFeedback() {
      return { feedback: completionFeedback, note: completionNote };
    },
    adaptationApplyCalls() {
      return adaptationApplyCalls;
    },
    setAdaptationApplyMode(mode) {
      adaptationApplyMode = mode;
    },
    accountExportCreates() {
      return accountExportCreates;
    },
    accountUnlinks() {
      return [...accountUnlinks];
    },
    accountDeletes() {
      return accountDeletes;
    },
    failNextAvatarUpload() {
      failNextAvatarUpload = true;
    },
    avatarUploads() {
      return avatarUploads;
    },
    avatarDeletes() {
      return avatarDeletes;
    },
  };
}
