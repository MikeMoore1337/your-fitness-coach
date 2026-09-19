import type {
  Client,
  CoachAssignedProgram,
  TrainerClientProgressSummary,
} from '../../shared/api/types';

export type CoachClientFilter = 'all' | 'attention' | 'recent' | 'pending' | 'without_program';

const DAY_MS = 24 * 60 * 60 * 1000;

function dateValue(value: string): number {
  return new Date(`${value}T12:00:00`).getTime();
}

export function clientDisplayName(client: Client): string {
  return (
    client.full_name ||
    (client.username ? `@${client.username}` : null) ||
    (client.status === 'pending' ? 'Ожидающий клиент' : null) ||
    'Клиент'
  );
}

export function daysSince(value: string | null | undefined, now = new Date()): number | null {
  if (!value) return null;
  const current = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12).getTime();
  return Math.max(0, Math.floor((current - dateValue(value)) / DAY_MS));
}

export function russianQuantity(
  value: number,
  forms: readonly [one: string, few: string, many: string],
): string {
  const absolute = Math.abs(value) % 100;
  const lastDigit = absolute % 10;
  if (absolute >= 11 && absolute <= 19) return forms[2];
  if (lastDigit === 1) return forms[0];
  if (lastDigit >= 2 && lastDigit <= 4) return forms[1];
  return forms[2];
}

export function formatDaysAgo(days: number): string {
  return `${days} ${russianQuantity(days, ['день', 'дня', 'дней'])} назад`;
}

export function activityLabel(value: string | null | undefined, now = new Date()): string {
  const days = daysSince(value, now);
  if (days == null) return 'Тренировок ещё не было';
  if (days === 0) return 'Тренировался сегодня';
  if (days === 1) return 'Тренировался вчера';
  return `Тренировался ${formatDaysAgo(days)}`;
}

export function needsCoachAttention(summary?: TrainerClientProgressSummary): boolean {
  const inactiveDays = daysSince(summary?.training.last_completed_workout_on);
  return inactiveDays == null || inactiveDays >= 7;
}

export function filterCoachClients({
  clients,
  filter,
  programs,
  search,
  summaries,
}: {
  clients: Client[];
  filter: CoachClientFilter;
  programs: CoachAssignedProgram[];
  search: string;
  summaries: Map<number, TrainerClientProgressSummary>;
}): Client[] {
  const normalizedSearch = search.trim().toLocaleLowerCase('ru-RU');
  const activeProgramClientIds = new Set(
    programs.filter((program) => program.is_active).map((program) => program.client_id),
  );

  return clients.filter((client) => {
    const searchable = [
      clientDisplayName(client),
      client.full_name,
      client.username,
      client.telegram_user_id,
    ]
      .filter(Boolean)
      .join(' ')
      .toLocaleLowerCase('ru-RU');
    if (normalizedSearch && !searchable.includes(normalizedSearch)) return false;

    if (filter === 'pending') return client.status === 'pending';
    if (client.status !== 'active' || client.id == null) return filter === 'all';
    const summary = summaries.get(client.id);
    if (filter === 'attention') return needsCoachAttention(summary);
    if (filter === 'recent') {
      const inactiveDays = daysSince(summary?.training.last_completed_workout_on);
      return inactiveDays != null && inactiveDays < 7;
    }
    if (filter === 'without_program') return !activeProgramClientIds.has(client.id);
    return true;
  });
}

export function coachWorkspaceStats(clients: Client[], summaries: TrainerClientProgressSummary[]) {
  const active = clients.filter((client) => client.status === 'active').length;
  const pending = clients.filter((client) => client.status === 'pending').length;
  const recent = summaries.filter((summary) => {
    const inactiveDays = daysSince(summary.training.last_completed_workout_on);
    return inactiveDays != null && inactiveDays < 7;
  }).length;
  const attention = summaries.filter(needsCoachAttention).length;
  const personalRecords = summaries.reduce(
    (total, summary) => total + summary.training.new_personal_records,
    0,
  );
  const measurementUpdates = summaries.filter((summary) => {
    const inactiveDays = daysSince(summary.body.latest_measurement?.measured_on);
    return inactiveDays != null && inactiveDays < 30;
  }).length;

  return { active, pending, recent, attention, personalRecords, measurementUpdates };
}
