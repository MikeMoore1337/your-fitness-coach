import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../src/shared/api/client';
import type { FoodDiaryDay, ProgressSummary, Workout } from '../../../../src/shared/api/types';
import { calendarWeek, dateInputValue } from '../../../../src/shared/dateTime';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import {
  formatNutritionDateLabel,
  formatTodayHeading,
  TodayDashboard,
} from '../../../../src/features/dashboard/TodayDashboard';

const apiMock = vi.hoisted(() => vi.fn());
const navigateMock = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: {
    id: 7,
    first_name: 'Анна',
    is_coach: false,
    is_admin: false,
    has_active_program: true,
    has_workout_history: true,
    onboarding: { status: 'complete', required_fields: ['goal'], missing_fields: [] },
    profile: {
      full_name: 'Анна Петрова',
      goal: 'maintenance',
      level: 'beginner' as string | null,
      height_cm: 168 as number | null,
      workouts_per_week: 3 as number | null,
      timezone: 'Europe/Moscow',
      kbju: null,
    },
  },
}));

vi.mock('../../../../src/shared/api/client', () => {
  class MockApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public body: unknown = null,
    ) {
      super(message);
      this.name = 'ApiError';
    }
  }
  return { api: apiMock, ApiError: MockApiError };
});

vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: authState.user }),
}));

vi.mock('../../../../src/shared/navigation/router', () => ({
  AppLink: ({ to, children, ...props }: React.ComponentProps<'a'> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigation: () => ({ navigate: navigateMock, search: window.location.search }),
}));

vi.mock('../../../../src/features/workouts/TodayWorkout', () => ({
  TodayWorkout: () => <div>Активная тренировка открыта</div>,
}));

Object.defineProperty(Element.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});

const plannedWorkout = {
  id: 42,
  scheduled_date: '2030-01-10',
  scheduled_time: '18:30:00',
  title: 'Силовая база',
  status: 'planned',
  day_number: 2,
  week_number: 1,
  started_at: null,
  completed_at: null,
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Приседания',
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
          actual_reps: null,
          actual_weight: null,
          is_completed: false,
          version: 1,
        },
      ],
    },
  ],
} as Workout;

const availableAdherence = {
  status: 'available' as const,
  percent: 84,
  achieved: 7,
  evaluated: 8,
  weight: 0.4,
  reason: null,
};

const sufficientSignal = {
  status: 'sufficient' as const,
  counters: {},
  reason_keys: ['thresholds_met' as const],
};

const progressSummary = {
  user_id: 7,
  period_days: 30,
  period_start: '2029-12-12',
  period_end: '2030-01-10',
  training: {
    planned_workouts: 8,
    completed_workouts: 7,
    skipped_workouts: 1,
    frequency_per_week: 1.63,
    volume_kg: 12400,
    new_personal_records: 1,
    last_completed_workout_on: '2030-01-08',
    next_workout: {
      id: 42,
      scheduled_date: '2030-01-10',
      scheduled_time: '18:30:00',
      title: 'Силовая база',
      status: 'planned',
    },
  },
  cardio: {
    completed_sessions: 1,
    planned_sessions: 0,
    frequency_per_week: 0.23,
    duration_minutes: 35,
    distance_km: 5.2,
    zone_duration: [{ zone: 3, duration_minutes: 35 }],
  },
  nutrition: {
    visible: true,
    logged_days: 20,
    complete_days: 18,
    incomplete_days: 2,
    fasted_days: 0,
    unlogged_days: 9,
    adherence_evaluated_days: 20,
    average_calories: 1980,
    target_calories: 2100,
    average_protein_g: 130,
    target_protein_g: 140,
    target_effective_on: '2029-12-01',
  },
  body: {
    latest_measurement: { measured_on: '2030-01-09', weight_kg: 68.4 },
    trends: [
      {
        metric: 'weight_kg',
        first_value: 69.1,
        latest_value: 68.4,
        change: -0.7,
        first_measured_on: '2029-12-15',
        latest_measured_on: '2030-01-09',
        point_count: 4,
        span_days: 25,
        interpretation_status: 'available',
        points: [],
      },
    ],
    priority: null,
    guidance: {
      comparison_basis: 'self',
      minimum_points_for_interpretation: 3,
      minimum_span_days_for_interpretation: 14,
      consistency_tips: [],
      circumference_limitations: [],
    },
  },
  adherence: {
    formula_version: 'adherence-v1',
    overall_percent: 84,
    included_components: ['workouts', 'calories', 'protein'],
    workouts: availableAdherence,
    cardio: {
      status: 'not_applicable',
      percent: null,
      achieved: 0,
      evaluated: 0,
      weight: 0.2,
      reason: 'cardio_not_planned',
    },
    calories: { ...availableAdherence, weight: 0.2 },
    protein: { ...availableAdherence, weight: 0.2 },
  },
  data_sufficiency: {
    ruleset_version: 'data-sufficiency-v1',
    workout_logging: sufficientSignal,
    working_sets: sufficientSignal,
    rir_coverage: sufficientSignal,
    nutrition_coverage: sufficientSignal,
    weight_trend: sufficientSignal,
    anthropometry: sufficientSignal,
    schedule_adherence: sufficientSignal,
  },
} satisfies ProgressSummary;

