import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { ApiError, api } from '../../shared/api/client';
import type {
  CardioSession,
  FoodDiaryDay,
  HydrationDay,
  ProgressSummary,
  WeeklyCheckInCurrent,
  Workout,
  WorkoutComment,
  WorkoutScheduleItem,
} from '../../shared/api/types';
import {
  calendarWeek,
  dateInputValue,
  detectedTimeZone,
  formatCalendarDate,
} from '../../shared/dateTime';
import { AppLink, useNavigation } from '../../shared/navigation/router';
import { queryKeys } from '../../shared/queryKeys';
import { crossContextCoordinator } from '../../shared/browser/crossContextLock';
import {
  activeWorkoutLockName,
  loadActiveWorkoutQueue,
  loadCurrentActiveWorkoutSnapshot,
  saveActiveWorkoutSnapshot,
} from '../workouts/activeWorkoutQueue';
import { WorkoutAdaptation } from '../workouts/WorkoutAdaptation';
import { TodayWorkout } from '../workouts/TodayWorkout';
import { Badge, Button, SemanticCard, Skeleton } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { CardioQuickLog } from '../cardio/CardioLogging';
import { DailyWellbeingCheckIn } from '../wellbeing/DailyWellbeingCheckIn';
import {
  nextActionHref,
  selectNextAction,
  type NextAction,
  type NextActionKind,
} from './nextAction';
import {
  TRAINING_WEEK_LEGEND,
  WeekStrip,
  type WeekStripActivity,
  type WeekStripDayMeta,
  type WeekStripStatus,
} from '../../shared/ui/WeekStrip';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import { isPwaStandalone } from '../../shared/pwa/pwaRuntime';
import { useRuntimeCapabilities } from '../../shared/runtime/runtime';

export function formatTodayHeading(value: string): { title: string } {
  const weekday = formatCalendarDate(value, { weekday: 'long' });
  const date = formatCalendarDate(value, { day: 'numeric', month: 'long' });
  return {
    title: `Сегодня · ${weekday}, ${date}`,
  };
}

const weekStatusPriority = ['in_progress', 'completed', 'planned', 'skipped'] as const;

function weekWorkoutForDate(
  workouts: WorkoutScheduleItem[] | undefined,
  value: string,
): WorkoutScheduleItem | undefined {
  const matches = workouts?.filter((item) => item.scheduled_date === value) ?? [];
  const priority = (status: string) => {
    const index = weekStatusPriority.indexOf(status as (typeof weekStatusPriority)[number]);
    return index === -1 ? weekStatusPriority.length : index;
  };
  return matches.sort((left, right) => priority(left.status) - priority(right.status))[0];
}

function weekStatus(
  item: WorkoutScheduleItem | undefined,
  date: string,
  today: string,
): WeekStripStatus | null {
  if (!item) return null;
  if (item.status === 'completed') return { key: 'completed', label: 'Выполнено' };
  if (item.status === 'in_progress') {
    return { key: 'in-progress', label: 'В процессе' };
  }
  if (item.status === 'skipped') return { key: 'skipped', label: 'Пропущено' };
  if (item.status === 'planned' && date > today) {
    return { key: 'upcoming', label: 'Предстоит тренировка' };
  }
  if (item.status === 'planned') {
    return { key: 'planned', label: 'Запланировано' };
  }
  return null;
}

function weekCardioForDate(
  sessions: CardioSession[] | undefined,
  value: string,
  timeZone: string,
): CardioSession[] {
  return (sessions ?? []).filter(
    (session) => dateInputValue(new Date(session.scheduled_at), timeZone) === value,
  );
}

function combinedWeekStatus(
  workout: WorkoutScheduleItem | undefined,
  cardio: CardioSession[],
  date: string,
  today: string,
): WeekStripStatus | null {
  if (workout && cardio.length === 0) return weekStatus(workout, date, today);
  const statuses = [workout?.status, ...cardio.map((session) => session.status)].filter(
    (status): status is string => Boolean(status),
  );
  if (statuses.length === 0) return null;
  if (statuses.includes('in_progress')) {
    return { key: 'in-progress', label: 'В процессе' };
  }
  if (statuses.every((status) => status === 'completed')) {
    return { key: 'completed', label: 'Выполнено' };
  }
  if (statuses.includes('completed')) {
    return { key: 'in-progress', label: 'Часть плана выполнена' };
  }
  if (statuses.every((status) => status === 'skipped')) {
    return { key: 'skipped', label: 'Пропущено' };
  }
  if (statuses.includes('planned')) {
    return {
      key: date > today ? 'upcoming' : 'planned',
      label: date > today ? 'Запланировано' : 'План на сегодня',
    };
  }
  return weekStatus(workout, date, today);
}

function WeekContext({
  cardio,
  selectedDate,
  today,
  timeZone,
  workouts,
  loading,
  error,
  onRetry,
  onSelect,
}: {
  cardio?: CardioSession[];
  selectedDate: string;
  today: string;
  timeZone: string;
  workouts?: WorkoutScheduleItem[];
  loading: boolean;
  error: boolean;
  onRetry(): void;
  onSelect(value: string): void;
}) {
  return (
    <WeekStrip
      anchorDate={today}
      ariaLabel="Эта неделя"
      getDayMeta={(date): WeekStripDayMeta => {
        const item = weekWorkoutForDate(workouts, date);
        const cardioSessions = weekCardioForDate(cardio, date, timeZone);
        const status = combinedWeekStatus(item, cardioSessions, date, today);
        const activities: WeekStripActivity[] = [];
        if (item) activities.push({ key: 'strength', label: 'Силовая' });
        if (cardioSessions.length > 0) {
          activities.push({ key: 'cardio', label: 'Кардио' });
        }
        if (activities.length === 0 && !loading && !error) {
          activities.push({ key: 'rest', label: 'Отдых' });
        }
        return {
          activities,
          status,
        };
      }}
      headerAction={
        error ? (
          <button className="today-text-link" type="button" onClick={onRetry}>
            Обновить план
          </button>
        ) : undefined
      }
      loading={loading}
      loadingLabel="Загружаем план недели"
      legend={TRAINING_WEEK_LEGEND}
      mode="picker"
      onSelect={onSelect}
      selectedDate={selectedDate}
      title="Эта неделя"
      today={today}
    />
  );
}

