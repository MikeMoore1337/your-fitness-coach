import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PreviousWorkoutNote } from '../../../../src/features/workouts/PreviousWorkoutNote';

const apiMock = vi.hoisted(() => vi.fn());
const auth = vi.hoisted(() => ({ user: { id: 7 } as { id: number } | null }));
const runtime = vi.hoisted(() => ({ kind: 'production' }));
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({ useAuth: () => auth }));
vi.mock('../../../../src/shared/runtime/runtime', () => ({ useRuntime: () => runtime }));

const savedNote = {
  note: 'Жим ногами можно прибавить',
  completed_on: '2026-10-23',
  day_number: 3,
  workout_title: 'Силовая база',
  is_latest_completion: true,
};

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value });
  window.dispatchEvent(new Event(value ? 'online' : 'offline'));
}

function setup(workoutId = 42) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <PreviousWorkoutNote workoutId={workoutId} />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

describe('previous workout note', () => {
  beforeEach(() => {
    auth.user = { id: 7 };
    runtime.kind = 'production';
    apiMock.mockReset();
    setOnline(true);
  });

  afterEach(() => {
    cleanup();
    setOnline(true);
  });

  it('shows the actual day and date and can collapse without changing the text', async () => {
    apiMock.mockResolvedValue({ previous_note: savedNote });
    setup();
    expect(await screen.findByText(savedNote.note)).toBeVisible();
    expect(screen.getByText('День 3 «Силовая база» · 23 октября 2026')).toBeVisible();
    const heading = screen.getByText('Заметка с прошлого выполнения');
    const details = heading.closest('details')!;
    expect(details.open).toBe(true);
    fireEvent.click(heading.closest('summary')!);
    expect(details.open).toBe(false);
    fireEvent.click(heading.closest('summary')!);
    expect(details.open).toBe(true);
    expect(screen.getByText(savedNote.note)).toBeVisible();
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/workouts/42/previous-completion-note',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('labels an older note honestly and renders user text as text', async () => {
    apiMock.mockResolvedValue({
      previous_note: {
        ...savedNote,
        is_latest_completion: false,
        note: '<b>Не HTML</b>\nСтрока 2',
      },
    });
    const { container } = setup();
    expect(await screen.findByText('Последняя сохранённая заметка')).toBeVisible();
    expect(screen.getByText(/Не HTML/).textContent).toBe('<b>Не HTML</b>\nСтрока 2');
    expect(container.querySelector('b')).toBeNull();
  });

  it('hides stale data offline and waits for a fresh response on reconnect', async () => {
    let resolveRefresh!: (value: unknown) => void;
    apiMock
      .mockResolvedValueOnce({ previous_note: savedNote })
      .mockImplementationOnce(() => new Promise((resolve) => (resolveRefresh = resolve)));
    setup();
    expect(await screen.findByText(savedNote.note)).toBeVisible();
    act(() => setOnline(false));
    expect(screen.queryByText(savedNote.note)).toBeNull();
    act(() => setOnline(true));
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(savedNote.note)).toBeNull();
    await act(async () =>
      resolveRefresh({ previous_note: { ...savedNote, note: 'Исправленная' } }),
    );
    expect(await screen.findByText('Исправленная')).toBeVisible();
    expect(screen.queryByText(savedNote.note)).toBeNull();
  });

  it('hides a previously confirmed note when the read fails or the note is deleted', async () => {
    apiMock
      .mockResolvedValueOnce({ previous_note: savedNote })
      .mockRejectedValueOnce(new Error('409'));
    const { client } = setup();
    await screen.findByText(savedNote.note);
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['workout', 'previous-completion-note'] });
    });
    await waitFor(() => expect(screen.queryByText(savedNote.note)).toBeNull());
    apiMock.mockResolvedValueOnce({ previous_note: null });
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['workout', 'previous-completion-note'] });
    });
    expect(screen.queryByText(savedNote.note)).toBeNull();
  });

  it('never shows a late response from another account or in demo mode', async () => {
    let resolveOld!: (value: unknown) => void;
    apiMock
      .mockImplementationOnce(() => new Promise((resolve) => (resolveOld = resolve)))
      .mockResolvedValueOnce({
        previous_note: { ...savedNote, note: 'Заметка второго пользователя' },
      });
    const { rerender, client } = setup();
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(1));
    auth.user = { id: 8 };
    rerender(
      <QueryClientProvider client={client}>
        <PreviousWorkoutNote workoutId={42} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Заметка второго пользователя')).toBeVisible();
    await act(async () => resolveOld({ previous_note: savedNote }));
    expect(screen.queryByText(savedNote.note)).toBeNull();
    runtime.kind = 'demo';
    rerender(
      <QueryClientProvider client={client}>
        <PreviousWorkoutNote workoutId={42} />
      </QueryClientProvider>,
    );
    expect(screen.queryByText('Заметка второго пользователя')).toBeNull();
  });
});
