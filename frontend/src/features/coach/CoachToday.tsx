import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Client, CoachAssignedProgram, CoachCapacityResponse } from '../../shared/api/types';
import { api } from '../../shared/api/client';
import { queryKeys } from '../../shared/queryKeys';
import type { CoachClientFilter } from './coachWorkspace';
import { CoachAttentionCenter } from './CoachAttentionCenter';
import { Badge, Button, ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';

export type CoachTodayNavigation = 'clients' | 'programs' | 'tools';

type CoachTodayProps = {
  clients: Client[];
  programs: CoachAssignedProgram[];
  clientsLoading: boolean;
  programsLoading: boolean;
  pendingCount: number;
  onNavigate: (destination: CoachTodayNavigation, filter?: CoachClientFilter) => void;
  onAttentionAction?: () => void;
};

export function CoachToday({
  clients,
  programs,
  clientsLoading,
  programsLoading,
  pendingCount,
  onNavigate,
  onAttentionAction,
}: CoachTodayProps) {
  const capacity = useQuery<CoachCapacityResponse>({
    queryKey: queryKeys.trainer.capacity,
    queryFn: () => api<CoachCapacityResponse>('/api/v1/coach/capacity'),
    staleTime: 15_000,
    retry: false,
  });
  const activeProgramClientIds = useMemo(
    () =>
      new Set(programs.filter((program) => program.is_active).map((program) => program.client_id)),
    [programs],
  );
  const withoutProgram = clients.filter(
    (client) =>
      client.status === 'active' && client.id != null && !activeProgramClientIds.has(client.id),
  );
  const firstBottleneck = capacity.data?.bottlenecks[0];
  return (
    <section className="coach-today" data-testid="coach-today" aria-labelledby="coach-today-title">
      <header className="coach-today__hero">
        <div>
          <span className="eyebrow">Рабочий цикл тренера</span>
          <h1 id="coach-today-title">Что требует действия?</h1>
          <p>Короткий список фактов и следующий шаг. Подробности открываются внутри клиента.</p>
        </div>
        <div className="coach-today__hero-actions app-action-group">
          <button type="button" onClick={() => onNavigate('clients')}>
            Открыть клиентов
            <Icon name="arrow-right" size={16} />
          </button>
        </div>
      </header>

      <CoachAttentionCenter enabled onAction={onAttentionAction} />

      <section
        className="coach-today__section coach-today__capacity"
        aria-labelledby="coach-today-capacity-title"
        data-testid="coach-capacity"
      >
        <div className="coach-os-section-heading">
          <div>
            <span className="eyebrow">Масштаб рабочего списка</span>
            <h2 id="coach-today-capacity-title">Где сейчас узкое место?</h2>
          </div>
          {capacity.data && (
            <Badge tone={capacity.data.capacity_band === '100_plus' ? 'warning' : 'neutral'}>
              {capacityBandLabel(capacity.data.capacity_band)}
            </Badge>
          )}
        </div>
        {capacity.isPending ? (
          <LoadingState label="Собираем факты ёмкости…" />
        ) : capacity.error ? (
          <ErrorState
            message="Факты ёмкости временно недоступны."
            retry={() => void capacity.refetch()}
          />
        ) : capacity.data ? (
          <>
            <div className="coach-today__capacity-metrics" aria-label="Факты ёмкости">
              <div>
                <span>Активные клиенты</span>
                <strong>{capacity.data.active_client_count}</strong>
              </div>
              <div>
                <span>Внимание</span>
                <strong>{capacity.data.attention_item_count}</strong>
              </div>
              <div>
                <span>Открытые задачи</span>
                <strong>{capacity.data.open_task_count}</strong>
              </div>
              <div>
                <span>Покрытие программой</span>
                <strong>
                  {capacity.data.roster_coverage_percent == null
                    ? '—'
                    : `${capacity.data.roster_coverage_percent}%`}
                </strong>
              </div>
            </div>
            <p className="muted">
              Ближайшие границы масштаба: 10 / 30 / 100 клиентов.
              {capacity.data.next_capacity_boundary
                ? ` До следующей — ${capacity.data.next_capacity_boundary - capacity.data.active_client_count}.`
                : ' Верхняя граница среза пройдена.'}
            </p>
            {firstBottleneck && (
              <p className="coach-today__capacity-bottleneck">
                <strong>Первое узкое место:</strong> {capacityBottleneckLabel(firstBottleneck.key)}{' '}
                · {firstBottleneck.count}
              </p>
            )}
          </>
        ) : null}
      </section>

      <section className="coach-today__section" aria-labelledby="coach-today-status-title">
        <div className="coach-os-section-heading">
          <div>
            <span className="eyebrow">Короткий статус</span>
            <h2 id="coach-today-status-title">Следующие рабочие шаги</h2>
          </div>
        </div>
        {clientsLoading || programsLoading ? (
          <LoadingState label="Проверяем рабочий статус…" />
        ) : (
          <div className="coach-today__compact-list">
            <button
              type="button"
              className="coach-today__compact-row coach-today__compact-row--button"
              onClick={() => onNavigate('clients', 'pending')}
            >
              <span>
                <strong>Ожидают подключения</strong>
                <small>{pendingCount ? `${pendingCount} приглаш.` : 'Новых приглашений нет'}</small>
              </span>
              {pendingCount > 0 ? (
                <Badge tone="warning">{pendingCount}</Badge>
              ) : (
                <Icon name="arrow-right" size={16} />
              )}
            </button>
            <button
              type="button"
              className="coach-today__compact-row coach-today__compact-row--button"
              onClick={() => onNavigate('clients', 'without_program')}
            >
              <span>
                <strong>Без активной программы</strong>
                <small>
                  {withoutProgram.length
                    ? `${withoutProgram.length} ${withoutProgram.length === 1 ? 'клиент' : 'клиента'}`
                    : 'Все активные клиенты покрыты'}
                </small>
              </span>
              {withoutProgram.length > 0 ? (
                <Badge tone="warning">{withoutProgram.length}</Badge>
              ) : (
                <Icon name="arrow-right" size={16} />
              )}
            </button>
          </div>
        )}
      </section>

      <div className="coach-today__secondary-grid">
        <section
          className="coach-today__section coach-today__section--compact"
          aria-label="Быстрый переход к клиентам"
        >
          <div className="coach-os-section-heading">
            <div>
              <span className="eyebrow">Рабочий список</span>
              <h2>Клиенты</h2>
            </div>
            <Badge>{clients.filter((client) => client.status === 'active').length}</Badge>
          </div>
          <Button
            type="button"
            variant="secondary"
            className="coach-today__text-action"
            onClick={() => onNavigate('clients')}
          >
            Открыть список клиентов <Icon name="arrow-right" size={16} />
          </Button>
        </section>
      </div>
    </section>
  );
}

function capacityBandLabel(band: CoachCapacityResponse['capacity_band']): string {
  return {
    '0_9': 'До 10 клиентов',
    '10_29': '10–29 клиентов',
    '30_99': '30–99 клиентов',
    '100_plus': '100+ клиентов',
  }[band];
}

function capacityBottleneckLabel(key: CoachCapacityResponse['bottlenecks'][number]['key']): string {
  return {
    attention: 'требуют внимания',
    open_tasks: 'открытые задачи',
    without_program: 'клиенты без программы',
    pending_invites: 'ожидающие приглашения',
  }[key];
}
