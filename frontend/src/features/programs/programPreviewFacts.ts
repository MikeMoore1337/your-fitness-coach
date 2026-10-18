import type { ProgramTemplate } from '../../shared/api/types';

export interface ProgramPreviewFact {
  label: string;
  value: string;
  source: string;
}

const levels: Record<string, string> = {
  beginner: 'Начальный',
  intermediate: 'Средний',
  advanced: 'Продвинутый',
};

function metadata(template: ProgramTemplate): Record<string, unknown> {
  const value = template.program_metadata;
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function knownFrequency(value: unknown): string | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 7
    ? String(value) + ' в неделю'
    : null;
}

function knownScheduleFrequency(value: unknown): string | null {
  if (
    !Array.isArray(value) ||
    value.length < 1 ||
    value.length > 7 ||
    !value.every(
      (entry) => typeof entry === 'number' && Number.isInteger(entry) && entry >= 0 && entry <= 6,
    )
  ) {
    return null;
  }
  if (new Set(value).size !== value.length) return null;
  return `${value.length} в неделю`;
}

function knownLevel(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  return levels[value.trim()] ?? null;
}

function formatWeeks(value: number): string {
  const remainder = value % 10;
  const suffix =
    remainder === 1 && value % 100 !== 11
      ? 'неделя'
      : remainder >= 2 && remainder <= 4 && (value % 100 < 10 || value % 100 >= 20)
        ? 'недели'
        : 'недель';
  return `${value} ${suffix}`;
}

function equipmentLabel(value: unknown): string {
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === 'string')) {
    return 'Нет данных';
  }
  const entries = value.map((entry: string) => entry.trim()).filter(Boolean);
  if (entries.length !== value.length) return 'Нет данных';
  return entries.length ? entries.join(' · ') : 'Не требуется (по данным шаблона)';
}

export function programPreviewFacts(template: ProgramTemplate): ProgramPreviewFact[] {
  const meta = metadata(template);
  const scheduleFrequency = knownScheduleFrequency(template.assigned_program_schedule_weekdays);
  const metadataFrequency = knownFrequency(meta.days_per_week);
  const frequency = scheduleFrequency ?? metadataFrequency ?? 'Нет данных';
  const equipment = equipmentLabel(meta.equipment);
  const level = knownLevel(template.level) ?? knownLevel(meta.level) ?? 'Нет данных';
  const weeks = template.days.flatMap((day) =>
    day.exercises.flatMap((exercise) =>
      (exercise.weekly_prescriptions ?? []).map((week) => week.week_number),
    ),
  );
  const maxExplicitWeek = Math.max(
    0,
    ...weeks.filter((week) => Number.isInteger(week) && week >= 1),
  );
  const knownSourceWeeks =
    maxExplicitWeek > 1
      ? maxExplicitWeek
      : template.default_duration_weeks > 1
        ? template.default_duration_weeks
        : null;
  const assignedWeeks =
    typeof template.assigned_program_duration_weeks === 'number' &&
    Number.isInteger(template.assigned_program_duration_weeks) &&
    template.assigned_program_duration_weeks >= 1
      ? template.assigned_program_duration_weeks
      : null;
  const weeksLabel = assignedWeeks == null ? 'Недель в источнике' : 'Срок назначения';
  const weeksValue =
    assignedWeeks == null
      ? knownSourceWeeks == null
        ? 'Нет данных'
        : formatWeeks(knownSourceWeeks)
      : formatWeeks(assignedWeeks);
  const weeksSource =
    assignedWeeks == null
      ? knownSourceWeeks == null
        ? 'Цикл и продолжительность не указаны'
        : 'Исходные данные, не автоматический повтор'
      : 'Срок текущего назначения';

  return [
    {
      label: 'Дни',
      value: String(template.days.length) + ' в составе шаблона',
      source: 'Состав программы, не частота',
    },
    {
      label: 'Частота',
      value: frequency,
      source:
        frequency === 'Нет данных'
          ? 'Не указана в источнике'
          : scheduleFrequency
            ? 'Расписание назначения'
            : 'Настройки шаблона',
    },
    {
      label: 'Уровень',
      value: level,
      source: level === 'Нет данных' ? 'Не указан' : 'Уровень программы',
    },
    {
      label: 'Оборудование',
      value: equipment,
      source: equipment === 'Нет данных' ? 'Полный список не указан' : 'Указано в источнике',
    },
    {
      label: 'Оценка времени',
      value: 'Нет данных',
      source: 'Достоверной оценки пока нет',
    },
    {
      label: weeksLabel,
      value: weeksValue,
      source: weeksSource,
    },
  ];
}

// A changed response is never silently assigned using previously displayed facts.
// The server remains responsible for authorization and transactional concurrency.
export function previewSourceSignature(template: ProgramTemplate): string {
  return JSON.stringify({
    id: template.id,
    title: template.title,
    level: template.level,
    split_type: template.split_type,
    provenance_type: template.provenance_type,
    provenance: template.provenance,
    is_example: template.is_example,
    is_assigned_to_current_user: template.is_assigned_to_current_user,
    is_active_for_current_user: template.is_active_for_current_user,
    owner_user_id: template.owner_user_id,
    owner_full_name: template.owner_full_name,
    can_edit: template.can_edit,
    assigned_by_user_id: template.assigned_by_user_id,
    assigned_by_full_name: template.assigned_by_full_name,
    assigned_program_id: template.assigned_program_id,
    assigned_program_status: template.assigned_program_status,
    assigned_program_start_date: template.assigned_program_start_date,
    assigned_program_duration_weeks: template.assigned_program_duration_weeks,
    assigned_program_schedule_weekdays: template.assigned_program_schedule_weekdays,
    current_revision_number: template.current_revision_number,
    assigned_program_revision_number: template.assigned_program_revision_number,
    assigned_program_updated: template.assigned_program_updated,
    future_workouts_updated: template.future_workouts_updated,
    default_duration_weeks: template.default_duration_weeks,
    program_metadata: template.program_metadata,
    days: template.days,
  });
}
