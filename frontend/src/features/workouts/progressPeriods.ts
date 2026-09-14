import { addCalendarDays } from '../../shared/dateTime';

export const PROGRESS_PERIODS = [7, 30, 90] as const;
export type ProgressPeriodDays = (typeof PROGRESS_PERIODS)[number];
export type ProgressSelection =
  | { kind: 'preset'; days: ProgressPeriodDays }
  | { kind: 'custom'; dateFrom: string; dateTo: string };

export const PROGRESS_DETAIL_VIEWS = [
  'body',
  'training',
  'nutrition',
  'cardio',
  'wellbeing',
  'history',
] as const;
export type ProgressDetailView = (typeof PROGRESS_DETAIL_VIEWS)[number];
export type ProgressView = 'overview' | ProgressDetailView;

export const progressPeriodOptions = [
  { value: '7', label: '7 дней' },
  { value: '30', label: '30 дней' },
  { value: '90', label: '90 дней' },
  { value: 'custom', label: 'Свой период' },
] as const;

const datePattern = /^\d{4}-\d{2}-\d{2}$/;

function preset(value: string | null): ProgressSelection | null {
  if (value === 'days_7' || value === '7') return { kind: 'preset', days: 7 };
  if (value === 'days_30' || value === '30') return { kind: 'preset', days: 30 };
  if (value === 'days_90' || value === '90') return { kind: 'preset', days: 90 };
  return null;
}

export function parseProgressSelection(search: string): ProgressSelection {
  const params = new URLSearchParams(search);
  const rawPeriod = params.get('progress_period') ?? params.get('period');
  const selectedPreset = preset(rawPeriod);
  if (selectedPreset) return selectedPreset;

  if (rawPeriod === 'custom') {
    const dateFrom = params.get('progress_from') ?? params.get('date_from') ?? '';
    const dateTo = params.get('progress_to') ?? params.get('date_to') ?? '';
    if (datePattern.test(dateFrom) && datePattern.test(dateTo)) {
      return { kind: 'custom', dateFrom, dateTo };
    }
  }
  return { kind: 'preset', days: 30 };
}

function isProgressDetailView(value: string | null): value is ProgressDetailView {
  return value != null && PROGRESS_DETAIL_VIEWS.includes(value as ProgressDetailView);
}

export function parseProgressView(search: string, hash = ''): ProgressView {
  const params = new URLSearchParams(search);
  const explicit = params.get('progress_view');
  if (isProgressDetailView(explicit)) return explicit;

  if (params.has('workout_id') || params.has('program_history')) return 'history';
  if (params.get('weekly_review') === '1') return 'wellbeing';
  if (params.get('focus') === 'measurements' || hash === '#progress-body') return 'body';
  if (params.get('cardio') === '1' || hash === '#progress-cardio') return 'cardio';
  if (hash === '#progress-training') return 'training';
  if (hash === '#progress-nutrition' || hash === '#progress-reports') return 'nutrition';
  return 'overview';
}

export function progressSelectionKey(selection: ProgressSelection): string {
  return selection.kind === 'custom'
    ? `custom:${selection.dateFrom}:${selection.dateTo}`
    : `days:${selection.days}`;
}

export function progressApiQuery(selection: ProgressSelection): string {
  const params = new URLSearchParams();
  if (selection.kind === 'custom') {
    params.set('date_from', selection.dateFrom);
    params.set('date_to', selection.dateTo);
  } else {
    params.set('period_days', String(selection.days));
  }
  return `?${params.toString()}`;
}

export function progressPath(search: string, selection: ProgressSelection): string {
  const url = new URL(
    `${window.location.pathname}${search}${window.location.hash}`,
    window.location.origin,
  );
  url.searchParams.set('section', 'progress');
  url.searchParams.set(
    'progress_period',
    selection.kind === 'custom' ? 'custom' : `days_${selection.days}`,
  );
  url.searchParams.delete('period');
  url.searchParams.delete('nutrition_period');
  url.searchParams.delete('progress_from');
  url.searchParams.delete('progress_to');
  url.searchParams.delete('date_from');
  url.searchParams.delete('date_to');
  if (selection.kind === 'custom') {
    url.searchParams.set('progress_from', selection.dateFrom);
    url.searchParams.set('progress_to', selection.dateTo);
  }
  return `${url.pathname}${url.search}${url.hash}`;
}

export function progressViewPath(search: string, view: ProgressView, hash = ''): string {
  const url = new URL(`${window.location.pathname}${search}${hash}`, window.location.origin);
  url.searchParams.set('section', 'progress');
  if (view === 'overview') url.searchParams.delete('progress_view');
  else url.searchParams.set('progress_view', view);
  url.hash = '';
  return `${url.pathname}${url.search}`;
}

export function progressReportPath(selection: ProgressSelection): string {
  const params = new URLSearchParams({
    period: selection.kind === 'custom' ? 'custom' : `days_${selection.days}`,
  });
  if (selection.kind === 'custom') {
    params.set('date_from', selection.dateFrom);
    params.set('date_to', selection.dateTo);
  }
  return `/app/report?${params.toString()}`;
}

export function nutritionPeriodForProgress(selection: ProgressSelection): {
  period: `days_${ProgressPeriodDays}` | 'custom';
  dateFrom: string;
  dateTo: string;
} {
  if (selection.kind === 'custom') {
    return { period: 'custom', dateFrom: selection.dateFrom, dateTo: selection.dateTo };
  }
  return { period: `days_${selection.days}`, dateFrom: '', dateTo: '' };
}

export function selectionDateRange(
  selection: ProgressSelection,
  today: string,
): { dateFrom: string; dateTo: string } {
  if (selection.kind === 'custom') {
    return { dateFrom: selection.dateFrom, dateTo: selection.dateTo };
  }
  return { dateFrom: addCalendarDays(today, -(selection.days - 1)), dateTo: today };
}

export function inclusiveDays(dateFrom: string, dateTo: string): number {
  return (
    Math.floor(
      (Date.parse(`${dateTo}T00:00:00Z`) - Date.parse(`${dateFrom}T00:00:00Z`)) / 86_400_000,
    ) + 1
  );
}

export function validateCustomProgressRange(
  dateFrom: string,
  dateTo: string,
  today: string,
): string | null {
  if (!dateFrom || !dateTo) return 'Укажите дату начала и окончания.';
  const days = inclusiveDays(dateFrom, dateTo);
  if (!Number.isFinite(days) || days < 1) {
    return 'Дата окончания не может быть раньше даты начала.';
  }
  if (days > 366) return 'Период не может превышать 366 дней.';
  if (dateTo > today) return 'Нельзя выбрать будущую дату.';
  return null;
}
