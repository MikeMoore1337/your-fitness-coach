import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProgramImportPanel } from '../../../../src/features/programs/ProgramImportPanel';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const previewWithIssues = {
  id: 'import-1',
  status: 'pending',
  source_format: 'csv',
  schema_version: 1,
  parser_version: 'program-import-v1',
  expires_at: '2026-09-06T12:00:00Z',
  program_title: null,
  goal: null,
  level: null,
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
      if (path === '/api/v1/programs/imports/import-1/resolve') {
        return new Response(JSON.stringify(resolvedPreview), { status: 200 });
      }
      if (path === '/api/v1/programs/imports/import-1/confirm') {
        return new Response(
          JSON.stringify({
            import_id: 'import-1',
            template: { id: 501 },
            assigned_program_id: null,
            workouts_created: 0,
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
    fireEvent.change(screen.getByLabelText('Загрузить XLSX или CSV'), {
      target: { files: [file] },
    });

    expect(
      await screen.findByRole('heading', { name: 'Проверьте план перед сохранением' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить и сохранить' })).toBeDisabled();

    const exerciseSelect = await screen.findByRole('combobox', {
      name: 'Упражнение для строки 3',
    });
    fireEvent.change(exerciseSelect, { target: { value: '11' } });
    fireEvent.change(screen.getByLabelText('Название программы'), {
      target: { value: 'Моя программа' },
    });
    fireEvent.change(screen.getByLabelText('Цель'), { target: { value: 'maintenance' } });
    fireEvent.change(screen.getByLabelText('Уровень'), { target: { value: 'beginner' } });
    await waitFor(() => expect(exerciseSelect).toHaveValue('11'));
    fireEvent.click(screen.getByRole('button', { name: 'Применить исправления' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Подтвердить и сохранить' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить и сохранить' }));

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
      rows: [{ row_number: 3, exercise_id: 11 }],
    });
    expect(requests.some(([input]) => String(input).endsWith('/confirm'))).toBe(true);
  });

  it('shows a safe error and keeps the upload surface available after rejection', async () => {
    vi.mocked(globalThis.fetch).mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: 'Нужен канонический шаблон YFC версии 1' }), {
          status: 422,
        }),
    );
    renderPanel();

    fireEvent.change(screen.getByLabelText('Загрузить XLSX или CSV'), {
      target: { files: [new File(['arbitrary'], 'arbitrary.csv', { type: 'text/csv' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Нужен канонический шаблон YFC версии 1',
    );
    expect(screen.getByLabelText('Загрузить XLSX или CSV')).toBeInTheDocument();
  });
});
