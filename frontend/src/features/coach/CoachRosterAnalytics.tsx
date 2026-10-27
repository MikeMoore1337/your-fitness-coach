import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  Client,
  CoachAssignedProgram,
  CoachAttentionResponse,
  CoachTask,
  TrainerClientProgressList,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { clientDisplayName, russianQuantity } from './coachWorkspace';

type RosterFilter = 'all' | 'attention' | 'without_program' | 'pending';

function dateLabel(value: string | null | undefined): string {
  return value
    ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('ru-RU')
    : 'Нет данных';
}

function attentionLabel(count: number): string {
  return `${count} ${russianQuantity(count, ['требует внимания', 'требуют внимания', 'требуют внимания'])}`;
}

export function CoachRosterAnalytics({
  clients,
  programs,
  summaries,
  onOpenClient,
}: {
  clients: Client[];
  programs: CoachAssignedProgram[];
  summaries?: TrainerClientProgressList;
  onOpenClient: (clientId: number) => void;
}) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<RosterFilter>('all');
  const attention = useQuery<CoachAttentionResponse>({
    queryKey: queryKeys.trainer.attention,
    queryFn: () => api<CoachAttentionResponse>('/api/v1/coach/attention?limit=50'),
    staleTime: 15_000,
    retry: false,
  });
  const tasks = useQuery<CoachTask[]>({
    queryKey: queryKeys.trainer.tasks,
    queryFn: () => api<CoachTask[]>('/api/v1/coach/tasks?state=open'),
    staleTime: 15_000,
    retry: false,
  });
  const summaryMap = useMemo(
    () => new Map((summaries?.items ?? []).map((summary) => [summary.user_id, summary] as const)),
    [summaries?.items],
  );
  const attentionByClient = useMemo(() => {
    const result = new Map<number, number>();
    for (const item of attention.data?.items ?? []) {
      result.set(item.client.id, (result.get(item.client.id) ?? 0) + 1);
    }
    return result;
  }, [attention.data?.items]);
  const activeProgramByClient = useMemo(
    () =>
      new Map(
        programs
          .filter((program) => program.is_active)
          .map((program) => [program.client_id, program] as const),
      ),
    [programs],
  );
  const rows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase('ru-RU');
    return clients
      .filter((client) => {
        if (filter === 'pending') return client.status === 'pending';
        if (filter === 'attention') return (attentionByClient.get(client.id ?? 0) ?? 0) > 0;
        if (filter === 'without_program') {
          return client.status === 'active' && !activeProgramByClient.has(client.id ?? 0);
        }
        return true;
      })
      .filter((client) => {
        if (!query) return true;
        return `${clientDisplayName(client)} ${client.username ?? ''}`
          .toLocaleLowerCase('ru-RU')
          .includes(query);
      })
      .sort((left, right) => clientDisplayName(left).localeCompare(clientDisplayName(right), 'ru'));
  }, [activeProgramByClient, attentionByClient, clients, filter, search]);

  const activeCount = clients.filter((client) => client.status === 'active').length;
  const pendingCount = clients.filter((client) => client.status === 'pending').length;
  const reviewCount = (attention.data?.items ?? []).filter(
    (item) => item.kind === 'weekly_check_in',
  ).length;

  return (
    <section className="coach-roster-analytics" data-testid="coach-roster-analytics">
      <Card
        className="coach-roster-analytics__summary"
        collapsible={false}
        title="Реестр и факты"
        description="Операционные показатели из текущего списка клиентов, очереди внимания и задач. Без общего рейтинга клиентов."
      >
        <div className="coach-roster-analytics__metrics" aria-label="Факты кабинета">
          <div>
            <span>Активные клиенты</span>
            <strong>{activeCount}</strong>
          </div>
          <div>
            <span>Требуют внимания</span>
            <strong>{attention.data?.total ?? '—'}</strong>
          </div>
          <div>
            <span>Итоги на проверке</span>
            <strong>{reviewCount}</strong>
          </div>
          <div>
            <span>Открытые задачи</span>
            <strong>{tasks.data?.length ?? '—'}</strong>
          </div>
        </div>
      </Card>

      <Card
        className="coach-roster-analytics__roster"
        collapsible={false}
        title="Список клиентов"
        actions={
          <Badge tone={pendingCount ? 'warning' : 'neutral'}>
            {pendingCount ? `Ожидают подтверждения: ${pendingCount}` : 'Нет ожидающих приглашений'}
          </Badge>
        }
      >
        <div className="coach-roster-analytics__toolbar">
          <label className="field">
            <span>Поиск</span>
            <input
              aria-label="Поиск по списку клиентов"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Имя или имя пользователя"
              type="search"
              value={search}
            />
          </label>
          <label className="field">
            <span>Фильтр</span>
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value as RosterFilter)}
            >
              <option value="all">Все</option>
              <option value="attention">Требуют внимания</option>
              <option value="without_program">Без программы</option>
              <option value="pending">Ожидают подключения</option>
            </select>
          </label>
        </div>
        {attention.isPending || tasks.isPending ? (
          <LoadingState label="Собираем факты списка клиентов…" />
        ) : attention.error || tasks.error ? (
          <ErrorState
            message="Часть операционных фактов временно недоступна."
            retry={() => {
              void attention.refetch();
              void tasks.refetch();
            }}
          />
        ) : !rows.length ? (
          <EmptyState title="В этом списке пусто" text="Измените фильтр или поисковый запрос." />
        ) : (
          <div
            className="coach-roster-analytics__list"
            data-testid="coach-roster-table"
            role="table"
            aria-label="Список клиентов"
          >
            <div className="coach-roster-table__header" role="row">
              <span role="columnheader">Клиент</span>
              <span role="columnheader">Программа</span>
              <span role="columnheader">Последняя</span>
              <span role="columnheader">Следующая</span>
              <span role="columnheader">Внимание</span>
              <span role="columnheader">Действие</span>
            </div>
            {rows.map((client) => {
              const summary = client.id ? summaryMap.get(client.id) : undefined;
              const program = client.id ? activeProgramByClient.get(client.id) : undefined;
              const attentionCount = client.id ? (attentionByClient.get(client.id) ?? 0) : 0;
              return (
                <article
                  className="coach-roster-row"
                  key={client.id ?? `invite-${client.invite_id}`}
                  role="row"
                >
                  <div className="coach-roster-row__identity" role="cell">
                    <span className="coach-roster-cell__label">Клиент</span>
                    <strong>{clientDisplayName(client)}</strong>
                    <span>
                      {client.status === 'pending'
                        ? 'Ожидает подтверждения'
                        : client.username
                          ? `@${client.username}`
                          : 'Активный клиент'}
                    </span>
                  </div>
                  <div className="coach-roster-row__program" role="cell">
                    <span className="coach-roster-cell__label">Программа</span>
                    <span className="coach-roster-cell__value">
                      {program
                        ? `${program.title} · версия ${program.current_revision_number}`
                        : 'Нет активной программы'}
                    </span>
                  </div>
                  <div className="coach-roster-row__last" role="cell">
                    <span className="coach-roster-cell__label">Последняя</span>
                    <span className="coach-roster-cell__value">
                      {dateLabel(summary?.training.last_completed_workout_on)}
                    </span>
                  </div>
                  <div className="coach-roster-row__next" role="cell">
                    <span className="coach-roster-cell__label">Следующая</span>
                    <span className="coach-roster-cell__value">
                      {dateLabel(summary?.training.next_workout?.scheduled_date)}
                    </span>
                  </div>
                  <div className="coach-roster-row__attention" role="cell">
                    <span className="coach-roster-cell__label">Внимание</span>
                    {attentionCount > 0 ? (
                      <Badge tone="warning">{attentionLabel(attentionCount)}</Badge>
                    ) : (
                      <span className="coach-roster-cell__value">Нет</span>
                    )}
                  </div>
                  <div className="coach-roster-row__actions" role="cell">
                    <span className="coach-roster-cell__label">Действие</span>
                    {client.id ? (
                      <button type="button" onClick={() => onOpenClient(client.id!)}>
                        Открыть профиль
                      </button>
                    ) : (
                      <span className="coach-roster-cell__value">Ожидает подтверждения</span>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Card>
    </section>
  );
}
