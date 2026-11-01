import type { Page } from '@playwright/test';
import type { ApiSchemas } from '../../../src/shared/api/types';

export type ImportProvider834 = 'fitnotes' | 'hevy';

export async function installIssue834ImportApi(page: Page, provider: ImportProvider834) {
  const unsupported = [
    { code: 'unsupported_rpe', field: 'rpe', message: 'RPE нельзя заменить на RIR' },
    {
      code: 'unsupported_field',
      field: 'duration_seconds',
      message: 'Показатель из исходного файла пока нельзя перенести без потери данных',
    },
  ];
  const source = {
    workout_ref: provider === 'fitnotes' ? 'fitnotes-2025-10-12' : 'hevy-2025-10-12',
    completed_at: provider === 'fitnotes' ? '' : '2025-10-12T19:30:00',
    started_at: provider === 'fitnotes' ? '' : '2025-10-12T18:50:00',
    timezone: '',
    workout_title: provider === 'fitnotes' ? 'FitNotes' : 'Верх тела',
    status: 'completed',
    exercise_ref: 'exercise-1',
    exercise_name: 'Жим штанги лёжа',
    set_number: '1',
    set_status: 'completed',
    set_kind: provider === 'fitnotes' ? '' : 'working',
    reps: '8',
    weight: provider === 'fitnotes' ? '100' : '60',
    weight_unit: provider === 'fitnotes' ? 'lb' : 'kg',
    rir: '',
    rpe: provider === 'hevy' ? '8' : '',
    side: '',
  };
  const row: ApiSchemas['HistoryImportRow'] = {
    line: 3,
    source,
    completed_at_utc: null,
    completed_on: '2025-10-12',
    set_number: 1,
    reps: 8,
    weight_kg: provider === 'fitnotes' ? '45.36' : '60.00',
    issues: provider === 'hevy' ? unsupported : [],
    blocking_issues: provider === 'hevy' ? unsupported : [],
    provider_fields:
      provider === 'fitnotes'
        ? { Date: '2025-10-12', Category: 'Грудь', 'Weight (lbs)': '100', Reps: '8' }
        : { start_time: '12 Oct 2025, 18:50', duration_seconds: '75', rpe: '8' },
    manual_set_kind: null,
    exercise_id: 11,
    match_mode: 'auto',
    match_status: 'matched',
    resolved_title: 'Жим штанги лёжа',
    candidates: [
      {
        exercise_id: 11,
        title: 'Жим штанги лёжа',
        metric_type: 'strength',
        unsupported_side: false,
      },
    ],
    excluded: false,
  };
  let preview: ApiSchemas['HistoryImportPreview'] = {
    id: '834-synthetic-draft',
    version: 1,
    status: 'pending',
    provider,
    schema_version: 3,
    parser_version: '1.0',
    expires_at: '2027-11-01T12:00:00Z',
    rows: [row],
    duplicate_choices: {},
    duplicates: [],
    preview_signature: 'a'.repeat(64),
  };
  let uploads = 0;
  let resolves = 0;
  let confirmations = 0;
  await page.route('**/api/v1/workout-history-imports**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const method = request.method();
    const base = '/api/v1/workout-history-imports';
    if (pathname === base && method === 'GET') {
      return route.fulfill({ json: [] });
    }
    if (pathname === base && method === 'POST') {
      uploads += 1;
      const submitted = request.postData() ?? '';
      if (!submitted.includes(provider)) {
        return route.fulfill({ status: 422, json: { detail: 'Неверный источник' } });
      }
      return route.fulfill({ status: 201, json: preview });
    }
    if (pathname.endsWith('/resolve') && method === 'POST') {
      resolves += 1;
      const input = request.postDataJSON() as {
        set_kind_choices?: Record<string, 'working' | 'warmup' | 'drop' | null>;
      };
      const manualKind = input.set_kind_choices?.['3'];
      const previous = preview.rows ?? [];
      preview = {
        ...preview,
        version: preview.version + 1,
        preview_signature: 'b'.repeat(64),
        rows: previous.map((item) => ({
          ...item,
          manual_set_kind: manualKind === undefined ? item.manual_set_kind : manualKind,
        })),
      };
      return route.fulfill({ json: preview });
    }
    if (pathname.endsWith('/confirm') && method === 'POST') {
      confirmations += 1;
      return route.fulfill({
        json: {
          id: preview.id,
          version: preview.version,
          status: 'confirmed',
          result: { workout_ids: [834], workout_count: 1, set_count: 1 },
        },
      });
    }
    if (pathname.endsWith('/catalog')) return route.fulfill({ json: row.candidates });
    if (pathname.endsWith('/834-synthetic-draft')) return route.fulfill({ json: preview });
    return route.fulfill({ status: 404, json: { detail: 'Нет записи' } });
  });
  return {
    uploads: () => uploads,
    resolves: () => resolves,
    confirmations: () => confirmations,
  };
}
