import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { CoachInbox, CoachInboxItem } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { AppLink } from '../../shared/navigation/router';
import { Badge, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';

const actionLabels: Record<CoachInboxItem['action'], string> = {
  review_workout: 'Открыть тренировку',
  review_check_in: 'Открыть проверку',
  assign_program: 'Назначить программу',
  review_program: 'Открыть программу',
  open_task: 'Открыть задачи',
  open_schedule: 'Открыть расписание',
  open_finance: 'Открыть финансы',
};

const kindLabels: Record<CoachInboxItem['kind'], string> = {
  attention: 'Сигнал',
  check_in: 'Недельный итог',
  task: 'Задача',
  session: 'Встреча',
  package: 'Пакет',
  payment: 'Оплата',
};

const priorityLabels: Record<CoachInboxItem['priority'], string> = {
  urgent: 'Сейчас',
  soon: 'Скоро',
  normal: 'Планово',
};

export function CoachInbox({ onAction }: { onAction?: () => void }) {
  const inbox = useQuery<CoachInbox>({
    queryKey: queryKeys.trainer.inbox,
    queryFn: () => api<CoachInbox>('/api/v1/coach/inbox?limit=50'),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const items = inbox.data?.items ?? [];

  return (
    <section className="coach-inbox" data-testid="coach-inbox" aria-labelledby="coach-inbox-title">
      <header className="coach-inbox__heading">
        <div>
          <span className="eyebrow">Coach OS · единый рабочий список</span>
          <h2 id="coach-inbox-title">Следующий шаг по клиентам</h2>
          <p>Сигналы, итоги, задачи и операции собраны из текущих источников.</p>
        </div>
        {inbox.data && (
          <Badge tone={inbox.data.total ? 'warning' : 'success'}>{inbox.data.total}</Badge>
        )}
      </header>

      {inbox.data && <InboxCounts counts={inbox.data.counts} />}
      {inbox.isPending ? (
        <LoadingState label="Собираем рабочие факты клиентов…" />
      ) : inbox.error ? (
        <ErrorState
          message="Не удалось загрузить единый рабочий список. Остальные разделы кабинета доступны."
          retry={() => void inbox.refetch()}
        />
      ) : !items.length ? (
        <EmptyState
          title="Новых действий нет"
          text="Здесь появится только следующий шаг, выведенный из текущих данных кабинета."
        />
      ) : (
        <ul className="coach-inbox__list">
          {items.map((item) => (
            <li className="coach-inbox__item" key={item.key}>
              <div className="coach-inbox__copy">
                <div className="coach-inbox__meta">
                  <span className="eyebrow">{item.client.name}</span>
                  <span className="coach-inbox__kind">{kindLabels[item.kind]}</span>
                  <Badge tone={item.priority === 'urgent' ? 'danger' : 'warning'}>
                    {priorityLabels[item.priority]}
                  </Badge>
                </div>
                <strong>{item.title}</strong>
                <p>{item.reason}</p>
                {item.evidence?.length ? (
                  <ul className="coach-inbox__evidence" aria-label="Основания действия">
                    {(item.evidence ?? []).slice(0, 3).map((evidence) => (
                      <li key={`${evidence.label}-${evidence.value}`}>
                        <span>{evidence.label}</span>
                        <strong>{evidence.value}</strong>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
              <AppLink
                className="button-link secondary-link"
                to={item.destination}
                onClick={() => onAction?.()}
              >
                {actionLabels[item.action]}
                <Icon name="arrow-right" size={16} />
              </AppLink>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function InboxCounts({ counts }: { counts: CoachInbox['counts'] }) {
  const values = [
    ['Сигналы', counts.attention],
    ['Итоги', counts.pending_reviews],
    ['Задачи', counts.tasks],
    ['Встречи', counts.sessions],
    ['Пакеты', counts.packages],
    ['Оплаты', counts.payments],
  ] as const;
  return (
    <div className="coach-inbox__counts" aria-label="Сводка рабочего списка">
      {values.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