function formatWorkoutDate(value: string, today: string): string {
  if (value === today) return 'сегодня';
  return formatCalendarDate(value, { weekday: 'long', day: 'numeric', month: 'short' });
}

function formatAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(Math.round(numeric)) : '—';
}

function finiteAmount(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function validDiaryRemaining(
  total: string | number | null | undefined,
  target: string | number | null | undefined,
  remaining: string | number | null | undefined,
): number | null {
  const totalAmount = finiteAmount(total);
  const targetAmount = finiteAmount(target);
  const remainingAmount = finiteAmount(remaining);
  if (totalAmount === null || targetAmount === null || remainingAmount === null) return null;
  return Math.abs(targetAmount - totalAmount - remainingAmount) <= 0.01 ? remainingAmount : null;
}

const nutritionMacroRows = [
  { key: 'protein_g', label: 'Белок' },
  { key: 'fat_g', label: 'Жиры' },
  { key: 'carbs_g', label: 'Углеводы' },
] as const;

const cardioActivityLabels: Record<CardioSession['activity_type'], string> = {
  walking: 'ходьба',
  running: 'бег',
  elliptical: 'эллиптический тренажёр',
  stationary_bike: 'велотренажёр',
  cycling: 'велосипед',
  rowing: 'гребля',
  stepper: 'степпер',
  swimming: 'плавание',
  other: 'активность',
};

function cardioSessionsCountLabel(value: number): string {
  const lastTwo = value % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return `${value} сессий`;
  const last = value % 10;
  if (last === 1) return `${value} сессия`;
  if (last >= 2 && last <= 4) return `${value} сессии`;
  return `${value} сессий`;
}

function compactSignal(value: string, maxLength = 140): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > maxLength
    ? `${normalized.slice(0, maxLength - 1).trimEnd()}…`
    : normalized;
}

function workoutStatusLabel(status: string): string {
  if (status === 'in_progress') return 'В процессе';
  if (status === 'completed') return 'Завершена';
  return 'Запланирована';
}

export function formatNutritionDateLabel(value: string, today: string): string {
  if (value === today) return 'сегодня';
  return formatCalendarDate(value, { day: 'numeric', month: 'long', year: 'numeric' });
}

