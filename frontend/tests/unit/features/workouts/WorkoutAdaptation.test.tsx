import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkoutAdaptation } from '../../../../src/features/workouts/WorkoutAdaptation';
import type { Workout } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const workout: Workout = {
  id: 42,
  scheduled_date: '2030-01-10',
  title: 'Тренировка A',
  status: 'planned',
  day_number: 1,
  week_number: 1,
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Жим штанги лежа',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 3,
      prescribed_reps: '8-10',
      rest_seconds: 90,
      has_guide: true,
      sets: [{ id: 201, set_number: 1, is_completed: false, version: 1 }],
    },
    {
      id: 102,
      exercise_id: 12,
      exercise_title: 'Разведение гантелей',
      metric_type: 'strength',
      sort_order: 3,
      prescribed_sets: 3,
      prescribed_reps: '10-12',
      rest_seconds: 60,
      has_guide: true,
      sets: [{ id: 202, set_number: 1, is_completed: false, version: 1 }],
    },
  ],
};

const preview = {
  status: 'preview',
  workout_id: 42,
  reason: 'limited_time',
  ruleset_version: 'workout-adaptation-v1',
  original_estimated_minutes: 32,
  adapted_estimated_minutes: 18,
  time_budget_minutes: 20,
  changes: [
    {
      kind: 'removed',
      workout_exercise_id: 102,
      from_exercise_id: 12,
      from_title: 'Разведение гантелей',
    },
  ],
  original_exercises: [],
  adapted_exercises: [],
  warnings: [],
  message: 'Проверьте изменения перед применением.',
  preview_token: 'a'.repeat(64),
};

function renderAdaptation(
  safetyOnly = false,
  options: { workout?: Workout; initialTargetId?: number; entryLabel?: string } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <WorkoutAdaptation
          entryLabel={options.entryLabel}
          initialTargetId={options.initialTargetId}
          safetyOnly={safetyOnly}
          workout={options.workout ?? workout}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

async function openTimePreview(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'Адаптировать тренировку' }));
  await user.click(screen.getByRole('button', { name: '20 мин' }));
  await user.click(screen.getByRole('button', { name: 'Показать изменения' }));
  await screen.findByRole('heading', { name: 'Что изменится' });
}

