import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExerciseExecutionNote } from '../../../../src/features/workouts/ExerciseExecutionNote';
import { ExerciseNoteHistory } from '../../../../src/features/workouts/ExerciseNoteHistory';
import { ExerciseNoteRecovery } from '../../../../src/features/workouts/ExerciseNoteRecovery';
import {
  flushExerciseNotes,
  historyNoteQueueKey,
  noteIdentity,
  noteQueueKey,
  readNoteQueue,
  type NoteResponse,
} from '../../../../src/features/workouts/exerciseNoteQueue';
import type { Workout } from '../../../../src/shared/api/types';
import { ApiError } from '../../../../src/shared/api/client';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', async (original) => ({
  ...(await original<typeof import('../../../../src/shared/api/client')>()),
  api: apiMock,
}));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => ({ confirm: async () => true }),
}));
vi.mock('../../../../src/shared/browser/crossContextLock', () => ({
  crossContextCoordinator: { run: async (_name: string, task: () => unknown) => task() },
}));

const exercise = {
  id: 101,
  exercise_id: 11,
  exercise_title: 'Жим лёжа',
  source_template_exercise_id: 71,
  metric_type: 'strength',
  sort_order: 1,
  prescribed_sets: 2,
  prescribed_reps: '8',
  rest_seconds: 90,
  has_guide: false,
  sets: [],
} satisfies Workout['exercises'][number];
const workout = {
  id: 42,
  title: 'Тренировка',
  scheduled_date: '2026-10-30',
  status: 'in_progress',
  day_number: 1,
  week_number: 2,
  plan_revision_number: 3,
  source_cycle_week: 2,
  cycle_iteration: 1,
  exercises: [exercise],
} satisfies Workout;
const response: NoteResponse = {
  workout_id: 42,
  workout_exercise_id: 101,
  ...noteIdentity(workout, exercise),
  version: 0,
  current_note: null,
  previous_note: {
    id: 5,
    workout_id: 35,
    workout_exercise_id: 88,
    version: 1,
    body: '<b>Легко</b>',
    tags: ['easy'],
    completed_on: '2026-10-16',
    week_type: 'light',
    load: {
      set_number: 2,
      actual_weight: 60,
      actual_reps: 8,
      duration_minutes: null,
      distance_km: null,
    },
  },
};

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value });
  window.dispatchEvent(new Event(value ? 'online' : 'offline'));
}
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

describe('exercise execution notes', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    setOnline(true);
  });
  afterEach(() => {
    cleanup();
    setOnline(true);
  });

  it('shows the previous note with its own date and load as text, without changing set values', async () => {
    apiMock.mockResolvedValue(response);
    const { container } = mount(
      <ExerciseExecutionNote userId={7} workout={workout} exercise={exercise} visible />,
    );
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('Заметка к упражнению').closest('summary')!);
    expect(await screen.findByText('<b>Легко</b>')).toBeVisible();
    expect(container.querySelector('b')).toBeNull();
    const past = within(container.querySelector('.exercise-execution-note__past') as HTMLElement);
    expect(past.getByText(/16 октября 2026.*лёгкая неделя/)).toBeVisible();
    expect(past.getByText(/Нагрузка: Подход 2 · 60 кг × 8 повторений/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('Заметка к этому выполнению'), {
      target: { value: 'Свободный текст' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Тяжело' }));
    fireEvent.click(screen.getByRole('button', { name: 'Повысить вес' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    await waitFor(() =>
      expect(readNoteQueue(noteQueueKey(7, 42, 101), 7)?.pending[0]).toMatchObject({
        body: 'Свободный текст',
        tags: ['hard', 'increase_weight'],
      }),
    );
    expect(exercise.sets).toEqual([]);
  });

  it('hides stale previous text while offline and during reconnect', async () => {
    let finish!: (value: NoteResponse) => void;
    apiMock.mockResolvedValueOnce(response).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount(<ExerciseExecutionNote userId={7} workout={workout} exercise={exercise} visible />);
    await waitFor(() => expect(screen.getByText(/Последняя ·/)).toBeVisible());
    act(() => setOnline(false));
    expect(screen.queryByText(/Последняя ·/)).toBeNull();
    act(() => setOnline(true));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/Последняя ·/)).toBeNull();
    await act(async () => finish({ ...response, previous_note: null }));
    await waitFor(() =>
      expect(
        within(screen.getByText('Заметка к упражнению').closest('summary')!).getByText(
          'Подходящих заметок пока нет',
        ),
      ).toBeVisible(),
    );
  });

  it('retains an offline historical edit and lets the user compare a conflict', async () => {
    const note = {
      id: 5,
      workout_id: 35,
      workout_exercise_id: 88,
      exercise_id: 11,
      exercise_title: 'Жим лёжа',
      body: 'Исходная',
      tags: ['easy'],
      version: 1,
    };
    apiMock.mockResolvedValueOnce([note]);
    mount(<ExerciseNoteHistory userId={7} workoutId={35} />);
    fireEvent.click(screen.getByText('Заметки к упражнениям').closest('summary')!);
    fireEvent.click((await screen.findByText('Жим лёжа')).closest('summary')!);
    fireEvent.change(screen.getByLabelText('Заметка к этому выполнению'), {
      target: { value: 'Мой текст' },
    });
    act(() => setOnline(false));
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    const key = historyNoteQueueKey(7, 35, 5);
    await waitFor(() => expect(readNoteQueue(key, 7)?.pending[0]?.body).toBe('Мой текст'));
    act(() => setOnline(true));
    apiMock.mockRejectedValueOnce(
      new ApiError('Конфликт', 409, { detail: { code: 'exercise_note_version_conflict' } }),
    );
    await act(async () => flushExerciseNotes(7, () => undefined));
    expect(await screen.findByText(/Ваш текст остался здесь/)).toBeVisible();
    apiMock.mockResolvedValueOnce({
      version: 2,
      current_note: { id: 5, body: 'С сервера', tags: ['hard'], version: 2 },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Посмотреть сохранённую версию' }));
    expect(await screen.findByText('На сервере: С сервера')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить мой вариант' }));
    await waitFor(() =>
      expect(readNoteQueue(key, 7)?.pending[0]).toMatchObject({
        body: 'Мой текст',
        expected_version: 2,
      }),
    );
  });

  it('keeps an unsent draft visible after an exercise is replaced', async () => {
    apiMock.mockResolvedValue(response);
    const view = mount(
      <>
        <ExerciseNoteRecovery userId={7} workout={workout} />
        <ExerciseExecutionNote key={11} userId={7} workout={workout} exercise={exercise} visible />
      </>,
    );
    fireEvent.click(screen.getByText('Заметка к упражнению').closest('summary')!);
    fireEvent.change(screen.getByLabelText('Заметка к этому выполнению'), {
      target: { value: 'Для прежнего упражнения' },
    });
    const replacement = { ...exercise, exercise_id: 12, exercise_title: 'Приседания' };
    const revisedWorkout = { ...workout, exercises: [replacement] };
    view.rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ExerciseNoteRecovery userId={7} workout={revisedWorkout} />
        <ExerciseExecutionNote
          key={12}
          userId={7}
          workout={revisedWorkout}
          exercise={replacement}
          visible
        />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText('Несохранённый черновик').closest('summary')!);
    expect(screen.getByText('Для прежнего упражнения')).toBeVisible();
    fireEvent.click(screen.getByText('Заметка к упражнению').closest('summary')!);
    expect(screen.getByLabelText('Заметка к этому выполнению')).toHaveValue('');
  });
});
