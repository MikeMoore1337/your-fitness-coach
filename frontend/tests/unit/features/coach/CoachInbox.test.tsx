import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CoachInbox } from '../../../../src/features/coach/CoachInbox';
import type { CoachInbox as CoachInboxResponse } from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import {
  PRODUCTION_CAPABILITIES,
  resetApiRuntime,
  setApiRuntime,
} from '../../../../src/shared/runtime/runtime';

const response = {
  date: '2026-10-07',
  timezone: 'Europe/Moscow',
  total: 1,
  generated_at: '2026-10-07T10:00:00Z',
  counts: {
    attention: 1,
    pending_reviews: 1,
    tasks: 1,
    sessions: 0,
    packages: 0,
    payments: 0,
  },
  items: [
    {
      key: 'task:1',
      kind: 'task',
      client: { id: 7, name: 'Анна' },
      title: 'Проверить следующий шаг',
      reason: 'Открытая задача тренера.',
      source_kind: 'manual',
      source_id: 1,
      action: 'open_task',
      destination: '/coach?tab=tools&tool=tasks',
      priority: 'urgent',
      created_at: '2026-10-07T09:00:00Z',
      due_at: '2026-10-07T10:00:00Z',
      evidence: [{ label: 'Срок', value: '2026-10-07T10:00:00+00:00' }],
    },
  ],
} as unknown as CoachInboxResponse;

afterEach(() => {
  cleanup();
  resetApiRuntime();
  vi.restoreAllMocks();
});

describe('CoachInbox', () => {
  it('renders one server-derived action without private payload fields', async () => {
    setApiRuntime({ kind: 'production', capabilities: PRODUCTION_CAPABILITIES });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <NavigationProvider>
          <CoachInbox />
        </NavigationProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Следующий шаг по клиентам' })).toBeVisible();
    expect(await screen.findByText('Проверить следующий шаг')).toBeVisible();
    expect(screen.getByText('Задачи')).toBeVisible();
    expect(screen.queryByText('Секретная заметка')).not.toBeInTheDocument();
  });
});
