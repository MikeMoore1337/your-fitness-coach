import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AssignedProgramDetails } from '../../../../src/features/programs/AssignedProgramDetails';
import { ApiError } from '../../../../src/shared/api/client';
import type {
  ProgramRevision,
  TrainingBlock,
} from '../../../../src/features/programs/programHistory';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../../src/shared/api/client')>(
    '../../../../src/shared/api/client',
  );
  return { ...actual, api: apiMock };
});

function block(overrides: Partial<TrainingBlock> = {}): TrainingBlock {
  return {
    id: 301,
    user_program_id: 77,
    title: 'Техническая база',
    start_date: '2026-08-03',
    end_date: '2026-08-23',
    duration_days: 21,
    purpose: 'Закрепить технику основных движений',
    priority_muscle_ids: [],
    notes: 'Без отказных повторов.',
    is_deload: false,
    status: 'active',
    created_by_user_id: 1,
    created_at: '2026-08-03T08:00:00',
    updated_at: '2026-08-10T08:00:00',
    ...overrides,
  };
}

function revisions(currentBlock: TrainingBlock): ProgramRevision[] {
  const workout = {
    id: 42,
    scheduled_date: '2026-08-20',
    title: 'Силовая база',
    status: 'completed',
    exercises: [],
  };
  const previousBlock = { ...currentBlock, purpose: 'Закрепить технику' };
  return [
    {
      id: 2,
      user_program_id: 77,
      revision_number: 2,
      changed_by_user_id: 11,
      actor_role: 'trainer',
      change_kind: 'block_updated',
      reason: 'Добавить устойчивый рабочий объём',
      changed_fields: { block_id: 301, fields: ['purpose'] },
      snapshot: { training_blocks: [currentBlock], workouts: [workout] },
      created_at: '2026-08-22T12:00:00',
    },
    {
      id: 1,
      user_program_id: 77,
      revision_number: 1,
      changed_by_user_id: 1,
      actor_role: 'self',
      change_kind: 'assigned',
      reason: null,
      changed_fields: {},
      snapshot: { training_blocks: [previousBlock], workouts: [workout] },
      created_at: '2026-08-03T08:00:00',
    },
  ];
}

function renderDetails() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <NavigationProvider>
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <AssignedProgramDetails
            programId={77}
            currentRevisionNumber={2}
            startDate="2026-08-03"
            durationWeeks={8}
            workoutHistoryReturnPath="/app?section=programs"
          />
        </FeedbackProvider>
      </QueryClientProvider>
    </NavigationProvider>,
  );
}

