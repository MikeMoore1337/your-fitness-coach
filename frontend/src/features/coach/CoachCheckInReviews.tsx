import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  CoachCheckInReviewItem,
  CoachCheckInReviewListResponse,
} from '../../shared/api/types';
import { queryKeys } from '../../shared/queryKeys';
import { AppLink } from '../../shared/navigation/router';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';

type Draft = {
  response: string;
  followUpTitle: string;
  followUpDueAt: string;
};

function draftFor(): Draft {
  return { response: '', followUpTitle: '', followUpDueAt: '' };
}

function summaryFacts(item: CoachCheckInReviewItem): string[] {
  const training = item.summary?.training;
  const completed =
    training && typeof training === 'object' && 'completed_workouts' in training
      ? training.completed_workouts
      : null;
  return [
    completed != null ? `Завершено тренировок: ${String(completed)}` : null,
    item.training_load != null ? `Нагрузка: ${item.training_load}/5` : null,
    item.recovery != null ? `Восстановление: ${item.recovery}/5` : null,
    item.adherence_difficulty != null
      ? `Сложность соблюдения плана: ${item.adherence_difficulty}/5`
      : null,
  ].filter((value): value is string => value != null);
}

export function CoachCheckInReviews({ timezone = 'Europe/Moscow' }: { timezone?: string | null }) {
  const queryClient = useQueryClient();
  const { toast } = useFeedback();
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const reviews = useQuery<CoachCheckInReviewListResponse>({
    queryKey: queryKeys.trainer.checkInReviews('pending'),
    queryFn: () =>
      api<CoachCheckInReviewListResponse>('/api/v1/coach/check-ins/review?status=pending&limit=50'),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const reviewMutation = useMutation({
    mutationFn: ({ item, draft }: { item: CoachCheckInReviewItem; draft: Draft }) => {
      const followUp =
        draft.followUpTitle.trim() && draft.followUpDueAt
          ? {
              follow_up_title: draft.followUpTitle.trim(),
              follow_up_due_at: draft.followUpDueAt,
              follow_up_timezone: timezone || 'Europe/Moscow',
            }
          : {};
      return api<CoachCheckInReviewItem>(`/api/v1/coach/check-ins/${item.check_in_id}/review`, {
        method: 'POST',
        body: { response: draft.response.trim() || null, ...followUp },
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.checkInReviews('pending') }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.checkInReviews('reviewed') }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.attention }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainer.tasks }),
      ]);
      toast('Итог отмечен как проверенный');
    },
    onError: (error) =>
      toast(error instanceof Error ? error.message : 'Не удалось сохранить', 'error'),
  });

  const items = reviews.data?.items ?? [];
  const pendingLabel = useMemo(
    () => (reviews.data?.total ? `${reviews.data.total} требуют ответа` : 'Новых итогов нет'),
    [reviews.data?.total],
  );

  return (
    <section className="coach-review-workspace" data-testid="coach-check-in-reviews">
      <Card
        className="coach-review-workspace__intro"
        collapsible={false}
        title="Проверка недельных итогов"
        description="Факты остаются данными клиента. Тренер добавляет ответ и при необходимости создаёт отдельную последующую задачу."
        actions={<Badge tone={items.length ? 'warning' : 'success'}>{pendingLabel}</Badge>}
      >
        {reviews.isPending ? (
          <LoadingState label="Загружаем итоги клиентов…" />
        ) : reviews.error ? (
          <ErrorState
            message="Не удалось загрузить итоги клиентов."
            retry={() => void reviews.refetch()}
          />
        ) : !items.length ? (
          <EmptyState
            title="Очередь проверки пуста"
            text="Новые недельные итоги появятся здесь после отправки клиентом."
          />
        ) : (
          <div className="coach-review-list">
            {items.map((item) => {
              const draft = drafts[item.check_in_id] ?? draftFor();
              const facts = summaryFacts(item);
              return (
                <article className="coach-review-card" key={item.check_in_id}>
                  <header className="coach-review-card__header">
                    <div>
                      <span className="eyebrow">Недельный итог · {item.week_start}</span>
                      <h3>{item.client_name}</h3>
                      <p>
                        Отправлен {item.submitted_on} ·{' '}
                        <AppLink to={`/coach?client_id=${item.client_id}&focus=review_workspace`}>
                          открыть профиль клиента
                        </AppLink>
                      </p>
                    </div>
                    <Badge tone="warning">Ожидает проверки</Badge>
                  </header>
                  <div className="coach-review-card__facts">
                    {facts.map((fact) => (
                      <span key={fact}>{fact}</span>
                    ))}
                    {!facts.length && <span>Количественных фактов за период нет</span>}
                  </div>
                  {item.note && (
                    <blockquote className="coach-review-card__note">«{item.note}»</blockquote>
                  )}
                  <div className="coach-review-card__form">
                    <label className="field">
                      <span>Ответ тренера</span>
                      <textarea
                        className="ui-input"
                        maxLength={2000}
                        onChange={(event) =>
                          setDrafts((current) => ({
                            ...current,
                            [item.check_in_id]: { ...draft, response: event.target.value },
                          }))
                        }
                        placeholder="Коротко зафиксируйте следующий шаг…"
                        rows={3}
                        value={draft.response}
                      />
                    </label>
                    <div className="coach-review-card__follow-up">
                      <label className="field">
                        <span>Последующая задача, если нужна</span>
                        <input
                          className="ui-input"
                          maxLength={240}
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [item.check_in_id]: { ...draft, followUpTitle: event.target.value },
                            }))
                          }
                          placeholder="Например, написать после следующей тренировки"
                          value={draft.followUpTitle}
                        />
                      </label>
                      <label className="field">
                        <span>Срок · {timezone || 'Europe/Moscow'}</span>
                        <input
                          className="ui-input"
                          onChange={(event) =>
                            setDrafts((current) => ({
                              ...current,
                              [item.check_in_id]: { ...draft, followUpDueAt: event.target.value },
                            }))
                          }
                          type="datetime-local"
                          value={draft.followUpDueAt}
                        />
                      </label>
                    </div>
                    <Button
                      disabled={reviewMutation.isPending}
                      onClick={() => reviewMutation.mutate({ item, draft })}
                      type="button"
                    >
                      {reviewMutation.isPending ? 'Сохраняем…' : 'Отметить проверенным'}
                    </Button>
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
