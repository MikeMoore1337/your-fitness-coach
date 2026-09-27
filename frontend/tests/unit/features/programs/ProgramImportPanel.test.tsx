import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgramImportPanel } from '../../../../src/features/programs/ProgramImportPanel';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const previewWithIssues = {
  id: 'import-1',
  status: 'pending',
  source_format: 'csv',
  schema_version: 3,
  parser_version: 'program-import-v4',
  expires_at: '2026-09-06T12:00:00Z',
  duration_weeks: 1,
  program_title: null,
  goal: null,
  level: null,
  provenance: { provenance_type: 'CUSTOM' },
  blocks: [],
  coaching_rules: [],
  rows: [
    {
      row_number: 3,
      day_number: 1,
      day_title: 'Силовая 1',
      exercise_name: 'Приседания без веса',
      exercise_id: null,
      exercise_slug: null,
      metric_type: 'strength',
      prescribed_sets: 3,
      prescribed_reps: '8-12',
      prescribed_duration_minutes: null,
      rest_seconds: 90,
      notes: null,
      superset_group: null,
      superset_order: null,
      resolved_exercise_id: null,
      resolved_exercise_title: null,
      match_status: 'needs_resolution',
      match_type: null,
      candidates: [],
      issues: [
        {
          code: 'exercise_not_found',
          severity: 'blocking',
          message: 'Упражнение не найдено в доступном каталоге',
          location: 'Строка 3',
          field: 'exercise_name',
        },
      ],
    },
  ],
  issues: [
    {
      code: 'missing_goal',
      severity: 'blocking',
      message: 'Заполните поле goal перед подтверждением импорта',
      location: 'Файл',
      field: 'goal',
    },
  ],
  summary: {
    row_count: 1,
    cell_count: 16,
    matched_row_count: 0,
    unresolved_row_count: 1,
    blocking_issue_count: 2,
    warning_count: 0,
  },
};

const resolvedPreview = {
  ...previewWithIssues,
  program_title: 'Моя программа',
  goal: 'maintenance',
  level: 'beginner',
  rows: [
    {
      ...previewWithIssues.rows[0],
      resolved_exercise_id: 11,
      resolved_exercise_title: 'Приседания без веса',
      match_status: 'matched',
      match_type: 'manual',
      issues: [],
    },
  ],
  issues: [],
  summary: {
    ...previewWithIssues.summary,
    matched_row_count: 1,
    unresolved_row_count: 0,
    blocking_issue_count: 0,
  },
};

