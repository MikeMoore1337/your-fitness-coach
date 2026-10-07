import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  Client,
  CoachAssignedProgram,
  ProgramTemplate,
} from '../../../../src/shared/api/types';
import { CoachProgramBulkOperations } from '../../../../src/features/coach/CoachProgramBulkOperations';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const clients = [
  { id: 71, status: 'active', full_name: 'Анна' },
  { id: 72, status: 'active', full_name: 'Иван' },
  { id: 73, status: 'active', full_name: 'Борис' },
] as Client[];

function program(id: number, clientId: number, revision: number): CoachAssignedProgram {
  return {
    id,
    client_id: clientId,
    client_telegram_user_id: clientId + 100,
    client_full_name: clients.find((client) => client.id === clientId)?.full_name ?? 'Клиент',
    template_id: 5,
    title: 'Силовая программа',
    assigned_at: '2026-09-01T10:00:00',
    is_active: true,
    status: 'active',
    start_date: '2026-09-30',
    duration_weeks: 4,
    schedule_weekdays: [1, 3],
    workouts_total: 8,
    workouts_completed: 2,
    workouts_planned: 6,
    current_revision_number: revision,
  };
}

function renderBulk(
  programs: CoachAssignedProgram[],
  selected = clients.slice(0, 2),
  selectedTemplate?: ProgramTemplate,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <CoachProgramBulkOperations
          programs={programs}
          selectedClients={selected}
          selectedTemplate={selectedTemplate}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('CoachProgramBulkOperations', () => {
  it('saves one reviewed common revision per selected client and reports partial conflicts', async () => {
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/v1/programs/exercises')) {
        return new Response(
          JSON.stringify([{ id: 9, title: 'Жим лёжа', metric_type: 'strength' }]),
          { status: 200 },
        );
      }
      if (url.includes('/api/v1/coach/clients/') && url.endsWith('/exercises')) {
        requests.push({ url, body: JSON.parse(String(init?.body)) });
        if (url.includes('/clients/72/')) {
          return new Response(JSON.stringify({ detail: 'Revision conflict' }), { status: 409 });
        }
        return new Response(JSON.stringify({ workouts_updated: 1, current_revision_number: 8 }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    renderBulk([program(44, 71, 7), program(45, 72, 4)]);

    fireEvent.click(screen.getByText('Запланировать общую правку программ'));
    const user = userEvent.setup();
    const exerciseOption = await screen.findByRole('option', { name: 'Жим лёжа' });
    await user.selectOptions(screen.getByLabelText('Упражнение'), exerciseOption);
    fireEvent.change(screen.getByLabelText('Причина общей правки'), {
      target: { value: 'Одинаковый новый план тренировки' },
    });
    const reviewButton = screen.getByRole('button', { name: 'Проверить и сохранить · 2' });
    await waitFor(() => expect(reviewButton).toBeEnabled());
    fireEvent.click(reviewButton);
    fireEvent.click(await screen.findByRole('button', { name: 'Сохранить · 2' }));

    expect(await screen.findByText('Ревизия сохранена')).toBeInTheDocument();
    expect(
      await screen.findByText(/Данные программы или тренировки изменились/),
    ).toBeInTheDocument();
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests.map((request) => request.body)).toEqual([
      {
        expected_revision_number: 7,
        effective_scope: 'next_workout',
        effective_date: null,
        exercise_id: 9,
        day_number: null,
        prescribed_sets: 3,
        prescribed_reps: '8-12',
        prescribed_duration_minutes: null,
        rest_seconds: 90,
        reason: 'Одинаковый новый план тренировки',
      },
      {
        expected_revision_number: 4,
        effective_scope: 'next_workout',
        effective_date: null,
        exercise_id: 9,
        day_number: null,
        prescribed_sets: 3,
        prescribed_reps: '8-12',
        prescribed_duration_minutes: null,
        rest_seconds: 90,
        reason: 'Одинаковый новый план тренировки',
      },
    ]);
  });

  it('confirms only matching eligible proposal classes', async () => {
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    const makeProposals = (programId: number, weight: number, setId: number) => ({
      target_program_id: programId,
      target_revision_number: programId === 44 ? 7 : 4,
      target_workout_id: programId + 100,
      scheduled_date: '2026-10-01',
      exercises: [
        {
          exercise_id: 9,
          exercise_title: 'Жим лёжа',
          guidance: {
            ruleset_version: 'progression-guidance-v2',
            outcome: 'consider_progressing',
            message: 'Подходящие данные',
            detail: 'Стабильная нагрузка',
            load_unit: 'kg',
            evidence: {},
            proposal: {
              proposal_id: String(programId).padStart(64, 'a'),
              rule_id: String(programId).padStart(64, 'b'),
              rule_kind: 'linear_load',
              rule_snapshot: { increment_kg: 2.5 },
              target_program_id: programId,
              target_revision_number: programId === 44 ? 7 : 4,
              target_exercise_id: 9,
              target_workout_id: programId + 100,
              current_weight: 40,
              proposed_weight: weight,
              proposed_action: 'set_load',
              target_set_updates: [
                {
                  set_id: setId,
                  set_number: 1,
                  planned_role: 'working',
                  current_weight: 40,
                  set_version: 1,
                  proposed_weight: weight,
                },
              ],
              source_evidence_ids: ['session'],
              comparable_session_count: 3,
              reason_codes: ['successful_sessions'],
              eligibility_status: 'eligible',
              requires_confirmation: true,
            },
          },
        },
      ],
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/44/progression-proposals')) {
        return new Response(JSON.stringify(makeProposals(44, 42.5, 101)), { status: 200 });
      }
      if (url.endsWith('/45/progression-proposals')) {
        return new Response(JSON.stringify(makeProposals(45, 42.5, 201)), { status: 200 });
      }
      if (url.endsWith('/46/progression-proposals')) {
        return new Response(JSON.stringify(makeProposals(46, 45, 301)), { status: 200 });
      }
      if (url.includes('/progression-proposals/') && url.endsWith('/review')) {
        requests.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(
          JSON.stringify({
            proposal_id: 'accepted',
            decision: 'confirm',
            applied_set_ids: [1],
            current_revision_number: 8,
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    renderBulk([program(44, 71, 7), program(45, 72, 4), program(46, 73, 3)], clients);

    fireEvent.click(screen.getByText('Проверить одинаковые предложения прогрессии'));
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Подтвердить одинаковые предложения · 2',
      }),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Подтвердить · 2' }));

    await waitFor(() => {
      const confirmedOutcomes = screen
        .getAllByRole('listitem')
        .filter((item) => item.textContent?.includes('Предложение подтверждено: Жим лёжа'));
      expect(confirmedOutcomes).toHaveLength(2);
    });
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests.map(({ url }) => url)).toEqual(
      expect.arrayContaining([
        expect.stringContaining('/assigned/44/progression-proposals/'),
        expect.stringContaining('/assigned/45/progression-proposals/'),
      ]),
    );
    expect(requests.map(({ body }) => body)).toEqual([
      {
        decision: 'confirm',
        workout_id: 144,
        exercise_id: 9,
        expected_revision_number: 7,
        expected_set_versions: { 101: 1 },
      },
      {
        decision: 'confirm',
        workout_id: 145,
        exercise_id: 9,
        expected_revision_number: 4,
        expected_set_versions: { 201: 1 },
      },
    ]);
  });

  it('keeps long bulk workflows progressively disclosed', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    renderBulk([program(44, 71, 7), program(45, 72, 4)]);

    const user = userEvent.setup();
    const revisionDetails = screen
      .getByText('Запланировать общую правку программ')
      .closest('details');
    const proposalDetails = screen
      .getByText('Проверить одинаковые предложения прогрессии')
      .closest('details');
    expect(revisionDetails).not.toBeNull();
    expect(proposalDetails).not.toBeNull();

    await user.click(screen.getByText('Запланировать общую правку программ'));
    expect(revisionDetails).toHaveAttribute('open');
    expect(proposalDetails).not.toHaveAttribute('open');

    await user.click(screen.getByText('Проверить одинаковые предложения прогрессии'));
    expect(proposalDetails).toHaveAttribute('open');
    expect(revisionDetails).not.toHaveAttribute('open');
  });

  it('previews compatible clients and skips manual-review targets before confirmation', async () => {
    const template = { id: 5, title: 'Новый блок' } as ProgramTemplate;
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/program-rollouts/preview')) {
        return new Response(
          JSON.stringify({
            template_id: 5,
            template_title: 'Новый блок',
            template_fingerprint: 'a'.repeat(64),
            targets: [
              {
                client_id: 71,
                client_name: 'Анна',
                program_id: 44,
                current_revision_number: 7,
                classification: 'compatible',
                can_apply: true,
                reason_codes: ['prescription_changes'],
                diff: [
                  {
                    week_number: 1,
                    day_number: 1,
                    exercise_title: 'Жим лёжа',
                    change: 'updated',
                    current: '2×8-10',
                    proposed: '3×8-10',
                  },
                ],
              },
              {
                client_id: 72,
                client_name: 'Иван',
                program_id: 45,
                current_revision_number: 4,
                classification: 'manual_review_required',
                can_apply: false,
                reason_codes: ['schedule_mismatch'],
                diff: [],
              },
            ],
            generated_at: '2026-10-07T10:00:00',
          }),
          { status: 200 },
        );
      }
      if (url.endsWith('/program-rollouts/apply')) {
        requests.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(
          JSON.stringify({
            rollout_id: 'b'.repeat(64),
            template_id: 5,
            results: [
              {
                client_id: 71,
                client_name: 'Анна',
                program_id: 44,
                status: 'applied',
                code: 'applied',
                detail: 'Шаблон применён к будущим тренировкам.',
                workouts_updated: 4,
                current_revision_number: 8,
              },
            ],
            applied_count: 1,
            already_applied_count: 0,
            failed_count: 0,
            completed_at: '2026-10-07T10:01:00',
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${url}` }), {
        status: 500,
      });
    });
    renderBulk([program(44, 71, 7), program(45, 72, 4)], clients, template);

    fireEvent.click(screen.getByText('Проверить применение выбранного шаблона'));
    fireEvent.click(await screen.findByRole('button', { name: 'Собрать предпросмотр' }));

    expect(await screen.findByText('Совместимо')).toBeInTheDocument();
    expect(screen.getByText('Нужна ручная проверка')).toBeInTheDocument();
    expect(screen.queryByText(/rollout/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Причина применения')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Применить к 1 клиенту' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Применить шаблон?' })).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: 'Применить к 1 клиенту',
      }),
    );

    expect(await screen.findByText('Шаблон применён к будущим тренировкам.')).toBeInTheDocument();
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0]?.body).toMatchObject({
      template_id: 5,
      confirmed: true,
      targets: [{ client_id: 71, program_id: 44, expected_revision_number: 7 }],
    });
  });
});
