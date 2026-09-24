import { useMemo } from 'react';
import type { Client, CoachAssignedProgram } from '../../shared/api/types';
import type { CoachClientFilter } from './coachWorkspace';
import { CoachAttentionCenter } from './CoachAttentionCenter';
import { Badge, Button, LoadingState } from '../../shared/ui/common';
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
  const activeProgramClientIds = useMemo(
    () =>
      new Set(programs.filter((program) => program.is_active).map((program) => program.client_id)),
    [programs],
  );
  const withoutProgram = clients.filter(
    (client) =>
      client.status === 'active' && client.id != null && !activeProgramClientIds.has(client.id),
  );
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
