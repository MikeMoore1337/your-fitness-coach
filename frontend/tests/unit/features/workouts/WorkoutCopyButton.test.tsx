import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Workout, WorkoutCopy } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { WorkoutCopyButton } from '../../../../src/features/workouts/WorkoutCopyButton';

const apiMock = vi.fn();
vi.mock('../../../../src/shared/api/client', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}));

const workout: Workout = {
  id: 42,
  title: 'Силовая тренировка',
  scheduled_date: '2026-10-30',
  completed_at: '2026-10-30T10:00:00',
  status: 'completed',
  day_number: 1,
  week_number: 1,
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Приседания',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 1,
      prescribed_reps: '8',
      rest_seconds: 90,
      has_guide: false,
      notes: 'СЕКРЕТНАЯ ЗАМЕТКА',
      sets: [
        {
          id: 201,
          set_number: 1,
          actual_weight: 40,
          actual_reps: 8,
          set_kind: 'working',
          is_completed: true,
          version: 1,
        },
      ],
    },
  ],
};

const history: WorkoutCopy = {
  title: workout.title,
  scheduled_date: workout.scheduled_date,
  completed_at: workout.completed_at,
  exercises: [
    {
      exercise_title: 'Приседания',
      metric_type: 'strength',
      sort_order: 1,
      sets: [
        {
          set_number: 1,
          actual_weight: 40,
          actual_reps: 8,
          set_kind: 'working',
          is_completed: true,
        },
      ],
    },
  ],
};

const expected =
  'Силовая тренировка\n30.10.2026\n\nПриседания\nРабочий подход 1: 40 кг × 8 повторений';
let clipboardDescriptor: PropertyDescriptor | undefined;

function setClipboard(value: unknown) {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value });
}

function renderButton(props: { workout: Workout } | { workoutId: number; workoutTitle: string }) {
  return render(
    <FeedbackProvider>
      <WorkoutCopyButton {...props} />
    </FeedbackProvider>,
  );
}

beforeEach(() => {
  clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  apiMock.mockReset();
});

afterEach(() => {
  cleanup();
  if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor);
  else Reflect.deleteProperty(navigator, 'clipboard');
  vi.unstubAllGlobals();
});

describe('WorkoutCopyButton', () => {
  it('copies the saved completion response without requesting history or private notes', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    renderButton({ workout });

    fireEvent.click(screen.getByRole('button', { name: 'Скопировать тренировку' }));

    await screen.findByText('Тренировка скопирована');
    expect(writeText).toHaveBeenCalledWith(expected);
    expect(apiMock).not.toHaveBeenCalled();
  });

  it('opens selectable manual text when clipboard access fails', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
    renderButton({ workout });
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать тренировку' }));

    const text = await screen.findByRole('textbox', { name: 'Текст тренировки' });
    expect(text).toHaveValue(expected);
    expect(screen.queryByText('Тренировка скопирована')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Выделить' }));
    expect((text as HTMLTextAreaElement).selectionStart).toBe(0);
    expect((text as HTMLTextAreaElement).selectionEnd).toBe(expected.length);
    fireEvent.click(screen.getByText('Закрыть', { selector: 'button' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers manual text when the Clipboard API is absent', async () => {
    setClipboard(undefined);
    renderButton({ workout });
    fireEvent.click(screen.getByRole('button', { name: 'Скопировать тренировку' }));

    expect(await screen.findByRole('textbox', { name: 'Текст тренировки' })).toHaveValue(expected);
    expect(screen.queryByText('Тренировка скопирована')).not.toBeInTheDocument();
  });

  it('starts a promise-backed clipboard write during the history click', async () => {
    let resolveHistory!: (value: WorkoutCopy) => void;
    apiMock.mockReturnValue(
      new Promise<WorkoutCopy>((resolve) => {
        resolveHistory = resolve;
      }),
    );
    class FakeClipboardItem {
      constructor(public data: Record<string, Promise<Blob>>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    const write = vi.fn(async ([item]: FakeClipboardItem[]) => {
      const data = item?.data['text/plain'];
      if (!data) throw new Error('Clipboard text missing');
      await data;
    });
    setClipboard({ write });
    renderButton({ workoutId: 42, workoutTitle: workout.title });

    fireEvent.click(
      screen.getByRole('button', { name: 'Скопировать тренировку: Силовая тренировка' }),
    );
    expect(apiMock).toHaveBeenCalledWith('/api/v1/workouts/42/copy');
    expect(write).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole('button', { name: 'Скопировать тренировку: Силовая тренировка' }),
    ).toBeDisabled();
    expect(screen.queryByText('Тренировка скопирована')).not.toBeInTheDocument();
    resolveHistory(history);
    await screen.findByText('Тренировка скопирована');
  });

  it('offers manual history text after both clipboard methods reject', async () => {
    apiMock.mockResolvedValue(history);
    class FakeClipboardItem {
      constructor(public data: Record<string, Promise<Blob>>) {}
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);
    setClipboard({
      write: vi.fn().mockRejectedValue(new Error('denied')),
      writeText: vi.fn().mockRejectedValue(new Error('denied')),
    });
    renderButton({ workoutId: 42, workoutTitle: workout.title });
    fireEvent.click(
      screen.getByRole('button', { name: 'Скопировать тренировку: Силовая тренировка' }),
    );

    expect(await screen.findByRole('textbox', { name: 'Текст тренировки' })).toHaveValue(expected);
    expect(apiMock).toHaveBeenCalledTimes(1);
  });

  it('reports a history load failure instead of claiming a copy', async () => {
    apiMock.mockRejectedValue(new Error('offline'));
    setClipboard(undefined);
    renderButton({ workoutId: 42, workoutTitle: workout.title });
    fireEvent.click(
      screen.getByRole('button', { name: 'Скопировать тренировку: Силовая тренировка' }),
    );

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Не удалось загрузить тренировку'),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText('Тренировка скопирована')).not.toBeInTheDocument();
  });
});
