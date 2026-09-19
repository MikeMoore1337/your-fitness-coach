import { useMemo } from 'react';
import type {
  Client,
  CoachAssignedProgram,
  TrainerClientProgressSummary,
} from '../../shared/api/types';
import { clientDisplayName } from './coachWorkspace';
import type { CoachClientFilter } from './coachWorkspace';
import { CoachAttentionCenter } from './CoachAttentionCenter';
import { Badge, EmptyState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';

export type CoachTodayNavigation = 'clients' | 'programs' | 'tools';

type CoachTodayProps = {
  clients: Client[];
  programs: CoachAssignedProgram[];
  summaries: TrainerClientProgressSummary[];
  clientsLoading: boolean;
  programsLoading: boolean;
  summariesLoading: boolean;
  pendingCount: number;
  inviteCreating: boolean;
  inviteDisabled: boolean;
  onNavigate: (destination: CoachTodayNavigation, filter?: CoachClientFilter) => void;
  onOpenClient: (clientId: number) => void;
  onInvite: () => void;
};

function formatDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  });
}

function clientById(clients: Client[], clientId: number): Client | undefined {
  return clients.find((client) => client.id === clientId);
}

export function CoachToday({
  clients,
  programs,
  summaries,
  clientsLoading,
  programsLoading,
  summariesLoading,
  pendingCount,
  inviteCreating,
  inviteDisabled,
  onNavigate,
  onOpenClient,
  onInvite,
}: CoachTodayProps) {
  const activeProgramClientIds = useMemo(
    () =>
      new Set(programs.filter((program) => program.is_active).map((program) => program.client_id)),
    [programs],
  );
  const nextWorkouts = useMemo(
    () =>
      summaries
        .filter((summary) => summary.training.next_workout)
        .map((summary) => ({
          summary,
          client: clientById(clients, summary.user_id),
        }))
        .filter((item): item is { summary: TrainerClientProgressSummary; client: Client } =>
          Boolean(
            item.client?.id &&
            item.client.status === 'active' &&
            item.summary.training.next_workout,
          ),
        )
        .sort((left, right) =>
          (left.summary.training.next_workout?.scheduled_date ?? '').localeCompare(
            right.summary.training.next_workout?.scheduled_date ?? '',
          ),
        )
        .slice(0, 5),
    [clients, summaries],
  );
  const withoutProgram = clients.filter(
    (client) =>
      client.status === 'active' && client.id != null && !activeProgramClientIds.has(client.id),
  );
  const pendingClients = clients.filter((client) => client.status === 'pending').slice(0, 3);

  return (
    <section className="coach-today" data-testid="coach-today" aria-labelledby="coach-today-title">
      <header className="coach-today__hero">
        <div>
          <span className="eyebrow">Рабочий цикл тренера</span>
          <h1 id="coach-today-title">Что требует действия?</h1>
          <p>Короткий список фактов и следующий шаг. Подробности открываются внутри клиента.</p>
        </div>
        <div className="coach-today__hero-actions">
          <button type="button" onClick={() => onNavigate('clients')}>
            Открыть клиентов
            <Icon name="arrow-right" size={16} />
          </button>
          <button
            type="button"
            className="secondary"
            disabled={inviteCreating || inviteDisabled}
            onClick={onInvite}
          >
            {inviteCreating ? 'Создаём…' : 'Пригласить клиента'}
          </button>
        </div>
      </header>

      <CoachAttentionCenter enabled />

      <section className="coach-today__section" aria-labelledby="coach-today-next-title">
        <div className="coach-os-section-heading">
          <div>
            <span className="eyebrow">Следом по плану</span>
            <h2 id="coach-today-next-title">Ближайшие тренировки</h2>
          </div>
          {nextWorkouts.length > 0 && <Badge>{nextWorkouts.length}</Badge>}
        </div>
        {summariesLoading || clientsLoading ? (
          <LoadingState label="Собираем рабочий список…" />
        ) : nextWorkouts.length === 0 ? (
          <EmptyState
            title="Ближайших тренировок нет"
            text="Когда у клиента появится запланированная тренировка, она будет здесь."
          />
        ) : (
          <div className="coach-today__next-list">
            {nextWorkouts.map(({ client, summary }) => {
              const workout = summary.training.next_workout!;
              return (
                <article className="coach-today__next-item" key={client.id}>
                  <div>
                    <strong>{clientDisplayName(client)}</strong>
                    <span>
                      {formatDate(workout.scheduled_date)}
                      {workout.scheduled_time ? ` · ${workout.scheduled_time.slice(0, 5)}` : ''}
                      {` · ${workout.title}`}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => onOpenClient(client.id!)}
                  >
                    Открыть
                    <Icon name="arrow-right" size={16} />
                  </button>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="coach-today__secondary-grid">
        <section
          className="coach-today__section coach-today__section--compact"
          aria-labelledby="coach-today-pending-title"
        >
          <div className="coach-os-section-heading">
            <div>
              <span className="eyebrow">Связи</span>
              <h2 id="coach-today-pending-title">Ожидают подключения</h2>
            </div>
            {pendingCount > 0 && <Badge tone="warning">{pendingCount}</Badge>}
          </div>
          {pendingClients.length === 0 ? (
            <p className="muted">Новых подтверждений нет.</p>
          ) : (
            <div className="coach-today__compact-list">
              {pendingClients.map((client) => (
                <div
                  className="coach-today__compact-row"
                  key={client.invite_id ?? client.full_name}
                >
                  <span>{clientDisplayName(client)}</span>
                  <Badge tone="warning">Ожидает</Badge>
                </div>
              ))}
              <button
                type="button"
                className="text-button coach-today__text-action"
                onClick={() => onNavigate('clients', 'pending')}
              >
                Показать все приглашения <Icon name="arrow-right" size={16} />
              </button>
            </div>
          )}
        </section>

        <section
          className="coach-today__section coach-today__section--compact"
          aria-labelledby="coach-today-program-title"
        >
          <div className="coach-os-section-heading">
            <div>
              <span className="eyebrow">Следующий шаг</span>
              <h2 id="coach-today-program-title">Без активной программы</h2>
            </div>
            {withoutProgram.length > 0 && <Badge tone="warning">{withoutProgram.length}</Badge>}
          </div>
          {clientsLoading || programsLoading ? (
            <LoadingState label="Проверяем назначенные программы…" />
          ) : withoutProgram.length === 0 ? (
            <p className="muted">У активных клиентов есть программа.</p>
          ) : (
            <div className="coach-today__compact-list">
              {withoutProgram.slice(0, 3).map((client) => (
                <button
                  type="button"
                  className="coach-today__compact-row coach-today__compact-row--button"
                  key={client.id}
                  onClick={() => onOpenClient(client.id!)}
                >
                  <span>{clientDisplayName(client)}</span>
                  <Icon name="arrow-right" size={16} />
                </button>
              ))}
              <button
                type="button"
                className="text-button coach-today__text-action"
                onClick={() => onNavigate('clients', 'without_program')}
              >
                Открыть список без программы <Icon name="arrow-right" size={16} />
              </button>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
