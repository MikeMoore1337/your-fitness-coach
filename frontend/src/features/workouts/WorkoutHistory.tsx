import { useEffect, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  WorkoutHistoryItem,
  WorkoutHistorySummary,
  WorkoutScheduleItem,
} from '../../shared/api/types';
import {
  Badge,
  Card,
  DisclosureIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { workoutStatusLabel } from '../../shared/statusLabels';
import { dateInputValue, detectedTimeZone } from '../../shared/dateTime';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { WorkoutFeedbackDisclosure } from './WorkoutFeedback';
import { workoutCompletionFeedbackLabels } from './WorkoutCompletionSummary';
import { WorkoutCopyButton } from './WorkoutCopyButton';

interface RestHistoryEntry {
  id: number;
  source_set_id: number;
  status: string;
  source: string | null;
  planned_seconds: number;
  adjusted_seconds: number;
  measured_seconds: number | null;
}

function restDuration(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}

function restHistoryLabel(row: RestHistoryEntry): string {
  const original = `План ${restDuration(row.planned_seconds)}`;
  const adjusted =
    row.adjusted_seconds !== row.planned_seconds
      ? ` · цель после +30/+60: ${restDuration(row.adjusted_seconds)}`
      : '';
  const measured = row.status === 'completed' ? row.measured_seconds : null;
  if (measured === null) return `${original}${adjusted} · нет достоверного замера`;
  const delta = measured - row.planned_seconds;
  const corrected = row.source === 'USER_CORRECTED' ? ' · исправлено вручную' : '';
  return `${original}${adjusted} · факт по отметке ${restDuration(measured)} · разница ${delta >= 0 ? '+' : ''}${delta} сек${corrected}`;
}

function RestHistory({ sessions }: { sessions?: RestHistoryEntry[] }) {
  if (!sessions?.length) return <p className="muted">Отдых: нет достоверных замеров.</p>;
  const confirmed = sessions.filter(
    (row) => row.status === 'completed' && row.measured_seconds !== null,
  ).length;
  return (
    <details className="workout-history__rest">
      <summary className="yfc-disclosure-summary">
        Отдых по подходам · {confirmed} замеров
        <Icon name="chevron-down" size={16} />
      </summary>
      <ul>
        {sessions.map((row) => (
          <li key={row.id}>{restHistoryLabel(row)}</li>
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
  compact = false,
  focusedWorkoutId,
  focusedCommentId,
  focusedExerciseId,
  onWorkoutSelect,
  readOnly = false,
  timeZone,
}: {
  compact?: boolean;
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

  const weekCard = (
    <Card
      className={compact ? 'progress-history-week__card' : undefined}
      collapsible={!compact}
      title="Неделя"
    >
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
  );

  return (
    <div className={`stack${compact ? ' workout-history--progress' : ''}`}>
      {compact ? (
        <details className="progress-history-week">
          <summary className="yfc-disclosure-summary">
            <span>
              <small>Контекст недели</small>
              <strong>План и навигация</strong>
            </span>
            <DisclosureIcon />
          </summary>
          {weekCard}
        </details>
      ) : (
        weekCard
      )}
      <Card
        className="workout-history-card"
        collapsible={!compact || Boolean(focusedWorkoutId)}
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
                    {item.adaptations.map((adaptation) => (
                      <p className="workout-history__adaptation" key={adaptation.id}>
                        Изменено перед тренировкой: {adaptationReasonLabels[adaptation.reason]}
                      </p>
                    ))}
                    {!readOnly && (
                      <WorkoutCopyButton workoutId={item.id} workoutTitle={item.title} />
                    )}
                    {(item.completion_feedback || item.completion_note) && (
                      <div className={`workout-completion-context${readOnly ? '' : ' top-gap'}`}>
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
                className="secondary"
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