const diary = {
  diary_date: '2030-01-10',
  timezone: 'Europe/Moscow',
  meals: [],
  totals: {
    energy_kcal: '1450.0',
    protein_g: '96.0',
    fat_g: '48.0',
    carbs_g: '160.0',
    fiber_g: '18.0',
  },
  targets: {
    energy_kcal: '2100.0',
    protein_g: '140.0',
    fat_g: '70.0',
    carbs_g: '230.0',
  },
  remaining: {
    energy_kcal: '650.0',
    protein_g: '44.0',
    fat_g: '22.0',
    carbs_g: '70.0',
  },
  status: 'incomplete',
  status_is_explicit: false,
} as FoodDiaryDay;

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <TodayDashboard />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

function CardioRequestHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Открыть cardio request
      </button>
      <TodayDashboard initialCardioOpen={open} />
    </>
  );
}

function auxiliaryResponse(
  path: string,
  options: {
    cardio?: Array<Record<string, unknown>>;
    week?: Array<Record<string, unknown>>;
    weeklyReviewAvailable?: boolean;
    comments?: Array<Record<string, unknown>>;
  } = {},
) {
  if (path === '/api/v1/workouts/week') return Promise.resolve(options.week ?? []);
  if (path.startsWith('/api/v1/workouts/cardio?')) return Promise.resolve(options.cardio ?? []);
  if (path === '/api/v1/check-ins/weekly/current') {
    return Promise.resolve({
      week_start: '2030-01-07',
      week_end: '2030-01-13',
      submitted_on: '2030-01-10',
      timezone: 'Europe/Moscow',
      existing: options.weeklyReviewAvailable ? null : { id: 1 },
      summary: {},
    });
  }
  if (path.startsWith('/api/v1/check-ins/daily?')) {
    return Promise.resolve({
      local_date: '2030-01-10',
      today: '2030-01-10',
      timezone: 'Europe/Moscow',
      record: null,
    });
  }
  if (/\/api\/v1\/workouts\/\d+\/comments$/.test(path)) {
    return Promise.resolve(options.comments ?? []);
  }
  return undefined;
}

function useAvailableData() {
  apiMock.mockImplementation((path: string) => {
    if (path === '/api/v1/workouts/today') return Promise.resolve(plannedWorkout);
    if (path.startsWith('/api/v1/workouts/progress/summary')) {
      return Promise.resolve(progressSummary);
    }
    if (path.startsWith('/api/v1/nutrition/diary')) return Promise.resolve(diary);
    if (path === '/api/v1/workouts/42/start') {
      return Promise.resolve({ ...plannedWorkout, status: 'in_progress' });
    }
    const auxiliary = auxiliaryResponse(path, {
      week: [plannedWorkout],
    });
    if (auxiliary) return auxiliary;
    throw new Error(`Unexpected API path: ${path}`);
  });
}

