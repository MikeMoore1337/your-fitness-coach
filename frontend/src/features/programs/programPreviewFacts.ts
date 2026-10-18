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
    ? value as Record<string, unknown>
    : {};
}

function knownFrequency(value: unknown): string {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 7
    ? String(value) + ' в неделю'
    : 'Нет данных';
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
  const frequency = knownFrequency(meta.days_per_week);
  const equipment = equipmentLabel(meta.equipment);
  const level = typeof template.level === 'string'
    ? levels[template.level] ?? 'Нет данных'
    : 'Нет данных';
  const weeks = template.days.flatMap((day) =>
    day.exercises.flatMap((exercise) =>
      exercise.weekly_prescriptions.map((week) => week.week_number),
    ),
  );
  const maxExplicitWeek = Math.max(0, ...weeks.filter((week) => Number.isInteger(week) && week >= 1));
  const knownSourceWeeks = maxExplicitWeek > 1
    ? maxExplicitWeek
    : template.default_duration_weeks > 1
      ? template.default_duration_weeks
      : null;

  return [
    {
      label: 'Дни',
      value: String(template.days.length) + ' в составе шаблона',
      source: 'Состав программы, не частота',
    },
    {
      label: 'Частота',
      value: frequency,
      source: frequency === 'Нет данных' ? 'Не указана в источнике' : 'Настройки шаблона',
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
      label: 'Недель в источнике',
      value: knownSourceWeeks == null ? 'Нет данных' : String(knownSourceWeeks),
      source: knownSourceWeeks == null
        ? 'Цикл и продолжительность не указаны'
        : 'Исходные данные, не автоматический повтор',
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
    owner_user_id: template.owner_user_id,
    can_edit: template.can_edit,
    assigned_by_user_id: template.assigned_by_user_id,
    current_revision_number: template.current_revision_number,
    assigned_program_revision_number: template.assigned_program_revision_number,
    assigned_program_updated: template.assigned_program_updated,
    default_duration_weeks: template.default_duration_weeks,
    program_metadata: template.program_metadata,
    days: template.days,
  });
}
