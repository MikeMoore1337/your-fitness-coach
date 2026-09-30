import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AiAdaptationProposal } from '../../../../src/features/ai/AiAdaptationProposal';
import { ApiError } from '../../../../src/shared/api/client';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../../src/shared/api/client')>(
    '../../../../src/shared/api/client',
  );
  return { ...actual, api: apiMock };
});

const availableStatus = {
  ui_enabled: true,
  generic_available: true,
  personal_available: true,
};
const consentGranted = {
  status: 'granted',
  scope: 'personal_ai_coach',
  consent_version: 'v1',
  categories: ['workout'],
  purpose: 'bounded adaptation',
  provider_name: 'controlled provider',
  provider_policy_revision: 'v1',
  retention_notice: 'short lived',
  consent_source: 'settings',
  granted_at: '2026-09-30T10:00:00Z',
  revoked_at: null,
};
const proposalId = 'a'.repeat(64);
const proposal = {
  proposal_id: proposalId,
  proposal_type: 'progression_explanation',
  target_program_id: 77,
  target_revision_id: 12,
  target_revision_number: 2,
  target_block_id: null,
  target_exercise_id: null,
  explanation: 'Детерминированная прогрессия уже учитывает доступные результаты.',
  suggested_change: {
    operation: 'explanation_only',
    replacement_candidate_ref: null,
    prescribed_sets: null,
    prescribed_reps: null,
    rest_seconds: null,
    effective_scope: 'next_workout',
  },
  evidence_ids: ['evidence:progression'],
  deterministic_rule_relationship: 'supports_deterministic_rule',
  limitations: ['Нужна явная проверка пользователя.'],
  requires_confirmation: true,
} as const;
const proposalResponse = {
  outcome: 'answer',
  proposal,
  proposal_token: 'signed-proposal-token',
  limitations: [],
  safety_category: 'clear',
  prompt_version: 'ai-coach-adaptation-v1',
  schema_version: 'ai-coach-adaptation-output-v1',
  policy_version: 'ai-coach-adaptation-policy-v1',
  request_id: 'request-1',
  quota: null,
};

function renderProposal() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <AiAdaptationProposal programId={77} revisionNumber={2} targetWorkoutId={42} />
    </QueryClientProvider>,
  );
}

function mockApi({
  consent = consentGranted,
  proposalResult = proposalResponse,
  reviewResult = {
    outcome: 'answer',
    proposal_id: proposalId,
    decision: 'confirm',
    applied: true,
    idempotent: false,
    current_revision_number: 3,
    limitations: [],
    quota: null,
  },
  status = availableStatus,
}: {
  consent?: unknown;
  proposalResult?: unknown;
  reviewResult?: unknown;
  status?: unknown;
} = {}) {
  apiMock.mockImplementation(
    async (path: string, options?: { method?: string; body?: unknown }) => {
      if (path === '/api/v1/ai-coach/status') return status;
      if (path === '/api/v1/ai-coach/consent') return consent;
      if (path === '/api/v1/ai-coach/adaptations/proposals') return proposalResult;
      if (path.endsWith('/review')) return reviewResult;
      throw new Error(`Unexpected API path: ${path} ${JSON.stringify(options)}`);
    },
  );
}