function NutritionSummary({ date, today }: { date: string; today: string }) {
  const diary = useQuery({
    queryKey: ['nutrition', 'diary', date],
    queryFn: () => api<FoodDiaryDay>(`/api/v1/nutrition/diary?diary_date=${date}`),
  });
  const hydration = useQuery({
    queryKey: queryKeys.nutrition.hydrationDate(date),
    queryFn: () => api<HydrationDay>(`/api/v1/nutrition/hydration?diary_date=${date}`),
  });

  if (diary.isLoading) {
    return (
      <section className="today-panel today-summary-card">
        <div aria-label="Загружаем питание" className="today-summary-skeleton" role="status">
          <Skeleton height="48px" width="100%" />
        </div>
      </section>
    );
  }

  if (diary.error || !diary.data) {
    return (
      <section className="today-panel today-inline-state" role="alert">
        <strong>Сводка питания временно недоступна</strong>
        <button className="today-text-link" type="button" onClick={() => void diary.refetch()}>
          Повторить
        </button>
      </section>
    );
  }

  const hasFoodEntries = diary.data.meals.some((meal) => meal.entries.length > 0);
  const calorieTotal = finiteAmount(diary.data.totals.energy_kcal);
  const calorieTarget = finiteAmount(diary.data.targets?.energy_kcal);
  const calorieRemaining = hasFoodEntries
    ? validDiaryRemaining(
        diary.data.totals.energy_kcal,
        diary.data.targets?.energy_kcal,
        diary.data.remaining?.energy_kcal,
      )
    : null;
  const foodSummary =
    diary.data.status === 'fasted' ? 'День отмечен как постный' : 'Записей за день пока нет';
  const hydrationSummary = hydration.data
    ? hydration.data.entries.length === 0
      ? 'Вода пока не записана'
      : hydration.data.goal?.enabled && hydration.data.goal.target_ml
        ? `Вода ${hydration.data.total_ml} из ${hydration.data.goal.target_ml} мл`
        : `Вода ${hydration.data.total_ml} мл`
    : hydration.isLoading
      ? 'Вода загружается…'
      : 'Вода недоступна';
  const dateLabel = formatNutritionDateLabel(date, today);
  const nutritionTitle = date === today ? 'Питание на сегодня' : `Питание за ${dateLabel}`;
  const caloriesLabel = date === today ? 'Калории за сегодня' : `Калории за ${dateLabel}`;
  const calorieValueLabel =
    calorieTarget === null
      ? `${formatAmount(diary.data.totals.energy_kcal)} ккал`
      : `${formatAmount(diary.data.totals.energy_kcal)} из ${formatAmount(diary.data.targets?.energy_kcal)} ккал`;
  return (
    <section className="today-nutrition" aria-label={nutritionTitle}>
      <h2>
        <Icon name="nav-nutrition" size={16} />
        {nutritionTitle}
      </h2>
      <div className="today-nutrition__content">
        <div className="today-nutrition__food-group">
          <div className="today-nutrition__values">
            {hasFoodEntries ? (
              <>
                <p aria-label={`${caloriesLabel}: ${calorieValueLabel}`}>
                  <strong>{formatAmount(diary.data.totals.energy_kcal)}</strong>
                  {diary.data.targets
                    ? ` / ${formatAmount(diary.data.targets.energy_kcal)}`
                    : ''}{' '}
                  ккал
                </p>
                {calorieRemaining !== null && (
                  <small className="today-nutrition__remaining">
                    {calorieRemaining >= 0
                      ? `Осталось ${formatAmount(calorieRemaining)} ккал`
                      : `Выше ориентира на ${formatAmount(Math.abs(calorieRemaining))} ккал`}
                  </small>
                )}
                {diary.data.targets &&
                  calorieTotal !== null &&
                  calorieTarget !== null &&
                  calorieTarget > 0 && (
                    <progress aria-label={caloriesLabel} max={calorieTarget} value={calorieTotal} />
                  )}
                <dl className="today-nutrition__macros" aria-label="Белки, жиры и углеводы">
                  {nutritionMacroRows.map(({ key, label }) => {
                    const total = diary.data.totals[key];
                    const target = diary.data.targets?.[key];
                    const targetAmount = finiteAmount(target);
                    return (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>
                          {targetAmount === null
                            ? `${formatAmount(total)} г`
                            : `${formatAmount(total)} / ${formatAmount(target)} г`}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
              </>
            ) : (
              <p>{foodSummary}</p>
            )}
          </div>
          <AppLink
            className="today-summary-card__action"
            to={`/app?section=nutrition&date=${date}`}
            aria-label="Открыть дневник питания"
          >
            <span className="today-nutrition__action-label-full">Открыть дневник питания</span>
            <span className="today-nutrition__action-label-compact" aria-hidden="true">
              Открыть дневник
            </span>
          </AppLink>
        </div>
        <div className="today-nutrition__water">
          <span>{hydrationSummary}</span>
          <AppLink
            className="today-summary-card__action"
            to={`/app?section=nutrition&date=${date}&hydration=quick`}
            aria-label="+ Вода"
          >
            <Icon name="plus" size={16} /> Вода
          </AppLink>
        </div>
      </div>
    </section>
  );
}

function ActivitySummary({
  cardio,
  date,
  error,
  loading,
  timeZone,
  today,
}: {
  cardio?: CardioSession[];
  date: string;
  error: boolean;
  loading: boolean;
  timeZone: string;
  today: string;
}) {
  if (loading || error) return null;
  const completedSessions = weekCardioForDate(cardio, date, timeZone).filter(
    (session) =>
      session.status === 'completed' && (finiteAmount(session.duration_minutes) ?? 0) > 0,
  );
  if (completedSessions.length === 0) return null;

  const totalDuration = completedSessions.reduce(
    (total, session) => total + (finiteAmount(session.duration_minutes) ?? 0),
    0,
  );
  const summary =
    completedSessions.length === 1
      ? `Кардио · ${cardioActivityLabels[completedSessions[0]!.activity_type]} · ${formatAmount(totalDuration)} мин`
      : `${cardioSessionsCountLabel(completedSessions.length)} · ${formatAmount(totalDuration)} мин`;
  const dateLabel = date === today ? 'сегодня' : formatNutritionDateLabel(date, today);

  return (
    <section className="today-activity-grid" aria-label={`Активность за ${dateLabel}`}>
      <SemanticCard
        action={<AppLink to="/app?section=progress&view=cardio">Открыть кардио</AppLink>}
        className="today-panel today-summary-card today-summary-card--activity"
        family="training"
        icon="nav-today"
        summary={summary}
        title="Активность"
        variant="action"
      />
    </section>
  );
}

function ProgressSummaryPanel({ summary }: { summary: ReturnType<typeof useProgressSummary> }) {
  if (summary.isLoading) {
    return (
      <section className="today-progress-grid" aria-label="Загружаем прогресс">
        <Skeleton className="today-progress-skeleton" height="76px" width="100%" />
      </section>
    );
  }
  if (summary.error || !summary.data) {
    return (
      <section className="today-panel today-inline-state today-progress-unavailable" role="alert">
        <span>Прогресс временно недоступен. Остальные данные на экране актуальны.</span>
        <button className="today-text-link" type="button" onClick={() => void summary.refetch()}>
          Повторить
        </button>
      </section>
    );
  }

  const completedWorkouts = summary.data.training.completed_workouts;
  const latestWeight = summary.data.body.latest_measurement?.weight_kg;
  const progressSignal =
    latestWeight != null
      ? `последний вес ${latestWeight.toLocaleString('ru-RU')} кг`
      : completedWorkouts > 0
        ? `${completedWorkouts} ${completedWorkouts === 1 ? 'тренировка' : completedWorkouts < 5 ? 'тренировки' : 'тренировок'} за 30 дней`
        : null;

  return (
    <section className="today-progress-grid" aria-label="Главное о прогрессе">
      <SemanticCard
        action={<AppLink to="/app?section=progress">Открыть прогресс</AppLink>}
        className="today-panel today-summary-card today-summary-card--progress"
        family="progress"
        icon="nav-progress"
        summary={progressSignal ?? 'Появится после первых тренировок и замеров'}
        title="Прогресс"
        variant="action"
      />
    </section>
  );
}

function useProgressSummary() {
  return useQuery({
    queryKey: queryKeys.progress.summary(30),
    queryFn: () => api<ProgressSummary>('/api/v1/workouts/progress/summary?period_days=30'),
  });
}

function WorkoutOverview({
  today,
  workout,
  todayScheduleItem,
  weeklyReview,
  trainerComment,
  progress,
  detailsOpen,
  startPending,
  onOpenDetails,
  onAddActivity,
  onStart,
  canMutateProgress,
  profileBlocksRecommendation,
}: {
  today: string;
  workout?: Workout;
  todayScheduleItem?: WorkoutScheduleItem;
  weeklyReview?: WeeklyCheckInCurrent;
  trainerComment?: WorkoutComment;
  progress: ReturnType<typeof useProgressSummary>;
  detailsOpen: boolean;
  startPending: boolean;
  onOpenDetails(): void;
  onAddActivity(): void;
  onStart(workoutId: number): void;
  canMutateProgress: boolean;
  profileBlocksRecommendation: boolean;
}) {
  const { user } = useAuth();
  const totalSets =
    workout?.exercises.reduce((sum, exercise) => sum + exercise.sets.length, 0) ?? 0;
  const completedSets =
    workout?.exercises.reduce(
      (sum, exercise) => sum + exercise.sets.filter((set) => set.is_completed).length,
      0,
    ) ?? 0;
  const completedToday = !workout && progress.data?.training.last_completed_workout_on === today;
  const nextWorkout = progress.data?.training.next_workout;
  const plan = selectNextAction({
    today,
    hasActiveProgram: Boolean(user?.has_active_program),
    workout,
    todayScheduleItem,
    trainerComment,
    weeklyReview,
    lastCompletedWorkoutOn: progress.data?.training.last_completed_workout_on,
    nextWorkout,
    profileBlocksRecommendation,
  });
  const primaryActionKind = plan.primary.kind;
  const secondaryActionKinds = plan.secondary.map((item) => item.kind).join('|');

  useEffect(() => {
    trackProductEvent(
      {
        name: 'next_action_shown',
        surface: productEventSurface(),
        action_kind: primaryActionKind,
        position: 'primary',
      },
      { dedupe: 'session', dedupeKey: `next-action:${primaryActionKind}:primary` },
    );
    for (const kind of secondaryActionKinds.split('|').filter(Boolean)) {
      trackProductEvent(
        {
          name: 'next_action_shown',
          surface: productEventSurface(),
          action_kind: kind as NextActionKind,
          position: 'secondary',
        },
        { dedupe: 'session', dedupeKey: `next-action:${kind}:secondary` },
      );
    }
  }, [primaryActionKind, secondaryActionKinds]);

  const trackNextActionClick = (item: NextAction, position: 'primary' | 'secondary') => {
    trackProductEvent({
      name: 'next_action_clicked',
      surface: productEventSurface(),
      action_kind: item.kind,
      position,
    });
    const destination =
      item.kind === 'active_workout' || item.kind === 'scheduled_workout'
        ? 'workout'
        : item.kind === 'weekly_review'
          ? 'weekly_review'
          : item.kind === 'ready_program' || item.kind === 'create_program'
            ? 'programs'
            : item.kind === 'nutrition'
              ? 'nutrition'
              : item.kind === 'trainer_feedback' || item.kind === 'workout_result'
                ? 'progress'
                : null;
    if (position === 'primary' && destination) {
      trackProductEvent({
        name: 'today_primary_action_selected',
        surface: productEventSurface(),
        destination,
      });
    }
  };

  const renderActionLink = (item: NextAction, position: 'primary' | 'secondary') => {
    if (item.target.type === 'activity') {
      return (
        <Button
          disabled={!canMutateProgress}
          fullWidth
          key={`${item.kind}-${position}`}
          variant="secondary"
          type="button"
          onClick={() => {
            trackNextActionClick(item, position);
            onAddActivity();
          }}
        >
          {item.title}
        </Button>
      );
    }
    return (
      <AppLink
        className={position === 'primary' ? 'button-link' : 'button-link secondary-link'}
        key={`${item.kind}-${position}`}
        onClick={() => trackNextActionClick(item, position)}
        to={nextActionHref(item.target)}
      >
        {item.title}
      </AppLink>
    );
  };

  const renderPrimaryWorkoutAction = (item: NextAction) => {
    const started = workout?.status === 'in_progress';
    const workoutId = item.target.type === 'today_workout' ? item.target.workoutId : null;
    return (
      <Button
        className="today-pulse-action"
        fullWidth
        disabled={startPending}
        type="button"
        onClick={() => {
          trackNextActionClick(item, 'primary');
          if (started) onOpenDetails();
          else if (workoutId !== null) onStart(workoutId);
        }}
      >
        {startPending ? 'Начинаем…' : started ? 'Продолжить тренировку' : 'Начать тренировку'}
      </Button>
    );
  };

  const renderActions = (className = 'today-workout-actions') => (
    <div className={className}>
      {plan.primary.kind === 'active_workout' || plan.primary.kind === 'scheduled_workout'
        ? renderPrimaryWorkoutAction(plan.primary)
        : renderActionLink(plan.primary, 'primary')}
      {plan.secondary.map((item) => renderActionLink(item, 'secondary'))}
      {workout?.status === 'planned' && !plan.secondary.length && !detailsOpen && (
        <Button fullWidth variant="secondary" type="button" onClick={onOpenDetails}>
          Посмотреть упражнения
        </Button>
      )}
      {workout?.status === 'planned' &&
        (canMutateProgress ? (
          <WorkoutAdaptation workout={workout} entryContext="today" />
        ) : (
          <p className="muted demo-capability-notice" role="status">
            Изменение плана тренировки доступно после входа.
          </p>
        ))}
      {!canMutateProgress && plan.secondary.some((item) => item.target.type === 'activity') && (
        <p className="muted demo-capability-notice" role="status">
          Добавление активности доступно после входа.
        </p>
      )}
    </div>
  );

  if (workout?.status === 'completed') {
    return (
      <>
        <div className="today-workout-copy">
          <Badge tone="success">Готово</Badge>
          <h2 id="today-workout-title">Тренировка завершена</h2>
          <p>Результат сохранён. Следующее действие — восстановиться и продолжить план.</p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (workout) {
    const started = workout.status === 'in_progress';
    return (
      <>
        <div className="today-workout-copy">
          <div className="today-workout-copy__status">
            <Badge tone={started ? 'warning' : 'neutral'}>
              {workoutStatusLabel(workout.status)}
            </Badge>
            <span>
              {workout.scheduled_time ? `${workout.scheduled_time.slice(0, 5)} · ` : ''}
              День {workout.day_number}
            </span>
          </div>
          <img
            className="today-workout-photo"
            src="/assets/marketing/strength-row.webp"
            alt=""
            width="1536"
            height="1024"
          />
          <h2 id="today-workout-title">{workout.title}</h2>
          <p>
            {started
              ? `${completedSets} из ${totalSets} подходов отмечено`
              : `${workout.exercises.length} упражнений · ${totalSets} подходов`}
          </p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (completedToday) {
    return (
      <>
        <div className="today-workout-copy">
          <Badge tone="success">Готово</Badge>
          <h2 id="today-workout-title">Тренировка завершена</h2>
          <p>
            {nextWorkout
              ? `Следующая — ${formatWorkoutDate(nextWorkout.scheduled_date, today)}${nextWorkout.scheduled_time ? ` в ${nextWorkout.scheduled_time.slice(0, 5)}` : ''}.`
              : 'На сегодня главное действие выполнено.'}
          </p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (todayScheduleItem?.status === 'planned') {
    return (
      <>
        <div className="today-workout-copy">
          <Badge>План на сегодня</Badge>
          <h2 id="today-workout-title">{todayScheduleItem.title}</h2>
          <p>Тренировка запланирована на сегодня. Откройте её, чтобы начать.</p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (plan.primary.kind === 'trainer_feedback') {
    return (
      <>
        <div className="today-workout-copy">
          <Badge tone="warning">Комментарий тренера</Badge>
          <h2 id="today-workout-title">Тренер оставил комментарий</h2>
          <p>{trainerComment ? compactSignal(trainerComment.body) : ''}</p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (plan.primary.kind === 'weekly_review') {
    return (
      <>
        <div className="today-workout-copy">
          <Badge>Итоги недели</Badge>
          <h2 id="today-workout-title">Неделя готова к проверке</h2>
          <p>Коротко отметьте нагрузку, восстановление и то, насколько легко было держать план.</p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (plan.primary.kind === 'profile') {
    return (
      <>
        <div className="today-workout-copy">
          <Badge>Основа рекомендаций</Badge>
          <h2 id="today-workout-title">Дополните профиль</h2>
          <p>{plan.primary.context}.</p>
        </div>
        {renderActions()}
      </>
    );
  }

  if (!user?.has_active_program) {
    return (
      <>
        <div className="today-workout-copy">
          <span className="today-workout-copy__marker" aria-hidden="true">
            01
          </span>
          <h2 id="today-workout-title">С чего начнём?</h2>
          <p>Настройки можно заполнить позже. Выберите полезное действие прямо сейчас.</p>
        </div>
        {renderActions('today-workout-actions today-workout-actions--quick-start')}
      </>
    );
  }

  return (
    <>
      <div className="today-workout-copy">
        <Badge>Восстановление</Badge>
        <h2 id="today-workout-title">Сегодня без тренировки</h2>
        <p>
          {nextWorkout
            ? `Ближайшая — ${formatWorkoutDate(nextWorkout.scheduled_date, today)}${nextWorkout.scheduled_time ? ` в ${nextWorkout.scheduled_time.slice(0, 5)}` : ''}: ${nextWorkout.title}.`
            : 'В активном плане пока нет ближайшей тренировки.'}
        </p>
      </div>
      {renderActions()}
    </>
  );
}

function millisecondsUntilNextCalendarDay(timeZone: string): number {
  const now = Date.now();
  const currentDay = dateInputValue(new Date(now), timeZone);
  let lowerBound = now;
  let upperBound = now + 30 * 60 * 60 * 1000;

  while (dateInputValue(new Date(upperBound), timeZone) === currentDay) {
    upperBound += 12 * 60 * 60 * 1000;
  }
  while (upperBound - lowerBound > 1_000) {
    const candidate = Math.floor((lowerBound + upperBound) / 2);
    if (dateInputValue(new Date(candidate), timeZone) === currentDay) lowerBound = candidate;
    else upperBound = candidate;
  }
  return Math.max(1_000, upperBound - now + 100);
}

function useCalendarDay(timeZone: string): string {
  const [day, setDay] = useState(() => dateInputValue(new Date(), timeZone));

  useEffect(() => {
    let timer: number | undefined;
    const scheduleNextDay = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      timer = window.setTimeout(refresh, millisecondsUntilNextCalendarDay(timeZone));
    };
    const refresh = () => {
      setDay((current) => {
        const next = dateInputValue(new Date(), timeZone);
        return next === current ? current : next;
      });
      scheduleNextDay();
    };
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };

    refresh();
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [timeZone]);

  return day;
}

export function TodayDashboard({
  initialWellbeingDate,
  initialWellbeingOpen = false,
  initialCardioOpen = false,
}: {
  initialWellbeingDate?: string;
  initialWellbeingOpen?: boolean;
  initialCardioOpen?: boolean;
} = {}) {
  const { user } = useAuth();
  const capabilities = useRuntimeCapabilities();
  const { toast } = useFeedback();
  const { navigate, search } = useNavigation();
  const queryClient = useQueryClient();
  const detailsRef = useRef<HTMLDivElement>(null);
  const autoOpenedCompletionRef = useRef<number | null>(null);
  const previousCardioOpenRef = useRef(initialCardioOpen);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [cardioOpenRequest, setCardioOpenRequest] = useState(initialCardioOpen ? 1 : 0);
  const wellbeingRequested = Boolean(initialWellbeingOpen || initialWellbeingDate);
  const timeZone = user?.profile?.timezone || detectedTimeZone();
  const today = useCalendarDay(timeZone);
  const [selectedDate, setSelectedDate] = useState(today);

  useEffect(() => {
    if (initialCardioOpen && !previousCardioOpenRef.current) {
      setCardioOpenRequest((current) => current + 1);
    }
    previousCardioOpenRef.current = initialCardioOpen;
  }, [initialCardioOpen]);

  const dismissCardioRequest = () => {
    const params = new URLSearchParams(search);
    if (params.get('cardio') !== '1') return;
    params.delete('cardio');
    const nextSearch = params.toString();
    navigate(`/app${nextSearch ? `?${nextSearch}` : ''}`, true);
  };
  const calendarContextRef = useRef(`${timeZone}:${today}`);
  const heading =
    selectedDate === today
      ? formatTodayHeading(today)
      : {
          title: formatCalendarDate(selectedDate, {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
          }),
        };
  const progress = useProgressSummary();
  const weekDates = calendarWeek(today);
  const weekStart = weekDates[0] ?? today;
  const weekEnd = weekDates.at(-1) ?? today;
  const week = useQuery({
    queryKey: ['workout', 'week'],
    queryFn: () => api<WorkoutScheduleItem[]>('/api/v1/workouts/week'),
  });
  const cardioWeek = useQuery({
    queryKey: queryKeys.cardio.range(weekStart, weekEnd),
    queryFn: () =>
      api<CardioSession[]>(
        `/api/v1/workouts/cardio?date_from=${weekStart}&date_to=${weekEnd}&limit=100`,
      ),
  });
  const weeklyReview = useQuery({
    queryKey: ['weekly-check-ins', 'current'],
    queryFn: () => api<WeeklyCheckInCurrent>('/api/v1/check-ins/weekly/current'),
  });
  const workout = useQuery({
    queryKey: ['workout', 'today'],
    queryFn: () => api<Workout>('/api/v1/workouts/today'),
    initialData: () => (user ? loadCurrentActiveWorkoutSnapshot(user.id) : undefined),
    initialDataUpdatedAt: 0,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const noTodayWorkout = workout.error instanceof ApiError && workout.error.status === 404;
  const hasPendingLocalChanges = Boolean(
    user && workout.data && loadActiveWorkoutQueue(user.id, workout.data.id).queue.length > 0,
  );
  const visibleWorkout = noTodayWorkout && !hasPendingLocalChanges ? undefined : workout.data;

  const persistSnapshotOnSuspend = useCallback(() => {
    if (!user || !workout.data || workout.data.status !== 'in_progress') return;
    void crossContextCoordinator
      .run(activeWorkoutLockName(user.id, workout.data.id), () => {
        saveActiveWorkoutSnapshot(user.id, workout.data!);
      })
      .catch(() => undefined);
  }, [user, workout.data]);

  useEffect(() => {
    const refreshOnReturn = () => {
      if (document.visibilityState !== 'visible' || !navigator.onLine) return;
      void queryClient.invalidateQueries({ queryKey: ['workout', 'today'], exact: true });
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') persistSnapshotOnSuspend();
      else refreshOnReturn();
    };
    window.addEventListener('pagehide', persistSnapshotOnSuspend);
    window.addEventListener('freeze', persistSnapshotOnSuspend);
    window.addEventListener('pageshow', refreshOnReturn);
    window.addEventListener('focus', refreshOnReturn);
    window.addEventListener('online', refreshOnReturn);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      window.removeEventListener('pagehide', persistSnapshotOnSuspend);
      window.removeEventListener('freeze', persistSnapshotOnSuspend);
      window.removeEventListener('pageshow', refreshOnReturn);
      window.removeEventListener('focus', refreshOnReturn);
      window.removeEventListener('online', refreshOnReturn);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [persistSnapshotOnSuspend, queryClient]);

  useEffect(() => {
    if (!user || !isPwaStandalone() || workout.fetchStatus !== 'idle') return;
    const snapshot = loadCurrentActiveWorkoutSnapshot(user.id);
    if (!snapshot || snapshot.status !== 'in_progress') return;
    const resumed = visibleWorkout?.id === snapshot.id && visibleWorkout.status === 'in_progress';
    trackProductEvent(
      {
        name: resumed ? 'pwa_workout_resume_success' : 'pwa_workout_resume_failure',
        surface: productEventSurface(),
      },
      { dedupe: 'session', dedupeKey: `workout:${snapshot.id}` },
    );
  }, [user, visibleWorkout, workout.fetchStatus]);

  const todayScheduleItem =
    weekWorkoutForDate(week.data, today) ??
    (visibleWorkout
      ? {
          id: visibleWorkout.id,
          scheduled_date: visibleWorkout.scheduled_date,
          scheduled_time: visibleWorkout.scheduled_time,
          title: visibleWorkout.title,
          status: visibleWorkout.status,
          day_number: visibleWorkout.day_number,
          week_number: visibleWorkout.week_number,
        }
      : undefined);
  const selectedScheduleItem = weekWorkoutForDate(week.data, selectedDate);
  const comments = useQuery({
    queryKey: todayScheduleItem
      ? queryKeys.workoutComments.client(todayScheduleItem.id)
      : ['workout', 'comments', 'today', 'disabled'],
    queryFn: () => api<WorkoutComment[]>(`/api/v1/workouts/${todayScheduleItem!.id}/comments`),
    enabled: Boolean(todayScheduleItem),
  });
  const trainerComment = comments.data
    ?.slice()
    .sort(
      (left, right) =>
        new Date(right.created_at).getTime() - new Date(left.created_at).getTime() ||
        right.id - left.id,
    )[0];

  useEffect(() => {
    if (
      visibleWorkout?.status !== 'completed' ||
      autoOpenedCompletionRef.current === visibleWorkout.id
    )
      return;
    autoOpenedCompletionRef.current = visibleWorkout.id;
    setDetailsOpen(true);
  }, [visibleWorkout?.id, visibleWorkout?.status]);
  const profileMissing = useMemo(
    () =>
      Boolean(
        user &&
        !user.has_active_program &&
        (!user.profile ||
          !user.profile.goal ||
          !user.profile.level ||
          !user.profile.workouts_per_week),
      ),
    [user],
  );
  const start = useMutation({
    mutationFn: (workoutId: number) =>
      api<Workout>(`/api/v1/workouts/${workoutId}/start`, { method: 'POST' }),
    onSuccess: async (startedWorkout) => {
      trackCoreProductEvent(
        { name: 'workout_started', surface: productEventSurface() },
        'workout_started',
      );
      trackProductEvent(
        {
          name: 'next_action_completed',
          surface: productEventSurface(),
          action_kind: 'scheduled_workout',
          position: 'primary',
        },
        { dedupe: 'session', dedupeKey: `next-action:scheduled-workout:${startedWorkout.id}` },
      );
      queryClient.setQueryData(['workout', 'today'], startedWorkout);
      queryClient.setQueryData<WorkoutScheduleItem[]>(['workout', 'week'], (items) =>
        items?.map((item) =>
          item.id === startedWorkout.id ? { ...item, status: startedWorkout.status } : item,
        ),
      );
      setDetailsOpen(true);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workout', 'week'], exact: true }),
        queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
      ]);
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  useEffect(() => {
    if (!detailsOpen) return;
    detailsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [detailsOpen]);

  useEffect(() => {
    const calendarContext = `${timeZone}:${today}`;
    if (calendarContextRef.current === calendarContext) return;
    calendarContextRef.current = calendarContext;
    setSelectedDate(today);
    setDetailsOpen(false);
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['workout', 'today'], exact: true }),
      queryClient.invalidateQueries({ queryKey: ['workout', 'week'], exact: true }),
      queryClient.invalidateQueries({ queryKey: ['weekly-check-ins', 'current'], exact: true }),
      queryClient.invalidateQueries({ queryKey: queryKeys.progress.summaries }),
    ]);
  }, [queryClient, timeZone, today]);

  const workoutFailed = Boolean(workout.error && !noTodayWorkout && !visibleWorkout);
  const priorityContextLoading = Boolean(
    !visibleWorkout &&
    user?.has_active_program &&
    (week.isLoading || weeklyReview.isLoading || (todayScheduleItem && comments.isLoading)),
  );

  if (detailsOpen && visibleWorkout) {
    return (
      <div className="today-workout-focus" ref={detailsRef}>
        <header className="today-workout-focus__header">
          <button className="today-text-link" type="button" onClick={() => setDetailsOpen(false)}>
            <Icon name="arrow-left" size={16} /> К сводке
          </button>
          <div>
            <span>{visibleWorkout.title}</span>
            <strong>
              {visibleWorkout.status === 'completed' ? 'Итог тренировки' : 'Текущая тренировка'}
            </strong>
          </div>
          <span>
            День {visibleWorkout.day_number} ·{' '}
            {visibleWorkout.status === 'completed'
              ? 'Завершена'
              : visibleWorkout.status === 'in_progress'
                ? 'В процессе'
                : 'План'}
          </span>
        </header>
        <TodayWorkout embedded onCompletionClose={() => setDetailsOpen(false)} />
      </div>
    );
  }

  return (
    <div className="today-dashboard today-dashboard--design-v2">
      <header className="today-dashboard__header">
        <p className="today-dashboard__date">{heading.title.replace(/^Сегодня · /, '')}</p>
        <h1 aria-label={heading.title}>СЕГОДНЯ</h1>
      </header>

      <div className="today-dashboard__overview">
        <div className="today-dashboard__training">
          <section
            className={`today-workout-spotlight semantic-card semantic-card--action semantic-card--training${noTodayWorkout ? ' today-workout-spotlight--rest-day' : ''}`}
            data-card-variant="action"
            data-semantic-family="training"
            aria-labelledby="today-workout-title"
          >
            {selectedDate !== today ? (
              week.isLoading ? (
                <div
                  className="today-summary-skeleton"
                  aria-label="Загружаем выбранный день"
                  role="status"
                >
                  <Skeleton height="34px" width="62%" />
                  <Skeleton height="20px" width="44%" />
                </div>
              ) : week.error ? (
                <div className="today-inline-state" role="alert">
                  <strong id="today-workout-title">Не удалось загрузить выбранный день</strong>
                  <button
                    className="today-text-link"
                    type="button"
                    onClick={() => void week.refetch()}
                  >
                    Повторить
                  </button>
                </div>
              ) : selectedScheduleItem ? (
                <div className="today-selected-day">
                  <h2 id="today-workout-title">{selectedScheduleItem.title}</h2>
                  <p>
                    {workoutStatusLabel(selectedScheduleItem.status)} ·{' '}
                    {formatWorkoutDate(selectedScheduleItem.scheduled_date, today)}
                  </p>
                  <AppLink
                    className="today-text-link"
                    to={
                      selectedScheduleItem.status === 'completed'
                        ? `/app?section=progress&workout_id=${selectedScheduleItem.id}`
                        : `/app?section=programs&workout_id=${selectedScheduleItem.id}&return_to=${encodeURIComponent('/app?section=today')}`
                    }
                  >
                    Открыть тренировку
                  </AppLink>
                </div>
              ) : (
                <div className="today-selected-day">
                  <h2 id="today-workout-title">Силовая тренировка не запланирована</h2>
                  <p>Выберите другой день или откройте программу тренировок.</p>
                </div>
              )
            ) : workout.isLoading ||
              priorityContextLoading ||
              (noTodayWorkout && progress.isLoading && user?.has_active_program) ? (
              <div
                className="today-summary-skeleton"
                aria-label="Проверяем план на сегодня"
                role="status"
              >
                <Skeleton height="34px" width="62%" />
                <Skeleton height="20px" width="44%" />
                <Skeleton height="48px" width="100%" />
              </div>
            ) : workoutFailed ? (
              <div className="today-inline-state" role="alert">
                <strong id="today-workout-title">Не удалось проверить тренировку</strong>
                <span>Остальные данные на экране доступны.</span>
                <button
                  className="today-text-link"
                  type="button"
                  onClick={() => void workout.refetch()}
                >
                  Повторить
                </button>
              </div>
            ) : (
              <WorkoutOverview
                today={today}
                workout={visibleWorkout}
                todayScheduleItem={todayScheduleItem}
                weeklyReview={weeklyReview.data}
                trainerComment={trainerComment}
                progress={progress}
                detailsOpen={detailsOpen}
                startPending={start.isPending}
                onOpenDetails={() => setDetailsOpen(true)}
                onAddActivity={() => setCardioOpenRequest((request) => request + 1)}
                onStart={(workoutId) => start.mutate(workoutId)}
                canMutateProgress={capabilities.canMutateProgress}
                profileBlocksRecommendation={profileMissing}
              />
            )}
          </section>

          <WeekContext
            cardio={cardioWeek.data}
            selectedDate={selectedDate}
            today={today}
            timeZone={timeZone}
            workouts={week.data}
            loading={week.isLoading || cardioWeek.isLoading}
            error={Boolean(week.error || cardioWeek.error)}
            onRetry={() => void Promise.all([week.refetch(), cardioWeek.refetch()])}
            onSelect={(date) => {
              setSelectedDate(date);
              setDetailsOpen(false);
              if (date !== today) {
                trackProductEvent({
                  name: 'today_week_navigated',
                  surface: productEventSurface(),
                  direction: 'workout_day',
                });
              }
            }}
          />
        </div>
        <div className="today-dashboard__facts">
          <NutritionSummary date={selectedDate} today={today} />
          <ActivitySummary
            cardio={cardioWeek.data}
            date={selectedDate}
            error={Boolean(cardioWeek.error)}
            loading={cardioWeek.isLoading}
            timeZone={timeZone}
            today={today}
          />
          <ProgressSummaryPanel summary={progress} />
          {user && wellbeingRequested && (
            <>
              {!capabilities.canMutateProgress && (
                <p className="muted demo-capability-notice" role="status">
                  Отметка самочувствия доступна после входа. В демо ответы не отправляются.
                </p>
              )}
              <fieldset
                className="demo-capability-fieldset"
                disabled={!capabilities.canMutateProgress}
              >
                <DailyWellbeingCheckIn
                  autoFocus={initialWellbeingOpen}
                  initialDate={initialWellbeingDate || selectedDate}
                  key={`${user.id}:${initialWellbeingDate || selectedDate}:${
                    initialWellbeingOpen ? 'open' : 'closed'
                  }`}
                  timeZone={timeZone}
                  userId={user.id}
                />
              </fieldset>
            </>
          )}
        </div>
      </div>

      {cardioOpenRequest > 0 &&
        (capabilities.canMutateProgress ? (
          <CardioQuickLog
            key={`${selectedDate}:${cardioOpenRequest}`}
            onDismiss={dismissCardioRequest}
            startOpen
            today={selectedDate}
          />
        ) : (
          <p className="muted demo-capability-notice" role="status">
            Добавление cardio-активности доступно после входа.
          </p>
        ))}

      {profileMissing && (
        <aside className="today-profile-nudge">
          <div>
            <strong>Сделайте рекомендации точнее</strong>
            <span>Дополните цель, уровень и желаемую частоту тренировок в профиле.</span>
          </div>
          <AppLink className="today-text-link" to="/app?section=profile#profile-fitness">
            Заполнить профиль
          </AppLink>
        </aside>
      )}
    </div>
  );
}
