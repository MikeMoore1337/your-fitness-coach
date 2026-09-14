import { beforeEach, describe, expect, it } from 'vitest';
import {
  inclusiveDays,
  nutritionPeriodForProgress,
  parseProgressSelection,
  parseProgressView,
  progressApiQuery,
  progressPath,
  progressPeriodOptions,
  progressReportPath,
  progressViewPath,
  selectionDateRange,
  validateCustomProgressRange,
} from '../../../../src/features/workouts/progressPeriods';

describe('progress period contract', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/app?section=progress');
  });

  it('normalizes supported preset aliases and keeps exact inclusive ranges', () => {
    expect(progressPeriodOptions.map((option) => option.label)).toEqual([
      '7 дней',
      '30 дней',
      '90 дней',
      'Свой период',
    ]);
    expect(parseProgressSelection('?progress_period=days_1')).toEqual({
      kind: 'preset',
      days: 30,
    });
    expect(parseProgressSelection('?period=year')).toEqual({ kind: 'preset', days: 30 });
    expect(selectionDateRange({ kind: 'preset', days: 7 }, '2026-09-02')).toEqual({
      dateFrom: '2026-08-27',
      dateTo: '2026-09-02',
    });
    expect(selectionDateRange({ kind: 'preset', days: 90 }, '2026-09-02')).toEqual({
      dateFrom: '2026-06-05',
      dateTo: '2026-09-02',
    });
    expect(progressApiQuery({ kind: 'preset', days: 7 })).toBe('?period_days=7');
    expect(nutritionPeriodForProgress({ kind: 'preset', days: 90 })).toEqual({
      period: 'days_90',
      dateFrom: '',
      dateTo: '',
    });
  });

  it('keeps custom dates in dashboard, API and report links', () => {
    const selection = { kind: 'custom' as const, dateFrom: '2024-02-29', dateTo: '2024-03-01' };
    expect(
      parseProgressSelection(
        '?progress_period=custom&progress_from=2024-02-29&progress_to=2024-03-01',
      ),
    ).toEqual(selection);
    expect(inclusiveDays(selection.dateFrom, selection.dateTo)).toBe(2);
    expect(progressApiQuery(selection)).toBe('?date_from=2024-02-29&date_to=2024-03-01');
    expect(progressReportPath(selection)).toBe(
      '/app/report?period=custom&date_from=2024-02-29&date_to=2024-03-01',
    );
    expect(
      progressPath(
        '?section=progress&progress_period=days_30&period=custom&nutrition_period=days_30&progress_from=old&date_from=old',
        selection,
      ),
    ).toBe(
      '/app?section=progress&progress_period=custom&progress_from=2024-02-29&progress_to=2024-03-01',
    );
  });

  it('validates empty, reversed, oversized and future custom ranges', () => {
    expect(validateCustomProgressRange('', '', '2026-09-02')).toBe(
      'Укажите дату начала и окончания.',
    );
    expect(validateCustomProgressRange('2026-09-03', '2026-09-02', '2026-09-02')).toBe(
      'Дата окончания не может быть раньше даты начала.',
    );
    expect(validateCustomProgressRange('2025-09-02', '2026-09-02', '2026-09-02')).toBeNull();
    expect(validateCustomProgressRange('2025-09-02', '2026-09-03', '2026-09-02')).toBe(
      'Период не может превышать 366 дней.',
    );
    expect(validateCustomProgressRange('2026-09-01', '2026-09-03', '2026-09-02')).toBe(
      'Нельзя выбрать будущую дату.',
    );
  });

  it('keeps overview and detail routes in the same period state', () => {
    expect(parseProgressView('?section=progress')).toBe('overview');
    expect(parseProgressView('?section=progress&progress_view=nutrition')).toBe('nutrition');
    expect(parseProgressView('?section=progress&workout_id=42')).toBe('history');
    expect(parseProgressView('?section=progress', '#progress-body')).toBe('body');
    expect(
      progressViewPath(
        '?section=progress&progress_period=custom&progress_from=2026-01-01&progress_to=2026-01-30',
        'nutrition',
      ),
    ).toBe(
      '/app?section=progress&progress_period=custom&progress_from=2026-01-01&progress_to=2026-01-30&progress_view=nutrition',
    );
    expect(
      progressViewPath('?section=progress&progress_period=days_90&progress_view=body', 'overview'),
    ).toBe('/app?section=progress&progress_period=days_90');
  });
});