const previewWithAi = {
  ...previewWithIssues,
  ai: {
    contract_version: 'program-import-ai-v1',
    prompt_version: 'program-import-ai-prompt-v1',
    status: 'proposed',
    attempts: 1,
    proposal_count: 1,
    candidate_rerank_count: 0,
    conflict_count: 0,
    fallback: 'deterministic_manual',
  },
  rows: [
    {
      ...previewWithIssues.rows[0],
      ai_proposals: [
        {
          field: 'prescribed_sets',
          value: '4',
          evidence_id: 'source:txt:3',
          source_location: 'строка 3',
          source_text: 'Приседания без веса 4x8',
          rationale: 'Источник содержит количество подходов',
          applied: false,
        },
      ],
    },
  ],
};

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <ProgramImportPanel />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('ProgramImportPanel', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/programs/imports' && init?.method === 'POST') {
        return new Response(JSON.stringify(previewWithIssues), { status: 201 });
      }
      if (path === '/api/v1/programs/exercises') {
        return new Response(
          JSON.stringify([
            {
              id: 11,
              title: 'Приседания без веса',
              slug: 'bodyweight-squat',
              metric_type: 'strength',
            },
          ]),
          { status: 200 },
        );
      }
      if (path === '/api/v1/programs/imports/targets') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === '/api/v1/programs/imports/import-1/resolve') {
        return new Response(JSON.stringify(resolvedPreview), { status: 200 });
      }
      if (path === '/api/v1/programs/imports/import-1/confirm') {
        return new Response(
          JSON.stringify({
            import_id: 'import-1',
            template: { id: 501 },
            assigned_program_id: null,
            revision_number: null,
            workouts_created: 0,
            workouts_updated: 0,
            target_user: { id: 7, telegram_user_id: null, full_name: 'Тест' },
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${path}` }), {
        status: 500,
      });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('blocks confirmation until metadata and manual exercise matching are applied', async () => {
    renderPanel();

    const file = new File(['canonical csv'], 'plan.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [file] },
    });

    expect(
      await screen.findByRole('heading', { name: 'Проверьте план перед сохранением' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить и сохранить шаблон' })).toBeDisabled();

    const exerciseSelect = await screen.findByRole('combobox', {
      name: 'Упражнение для строки 3',
    });
    await screen.findByRole('option', { name: 'Приседания без веса' });
    fireEvent.change(exerciseSelect, { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('Название программы'), {
      target: { value: 'Моя программа' },
    });
    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'maintenance' } });
    fireEvent.change(screen.getByLabelText('Уровень'), { target: { value: 'beginner' } });
    await waitFor(() => expect(exerciseSelect).toHaveValue('11'));
    fireEvent.click(screen.getByRole('button', { name: 'Применить исправления' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Подтвердить и сохранить шаблон' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить шаблон' }));

    await waitFor(() =>
      expect(screen.getByText('Программа импортирована в личные шаблоны')).toBeInTheDocument(),
    );
    const requests = vi.mocked(globalThis.fetch).mock.calls;
    const resolveRequest = requests.find(([input]) => String(input).endsWith('/resolve'));
    expect(resolveRequest).toBeDefined();
    expect(JSON.parse(String(resolveRequest?.[1]?.body))).toMatchObject({
      title: 'Моя программа',
      goal: 'maintenance',
      level: 'beginner',
      provenance: { provenance_type: 'CUSTOM' },
      rows: [{ row_number: 3, exercise_id: 11 }],
    });
    const confirmRequest = requests.find(([input]) => String(input).endsWith('/confirm'));
    expect(confirmRequest).toBeDefined();
    expect(JSON.parse(String(confirmRequest?.[1]?.body))).toEqual({
      target_program_id: null,
      expected_revision_number: null,
    });
  });

  it('creates an explicit revision with the selected program revision as its precondition', async () => {
    const revisionTarget = {
      program_id: 99,
      title: 'Назначенная программа',
      owner_name: null,
      duration_weeks: 1,
      current_revision_number: 4,
      status: 'active',
      day_numbers: [1],
    };
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/programs/imports' && init?.method === 'POST') {
        return new Response(JSON.stringify(resolvedPreview), { status: 201 });
      }
      if (path === '/api/v1/programs/exercises') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (path === '/api/v1/programs/imports/targets') {
        return new Response(JSON.stringify([revisionTarget]), { status: 200 });
      }
      if (path === '/api/v1/programs/imports/import-1/confirm') {
        return new Response(
          JSON.stringify({
            import_id: 'import-1',
            template: { id: 501 },
            assigned_program_id: 99,
            revision_number: 5,
            workouts_created: 0,
            workouts_updated: 1,
            target_user: { id: 7, telegram_user_id: null, full_name: 'Тест' },
          }),
          { status: 200 },
        );
      }
      return new Response(JSON.stringify({ detail: `Unexpected request: ${path}` }), {
        status: 500,
      });
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [new File(['canonical csv'], 'plan.csv', { type: 'text/csv' })] },
    });
    await screen.findByRole('option', { name: 'Назначенная программа' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Сохранить как' }), {
      target: { value: '99' },
    });
    expect(await screen.findByText(/Будет создана ревизия 5/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и создать ревизию' }));

    await waitFor(() =>
      expect(screen.getByText('Новая ревизия программы сохранена')).toBeInTheDocument(),
    );
    const confirmRequest = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([input]) => String(input).endsWith('/confirm'));
    expect(JSON.parse(String(confirmRequest?.[1]?.body))).toEqual({
      target_program_id: 99,
      expected_revision_number: 4,
    });
  });

  it('shows progression thresholds and actions in the exact confirmation preview', async () => {
    const preview = {
      ...resolvedPreview,
      coaching_rules: [
        {
          kind: 'double_progression',
          scope: 'program',
          rep_target: { kind: 'range', min_reps: 8, max_reps: 12 },
          increment_value: 2.5,
          increment_unit: 'kg',
          reset_on_failure: true,
        },
      ],
    };
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/programs/imports' && init?.method === 'POST') {
        return new Response(JSON.stringify(preview), { status: 201 });
      }
      if (String(input) === '/api/v1/programs/exercises') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (String(input) === '/api/v1/programs/imports/targets') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [new File(['canonical csv'], 'plan.csv', { type: 'text/csv' })] },
    });

    expect(await screen.findByText(/8–12 повторов/)).toBeInTheDocument();
    expect(screen.getByText(/шаг 2,5 кг/)).toBeInTheDocument();
    expect(screen.getByText(/сброс после неудачи/)).toBeInTheDocument();
  });

  it('shows relative load ratios and complete prescription group details', async () => {
    const preview = {
      ...resolvedPreview,
      rows: [
        {
          ...resolvedPreview.rows[0],
          prescription: {
            version: 1,
            metric_type: 'strength',
            segments: [
              {
                position: 1,
                role: 'top',
                rep_target: { kind: 'exact', value: 5 },
                load_target: { kind: 'absolute', value: 100 },
                effort_target: { kind: 'none' },
                rest_after_seconds: 120,
              },
              {
                position: 2,
                role: 'working',
                rep_target: { kind: 'exact', value: 4 },
                load_target: { kind: 'user_selected' },
                effort_target: { kind: 'none' },
                rest_after_seconds: 20,
                group_id: 3,
                group_position: 1,
              },
              {
                position: 3,
                role: 'mini_set',
                rep_target: { kind: 'exact', value: 4 },
                load_target: { kind: 'relative_to_top', value: 0.8 },
                effort_target: { kind: 'none' },
                rest_after_seconds: 20,
                group_id: 3,
                group_position: 2,
              },
              {
                position: 4,
                role: 'working',
                rep_target: { kind: 'exact', value: 5 },
                load_target: { kind: 'user_selected' },
                effort_target: { kind: 'none' },
                rest_after_seconds: 90,
                group_id: 4,
                group_position: 1,
                round_number: 1,
              },
              {
                position: 5,
                role: 'working',
                rep_target: { kind: 'exact', value: 5 },
                load_target: { kind: 'user_selected' },
                effort_target: { kind: 'none' },
                rest_after_seconds: 90,
                group_id: 4,
                group_position: 1,
                round_number: 2,
              },
            ],
            groups: [
              {
                group_id: 3,
                kind: 'rest_pause',
                intra_group_rest_seconds: 20,
                rest_after_group_seconds: 120,
              },
              {
                group_id: 4,
                kind: 'circuit',
                intra_group_rest_seconds: 0,
                rest_after_group_seconds: 90,
                rounds: 2,
                exercise_slot: 1,
              },
            ],
          },
        },
      ],
    };
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/programs/imports' && init?.method === 'POST') {
        return new Response(JSON.stringify(preview), { status: 201 });
      }
      if (String(input) === '/api/v1/programs/exercises') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (String(input) === '/api/v1/programs/imports/targets') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [new File(['canonical csv'], 'plan.csv', { type: 'text/csv' })] },
    });

    expect(await screen.findByText(/80% от топ-сета/)).toBeInTheDocument();
    expect(screen.getByText(/группа 3, позиция 2/)).toBeInTheDocument();
    expect(screen.getByText(/Группа 3: Отдых-пауза/)).toBeInTheDocument();
    expect(screen.getByText(/пауза между элементами 20 сек\./)).toBeInTheDocument();
    expect(screen.getByText(/отдых после группы 120 сек\./)).toBeInTheDocument();
    expect(screen.getByText(/группа 4, позиция 1, раунд 2/)).toBeInTheDocument();
    expect(screen.getByText(/Группа 4: Круговая тренировка/)).toBeInTheDocument();
    expect(screen.getByText(/упражнение в группе 1/)).toBeInTheDocument();
    expect(screen.getByText(/раундов 2/)).toBeInTheDocument();
  });

  it('shows a safe error and keeps the upload surface available after rejection', async () => {
    vi.mocked(globalThis.fetch).mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: 'Нужен канонический шаблон YFC версии 1' }), {
          status: 422,
        }),
    );
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [new File(['arbitrary'], 'arbitrary.csv', { type: 'text/csv' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Нужен канонический шаблон YFC версии 1',
    );
    expect(screen.getByLabelText('Загрузить документ программы')).toBeInTheDocument();
  });

  it('shows source evidence for advisory AI proposals', async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/programs/imports' && init?.method === 'POST') {
        return new Response(JSON.stringify(previewWithAi), { status: 201 });
      }
      if (String(input) === '/api/v1/programs/exercises') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (String(input) === '/api/v1/programs/imports/targets') {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить документ программы'), {
      target: { files: [new File(['program'], 'program.txt', { type: 'text/plain' })] },
    });

    expect(await screen.findByText(/AI-помощь:/)).toHaveTextContent(
      'есть предложения для проверки',
    );
    expect(screen.getByText(/AI-подсказка: prescribed_sets/)).toHaveTextContent('= 4');
    expect(screen.getByText(/AI-подсказка: prescribed_sets/)).toHaveTextContent('только подсказка');
    expect(screen.getByText(/Источник: строка 3/)).toHaveTextContent('Приседания без веса 4x8');
  });
});
