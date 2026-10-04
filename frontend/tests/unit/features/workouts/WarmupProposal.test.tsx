import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WarmupProposal } from '../../../../src/features/workouts/WarmupProposal';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const preview = {
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
};

function renderProposal() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <WarmupProposal
          workoutId={42}
          workoutExerciseId={101}
          targetSetId={201}
          exerciseTitle="Жим штанги лежа"
          workingWeight="80"
          disabled={false}
          hasWarmupRows={false}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('WarmupProposal', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
  });

  it('keeps the proposal local until confirmation and applies edited rows', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/warmup-proposals/preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      if (path.endsWith('/warmup-proposals/apply')) {
        return new Response(
          JSON.stringify({
            workout_id: 42,
            workout_exercise_id: 101,
            ruleset_version: 'warmup-proposal-v1',
            idempotent: false,
            materialized_set_ids: [301, 302, 303],
            workout: {},
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    const user = userEvent.setup();
    renderProposal();

    await user.click(screen.getByRole('button', { name: 'Подготовить разминку' }));
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Рассчитать предложение' }));
    await screen.findByRole('heading', { name: 'Проверьте подходы' });
    expect(screen.getByLabelText('Вес разминки, подход 1')).toHaveValue(32);
    expect(screen.getByLabelText('Повторы разминки, подход 1')).toHaveValue(8);

    await user.clear(screen.getByLabelText('Вес разминки, подход 1'));
    await user.type(screen.getByLabelText('Вес разминки, подход 1'), '30');
    await user.click(screen.getByRole('button', { name: 'Добавить подход' }));
    expect(screen.getByLabelText('Вес разминки, подход 4')).toHaveValue(null);
    await user.click(screen.getByRole('button', { name: 'Удалить подход разминки 4' }));
    expect(screen.queryByLabelText('Вес разминки, подход 4')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Добавить в тренировку' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const applyCall = fetchMock.mock.calls[1]!;
    const body = JSON.parse(String((applyCall[1] as RequestInit).body)) as {
      rows: Array<{ weight_kg: number; reps: number }>;
      mutation_id: string;
      state_token: string;
      proposal_token: string;
    };
    expect(body.rows).toEqual([
      { weight_kg: 30, reps: 8 },
      { weight_kg: 48, reps: 5 },
      { weight_kg: 60, reps: 3 },
    ]);
    expect(body.mutation_id).toHaveLength(36);
    expect(body.state_token).toBe('a'.repeat(64));
    expect(body.proposal_token).toBe('b'.repeat(64));
    expect(
      await screen.findByText('Разминочные подходы добавлены в эту тренировку'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('requires a fresh preview after a stale conflict', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/warmup-proposals/preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      return new Response(
        JSON.stringify({ detail: { code: 'warmup_stale', message: 'Тренировка изменилась' } }),
        { status: 409 },
      );
    });
    const user = userEvent.setup();
    renderProposal();

    await user.click(screen.getByRole('button', { name: 'Подготовить разминку' }));
    await user.click(screen.getByRole('button', { name: 'Рассчитать предложение' }));
    await screen.findByRole('heading', { name: 'Проверьте подходы' });
    await user.click(screen.getByRole('button', { name: 'Добавить в тренировку' }));

    expect(
      await screen.findByText(
        'Тренировка уже изменилась. Сформируйте предложение заново перед добавлением.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Добавить в тренировку' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Обновить предложение' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not offer persistence while offline', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    renderProposal();

    expect(
      screen.getByText('Разминка требует подключения. Ничего не сохранено.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подготовить разминку' })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does not render a duplicate entry after warm-up rows exist', () => {
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <WarmupProposal
            workoutId={42}
            workoutExerciseId={101}
            targetSetId={301}
            exerciseTitle="Жим штанги лежа"
            workingWeight="80"
            disabled={false}
            hasWarmupRows
          />
        </FeedbackProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText('Разминочные подходы уже добавлены.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Подготовить разминку' })).not.toBeInTheDocument();
  });
});
