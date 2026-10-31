import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WorkoutHistoryImport } from '../../../../src/features/workouts/WorkoutHistoryImport';

const source = {
  workout_ref: 'w1',
  completed_at: '2025-10-12T18:30:00+03:00',
  timezone: 'Europe/Moscow',
  workout_title: 'Верх тела',
  status: 'completed',
  exercise_ref: 'e1',
  exercise_name: 'Жим',
  set_number: '1',
  set_status: 'completed',
  set_kind: 'working',
  reps: '8',
  weight: '100',
  weight_unit: 'lb',
  rir: '2',
  rpe: '',
  side: '',
};
const candidate = {
  exercise_id: 11,
  title: 'Жим штанги лёжа',
  metric_type: 'strength',
  unsupported_side: false,
};
const issue = {
  code: 'exercise_unresolved',
  field: 'exercise_name',
  message: 'Выберите упражнение из каталога',
};
const row = {
  line: 3,
  source,
  completed_at_utc: '2025-10-12T15:30:00',
  completed_on: '2025-10-12',
  set_number: 1,
  reps: 8,
  weight_kg: '45.36',
  issues: [],
  blocking_issues: [issue],
  exercise_id: null,
  match_mode: null,
  match_status: 'unknown',
  resolved_title: null,
  candidates: [],
  excluded: false,
};
const preview = {
  id: 'draft-1',
  version: 1,
  status: 'pending',
  provider: 'yfc-neutral-csv',
  schema_version: 1,
  parser_version: '1.0',
  expires_at: '2027-01-01T00:00:00Z',
  rows: [row],
  duplicates: [],
  duplicate_choices: {},
  preview_signature: 'a'.repeat(64),
  result: null,
};
const resolved = {
  ...preview,
  version: 2,
  preview_signature: 'b'.repeat(64),
  rows: [
    {
      ...row,
      exercise_id: 11,
      match_mode: 'manual',
      match_status: 'matched',
      resolved_title: candidate.title,
      blocking_issues: [],
    },
  ],
  duplicates: [
    {
      workout_ref: 'w1',
      source_sets: [[11, 1, 8, '45.36', 'working', '2']],
      candidates: [],
      choice: null,
    },
  ],
};

function renderImport() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkoutHistoryImport onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('WorkoutHistoryImport', () => {
  it('requires manual mapping and explicit confirmation, then recovers an unknown save result', async () => {
    const calls: Array<{ path: string; method: string; body: unknown }> = [];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';
      calls.push({ path, method, body: init?.body });
      if (path === '/api/v1/workout-history-imports' && method === 'GET') return Response.json([]);
      if (path === '/api/v1/workout-history-imports' && method === 'POST')
        return Response.json(preview, { status: 201 });
      if (path.endsWith('/catalog')) return Response.json([candidate]);
      if (path.endsWith('/resolve')) return Response.json(resolved);
      if (path.endsWith('/confirm')) throw new TypeError('network interrupted');
      if (path.endsWith('/draft-1'))
        return Response.json({
          id: 'draft-1',
          version: 2,
          status: 'confirmed',
          result: { workout_ids: [99], workout_count: 1, set_count: 1 },
        });
      throw new Error(`unexpected request ${method} ${path}`);
    });
    renderImport();
    const fileInput = await screen.findByLabelText('Выбрать CSV-файл');
    fireEvent.change(fileInput, {
      target: { files: [new File(['fixture'], 'history.csv', { type: 'text/csv' })] },
    });
    expect(await screen.findByText('Нужно проверить записи')).toBeInTheDocument();
    expect(calls.some((call) => call.path.endsWith('/confirm'))).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Проверить записи' }));
    const option = await screen.findByRole('radio', { name: 'Жим штанги лёжа' });
    await userEvent.click(option);
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить выбор' }));
    expect(await screen.findByText(/45.36 кг/)).toBeInTheDocument();
    expect(calls.some((call) => call.path.endsWith('/confirm'))).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
    expect(
      screen.getByText('После подтверждения эти данные появятся в истории и статистике.'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить историю' }));
    expect(await screen.findByText('Проверьте состояние импорта')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Обновить статус' }));
    expect(await screen.findByText('История дополнена')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([path]) => String(path).endsWith('/confirm'))).toHaveLength(
      1,
    );
    const resolve = calls.find((call) => call.path.endsWith('/resolve'));
    expect(JSON.parse(String(resolve?.body))).toMatchObject({
      version: 1,
      exercise_choices: { 3: 11 },
      excluded_lines: [],
    });
  });

  it('requires a fresh preview when another change invalidates confirmation', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';
      if (path === '/api/v1/workout-history-imports' && method === 'GET') return Response.json([]);
      if (path === '/api/v1/workout-history-imports' && method === 'POST')
        return Response.json(resolved, { status: 201 });
      if (path.endsWith('/confirm'))
        return Response.json(
          { detail: { code: 'preview_changed', message: 'История изменилась' } },
          { status: 409 },
        );
      if (path.endsWith('/draft-1'))
        return Response.json({ ...resolved, version: 3, preview_signature: 'c'.repeat(64) });
      throw new Error(`unexpected request ${method} ${path}`);
    });
    renderImport();
    fireEvent.change(await screen.findByLabelText('Выбрать CSV-файл'), {
      target: { files: [new File(['fixture'], 'history.csv')] },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Продолжить' }));
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить историю' }));
    expect(await screen.findByText('Нужен актуальный просмотр')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Обновить предпросмотр' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Продолжить' })).toBeInTheDocument(),
    );
  });

  it('paginates only workouts with included rows on the confirmation screen', async () => {
    const rows = Array.from({ length: 8 }, (_, index) => ({
      ...resolved.rows[0],
      line: index + 3,
      excluded: index < 2,
      source: {
        ...source,
        workout_ref: `w${index + 1}`,
        workout_title: `Тренировка ${index + 1}`,
      },
    }));
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      const method = init?.method ?? 'GET';
      if (path === '/api/v1/workout-history-imports' && method === 'GET') return Response.json([]);
      if (path === '/api/v1/workout-history-imports' && method === 'POST')
        return Response.json({ ...resolved, rows, duplicates: [] }, { status: 201 });
      throw new Error(`unexpected request ${method} ${path}`);
    });
    renderImport();
    fireEvent.change(await screen.findByLabelText('Выбрать CSV-файл'), {
      target: { files: [new File(['fixture'], 'history.csv')] },
    });
    await userEvent.click(await screen.findByRole('button', { name: 'Продолжить' }));
    expect(screen.getByText('Страница 1 из 2')).toBeInTheDocument();
    expect(screen.queryByText('Тренировка 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Тренировка 2')).not.toBeInTheDocument();
    expect(screen.getByText('Тренировка 3')).toBeInTheDocument();
    expect(screen.getByText('Тренировка 7')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Далее' }));
    expect(screen.getByText('Страница 2 из 2')).toBeInTheDocument();
    expect(screen.getByText('Тренировка 8')).toBeInTheDocument();
    expect(screen.queryByText('Тренировка 7')).not.toBeInTheDocument();
  });
});
