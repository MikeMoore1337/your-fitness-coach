import { useEffect, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  WorkoutHistoryItem,
  WorkoutHistorySummary,
  WorkoutScheduleItem,
} from '../../shared/api/types';
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { workoutStatusLabel } from '../../shared/statusLabels';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { WorkoutFeedbackDisclosure } from './WorkoutFeedback';
import { workoutCompletionFeedbackLabels } from './WorkoutCompletionSummary';

interface RestHistoryEntry {
  source_set_id: number;
  status: string;
  planned_seconds: number;
  adjusted_seconds: number;
  measured_seconds: number | null;
}

function restDuration(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}

function RestHistory({ sessions }: { sessions?: RestHistoryEntry[] }) {
  if (!sessions?.length) {
    return <p className="muted">Отдых: нет достоверных замеров.</p>;
  }
  return (
    <details className="workout-history__rest">
      <summary>
        Отдых по подходам · {sessions.filter((row) => row.status === 'completed').length} замеров
      </summary>
      <ul>
        {sessions.map((row) => (
          <li key={row.source_set_id}>
            План {restDuration(row.planned_seconds)}
            {row.adjusted_seconds !== row.planned_seconds
              ? ` · скорректирован до ${restDuration(row.adjusted_seconds)}`
              : ''}
            {' · '}
            {row.status === 'completed' && row.measured_seconds !== null
              ? `по отметке ${restDuration(row.measured_seconds)} (разница ${row.measured_seconds - row.planned_seconds > 0 ? '+' : ''}${row.measured_seconds - row.planned_seconds} с)`
              : 'нет достоверного замера'}
          </li>
        ))}
      </ul>
    </details>
  );
}

const HISTORY_PAGE_SIZE = 10;
const adaptationReasonLabels: Record<string, string> = {
  limited_time: 'мало времени',
  unavailable_equipment: 'оборудование недоступно',
  replace_exercise: 'замена упражнения',
  different_environment: 'другое место тренировки',
};
export type WorkoutNavigationTarget = 'schedule' | 'history';

