import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ActiveProgramPeriodization } from '../../../../src/features/programs/ActiveProgramPeriodization';
import { ApiError } from '../../../../src/shared/api/client';
import type { Exercise } from '../../../../src/shared/api/types';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../../../../src/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../src/shared/api/client')>()),
  api: (...args: unknown[]) => apiMock(...args),
}));

const week = (number: number, changeable = true) => ({
  week_number: number,
  source_cycle_week: 1,
  cycle_iteration: Math.floor((number - 1) / 3) + 1,
  cycle_length: 3,
  repeat: true,
  periodization_enabled: true,
  workouts: [
    {
      id: number,
      day_number: 1,
      title: 'Тренировка 1',
      scheduled_date: '2026-12-14',
      status: changeable ? 'planned' : 'completed',
      changeable,
      week_type: 'heavy',
      exercises: [],
    },
  ],
});

function setup(onChanged = vi.fn(), readOnly = false, exercises: Exercise[] = []) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ActiveProgramPeriodization
        programId={9}
        revision={4}
        duration={16}
        initialWeek={7}
        exercises={exercises}
        dirty={false}
        readOnly={readOnly}
        onChanged={onChanged}
      />
    </QueryClientProvider>,
  );
  return onChanged;
}

describe('Изменение назначенной периодизации', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string, options: { body: Record<string, unknown> }) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({
          weeks: options.body.from_week ? [week(7, false), week(10)] : [week(7)],
          total_weeks: options.body.from_week ? 2 : 1,
          offset: 0,
        });
      if (path.endsWith('/week-type')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
  });
  afterEach(cleanup);

  it('добавляет упражнение с одной идентичностью на preview и сохранении', async () => {
    const user = userEvent.setup();
    const base = week(7);
    const first = {
      source_template_exercise_id: 3,
      exercise_id: 11,
      metric_type: 'strength',
      prescribed_sets: 3,
      prescribed_reps: '8-12',
      prescribed_duration_minutes: null,
      rest_seconds: 90,
      notes: null,
      prescription: null,
    };
    const initial = { ...base, workouts: [{ ...base.workouts[0], exercises: [first] }] };
    let previewSlot = '';
    apiMock.mockImplementation((path: string, options: { body: Record<string, unknown> }) => {
      if (path.endsWith('/structure/preview')) {
        previewSlot = String(options.body.assignment_slot_id);
        return Promise.resolve({
          weeks: [
            {
              ...initial,
              workouts: [
                {
                  ...initial.workouts[0],
                  new_exercises: [
                    first,
                    {
                      ...first,
                      source_template_exercise_id: null,
                      source_assignment_slot_id: previewSlot,
                      exercise_id: 12,
                    },
                  ],
                  structure_changed: true,
                },
              ],
            },
          ],
          total_weeks: 1,
          offset: 0,
        });
      }
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/structure')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup(vi.fn(), false, [
      { id: 11, title: 'Приседания', metric_type: 'strength' },
      { id: 12, title: 'Тяга', metric_type: 'strength' },
    ] as Exercise[]);
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'structure');
    await user.click(screen.getByRole('button', { name: 'Добавить упражнение' }));
    expect(screen.getByRole('button', { name: 'Проверить изменения' })).toBeDisabled();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Новое упражнение' }), '12');
    expect(screen.getByRole('button', { name: 'Проверить изменения' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(previewSlot).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByText(/Станет:.*Тяга/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/cycle/structure',
      expect.objectContaining({
        body: expect.objectContaining({
          assignment_slot_id: previewSlot,
          operation: 'add_exercise',
        }),
      }),
    );
  });

  it('редактирует добавленную позицию по её идентичности', async () => {
    const user = userEvent.setup();
    const slot = 'b714c414-58ee-4aad-a214-fd21d5ef2f30';
    const base = week(7);
    const item = {
      source_template_exercise_id: null,
      source_assignment_slot_id: slot,
      exercise_id: 11,
      metric_type: 'strength',
      prescribed_sets: 2,
      prescribed_reps: '8-10',
      prescribed_duration_minutes: null,
      rest_seconds: 90,
      notes: null,
      prescription: null,
    };
    const initial = { ...base, workouts: [{ ...base.workouts[0], exercises: [item] }] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/exercises')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup(vi.fn(), false, [{ id: 11, title: 'Тяга', metric_type: 'strength' }] as Exercise[]);
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Упражнение' }),
      `1:assignment:${slot}`,
    );
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/exercises',
      expect.objectContaining({
        body: expect.objectContaining({ target_assignment_slot_id: slot }),
      }),
    );
  });

  it('показывает новые даты при перестановке дней', async () => {
    const user = userEvent.setup();
    const base = week(7);
    const first = base.workouts[0]!;
    const second = {
      ...first,
      id: 2,
      day_number: 2,
      title: 'Тренировка 2',
      scheduled_date: '2026-12-15',
    };
    const initial = { ...base, workouts: [first, second] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/revision/preview'))
        return Promise.resolve({
          weeks: [
            {
              ...initial,
              workouts: [
                { ...first, new_scheduled_date: second.scheduled_date },
                { ...second, new_scheduled_date: first.scheduled_date },
              ],
            },
          ],
          total_weeks: 1,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/cycle')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'days');
    await user.click(screen.getAllByRole('button', { name: 'Переместить выше' })[1]!);
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/2026-12-14 → 2026-12-15/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle', {
      method: 'PATCH',
      body: {
        expected_revision_number: 4,
        effective_from_week: 7,
        swap_day_number: 2,
        swap_with_day_number: 1,
      },
    });
  });

  it.each([
    ['one', /Только неделя 7/, { occurrence_weeks: [7] }],
    ['repeat', /Будущие повторы исходной недели/, { source_cycle_week: 1 }],
    ['selected', /Выбрать недели/, { occurrence_weeks: [7, 9] }],
  ])('сохраняет выбранную область дней: %s', async (scope, label, expectedScope) => {
    const user = userEvent.setup();
    const base = week(7);
    const day = { ...base.workouts[0]!, day_number: 2, title: 'День 2' };
    const initial = { ...base, workouts: [base.workouts[0], day] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/revision/preview'))
        return Promise.resolve({
          weeks: [{ ...initial, workouts: [{ ...day, removed: true }] }],
          total_weeks: 1,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/cycle')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'days');
    await user.click(screen.getAllByRole('button', { name: 'Убрать из будущего плана' })[1]!);
    await user.click(screen.getByRole('radio', { name: label }));
    if (scope === 'selected') {
      await user.click(screen.getByRole('checkbox', { name: 'Неделя 7' }));
      await user.click(screen.getByRole('checkbox', { name: 'Неделя 9' }));
    }
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/cycle/revision/preview',
      expect.objectContaining({
        body: expect.objectContaining({ ...expectedScope, effective_from_week: 7 }),
      }),
    );
    await user.click(await screen.findByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/cycle',
      expect.objectContaining({
        body: expect.objectContaining({ ...expectedScope, effective_from_week: 7 }),
      }),
    );
  });

  it('добавляет день как копию существующего после предпросмотра', async () => {
    const user = userEvent.setup();
    const base = week(7);
    const day = {
      ...base.workouts[0],
      id: 2,
      day_number: 2,
      title: 'Тренировка 2',
      scheduled_date: '2026-12-15',
    };
    const initial = { ...base, workouts: [base.workouts[0], day] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/revision/preview'))
        return Promise.resolve({
          weeks: [
            {
              ...initial,
              workouts: [
                {
                  ...day,
                  id: null,
                  day_number: 3,
                  title: 'Тренировка 1 · копия',
                  added: true,
                  new_exercises: [],
                },
              ],
            },
          ],
          total_weeks: 1,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/cycle')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'days');
    await user.click(screen.getByRole('button', { name: 'Добавить тренировочный день' }));
    expect(screen.getByRole('combobox', { name: 'День недели' })).toHaveValue('2');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/будет добавлена/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle', {
      method: 'PATCH',
      body: {
        expected_revision_number: 4,
        effective_from_week: 7,
        copy_day_number: 1,
        new_day_weekday: 2,
        new_day_title: 'Тренировка 1 · копия',
      },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('показывает начатый и отменяемый день до удаления будущих тренировок', async () => {
    const user = userEvent.setup();
    const base = week(7);
    const day = { ...base.workouts[0], id: 2, day_number: 2, title: 'Тренировка 2' };
    const initial = { ...base, workouts: [base.workouts[0], day] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/revision/preview'))
        return Promise.resolve({
          weeks: [
            {
              ...initial,
              workouts: [{ ...day, status: 'in_progress', changeable: false, removed: true }],
            },
            { ...week(8), workouts: [{ ...day, id: 8, removed: true }] },
          ],
          total_weeks: 2,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/cycle')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'days');
    await user.click(screen.getAllByRole('button', { name: 'Убрать из будущего плана' })[1]!);
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/начата · не изменится/)).toBeVisible();
    expect(screen.getByText(/будет отменена/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle', {
      method: 'PATCH',
      body: { expected_revision_number: 4, effective_from_week: 7, remove_day_number: 2 },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('показывает изменение состава и применяет его только к выбранной неделе', async () => {
    const user = userEvent.setup();
    const base = week(7);
    const first = {
      source_template_exercise_id: 3,
      exercise_id: 11,
      metric_type: 'strength',
      prescribed_sets: 3,
      prescribed_reps: '8-12',
      prescribed_duration_minutes: null,
      rest_seconds: 90,
      notes: null,
      prescription: null,
    };
    const second = { ...first, source_template_exercise_id: 4, exercise_id: 12 };
    const initial = { ...base, workouts: [{ ...base.workouts[0], exercises: [first, second] }] };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/structure/preview'))
        return Promise.resolve({
          weeks: [
            {
              ...initial,
              workouts: [
                { ...initial.workouts[0], new_exercises: [second], structure_changed: true },
              ],
            },
          ],
          total_weeks: 1,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [initial], total_weeks: 1, offset: 0 });
      if (path.endsWith('/structure')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'structure');
    const row = screen.getByText('1 · Упражнение 11').parentElement!;
    await user.click(within(row).getByRole('button', { name: 'Убрать из будущего плана' }));
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/Было: Упражнение 11/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle/structure', {
      method: 'POST',
      body: {
        expected_revision_number: 4,
        occurrence_weeks: [7],
        day_number: 1,
        target_template_exercise_id: 3,
        operation: 'remove_exercise',
        offset: 0,
      },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('показывает новый порядок цикла и применяет проверенную карту недель', async () => {
    const user = userEvent.setup();
    const changed = setup();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/revision/preview'))
        return Promise.resolve({
          weeks: [{ ...week(7, false), new_source_cycle_week: 1 }],
          total_weeks: 10,
          offset: 0,
        });
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [week(7)], total_weeks: 1, offset: 0 });
      if (path.endsWith('/cycle')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'cycle');
    const count = screen.getByRole('spinbutton', { name: 'Исходных недель в новом цикле' });
    await user.clear(count);
    await user.type(count, '4');
    expect(screen.getByRole('combobox', { name: 'Новая неделя 4' })).toHaveValue('1');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/исходная 1 → новая 1/)).toBeVisible();
    expect(screen.getByText(/не изменится/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle', {
      method: 'PATCH',
      body: {
        expected_revision_number: 4,
        effective_from_week: 7,
        source_week_order: [1, 2, 3, 1],
        repeat: true,
      },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('показывает защищённую тренировку и применяет только проверенную ревизию', async () => {
    const user = userEvent.setup();
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Новый тип недели' }), 'light');
    await user.click(screen.getByRole('radio', { name: /Будущие повторы/ }));
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    const preview = screen.getByRole('heading', { name: 'Проверить изменения' }).parentElement!;
    expect(within(preview).getByText(/не изменится/)).toBeVisible();
    expect(within(preview).getByText(/Тяжёлая → Лёгкая/)).toBeVisible();
    await user.click(within(preview).getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle/week-type', {
      method: 'POST',
      body: {
        expected_revision_number: 4,
        week_type: 'light',
        from_week: 7,
        source_cycle_week: 1,
        offset: 0,
      },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('сохраняет выбор и сообщает о конфликте ревизии', async () => {
    const user = userEvent.setup();
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Новый тип недели' }), 'light');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    apiMock.mockRejectedValueOnce(new ApiError('conflict', 409));
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('План уже изменился');
    expect(screen.getByRole('button', { name: 'Применить изменения' })).toBeDisabled();
    apiMock.mockResolvedValueOnce({ current_revision_number: 6, duration_weeks: 16 });
    await user.click(screen.getByRole('button', { name: 'Обновить план' }));
    expect(await screen.findByRole('combobox', { name: 'Новый тип недели' })).toHaveValue('light');
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(apiMock).toHaveBeenLastCalledWith(
      '/api/v1/programs/assigned/9/cycle/week-type/preview',
      {
        method: 'POST',
        body: { expected_revision_number: 6, week_type: 'light', occurrence_weeks: [7], offset: 0 },
      },
    );
    expect(changed).not.toHaveBeenCalled();
  });

  it('не применяет предпросмотр после обновления ревизии родителем', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (revision: number) => (
      <QueryClientProvider client={queryClient}>
        <ActiveProgramPeriodization
          programId={9}
          revision={revision}
          duration={16}
          initialWeek={7}
          exercises={[]}
          dirty={false}
          onChanged={vi.fn()}
        />
      </QueryClientProvider>
    );
    const { rerender } = render(view(4));
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'duration');
    await user.clear(screen.getByRole('spinbutton', { name: 'Всего недель' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Всего недель' }), '20');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByRole('button', { name: 'Применить изменения' })).toBeEnabled();

    rerender(view(5));
    expect(screen.getByRole('button', { name: 'Применить изменения' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('План уже изменился');
    expect(apiMock).not.toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/cycle',
      expect.objectContaining({ method: 'PATCH' }),
    );
  });

  it('применяет предписание, проверенное до завершения предпросмотра', async () => {
    const user = userEvent.setup();
    const initial = week(7);
    const plannedWeek = {
      ...initial,
      workouts: [
        {
          ...initial.workouts[0],
          exercises: [
            {
              source_template_exercise_id: 3,
              exercise_id: 11,
              metric_type: 'strength',
              prescribed_sets: 3,
              prescribed_reps: '8-12',
              prescribed_duration_minutes: null,
              rest_seconds: 90,
              notes: null,
              prescription: null,
            },
          ],
        },
      ],
    };
    const preview = { weeks: [plannedWeek], total_weeks: 1, offset: 0 };
    let resolvePreview: (value: typeof preview) => void = () => {};
    let previews = 0;
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview')) {
        previews += 1;
        return previews === 1
          ? Promise.resolve(preview)
          : new Promise<typeof preview>((resolve) => {
              resolvePreview = resolve;
            });
      }
      if (path.endsWith('/exercises')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Упражнение' }), '1:3');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    await user.clear(screen.getByRole('spinbutton', { name: 'Подходы' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Подходы' }), '7');
    resolvePreview(preview);

    expect(await screen.findByText(/Новое предписание: 3 подх./)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/exercises',
      expect.objectContaining({ body: expect.objectContaining({ prescribed_sets: 3 }) }),
    );
  });

  it('заменяет упражнение во всей будущей области после проверки', async () => {
    const user = userEvent.setup();
    const initial = week(7);
    const plannedWeek = {
      ...initial,
      workouts: [
        {
          ...initial.workouts[0],
          exercises: [
            {
              source_template_exercise_id: 3,
              exercise_id: 11,
              metric_type: 'strength',
              prescribed_sets: 3,
              prescribed_reps: '8-12',
              prescribed_duration_minutes: null,
              rest_seconds: 90,
              notes: null,
              prescription: null,
            },
          ],
        },
      ],
    };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [plannedWeek], total_weeks: 1, offset: 0 });
      if (path.endsWith('/exercises')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup(vi.fn(), false, [
      { id: 11, title: 'Жим штанги', metric_type: 'strength' },
      { id: 12, title: 'Жим гантелей', metric_type: 'strength' },
      { id: 13, title: 'Бег', metric_type: 'cardio' },
    ] as Exercise[]);
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Упражнение' }), '1:3');
    const replacement = screen.getByRole('combobox', { name: 'Заменить на' });
    expect(within(replacement).queryByRole('option', { name: 'Бег' })).not.toBeInTheDocument();
    await user.selectOptions(replacement, '12');
    await user.click(screen.getByRole('radio', { name: /Все будущие недели/ }));
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(screen.getByText(/Жим штанги → Жим гантелей/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/exercises',
      expect.objectContaining({
        body: expect.objectContaining({
          expected_revision_number: 4,
          from_week: 7,
          exercise_id: 12,
          target_template_exercise_id: 3,
        }),
      }),
    );
  });

  it('проверяет и сохраняет структурное предписание подходов', async () => {
    const user = userEvent.setup();
    const initial = week(7);
    const plannedWeek = {
      ...initial,
      workouts: [
        {
          ...initial.workouts[0],
          exercises: [
            {
              source_template_exercise_id: 3,
              exercise_id: 11,
              metric_type: 'strength',
              prescribed_sets: 2,
              prescribed_reps: '8-10',
              prescribed_duration_minutes: null,
              rest_seconds: 90,
              notes: null,
              prescription: null,
            },
          ],
        },
      ],
    };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [plannedWeek], total_weeks: 1, offset: 0 });
      if (path.endsWith('/exercises')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Упражнение' }), '1:3');
    await user.click(screen.getByRole('button', { name: 'Настроить предписание подходов' }));
    await user.type(screen.getByRole('textbox', { name: 'Вес, кг · подход 1' }), '40');
    await user.type(screen.getByRole('textbox', { name: 'RIR · подход 1' }), '2');
    await user.click(screen.getByRole('button', { name: 'Добавить подход' }));
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(screen.getByText(/Подход 1 · 8–10 повторов · 40 кг · RIR 2/)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/exercises',
      expect.objectContaining({
        body: expect.objectContaining({
          prescription: expect.objectContaining({
            segments: expect.arrayContaining([
              expect.objectContaining({
                position: 1,
                load_target: { kind: 'absolute', value: 40 },
                effort_target: { kind: 'rir', value: 2 },
              }),
              expect.objectContaining({ position: 3, role: 'working' }),
            ]),
          }),
        }),
      }),
    );
  });

  it('не упрощает разные предписания отдельных подходов', async () => {
    const user = userEvent.setup();
    const initial = week(7);
    const plannedWeek = {
      ...initial,
      workouts: [
        {
          ...initial.workouts[0],
          exercises: [
            {
              source_template_exercise_id: 3,
              exercise_id: 11,
              metric_type: 'strength',
              prescribed_sets: 2,
              prescribed_reps: '8',
              prescribed_duration_minutes: null,
              rest_seconds: 90,
              notes: null,
              prescription: {
                version: 1,
                metric_type: 'strength',
                groups: [],
                segments: [
                  {
                    position: 1,
                    role: 'working',
                    rep_target: { kind: 'exact', value: 8 },
                    load_target: { kind: 'user_selected' },
                    effort_target: { kind: 'none' },
                    rest_after_seconds: 90,
                  },
                  {
                    position: 2,
                    role: 'working',
                    rep_target: { kind: 'exact', value: 12 },
                    load_target: { kind: 'user_selected' },
                    effort_target: { kind: 'none' },
                    rest_after_seconds: 90,
                  },
                ],
              },
            },
          ],
        },
      ],
    };
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({ weeks: [plannedWeek], total_weeks: 1, offset: 0 });
      if (path.endsWith('/exercises')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Упражнение' }), '1:3');
    expect(await screen.findByRole('textbox', { name: 'Повторы · подход 2' })).toHaveValue('12');
    await user.type(screen.getByRole('textbox', { name: 'Вес, кг · подход 1' }), '40');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/programs/assigned/9/exercises',
      expect.objectContaining({
        body: expect.objectContaining({
          prescription: expect.objectContaining({
            segments: expect.arrayContaining([
              expect.objectContaining({
                position: 2,
                rep_target: expect.objectContaining({ kind: 'exact', value: 12 }),
              }),
            ]),
          }),
        }),
      }),
    );
  });

  it('показывает программу тренера без действий изменения', async () => {
    setup(vi.fn(), true);
    expect(await screen.findByText(/План подготовлен тренером/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Проверить изменения' })).not.toBeInTheDocument();
  });

  it('не предлагает изменить упражнение без устойчивой исходной позиции', async () => {
    const user = userEvent.setup();
    const initial = week(7);
    apiMock.mockResolvedValue({
      weeks: [
        {
          ...initial,
          workouts: [
            {
              ...initial.workouts[0],
              exercises: [{ source_template_exercise_id: null, exercise_id: 11 }],
            },
          ],
        },
      ],
      total_weeks: 1,
      offset: 0,
    });
    setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Что изменить' }), 'exercise');
    expect(screen.getByRole('option', { name: /измените в тренировке/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Проверить изменения' })).toBeDisabled();
  });
});