describe('TodayDashboard', () => {
  beforeEach(() => {
    apiMock.mockReset();
    authState.user.has_active_program = true;
    authState.user.profile.level = 'beginner';
    authState.user.profile.height_cm = 168;
    authState.user.profile.workouts_per_week = 3;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('formats the day context in clear Russian', () => {
    expect(formatTodayHeading('2030-01-10')).toEqual({
      title: 'Сегодня · четверг, 10 января',
    });
    expect(formatNutritionDateLabel('2030-01-10', '2030-01-10')).toBe('сегодня');
    expect(formatNutritionDateLabel('2030-01-09', '2030-01-10')).toMatch(/9 января 2030/);
    expect(calendarWeek('2029-12-31')).toEqual([
      '2029-12-31',
      '2030-01-01',
      '2030-01-02',
      '2030-01-03',
      '2030-01-04',
      '2030-01-05',
      '2030-01-06',
    ]);
  });

  it('puts the real workout CTA first and shows compact nutrition and progress data', async () => {
    useAvailableData();
    renderDashboard();

    expect(await screen.findByRole('heading', { name: 'Силовая база' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Начать тренировку' })).toBeInTheDocument();
    expect(screen.getByText('Записей за день пока нет')).toBeInTheDocument();
    expect(screen.getByText(/последний вес 68,4 кг/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Добавить отметку' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /^Кардио$/ })).not.toBeInTheDocument();
    expect(screen.queryByText('84%')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Начать тренировку' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/workouts/42/start', { method: 'POST' }),
    );
    expect(await screen.findByText('Активная тренировка открыта')).toBeInTheDocument();
  });

  it('opens cardio when the quick-action intent arrives while Today is already mounted', async () => {
    useAvailableData();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <CardioRequestHarness />
        </FeedbackProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Силовая база' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /^Кардио$/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Открыть cardio request' }));

    expect(await screen.findByRole('heading', { name: /^Кардио$/ })).toBeInTheDocument();
  });

  it('announces the nutrition loading state from the live status element', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') return Promise.resolve(plannedWorkout);
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve(progressSummary);
      }
      if (path.startsWith('/api/v1/nutrition/diary')) return new Promise(() => undefined);
      const auxiliary = auxiliaryResponse(path, { week: [plannedWorkout] });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(await screen.findByRole('status', { name: 'Загружаем питание' })).toBeInTheDocument();
  });

  it('keeps the workout usable when the nutrition request fails', async () => {
    useAvailableData();
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') return Promise.resolve(plannedWorkout);
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve(progressSummary);
      }
      if (path.startsWith('/api/v1/nutrition/diary')) {
        return Promise.reject(new ApiError('Нет соединения', 0));
      }
      const auxiliary = auxiliaryResponse(path, { week: [plannedWorkout] });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(await screen.findByRole('button', { name: 'Начать тренировку' })).toBeInTheDocument();
    expect(await screen.findByText('Сводка питания временно недоступна')).toBeInTheDocument();
    expect(screen.getByText(/последний вес 68,4 кг/)).toBeInTheDocument();
  });

  it('shows a completed state without invented duration or volume', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') {
        return Promise.reject(new ApiError('На сегодня тренировка не назначена', 404));
      }
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        const currentDate = dateInputValue(new Date(), 'Europe/Moscow');
        return Promise.resolve({
          ...progressSummary,
          period_end: currentDate,
          training: {
            ...progressSummary.training,
            last_completed_workout_on: currentDate,
            next_workout: null,
          },
        });
      }
      if (path.startsWith('/api/v1/nutrition/diary')) return Promise.resolve(diary);
      const auxiliary = auxiliaryResponse(path, {
        week: [
          {
            ...plannedWorkout,
            scheduled_date: dateInputValue(new Date(), 'Europe/Moscow'),
            status: 'completed',
          },
        ],
      });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(
      await screen.findByRole('heading', { name: 'Тренировка завершена' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/длительность тренировки/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/объём/i)).not.toBeInTheDocument();
  });

  it('shows a factual rest day and the nearest planned workout', async () => {
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') {
        return Promise.reject(new ApiError('На сегодня тренировка не назначена', 404));
      }
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve({
          ...progressSummary,
          training: {
            ...progressSummary.training,
            last_completed_workout_on: '2030-01-08',
            next_workout: {
              id: 55,
              scheduled_date: '2030-01-12',
              scheduled_time: '19:00:00',
              title: 'Верх тела',
              status: 'planned',
            },
          },
        });
      }
      if (path.startsWith('/api/v1/nutrition/diary')) return Promise.resolve(diary);
      const auxiliary = auxiliaryResponse(path);
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(
      await screen.findByRole('heading', { name: 'Сегодня без тренировки' }),
    ).toBeInTheDocument();
    expect(document.querySelector('.ui-semantic-artwork--current-action')).not.toBeInTheDocument();
    expect(screen.getByText(/Ближайшая .*Верх тела/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Добавить питание' })).toHaveAttribute(
      'href',
      '/app?section=nutrition',
    );
    expect(screen.getByRole('button', { name: 'Добавить активность' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Сон и настроение' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /^Кардио$/ })).not.toBeInTheDocument();
  });

  it('guides a new user to a program and keeps incomplete profile secondary', async () => {
    authState.user.has_active_program = false;
    authState.user.profile.level = null;
    authState.user.profile.height_cm = null;
    authState.user.profile.workouts_per_week = null;
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') {
        return Promise.reject(new ApiError('На сегодня тренировка не назначена', 404));
      }
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve({
          ...progressSummary,
          body: { ...progressSummary.body, latest_measurement: null, trends: [] },
          adherence: {
            ...progressSummary.adherence,
            overall_percent: null,
            included_components: [],
          },
          training: {
            ...progressSummary.training,
            completed_workouts: 0,
            next_workout: null,
          },
        });
      }
      if (path.startsWith('/api/v1/nutrition/diary')) {
        return Promise.resolve({ ...diary, targets: null, remaining: null });
      }
      const auxiliary = auxiliaryResponse(path);
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(await screen.findByRole('heading', { name: 'С чего начнём?' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Создать свою программу' })).toHaveAttribute(
      'href',
      '/app?section=programs&start=create',
    );
    expect(screen.getByRole('link', { name: 'Выбрать готовую' })).toHaveAttribute(
      'href',
      '/app?section=programs&start=templates',
    );
    expect(screen.getByText('Сделайте рекомендации точнее')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Заполнить профиль' })).toHaveAttribute(
      'href',
      '/app?section=profile#profile-fitness',
    );
    expect(screen.queryByRole('link', { name: 'Записать питание' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Добавить активность' })).not.toBeInTheDocument();
    expect(screen.getByText('Появится после первых тренировок и замеров')).toBeInTheDocument();
  });

  it('shows a compact week with honest workout links and textual states', async () => {
    const today = dateInputValue(new Date(), 'Europe/Moscow');
    const days = calendarWeek(today);
    const friday = days[4];
    const pastDay = days
      .slice()
      .reverse()
      .find((day) => day < today);
    const futureDay = days.find((day) => day > today);
    const cardioDay = days.find(
      (day) => day !== today && day !== pastDay && day !== futureDay && day !== friday,
    );
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') return Promise.resolve(plannedWorkout);
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve(progressSummary);
      }
      if (path.startsWith('/api/v1/nutrition/diary')) return Promise.resolve(diary);
      const auxiliary = auxiliaryResponse(path, {
        cardio: cardioDay
          ? [
              {
                id: 91,
                activity_type: 'running',
                duration_minutes: 30,
                scheduled_at: `${cardioDay}T12:00:00Z`,
                status: 'planned',
                source: 'manual',
                created_at: `${cardioDay}T09:00:00Z`,
                updated_at: `${cardioDay}T09:00:00Z`,
              },
            ]
          : [],
        week: [
          {
            ...plannedWorkout,
            id: 31,
            scheduled_date: pastDay ?? today,
            status: 'completed',
          },
          ...(futureDay
            ? [{ ...plannedWorkout, id: 32, scheduled_date: futureDay, status: 'planned' }]
            : []),
          { ...plannedWorkout, id: 33, scheduled_date: friday, status: 'skipped' },
        ],
      });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    const weekRegion = await screen.findByRole('navigation', { name: 'Эта неделя' });
    fireEvent.click(screen.getByText('Обозначения').closest('summary')!);
    const legend = screen.getByRole('list', { name: 'Обозначения недели' });
    expect(legend).toHaveTextContent('Силовая');
    expect(legend).toHaveTextContent('Кардио');
    expect(legend).toHaveTextContent('Отдых');
    await screen.findByLabelText(/Выполнено/i);
    const currentDay = weekRegion.querySelector('[aria-current="date"]');
    expect(currentDay).toHaveAttribute('aria-current', 'date');
    expect(currentDay).toHaveAccessibleName(/сегодня/i);
    expect(currentDay).not.toHaveTextContent(/сегодня/i);
    if (pastDay) {
      const pastButton = screen.getByRole('button', { name: /Выполнено/i });
      fireEvent.click(pastButton);
      expect(await screen.findByRole('heading', { name: 'Силовая база' })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: 'Открыть тренировку' })).toHaveAttribute(
        'href',
        '/app?section=progress&workout_id=31',
      );
      expect(pastButton).toHaveAttribute('aria-pressed', 'true');
    }
    if (futureDay) {
      expect(screen.getByRole('button', { name: /Предстоит тренировка/i })).toBeVisible();
    }
    if (cardioDay) {
      expect(
        screen.getByRole('button', {
          name: new RegExp(`${Number(cardioDay.slice(-2))}.*Кардио`),
        }),
      ).toBeVisible();
    }
  });

  it('uses weekly review and trainer feedback only when they outrank a rest-day action', async () => {
    const today = dateInputValue(new Date(), 'Europe/Moscow');
    apiMock.mockImplementation((path: string) => {
      if (path === '/api/v1/workouts/today') {
        return Promise.reject(new ApiError('На сегодня тренировка не назначена', 404));
      }
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve({
          ...progressSummary,
          training: { ...progressSummary.training, last_completed_workout_on: today },
        });
      }
      if (path.startsWith('/api/v1/nutrition/diary')) return Promise.resolve(diary);
      const auxiliary = auxiliaryResponse(path, {
        weeklyReviewAvailable: true,
        week: [{ ...plannedWorkout, scheduled_date: today, status: 'completed' }],
        comments: [
          {
            id: 9,
            workout_id: 42,
            body: 'Сохрани спокойный темп в следующей тренировке.',
            created_at: '2030-01-10T12:00:00Z',
          },
        ],
      });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(
      await screen.findByRole('heading', { name: 'Тренировка завершена' }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Открыть комментарий' })).toHaveAttribute(
      'href',
      '/app?section=progress&workout_id=42&comment_id=9',
    );
    expect(
      screen.queryByRole('link', { name: 'Пройти короткую проверку' }),
    ).not.toBeInTheDocument();
  });

  it('refreshes date-sensitive context after returning across the local midnight', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2030-01-06T20:59:30.000Z'));
    let serverDay = '2030-01-06';

    apiMock.mockImplementation((path: string) => {
      const dayWorkout = {
        ...plannedWorkout,
        scheduled_date: serverDay,
        title: serverDay === '2030-01-06' ? 'Воскресная тренировка' : 'Понедельничная тренировка',
      };
      if (path === '/api/v1/workouts/today') return Promise.resolve(dayWorkout);
      if (path === '/api/v1/workouts/week') return Promise.resolve([dayWorkout]);
      if (path.startsWith('/api/v1/workouts/progress/summary')) {
        return Promise.resolve({
          ...progressSummary,
          period_end: serverDay,
          training: {
            ...progressSummary.training,
            last_completed_workout_on: null,
            next_workout: null,
          },
        });
      }
      if (path.startsWith('/api/v1/nutrition/diary')) {
        return Promise.resolve({ ...diary, diary_date: serverDay });
      }
      const auxiliary = auxiliaryResponse(path, { week: [dayWorkout] });
      if (auxiliary) return auxiliary;
      throw new Error(`Unexpected API path: ${path}`);
    });
    renderDashboard();

    expect(
      await screen.findByRole('heading', { name: 'Воскресная тренировка' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Сегодня · воскресенье, 6 января' }),
    ).toBeInTheDocument();

    serverDay = '2030-01-07';
    vi.setSystemTime(new Date('2030-01-06T21:00:30.000Z'));
    fireEvent(document, new Event('visibilitychange'));

    expect(
      await screen.findByRole('heading', { name: 'Понедельничная тренировка' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Сегодня · понедельник, 7 января' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /7 января, сегодня.*Силовая, Запланировано/i }),
    ).toHaveAttribute('aria-current', 'date');
    expect(apiMock.mock.calls.filter(([path]) => path === '/api/v1/workouts/week')).toHaveLength(2);
  });
});
