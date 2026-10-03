import { useEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type { WorkoutScheduleItem } from '../../shared/api/types';
import { formatCalendarDate } from '../../shared/dateTime';
import { workoutStatusLabel } from '../../shared/statusLabels';
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { ProgressExperience } from './ProgressExperience';
import { WeeklyCheckInCard } from './WeeklyCheckInCard';
import { WorkoutFeedbackDisclosure } from './WorkoutFeedback';
import { WorkoutRecovery } from './WorkoutRecovery';

function formatDate(value: string): string {
  return formatCalendarDate(value, {
    day: 'numeric',
    month: 'short',
    weekday: 'short',
  });
}

function ScheduleRow({
  item,
  timeZone,
  focusedCommentId,
  focusedExerciseId,
}: {
  item: WorkoutScheduleItem;
  timeZone?: string | null;
  focusedCommentId?: number | null;
  focusedExerciseId?: number | null;
}) {
  return (
    <article
      className="list-row workout-context-row"
      id={`workout-schedule-${item.id}`}
      tabIndex={-1}
      aria-label={`Тренировка ${item.title} в расписании`}
    >
      <div className="list-row__main">
        <strong>{item.title}</strong>
        <span className="muted">
          {formatDate(item.scheduled_date)}
          {item.scheduled_time ? ` в ${item.scheduled_time.slice(0, 5)}` : ''} · неделя{' '}
          {item.week_number}
        </span>
        <Badge>{workoutStatusLabel(item.status)}</Badge>
      </div>
      {(item.status === 'planned' || item.status === 'missed') && (
        <div className="list-row__actions workout-schedule-actions">
          <WorkoutRecovery
            workout={item}
            timeZone={timeZone}
            triggerLabel={
              item.status === 'missed'
                ? 'Вернуться к тренировке'
                : 'Изменить план'
            }
          />
        </div>
      )}
      <WorkoutFeedbackDisclosure
        workoutId={item.id}
        workoutTitle={item.title}
        workoutDate={item.scheduled_date}
        exercises={[]}
        viewer="client"
        focusedCommentId={focusedCommentId}
        focusedExerciseId={focusedExerciseId}
        defaultOpen={Boolean(focusedCommentId)}
      />
    </article>
  );
}

export function SchedulePanel({
  timeZone,
  focusedWorkoutId,
  focusedCommentId,
  focusedExerciseId,
}: {
  timeZone?: string | null;
  focusedWorkoutId?: number | null;
  focusedCommentId?: number | null;
  focusedExerciseId?: number | null;
}) {
  const schedule = useQuery({
    queryKey: ['workout', 'schedule'],
    queryFn: () => api<WorkoutScheduleItem[]>('/api/v1/workouts/schedule'),
  });
  useEffect(() => {
    if (
      !focusedWorkoutId ||
      !schedule.data?.some((item) => item.id === focusedWorkoutId && item.status !== 'completed')
    )
      return;
    const row = document.getElementById(`workout-schedule-${focusedWorkoutId}`);
    const disclosure = row?.closest<HTMLDetailsElement>('details.card-disclosure');
    if (disclosure) disclosure.open = true;
    row?.focus({ preventScroll: true });
    row?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, [focusedWorkoutId, schedule.data]);

  return (
    <Card title="Расписание" description="Ближайшие восемь недель">
      {schedule.isLoading ? (
        <LoadingState />
      ) : schedule.error ? (
        <ErrorState
          message={(schedule.error as Error).message}
          retry={() => void schedule.refetch()}
        />
      ) : !schedule.data?.length ? (
        <EmptyState title="Активного расписания пока нет" />
      ) : (
        <div className="list-grid top-gap">
          {schedule.data.map((item) => (
            <ScheduleRow
              key={`${item.id}-${item.scheduled_date}-${item.scheduled_time}-${item.status}`}
              item={item}
              timeZone={timeZone}
              focusedCommentId={
                focusedWorkoutId === item.id && item.status !== 'completed'
                  ? focusedCommentId
                  : null
              }
              focusedExerciseId={
                focusedWorkoutId === item.id && item.status !== 'completed'
                  ? focusedExerciseId
                  : null
              }
            />
          ))}
        </div>
      )}
    </Card>
  );
}

export function ProgressSchedule({
  timeZone,
  focusedWorkoutId,
  focusedCommentId,
  focusedExerciseId,
  focusWeeklyReview = false,
  userId = 'anonymous',
  measurementDiary,
}: {
  timeZone?: string | null;
  focusedWorkoutId?: number | null;
  focusedCommentId?: number | null;
  focusedExerciseId?: number | null;
  focusWeeklyReview?: boolean;
  userId?: number | 'anonymous';
  measurementDiary?: ReactNode;
}) {
  return (
    <div className="stack progress-schedule">
      <ProgressExperience measurementDiary={measurementDiary} timeZone={timeZone} />
      <WeeklyCheckInCard autoFocus={focusWeeklyReview} userId={userId} />
      <SchedulePanel
        timeZone={timeZone}
        focusedWorkoutId={focusedWorkoutId}
        focusedCommentId={focusedCommentId}
        focusedExerciseId={focusedExerciseId}
      />
    </div>
  );
}