describe('WorkoutAdaptation', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('показывает плоский diff и сохраняет выбор после отмены sheet', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(preview), { status: 200 }));
    const user = userEvent.setup();
    renderAdaptation();

    await openTimePreview(user);

    const comparison = screen.getByRole('list', { name: 'Сравнение тренировки' });
    expect(within(comparison).getByText('32 мин')).toBeInTheDocument();
    expect(within(comparison).getByText('18 мин')).toBeInTheDocument();
    expect(within(comparison).getByText('Разведение гантелей')).toBeInTheDocument();
    expect(within(comparison).getByText('Убрать')).toBeInTheDocument();
    expect(comparison.querySelectorAll('[data-icon="arrow-right"]')).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Отмена' }));
    expect(screen.queryByRole('dialog', { name: 'Подстроить тренировку' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Адаптировать тренировку' }));
    expect(screen.getByRole('button', { name: '20 мин' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: 'Что изменится' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('применяет только после preview и явного действия Применить', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/adaptations/preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      if (path.endsWith('/adaptations/apply')) {
        return new Response(
          JSON.stringify({ adaptation_id: 9, applied_at: '2030-01-10T10:00:00', workout }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    const user = userEvent.setup();
    renderAdaptation();

    await openTimePreview(user);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Применить' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const applyCall = fetchMock.mock.calls[1]!;
    expect(String(applyCall[0])).toContain('/adaptations/apply');
    expect(String((applyCall[1] as RequestInit).body)).toContain('"preview_token"');
    expect(
      await screen.findByText('Изменения применены только к сегодняшней тренировке'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Подстроить тренировку' })).not.toBeInTheDocument();
  });

  it('при conflict сохраняет условия и требует обновить preview', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/adaptations/preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      return new Response(
        JSON.stringify({ detail: 'Тренировка или условия изменились. Сформируйте preview заново' }),
        { status: 409 },
      );
    });
    const user = userEvent.setup();
    renderAdaptation();

    await openTimePreview(user);
    await user.click(screen.getByRole('button', { name: 'Применить' }));

    expect(await screen.findByText('Тренировка уже изменилась')).toBeInTheDocument();
    expect(screen.getByText(/Ваш выбор сохранён/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '20 мин' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Обновить изменения' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Применить' })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('показывает честный missing-alternative state', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    const user = userEvent.setup();
    renderAdaptation();

    await user.click(screen.getByRole('button', { name: 'Адаптировать тренировку' }));
    await user.click(screen.getByRole('radio', { name: /Заменить упражнение/ }));
    await user.selectOptions(screen.getByLabelText('Какое упражнение изменить?'), '101');
    await user.click(screen.getByRole('checkbox', { name: 'Гантели' }));

    expect(
      await screen.findByText(/Для выбранного оборудования нет проверенной замены/),
    ).toBeInTheDocument();
  });

  it('во время тренировки оставляет только controlled safety boundary', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          ...preview,
          status: 'safety_stop',
          reason: 'pain_or_injury',
          changes: [],
          message: 'Приложение не подбирает медицинскую замену.',
          preview_token: null,
        }),
        { status: 200 },
      ),
    );
    const user = userEvent.setup();
    renderAdaptation(true);

    await user.click(screen.getByRole('button', { name: 'Боль или травма во время тренировки' }));
    expect(screen.queryByText('Что изменилось сегодня?')).not.toBeInTheDocument();
    expect(screen.getByText('Не подбираем «лечебную» замену')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Показать рекомендации' }));
    expect(await screen.findByText('Безопасность прежде всего')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Применить' })).not.toBeInTheDocument();
  });

  it('показывает замену для незапущенного упражнения в активной тренировке', async () => {
    const activeWorkout: Workout = {
      ...workout,
      status: 'in_progress',
      started_at: '2030-01-10T10:00:00',
      exercises: workout.exercises.map((exercise) => ({
        ...exercise,
        sets: exercise.sets.map((set) => ({
          ...set,
          actual_reps: null,
          actual_weight: null,
          duration_minutes: null,
          distance_km: null,
          average_heart_rate_bpm: null,
          heart_rate_zone: null,
          rir: null,
          reached_failure: null,
          is_completed: false,
        })),
      })),
    };
    const activePreview = {
      ...preview,
      reason: 'replace_exercise',
      changes: [
        {
          kind: 'replaced',
          workout_exercise_id: 101,
          from_exercise_id: 11,
          from_title: 'Жим штанги лежа',
          to_exercise_id: 13,
          to_title: 'Жим гантелей лежа',
          transfer: 'compatible_with_load_reset',
          load_reset_required: true,
        },
      ],
      adapted_exercises: [],
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.includes('/alternatives?')) {
        return new Response(
          JSON.stringify([
            {
              exercise_id: 13,
              title: 'Жим гантелей лежа',
              equipment_ids: ['dumbbell', 'bench'],
              score: 100,
              reason_keys: ['curated_pair'],
            },
          ]),
          { status: 200 },
        );
      }
      if (path.endsWith('/adaptations/preview')) {
        return new Response(JSON.stringify(activePreview), { status: 200 });
      }
      if (path.endsWith('/adaptations/apply')) {
        return new Response(
          JSON.stringify({
            adaptation_id: 9,
            applied_at: '2030-01-10T10:00:00',
            workout: activeWorkout,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    const user = userEvent.setup();
    renderAdaptation(false, {
      workout: activeWorkout,
      initialTargetId: 101,
      entryLabel: 'Заменить только в этой тренировке',
    });

    await user.click(screen.getByRole('button', { name: 'Заменить только в этой тренировке' }));
    expect(
      screen.getByRole('heading', { name: 'Заменить только в этой тренировке' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('checkbox', { name: 'Гантели' }));
    await user.click(screen.getByRole('checkbox', { name: 'Скамья' }));
    await user.click(await screen.findByRole('radio', { name: /Жим гантелей лежа/ }));
    await user.click(screen.getByRole('button', { name: 'Показать изменения' }));
    expect(await screen.findByRole('heading', { name: 'Что изменится' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Применить' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/adaptations/apply'),
        expect.anything(),
      ),
    );
  });

  it('не предлагает замену для уже начатого target', () => {
    const startedWorkout: Workout = {
      ...workout,
      status: 'in_progress',
      exercises: workout.exercises.map((exercise, index) =>
        index === 0
          ? {
              ...exercise,
              sets: [{ ...exercise.sets[0]!, actual_reps: 1 }],
            }
          : exercise,
      ),
    };
    renderAdaptation(false, {
      workout: startedWorkout,
      initialTargetId: 101,
      entryLabel: 'Заменить только в этой тренировке',
    });

    expect(
      screen.getByText('Замена недоступна: в этом упражнении уже есть фактические данные.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Заменить только в этой тренировке' }),
    ).not.toBeInTheDocument();
  });

  it('отключает server-confirmed replacement offline', () => {
    const originalOnline = navigator.onLine;
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    try {
      renderAdaptation(false, {
        workout: { ...workout, status: 'in_progress' },
        initialTargetId: 101,
        entryLabel: 'Заменить только в этой тренировке',
      });
      expect(
        screen.getByRole('button', { name: 'Заменить только в этой тренировке' }),
      ).toBeDisabled();
      expect(screen.getByText(/Замена требует подключения к интернету/)).toBeInTheDocument();
    } finally {
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: originalOnline });
    }
  });
});