describe('AiAdaptationProposal', () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  afterEach(() => cleanup());

  it('keeps the request bounded, renders a review, and confirms once without optimistic apply', async () => {
    const onApplied = vi.fn();
    mockApi();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <AiAdaptationProposal
          onApplied={onApplied}
          programId={77}
          revisionNumber={2}
          targetWorkoutId={42}
        />
      </QueryClientProvider>,
    );

    await screen.findByRole('button', { name: 'Предложить адаптацию с AI' });
    fireEvent.click(screen.getByRole('button', { name: 'Предложить адаптацию с AI' }));
    expect(apiMock).not.toHaveBeenCalledWith(
      '/api/v1/ai-coach/adaptations/proposals',
      expect.anything(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));

    expect(await screen.findByText(proposal.explanation)).toBeInTheDocument();
    expect(screen.getByText('Поддерживает детерминированное правило')).toBeInTheDocument();
    expect(screen.getByText(/результаты прогрессии/)).toBeInTheDocument();
    expect(screen.getByText('Нужна явная проверка пользователя.')).toBeInTheDocument();
    expect(screen.queryByText('evidence:progression')).not.toBeInTheDocument();
    const generateCall = apiMock.mock.calls.find(
      ([path]) => path === '/api/v1/ai-coach/adaptations/proposals',
    );
    expect(generateCall?.[1]).toEqual({
      method: 'POST',
      body: {
        program_id: 77,
        expected_revision_number: 2,
        target_workout_id: 42,
        message: 'Предложи безопасную адаптацию текущей программы с учётом ближайшей тренировки.',
        locale: 'ru',
      },
    });
    expect(onApplied).not.toHaveBeenCalled();

    const confirm = screen.getByRole('button', { name: 'Подтвердить адаптацию' });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await screen.findByText(/Предложение подтверждено/);
    expect(onApplied).toHaveBeenCalledWith(3);
    const reviewCalls = apiMock.mock.calls.filter(([path]) => path.endsWith('/review'));
    expect(reviewCalls).toHaveLength(1);
    expect(reviewCalls[0]?.[1]).toEqual({
      method: 'POST',
      body: {
        proposal_id: proposalId,
        proposal_token: 'signed-proposal-token',
        expected_revision_number: 2,
        decision: 'confirm',
      },
    });
  });

  it('rejects without changing the program', async () => {
    mockApi({
      reviewResult: {
        outcome: 'answer',
        proposal_id: proposalId,
        decision: 'reject',
        applied: false,
        idempotent: false,
        current_revision_number: 2,
        limitations: [],
        quota: null,
      },
    });
    renderProposal();
    fireEvent.click(await screen.findByRole('button', { name: 'Предложить адаптацию с AI' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));
    await screen.findByRole('button', { name: 'Отклонить' });
    fireEvent.click(screen.getByRole('button', { name: 'Отклонить' }));
    expect(
      await screen.findByText(/Текущая программа сохранена без изменений/),
    ).toBeInTheDocument();
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/review'))[0]?.[1]).toEqual({
      method: 'POST',
      body: {
        proposal_id: proposalId,
        proposal_token: 'signed-proposal-token',
        expected_revision_number: 2,
        decision: 'reject',
      },
    });
  });

  it('does not request an adaptation without consent', async () => {
    mockApi({ consent: { ...consentGranted, status: 'revoked' } });
    renderProposal();
    fireEvent.click(await screen.findByRole('button', { name: 'Предложить адаптацию с AI' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));
    await waitFor(() =>
      expect(apiMock.mock.calls.some(([path]) => path === '/api/v1/ai-coach/consent')).toBe(true),
    );
    expect(await screen.findByText(/отдельное согласие/)).toBeInTheDocument();
    expect(
      apiMock.mock.calls.some(([path]) => path === '/api/v1/ai-coach/adaptations/proposals'),
    ).toBe(false);
  });

  it('fails closed for disabled and malformed responses', async () => {
    mockApi({ status: { ...availableStatus, ui_enabled: false, personal_available: false } });
    renderProposal();
    await screen.findByRole('button', { name: 'AI-адаптация недоступна' });
    expect(screen.getByTestId('ai-adaptation')).toHaveAttribute('data-state', 'disabled');
    expect(screen.getByRole('button', { name: 'AI-адаптация недоступна' })).toBeDisabled();

    cleanup();
    apiMock.mockReset();
    mockApi({
      proposalResult: {
        ...proposalResponse,
        proposal: { ...proposal, requires_confirmation: false },
      },
    });
    renderProposal();
    fireEvent.click(await screen.findByRole('button', { name: 'Предложить адаптацию с AI' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));
    expect(await screen.findByText(/не прошёл проверку формата/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Подтвердить адаптацию' })).not.toBeInTheDocument();
  });

  it('shows a stale state without retrying automatically', async () => {
    mockApi();
    apiMock.mockImplementation(
      async (path: string, options?: { method?: string; body?: unknown }) => {
        if (path === '/api/v1/ai-coach/status') return availableStatus;
        if (path === '/api/v1/ai-coach/consent') return consentGranted;
        if (path === '/api/v1/ai-coach/adaptations/proposals') return proposalResponse;
        if (path.endsWith('/review')) throw new ApiError('Program revision conflict', 409);
        throw new Error(`Unexpected API path: ${path} ${JSON.stringify(options)}`);
      },
    );
    renderProposal();
    fireEvent.click(await screen.findByRole('button', { name: 'Предложить адаптацию с AI' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Подтвердить адаптацию' }));
    expect(await screen.findByText(/Программа уже изменилась/)).toBeInTheDocument();
    expect(apiMock.mock.calls.filter(([path]) => path.endsWith('/review'))).toHaveLength(1);
  });

  it('shows provider unavailability without exposing a confirm action', async () => {
    mockApi({
      proposalResult: {
        outcome: 'unavailable',
        proposal: null,
        proposal_token: null,
        limitations: ['Поставщик временно недоступен.'],
        safety_category: 'provider_unavailable',
        prompt_version: 'ai-coach-adaptation-v1',
        schema_version: 'ai-coach-adaptation-output-v1',
        policy_version: 'ai-coach-adaptation-policy-v1',
        request_id: 'request-unavailable',
        quota: null,
      },
    });
    renderProposal();
    fireEvent.click(await screen.findByRole('button', { name: 'Предложить адаптацию с AI' }));
    fireEvent.click(screen.getByRole('button', { name: 'Сформировать предложение' }));
    expect(await screen.findByText(/AI-адаптация сейчас недоступна/)).toBeInTheDocument();
    expect(screen.getByText('Поставщик временно недоступен.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Подтвердить адаптацию' })).not.toBeInTheDocument();
  });
});