describe('AssignedProgramDetails', () => {
  beforeEach(() => {
    apiMock.mockReset();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    window.history.replaceState({}, '', '/app?section=programs');
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('shows the current block first and exposes trainer, reason, readable diff and revision workout', async () => {
    const currentBlock = block();
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/blocks')) return [currentBlock];
      if (path.endsWith('/revisions')) return revisions(currentBlock);
      throw new Error(`Unexpected API path: ${path}`);
    });

    renderDetails();

    expect(await screen.findByText('Текущий тренировочный блок')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Техническая база' })).toBeInTheDocument();
    expect(screen.getAllByText('Закрепить технику основных движений').length).toBeGreaterThan(0);
    expect(apiMock).not.toHaveBeenCalledWith(expect.stringContaining('/revisions'));

    fireEvent.click(screen.getByText('Все этапы и изменения').closest('summary')!);
    const revisionSummary = await screen.findByText('Тренировочный блок изменён');
    fireEvent.click(revisionSummary.closest('summary')!);

    expect(screen.getByText('Тренер · 22.08.2026, 12:00')).toBeInTheDocument();
    expect(screen.getByText('Добавить устойчивый рабочий объём')).toBeInTheDocument();
    expect(screen.getByText('Закрепить технику')).toBeInTheDocument();
    expect(screen.getAllByText('Закрепить технику основных движений').length).toBeGreaterThan(1);
    const workoutLink = screen.getAllByRole('link', { name: /Силовая база.*Открыть/ })[0]!;
    expect(workoutLink).toHaveAttribute('href', expect.stringContaining('workout_id=42'));
    expect(workoutLink).toHaveAttribute('href', expect.stringContaining('program_history=77'));
    expect(workoutLink).toHaveAttribute('href', expect.stringContaining('program_revision=2'));
    expect(workoutLink).toHaveAttribute('href', expect.stringContaining('program_revision%3D2'));
  });

  it.each([
    ['prescription_updated', 'Предписание упражнения изменено'],
    ['exercise_replaced', 'Упражнение заменено'],
  ] as const)('derives the %s label from structured revision data', async (operation, label) => {
    const currentBlock = block();
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/blocks')) return [currentBlock];
      if (path.endsWith('/revisions')) {
        const history = revisions(currentBlock);
        history[0] = {
          ...history[0]!,
          change_kind: 'plan_updated',
          changed_fields: { operation },
        };
        return history;
      }
      throw new Error(`Unexpected API path: ${path}`);
    });

    renderDetails();

    fireEvent.click((await screen.findByText('Все этапы и изменения')).closest('summary')!);
    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it('keeps empty blocks distinct from empty revision history', async () => {
    apiMock.mockResolvedValue([]);

    renderDetails();

    expect(await screen.findByText('Тренировочные блоки ещё не настроены')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Все этапы и изменения').closest('summary')!);
    expect(
      await screen.findByText('История появится после первого сохранённого изменения'),
    ).toBeInTheDocument();
  });

  it('explains that a revoked trainer may no longer access program history', async () => {
    apiMock.mockRejectedValue(new ApiError('Доступ к клиенту отозван', 403));

    renderDetails();

    expect(
      await screen.findByText(
        'История недоступна. Возможно, доступ тренера к программе был отозван.',
      ),
    ).toBeInTheDocument();
  });

  it('requires a reason for a trainer-compatible edit and sends it with the optimistic revision', async () => {
    const currentBlock = block();
    apiMock.mockImplementation(
      async (path: string, options?: { method?: string; body?: unknown }) => {
        if (path.includes('/blocks/') && options?.method === 'PATCH') {
          return { block: currentBlock, current_revision_number: 3 };
        }
        if (path.endsWith('/blocks')) return [currentBlock];
        if (path.endsWith('/revisions')) return revisions(currentBlock);
        throw new Error(`Unexpected API path: ${path}`);
      },
    );

    renderDetails();
    await screen.findByText('Текущий тренировочный блок');
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    const save = screen.getByRole('button', { name: 'Сохранить изменения' });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Цель этапа'), {
      target: { value: 'Закрепить технику и увеличить рабочий объём' },
    });
    fireEvent.change(screen.getByLabelText('Почему меняется программа'), {
      target: { value: 'Клиент уверенно выполняет текущий объём' },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/77/blocks/301', {
        method: 'PATCH',
        body: expect.objectContaining({
          expected_revision_number: 2,
          purpose: 'Закрепить технику и увеличить рабочий объём',
          reason: 'Клиент уверенно выполняет текущий объём',
        }),
      }),
    );
  });

  it('closes a stale editor after a revision conflict instead of rebasing old fields', async () => {
    const staleBlock = block();
    const freshBlock = block({ purpose: 'Свежая цель тренера' });
    let blockReads = 0;
    apiMock.mockImplementation(
      async (path: string, options?: { method?: string; body?: unknown }) => {
        if (path.includes('/blocks/') && options?.method === 'PATCH') {
          throw new ApiError('Program revision conflict', 409);
        }
        if (path.endsWith('/blocks')) {
          blockReads += 1;
          return [blockReads === 1 ? staleBlock : freshBlock];
        }
        if (path.endsWith('/revisions')) return revisions(freshBlock);
        throw new Error(`Unexpected API path: ${path}`);
      },
    );

    renderDetails();
    await screen.findByText('Текущий тренировочный блок');
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByLabelText('Цель этапа'), {
      target: { value: 'Устаревшая локальная цель' },
    });
    fireEvent.change(screen.getByLabelText('Почему меняется программа'), {
      target: { value: 'Старый черновик' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

    await waitFor(() => expect(screen.queryByLabelText('Цель этапа')).not.toBeInTheDocument());
    expect(screen.queryByDisplayValue('Устаревшая локальная цель')).not.toBeInTheDocument();
    expect((await screen.findAllByText('Свежая цель тренера')).length).toBeGreaterThan(0);
  });
});
