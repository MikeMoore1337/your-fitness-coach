import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkoutRecovery } from '../../../../src/features/workouts/WorkoutRecovery';
import type { WorkoutRecoveryPreview, WorkoutScheduleItem } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const workout: WorkoutScheduleItem = {
  id: 42,
  scheduled_date: '2030-01-10',
  scheduled_time: '18:30:00',
  title: 'Тренировка A',
  status: 'planned',
  day_number: 1,
  week_number: 1,
};

const preview: WorkoutRecoveryPreview = {
  status: 'preview',
  workout,
  action: 'move',
  ruleset_version: 'schedule-recovery-v1',
  changes: [
    {
      kind: 'moved',
      from_scheduled_date: '2030-01-10',
      from_scheduled_time: '18:30:00',
      to_scheduled_date: '2030-01-12',
      to_scheduled_time: '19:15:00',
    },
  ],
  remaining_workouts: [],
  warnings: [],
  message: 'Перенесём только эту тренировку.',
  preview_token: 'a'.repeat(64),
};

function renderRecovery() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <WorkoutRecovery workout={workout} />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('WorkoutRecovery', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('requires preview before applying a schedule change', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/recovery/preview')) {
        return new Response(JSON.stringify(preview), { status: 200 });
      }
      if (path.endsWith('/recovery/apply')) {
        return new Response(
          JSON.stringify({
            applied_at: '2030-01-10T12:00:00',
            workout: { ...workout, scheduled_date: '2030-01-12', scheduled_time: '19:15:00' },
            remaining_workouts: [],
            next_workout: null,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    const user = userEvent.setup();
    renderRecovery();

    await user.click(screen.getByRole('button', { name: 'Изменить план' }));
    await user.click(screen.getByLabelText('Новая дата'));
    await user.clear(screen.getByLabelText('Новая дата'));
    await user.type(screen.getByLabelText('Новая дата'), '2030-01-12');
    await user.click(screen.getByRole('button', { name: 'Показать изменения' }));

    expect(await screen.findByRole('heading', { name: 'Что изменится' })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/recovery/apply')),
    ).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: 'Подтвердить' }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/recovery/apply'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"preview_token"'),
        }),
      ),
    );
  });
});
