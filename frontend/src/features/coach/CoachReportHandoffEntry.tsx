import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { ReportHandoff } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { AppLink } from '../../shared/navigation/router';
import { EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

function formatDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

export function CoachReportHandoffEntry({
  clientId,
  enabled,
}: {
  clientId: number;
  enabled: boolean;
}) {
  const handoffs = useQuery({
    queryKey: queryKeys.trainer.clientReportHandoffs(clientId),
    queryFn: () =>
      api<ReportHandoff[]>(`/api/v1/coach/clients/${clientId}/report-handoffs?limit=5`),
    enabled,
    retry: false,
  });
  if (!enabled) return null;
  const latest = handoffs.data?.[0];
  return (
    <section
      className="coach-report-entry"
      data-testid="coach-report-entry"
      aria-labelledby="coach-report-entry-title"
    >
      <div className="coach-os-section-heading">
        <div>
          <span className="eyebrow">Task 296 · общий report contract</span>
          <h3 id="coach-report-entry-title">Отчёт клиента</h3>
        </div>
      </div>
      {handoffs.isLoading ? (
        <LoadingState label="Проверяем отправленные отчёты…" />
      ) : handoffs.error ? (
        <ErrorState
          message="Не удалось загрузить комментарий клиента. Канонический отчёт доступен отдельно."
          retry={() => void handoffs.refetch()}
        />
      ) : !latest ? (
        <EmptyState
          title="Отправленных отчётов пока нет"
          text="Когда клиент отправит отчёт, его комментарий появится здесь."
        />
      ) : (
        <div className="coach-report-entry__content">
          <p className="muted">
            Последний отчёт: {formatDate(latest.period_start)} — {formatDate(latest.period_end)}
          </p>
          {latest.client_comment ? (
            <blockquote className="coach-report-entry__comment">
              <span>Комментарий клиента</span>
              <p>{latest.client_comment}</p>
            </blockquote>
          ) : (
            <p className="muted">Клиент не добавил комментарий к этому отчёту.</p>
          )}
          <AppLink
            className="button-link secondary-link"
            to={`/app/report?period=${latest.period}&client_id=${clientId}`}
            onClick={() => {
              trackProductEvent({
                name: 'coach_quick_action_used',
                surface: productEventSurface(),
                kind: 'report',
              });
            }}
          >
            Открыть расширенный отчёт <Icon name="arrow-right" size={16} />
          </AppLink>
        </div>
      )}
    </section>
  );
}