export function WorkoutHistory({
  focusedWorkoutId,
  focusedCommentId,
  focusedExerciseId,
  onWorkoutSelect,
  readOnly = false,
  timeZone,
}: {
  focusedWorkoutId?: number | null;
  focusedCommentId?: number | null;
  focusedExerciseId?: number | null;
  onWorkoutSelect?: (workoutId: number, target: WorkoutNavigationTarget) => void;
  readOnly?: boolean;
  timeZone?: string | null;
}) {
  const queryClient = useQueryClient();
  const { confirm, toast } = useFeedback();
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const week = useQuery({
    queryKey: ['workout', 'week'],
    queryFn: () => api<WorkoutScheduleItem[]>('/api/v1/workouts/week'),
  });
  const history = useInfiniteQuery({
    queryKey: ['workout', 'history'],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      api<WorkoutHistoryItem[]>(
        `/api/v1/workouts/history?offset=${pageParam}&limit=${HISTORY_PAGE_SIZE}`,
      ),
    getNextPageParam: (lastPage, pages) =>
      lastPage.length === HISTORY_PAGE_SIZE ? pages.flat().length : undefined,
  });
  const summary = useQuery({
    queryKey: ['workout', 'history', 'summary'],
    queryFn: () => api<WorkoutHistorySummary>('/api/v1/workouts/history/summary'),
  });
  const rows = useMemo(() => history.data?.pages.flat() ?? [], [history.data?.pages]);
  const today = dateInputValue(new Date(), timeZone || detectedTimeZone());
  const clearHistory = useMutation({
    mutationFn: () => api('/api/v1/workouts/history', { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workout'] });
      toast('История тренировок очищена');
    },
    onError: (reason) => toast((reason as Error).message, 'error'),
  });

  useEffect(() => {
    if (!focusedWorkoutId || !rows.some((item) => item.id === focusedWorkoutId)) return;
    const row = document.getElementById(`workout-history-${focusedWorkoutId}`);
    row?.focus({ preventScroll: true });
    row?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [focusedWorkoutId, rows]);

  return (
    <div className="stack">
      <Card title="Неделя">
        {week.isLoading ? (
          <LoadingState />
        ) : week.error ? (
          <ErrorState message={(week.error as Error).message} />
        ) : !week.data?.length ? (
          <EmptyState title="На этой неделе нет тренировок" />
        ) : (
          <div className="list-grid top-gap">
            {week.data.map((item) => {
              const target: WorkoutNavigationTarget | null =
                item.status === 'completed'
                  ? rows.some((row) => row.id === item.id)
                    ? 'history'
                    : null
                  : item.scheduled_date >= today
                    ? 'schedule'
                    : null;
              const content = (
                <>
                  <div>
                    <strong>{item.title}</strong>
                    <p className="muted">{item.scheduled_date}</p>
                  </div>
                  <Badge>{workoutStatusLabel(item.status)}</Badge>
                </>
              );
              if (!target) {
                return (
                  <article className="list-row" key={item.id}>
                    {content}
                  </article>
                );
              }
              const targetId = `workout-${target}-${item.id}`;
              return (
                <a
                  className="list-row workout-day-link"
                  href={`#${targetId}`}
                  key={item.id}
                  aria-label={`Открыть тренировочный день: ${item.title}`}
                  onClick={() => onWorkoutSelect?.(item.id, target)}
                >
                  {content}
                </a>
              );
            })}
          </div>
        )}
      </Card>
      <Card
        className="workout-history-card"
        defaultOpen={Boolean(focusedWorkoutId)}
        key={focusedWorkoutId ?? 'history'}
        title="История"
      >
        {history.isLoading || summary.isLoading ? (
          <LoadingState />
        ) : history.error || summary.error ? (
          <ErrorState message={((history.error || summary.error) as Error).message} />
        ) : !rows.length ? (
          <EmptyState title="История пока пуста" />
        ) : (
          <>
            <div className="metric-grid workout-history__metrics">
              <div className="metric">
                <span>Тренировок</span>
                <strong>{summary.data?.workouts_completed ?? 0}</strong>
              </div>
              <div className="metric">
                <span>Подходов</span>
                <strong>{summary.data?.completed_sets ?? 0}</strong>
              </div>
              <div className="metric">
                <span>Объём</span>
                <strong>{Math.round(summary.data?.volume_kg ?? 0)} кг</strong>
              </div>
            </div>
            <div className="list-grid top-gap">
              {rows.map((item) => (
                <article
                  className="list-row workout-context-row"
                  id={`workout-history-${item.id}`}
                  key={item.id}
                  tabIndex={-1}
                  aria-label={`Тренировка ${item.title} в истории`}
                >
                  <div>
                    <strong>{item.title}</strong>
                    <p className="muted">
                      {item.scheduled_date} · {item.completed_sets} подходов
                    </p>
                    <div className="workout-history__exercises" aria-label="Выполненные упражнения">
                      {item.exercises.map((exercise) => (
                        <button
                          type="button"
                          className="text-button"
                          key={exercise.workout_exercise_id}
                          onClick={() =>
                            setGuide({ id: exercise.exercise_id, title: exercise.title })
                          }
                        >
                          {exercise.title}
                        </button>
                      ))}
                    </div>
                    <RestHistory
                      sessions={
                        (item as WorkoutHistoryItem & { rest_sessions?: RestHistoryEntry[] })
                          .rest_sessions
                      }
                    />
                    {(
                      item as WorkoutHistoryItem & {
                        rest_sessions?: Array<{
                          id: number;
                          planned_seconds: number;
                          adjusted_seconds: number;
                          measured_seconds: number | null;
                          status: string;
                          source: string | null;
                        }>;
                      }
                    ).rest_sessions?.length ? (
                      <div className="workout-history__rest-log" aria-label="Отдых между подходами">
                        <strong>Отдых по отметке пользователя</strong>
                        {(
                          item as WorkoutHistoryItem & {
                            rest_sessions: Array<{
                              id: number;
                              planned_seconds: number;
                              adjusted_seconds: number;
                              measured_seconds: number | null;
                              status: string;
                              source: string | null;
                            }>;
                          }
                        ).rest_sessions.map((rest, index) => {
                          const measured =
                            rest.status === 'completed' ? rest.measured_seconds : null;
                          const delta = measured === null ? null : measured - rest.adjusted_seconds;
                          const minutes = (seconds: number) =>
                            `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
                          return (
                            <p className="muted" key={rest.id}>
                              {index + 1}. План {minutes(rest.planned_seconds)}
                              {rest.adjusted_seconds !== rest.planned_seconds
                                ? ` (скорректирован: ${minutes(rest.adjusted_seconds)})`
                                : ''}
                              {' · '}
                              {measured === null
                                ? 'Нет достоверного замера'
                                : `По отметке: ${minutes(measured)}, отклонение ${delta! >= 0 ? '+' : ''}${delta} сек`}
                              {rest.source === 'USER_CORRECTED' ? ' · Исправлено вручную' : ''}
                            </p>
                          );
                        })}
                      </div>
                    ) : null}
                    {item.adaptations.map((adaptation) => (
                      <p className="workout-history__adaptation" key={adaptation.id}>
                        Изменено перед тренировкой: {adaptationReasonLabels[adaptation.reason]}
                      </p>
                    ))}
                    {(item.completion_feedback || item.completion_note) && (
                      <div className="workout-completion-context">
                        {item.completion_feedback && (
                          <strong>
                            Самооценка: {workoutCompletionFeedbackLabels[item.completion_feedback]}
                          </strong>
                        )}
                        {item.completion_note && <p>{item.completion_note}</p>}
                      </div>
                    )}
                  </div>
                  <strong>{item.volume_kg} кг</strong>
                  <WorkoutFeedbackDisclosure
                    workoutId={item.id}
                    workoutTitle={item.title}
                    workoutDate={item.scheduled_date}
                    exercises={item.exercises.map((exercise) => ({
                      workoutExerciseId: exercise.workout_exercise_id,
                      title: exercise.title,
                    }))}
                    viewer="client"
                    focusedCommentId={focusedWorkoutId === item.id ? focusedCommentId : null}
                    focusedExerciseId={focusedWorkoutId === item.id ? focusedExerciseId : null}
                    defaultOpen={focusedWorkoutId === item.id && Boolean(focusedCommentId)}
                  />
                </article>
              ))}
            </div>
            {history.hasNextPage && (
              <button
                className="secondary top-gap"
                disabled={history.isFetchingNextPage}
                onClick={() => void history.fetchNextPage()}
              >
                {history.isFetchingNextPage ? 'Загружаем…' : 'Показать ещё'}
              </button>
            )}
            <div className="workout-history__footer-actions">
              <button
                className="btn-danger"
                disabled={readOnly || clearHistory.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      title: 'Очистить историю?',
                      message: 'Завершённые тренировки и их подходы будут удалены безвозвратно.',
                      confirmText: 'Очистить',
                    })
                  )
                    clearHistory.mutate();
                }}
              >
                Очистить историю
              </button>
            </div>
            {readOnly && (
              <p className="muted demo-capability-notice" role="status">
                Очистка истории доступна после входа. Просмотр и навигация по результатам доступны в
                демо.
              </p>
            )}
          </>
        )}
      </Card>
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
    </div>
  );
}
