import { useEffect, useMemo, useRef, useState } from 'react';
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
  review_program: 'Открыть программу',
};

const priorityLabels = {
  urgent: 'Сейчас',
  soon: 'Скоро',
  normal: 'Планово',
} as const;

const priorityRank = { urgent: 0, soon: 1, normal: 2 } as const;
const EMPTY_ATTENTION_ITEMS: CoachAttentionItem[] = [];

type AttentionFilter = 'all' | 'review' | 'workout' | 'program';

function attentionLatencyBucket(elapsedMs: number) {
  if (elapsedMs < 250) return 'under_250ms' as const;
  if (elapsedMs < 1_000) return '250_1000ms' as const;
  return 'over_1s' as const;
}

export function CoachAttentionCenter({
  enabled = true,
  onAction,
}: {
  enabled?: boolean;
  onAction?: () => void;
}) {
  const startedAt = useRef<number | null>(null);
  const timingTracked = useRef(false);
  const previousKeys = useRef<Set<string> | null>(null);
  const [filter, setFilter] = useState<AttentionFilter>('all');
  const [sort, setSort] = useState<'priority' | 'newest'>('priority');
  const attention = useQuery<CoachAttentionResponse>({
    queryKey: queryKeys.trainer.attention,
    queryFn: () => api<CoachAttentionResponse>(`/api/v1/coach/attention?limit=${ATTENTION_LIMIT}`),
    enabled,
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const items = attention.data?.items ?? EMPTY_ATTENTION_ITEMS;
  const filteredItems = useMemo(() => {
    const filtered = items.filter((item) => {
      if (filter === 'review') return item.kind === 'weekly_check_in';
      if (filter === 'workout') return item.source_kind === 'workout';
      if (filter === 'program')
        return item.source_kind === 'program' || item.kind === 'without_program';
      return true;
    });
    return [...filtered].sort((left, right) => {
      if (sort === 'priority') {
        const priorityDifference =
          priorityRank[left.priority ?? 'normal'] - priorityRank[right.priority ?? 'normal'];
        if (priorityDifference) return priorityDifference;
      }
      return right.created_at.localeCompare(left.created_at) || left.key.localeCompare(right.key);
    });
  }, [filter, items, sort]);
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
        const parsedKind = key.split(':', 1)[0] as CoachAttentionItem['kind'];
        trackProductEvent(
          {
            name: 'coach_attention_resolved',
            surface: productEventSurface(),
            kind: parsedKind,
          },
          { dedupe: 'session', dedupeKey: `coach-attention-resolved:${key}` },
        );
      }
    }
    previousKeys.current = currentKeys;
  }, [attention.data, items]);

  if (!enabled) return null;

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
      {items.length > 0 && (
        <div className="coach-attention-center__controls" aria-label="Фильтры внимания">
          <div className="coach-attention-center__filters" role="group" aria-label="Тип сигнала">
            {(
              [
                ['all', 'Все'],
                ['review', 'Итоги'],
                ['workout', 'Тренировки'],
                ['program', 'Программы'],
              ] as const
            ).map(([value, label]) => (
              <button
                className={filter === value ? 'is-active' : undefined}
                key={value}
                onClick={() => setFilter(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <label className="coach-attention-center__sort">
            <span>Сортировка</span>
            <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}>
              <option value="priority">По приоритету</option>
              <option value="newest">Сначала новые</option>
            </select>
          </label>
        </div>
      )}
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
      ) : !filteredItems.length ? (
        <EmptyState title="В этом фильтре пусто" text="Выберите другой тип сигнала." />
      ) : (
        <ul className="coach-attention-center__list">
          {filteredItems.slice(0, VISIBLE_ITEM_LIMIT).map((item) => (
            <li className="coach-attention-item" key={item.key}>
              <div className="coach-attention-item__copy">
                <div className="coach-attention-item__meta">
                  <span className="eyebrow">{item.client.name}</span>
                  <Badge tone={item.priority === 'urgent' ? 'danger' : 'warning'}>
                    {priorityLabels[item.priority ?? 'normal']}
                  </Badge>
                </div>
                <strong>{item.title}</strong>
                <p>{item.reason}</p>
                {item.evidence?.length ? (
                  <ul className="coach-attention-item__evidence" aria-label="Основания">
                    {item.evidence.slice(0, 3).map((evidence) => (
                      <li key={`${evidence.label}-${evidence.value}`}>
                        <span>{evidence.label}</span>
                        <strong>{evidence.value}</strong>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <small className="coach-attention-item__age">
                  {item.age_days ? `${item.age_days} дн. назад` : 'Сегодня'}
                </small>
              </div>
              <AppLink
                className="button-link secondary-link"
                to={item.destination}
                onClick={() => {
                  onAction?.();
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
