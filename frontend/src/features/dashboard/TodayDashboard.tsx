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
import { AppLink } from '../../shared/navigation/router';
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
import { AiCoachEntry } from '../ai/AiCoachExperience';

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

  const foodSummary = diary.data.meals.some((meal) => meal.entries.length > 0)
    ? diary.data.targets
      ? `${formatAmount(diary.data.totals.energy_kcal)} из ${formatAmount(diary.data.targets.energy_kcal)} ккал · белок ${formatAmount(diary.data.totals.protein_g)} г`
      : `${formatAmount(diary.data.totals.energy_kcal)} ккал записано`
    : 'Записей за день пока нет';
  const hydrationSummary = hydration.data
    ? hydration.data.goal?.enabled && hydration.data.goal.target_ml
      ? `вода ${hydration.data.total_ml} из ${hydration.data.goal.target_ml} мл`
      : `вода ${hydration.data.total_ml} мл`
    : hydration.isLoading
      ? 'вода загружается…'
      : 'вода недоступна';
  const dateLabel = formatNutritionDateLabel(date, today);
  const nutritionTitle = date === today ? 'Питание на сегодня' : `Питание за ${dateLabel}`;
  const caloriesLabel = date === today ? 'Калории за сегодня' : `Калории за ${dateLabel}`;
  return (
    <section className="today-nutrition" aria-label={nutritionTitle}>
      <h2>{nutritionTitle}</h2>
      <div className="today-nutrition__content">
        <Icon name="nav-nutrition" style={{ width: 72, height: 72 }} />
        <div className="today-nutrition__values">
          {diary.data.meals.some((meal) => meal.entries.length > 0) && (
            <p aria-label={foodSummary}>
              <strong>{formatAmount(diary.data.totals.energy_kcal)}</strong>
              {diary.data.targets ? ` / ${formatAmount(diary.data.targets.energy_kcal)}` : ''} ккал
            </p>
          )}
          {!diary.data.meals.some((meal) => meal.entries.length > 0) && <p>{foodSummary}</p>}
          {diary.data.meals.some((meal) => meal.entries.length > 0) &&
            diary.data.targets &&
            Number(diary.data.targets.energy_kcal) > 0 && (
              <progress
                aria-label={caloriesLabel}
                max={diary.data.targets.energy_kcal}
                value={diary.data.totals.energy_kcal}
              />
            )}
          <AppLink
            className="today-summary-card__action"
            to={`/app?section=nutrition&date=${date}`}
          >
            Открыть дневник питания
          </AppLink>
        </div>
      </div>
      <div className="today-nutrition__water">
        <span>{hydrationSummary}</span>
        <AppLink
          className="today-summary-card__action"
          to={`/app?section=nutrition&date=${date}&hydration=quick`}
        >
          + Вода
        </AppLink>
      </div>
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
  const progressSignals = [
    completedWorkouts > 0
      ? `${completedWorkouts} ${completedWorkouts === 1 ? 'тренировка' : completedWorkouts < 5 ? 'тренировки' : 'тренировок'} за 30 дней`
      : null,
    latestWeight != null ? `последний вес ${latestWeight.toLocaleString('ru-RU')} кг` : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <section className="today-progress-grid" aria-label="Главное о прогрессе">
      <SemanticCard
        action={<AppLink to="/app?section=progress">Открыть</AppLink>}
        className="today-panel today-summary-card today-summary-card--progress"
        family="progress"
        icon="nav-progress"
        summary={
          progressSignals.length > 0
            ? progressSignals.join(' · ')
            : 'Появится после первых тренировок и замеров'
        }
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
  onStart(): void;
}) {
  const { user } = useAuth();
  const trackPrimaryAction = (
    destination: 'workout' | 'nutrition' | 'weekly_review' | 'programs' | 'progress',
  ) =>
    trackProductEvent({
      name: 'today_primary_action_selected',
      surface: productEventSurface(),
      destination,
    });
  const totalSets =
    workout?.exercises.reduce((sum, exercise) => sum + exercise.sets.length, 0) ?? 0;
  const completedSets =
    workout?.exercises.reduce(
      (sum, exercise) => sum + exercise.sets.filter((set) => set.is_completed).length,
      0,
    ) ?? 0;
  const completedToday = !workout && progress.data?.training.last_completed_workout_on === today;
  const nextWorkout = progress.data?.training.next_workout;
  const weeklyReviewAvailable = Boolean(weeklyReview && !weeklyReview.existing);
  const feedbackWorkoutId = workout?.id ?? todayScheduleItem?.id;
  const trainerCommentLink =
    trainerComment && feedbackWorkoutId
      ? `/app?section=progress&workout_id=${feedbackWorkoutId}&comment_id=${trainerComment.id}`
      : null;

  const completedAction = () => {
    if (trainerCommentLink) {
      return (
        <AppLink
          className="button-link"
          onClick={() => trackPrimaryAction('progress')}
          to={trainerCommentLink}
        >
          Открыть комментарий
        </AppLink>
      );
    }
    if (weeklyReviewAvailable) {
      return (
        <AppLink
          className="button-link"
          onClick={() => trackPrimaryAction('weekly_review')}
          to="/app?section=progress&weekly_review=1"
        >
          Пройти короткую проверку
        </AppLink>
      );
    }
    return (
      <AppLink
        className="button-link"
        onClick={() => trackPrimaryAction('progress')}
        to={
          feedbackWorkoutId
            ? `/app?section=progress&workout_id=${feedbackWorkoutId}`
            : '/app?section=progress'
        }
      >
        Посмотреть итог
      </AppLink>
    );
  };

  if (workout) {
    if (workout.status === 'completed') {
      return (
        <>
          <div className="today-workout-copy">
            <Badge tone="success">Готово</Badge>
            <h2 id="today-workout-title">Тренировка завершена</h2>
            <p>Результат сохранён. Следующее действие — восстановиться и продолжить план.</p>
          </div>
          {completedAction()}
        </>
      );
    }
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
        <div className="today-workout-actions">
          <Button
            className="today-pulse-action"
            fullWidth
            disabled={startPending}
            type="button"
            onClick={() => {
              trackPrimaryAction('workout');
              if (started) onOpenDetails();
              else onStart();
            }}
          >
            {startPending ? 'Начинаем…' : started ? 'Продолжить тренировку' : 'Начать тренировку'}
          </Button>
          {trainerCommentLink ? (
            <AppLink className="button-link secondary-link" to={trainerCommentLink}>
              Открыть комментарий тренера
            </AppLink>
          ) : !detailsOpen ? (
            <Button fullWidth variant="secondary" type="button" onClick={onOpenDetails}>
              Посмотреть упражнения
            </Button>
          ) : null}
          {!started && <WorkoutAdaptation workout={workout} entryContext="today" />}
        </div>
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
        {completedAction()}
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
        <div className="today-workout-actions today-workout-actions--quick-start">
          <AppLink
            className="button-link"
            onClick={() => trackPrimaryAction('programs')}
            to="/app?section=programs&start=create"
          >
            Создать свою программу
          </AppLink>
          <AppLink
            className="button-link secondary-link"
            to="/app?section=programs&start=templates"
          >
            Выбрать готовую
          </AppLink>
        </div>
      </>
    );
  }

  if (trainerCommentLink) {
    return (
      <>
        <div className="today-workout-copy">
          <Badge tone="warning">Комментарий тренера</Badge>
          <h2 id="today-workout-title">Тренер оставил комментарий</h2>
          <p>{trainerComment ? compactSignal(trainerComment.body) : ''}</p>
        </div>
        <AppLink
          className="button-link"
          onClick={() => trackPrimaryAction('progress')}
          to={trainerCommentLink}
        >
          Открыть комментарий
        </AppLink>
      </>
    );
  }

  if (weeklyReviewAvailable) {
    return (
      <>
        <div className="today-workout-copy">
          <Badge>Итоги недели</Badge>
          <h2 id="today-workout-title">Неделя готова к проверке</h2>
          <p>Коротко отметьте нагрузку, восстановление и то, насколько легко было держать план.</p>
        </div>
        <AppLink
          className="button-link"
          onClick={() => trackPrimaryAction('weekly_review')}
          to="/app?section=progress&weekly_review=1"
        >
          Пройти короткую проверку
        </AppLink>
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
      <div className="today-workout-actions">
        <AppLink
          className="button-link"
          onClick={() => trackPrimaryAction('nutrition')}
          to="/app?section=nutrition"
        >
          Добавить питание
        </AppLink>
        <Button fullWidth variant="secondary" type="button" onClick={onAddActivity}>
          Добавить активность
        </Button>
      </div>
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
}: {
  initialWellbeingDate?: string;
  initialWellbeingOpen?: boolean;
} = {}) {
  const { user } = useAuth();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const detailsRef = useRef<HTMLDivElement>(null);
  const autoOpenedCompletionRef = useRef<number | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [cardioOpenRequest, setCardioOpenRequest] = useState(0);
  const timeZone = user?.profile?.timezone || detectedTimeZone();
  const today = useCalendarDay(timeZone);
  const [selectedDate, setSelectedDate] = useState(today);
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
        (!user.profile ||
          !user.profile.goal ||
          !user.profile.level ||
          !user.profile.workouts_per_week ||
          !user.profile.height_cm),
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
                    to={`/app?section=progress&workout_id=${selectedScheduleItem.id}`}
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
                onStart={() => visibleWorkout && start.mutate(visibleWorkout.id)}
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
          <ProgressSummaryPanel summary={progress} />
          <AiCoachEntry entryPoint="today" />
          {user && (
            <DailyWellbeingCheckIn
              autoFocus={initialWellbeingOpen}
              initialDate={initialWellbeingDate || selectedDate}
              key={`${user.id}:${initialWellbeingDate || selectedDate}:${
                initialWellbeingOpen ? 'open' : 'closed'
              }`}
              timeZone={timeZone}
              userId={user.id}
            />
          )}
        </div>
      </div>

      <CardioQuickLog
        key={`${selectedDate}:${cardioOpenRequest}`}
        startOpen={cardioOpenRequest > 0}
        today={selectedDate}
      />

      {profileMissing && (
        <aside className="today-profile-nudge">
          <div>
            <strong>Сделайте рекомендации точнее</strong>
            <span>Дополните цель, уровень, рост и желаемую частоту тренировок в профиле.</span>
          </div>
          <AppLink className="today-text-link" to="/app?section=profile#profile-fitness">
            Заполнить профиль
          </AppLink>
        </aside>
      )}
    </div>
  );
}
