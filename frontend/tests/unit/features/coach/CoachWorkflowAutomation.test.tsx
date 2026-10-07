import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CoachWorkflowAutomation } from '../../../../src/features/coach/CoachWorkflowAutomation';
import type { CoachWorkflowAutomation as CoachWorkflowAutomationResponse } from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import {
  PRODUCTION_CAPABILITIES,
  resetApiRuntime,
  setApiRuntime,
} from '../../../../src/shared/runtime/runtime';

const preview = {
  ruleset_version: 'coach-workflow-v1',
  mode: 'preview',
  events_evaluated: 1,
  proposals: [
    {
      key: 'check_in_submitted:7:44:check-in-submitted-v1',
      event_kind: 'check_in_submitted',
      rule_id: 'check-in-submitted-v1',
      client_id: 7,
      client_name: 'Анна',
      source_kind: 'weekly_check_in',
      source_id: 44,
      occurred_at: '2026-10-07T10:00:00Z',
      title: 'Проверить недельный итог',
      reason: 'Клиент отправил недельный итог; проверьте его вручную.',
      priority: 'urgent',
      outcome: 'draft',
      task_id: null,
      task_state: null,
    },
  ],
  tasks_created: 0,
  tasks_reused: 0,
  generated_at: '2026-10-07T10:00:00Z',
} as unknown as CoachWorkflowAutomationResponse;

const evaluated = {
  ...preview,
  mode: 'evaluated',
  proposals: preview.proposals?.map((proposal) => ({
    ...proposal,
    outcome: 'created',
    task_id: 99,
    task_state: 'open',
  })),
  tasks_created: 1,
} as unknown as CoachWorkflowAutomationResponse;

afterEach(() => {
  cleanup();
  resetApiRuntime();
  vi.restoreAllMocks();
});

describe('CoachWorkflowAutomation', () => {
  it('keeps generated proposals visibly pending trainer confirmation', async () => {
    setApiRuntime({ kind: 'production', capabilities: PRODUCTION_CAPABILITIES });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/workflow-automation/evaluate') && init?.method === 'POST') {
        return new Response(JSON.stringify(evaluated), { status: 200 });
      }
      return new Response(JSON.stringify(preview), { status: 200 });
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <NavigationProvider>
            <CoachWorkflowAutomation />
          </NavigationProvider>
        </FeedbackProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Предложения для тренера' })).toBeVisible();
    expect(await screen.findByText('Черновик')).toBeVisible();
    expect(await screen.findByText('Черновик задачи требует подтверждения тренера.')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Собрать предложения' }));
    expect(await screen.findByText('Открыто')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Открыть задачу' })).toHaveAttribute(
      'href',
      '/coach?tab=tools&tool=tasks',
    );
  });
});
