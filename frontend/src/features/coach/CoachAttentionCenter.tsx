import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { CoachAttentionItem, CoachAttentionResponse } from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';
import { AppLink } from '../../shared/navigation/router';
import { Badge, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';

const ATTENTION_LIMIT = 50;
const VISIBLE_ITEM_LIMIT = 5;

const actionLabels: Record<CoachAttentionItem['action'], string> = {
  review_check_in: 'Открыть проверку',
  review_workout: 'Открыть тренировку',
  assign_program: 'Назначить программу',
};

function attentionLatencyBucket(elapsedMs: number) {
  if (elapsedMs < 250) return 'under_250ms' as const;
  if (elapsedMs < 1_000) return '250_1000ms' as const;
  return 'over_1s' as const;
}

export function CoachAttentionCenter({ enabled = true }: { enabled?: boolean }) {
  const startedAt = useRef<number | null>(null);
  const timingTracked = useRef(false);
  const previousKeys = useRef<Set<string> | null>(null);
  const attention = useQuery<CoachAttentionResponse>({
    queryKey: queryKeys.trainer.attention,
    queryFn: () => api<CoachAttentionResponse>(`/api/v1/coach/attention?limit=${ATTENTION_LIMIT}`),
    enabled,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  useEffect(() => {
    startedAt.current = performance.now();
  }, []);

  useEffect(() => {
    if (!enabled || timingTracked.current || (!attention.data && !attention.error)) return;
    timingTracked.current = true;
    trackProductEvent({
      name: 'coach_attention_load_timing',
      surface: productEventSurface(),
      latency_bucket: attentionLatencyBucket(
        performance.now() - (startedAt.current ?? performance.now()),
      ),
    });
  }, [attention.data, attention.error, enabled]);

  useEffect(() => {
    if (!attention.data) return;
    const items = attention.data.items ?? [];
    const currentKeys = new Set(items.map((item) => item.key));
    for (const item of items) {
      trackProductEvent(
        {
          name: 'coach_attention_shown',
          surface: productEventSurface(),
          kind: item.kind,
        },
        { dedupe: 'session', dedupeKey: `coach-attention-shown:${item.key}` },
      );
    }
    const previous = previousKeys.current;
    if (previous && attention.data.total < previous.size) {
      for (const key of previous) {
        if (currentKeys.has(key)) continue;
        const kind = key.split(':', 1)[0] as CoachAttentionItem['kind'];
        trackProductEvent(
          {
            name: 'coach_attention_resolved',
            surface: productEventSurface(),
            kind,
          },
          { dedupe: 'session', dedupeKey: `coach-attention-resolved:${key}` },
        );
      }
    }
    previousKeys.current = currentKeys;
  }, [attention.data]);

  if (!enabled) return null;
  const items = attention.data?.items ?? [];

  return (
    <section className="coach-attention-center" aria-labelledby="coach-attention-title">
      <div className="coach-attention-center__heading">
        <div>
          <span className="eyebrow">Короткий список действий</span>
          <h2 id="coach-attention-title">Требует внимания</h2>
        </div>
        {attention.data && (
          <Badge tone={attention.data.total ? 'warning' : 'success'}>{attention.data.total}</Badge>
        )}
      </div>
      {attention.isLoading ? (
        <LoadingState label="Проверяем сигналы клиентов…" />
      ) : attention.error ? (
        <ErrorState
          message="Не удалось загрузить список внимания. Остальные разделы кабинета доступны."
          retry={() => void attention.refetch()}
        />
      ) : !items.length ? (
        <EmptyState
          title="Срочных действий нет"
          text="Здесь появятся только конкретные новые состояния клиента."
        />
      ) : (
        <ul className="coach-attention-center__list">
          {items.slice(0, VISIBLE_ITEM_LIMIT).map((item) => (
            <li className="coach-attention-item" key={item.key}>
              <div className="coach-attention-item__copy">
                <span className="eyebrow">{item.client.name}</span>
                <strong>{item.title}</strong>
                <p>{item.reason}</p>
              </div>
              <AppLink
                className="button-link secondary-link"
                to={item.destination}
                onClick={() => {
                  trackProductEvent({
                    name: 'coach_attention_opened',
                    surface: productEventSurface(),
                    kind: item.kind,
                  });
                }}
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
