import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../shared/api/client';
import type {
  BodyMeasurement,
  WeeklyCheckInHistory,
  WorkoutTimelineItem,
} from '../../shared/api/types';
import { formatMeasurementDetail } from './coachMeasurementFacts';
import { queryKeys } from '../../shared/queryKeys';
import { Badge, EmptyState, ErrorState, LoadingState } from '../../shared/ui/common';
import { Icon } from '../../shared/ui/Icon';
import { productEventSurface, trackProductEvent } from '../../shared/analytics/productEvents';

type TimelineEventKind = 'workout' | 'check_in' | 'measurement';

type TimelineEvent = {
  key: string;
  date: string;
  kind: TimelineEventKind;
  title: string;
  detail: string;
  actionLabel: string;
  action: () => void;
};

function formatDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function workoutEventLabel(workout: WorkoutTimelineItem): { title: string; detail: string } {
  if (workout.status === 'completed') {
    return {
      title: 'Тренировка завершена',
      detail: `${workout.title} · ${workout.completed_sets} подходов${workout.completion_note ? ' · есть комментарий клиента' : ''}`,
    };
  }
  if (workout.status === 'skipped') {
    return { title: 'Тренировка пропущена', detail: workout.title };
  }
  if (workout.status === 'missed') {
    return { title: 'Тренировка просрочена', detail: workout.title };
  }
  return { title: 'Тренировка запланирована', detail: workout.title };
}

export function CoachClientTimeline({
  clientId,
  enabled,
  onOpenWorkout,
  onOpenCheckIn,
  onOpenProgress,
}: {
  clientId: number;
  enabled: boolean;
  onOpenWorkout: (workoutId: number) => void;
  onOpenCheckIn: () => void;
  onOpenProgress: () => void;
}) {
  const workouts = useQuery({
    queryKey: queryKeys.trainer.clientWorkouts(clientId),
    queryFn: () =>
      api<WorkoutTimelineItem[]>(`/api/v1/coach/clients/${clientId}/workouts?limit=30`),
    enabled,
    retry: false,
  });
  const checkIns = useQuery({
    queryKey: queryKeys.trainer.clientCheckIns(clientId),
    queryFn: () =>
      api<WeeklyCheckInHistory>(`/api/v1/coach/clients/${clientId}/weekly-check-ins?limit=12`),
    enabled,
    retry: false,
  });
  const measurements = useQuery({
    queryKey: queryKeys.measurements.subject(clientId),
    queryFn: () => api<BodyMeasurement[]>(`/api/v1/coach/clients/${clientId}/measurements`),
    enabled,
    retry: false,
  });

  const events = useMemo<TimelineEvent[]>(() => {
    const workoutEvents = (workouts.data ?? []).map((workout): TimelineEvent => {
      const label = workoutEventLabel(workout);
      return {
        key: `workout:${workout.id}`,
        date: workout.completed_at?.slice(0, 10) ?? workout.scheduled_date,
        kind: 'workout',
        title: label.title,
        detail: label.detail,
        actionLabel: workout.status === 'completed' ? 'Посмотреть' : 'Открыть план',
        action: () => {
          trackProductEvent({
            name: 'coach_timeline_event_opened',
            surface: productEventSurface(),
            kind: 'workout',
          });
          onOpenWorkout(workout.id);
        },
      };
    });
    const checkInEvents = (checkIns.data?.items ?? []).map((checkIn): TimelineEvent => ({
      key: `check-in:${checkIn.id}`,
      date: checkIn.submitted_on,
      kind: 'check_in',
      title:
        checkIn.status === 'completed' ? 'Недельный итог отправлен' : 'Недельный итог пропущен',
      detail: `${formatDate(checkIn.week_start)} — ${formatDate(checkIn.week_end)}`,
      actionLabel: 'Открыть итог',
      action: () => {
        trackProductEvent({
          name: 'coach_timeline_event_opened',
          surface: productEventSurface(),
          kind: 'check_in',
        });
        onOpenCheckIn();
      },
    }));
    const measurementEvents = (measurements.data ?? []).map((measurement): TimelineEvent => ({
      key: `measurement:${measurement.id}`,
      date: measurement.measured_on,
      kind: 'measurement',
      title: 'Замер сохранён',
      detail: formatMeasurementDetail(measurement),
      actionLabel: 'Открыть прогресс',
      action: () => {
        trackProductEvent({
          name: 'coach_timeline_event_opened',
          surface: productEventSurface(),
          kind: 'measurement',
        });
        onOpenProgress();
      },
    }));
    return [...workoutEvents, ...checkInEvents, ...measurementEvents]
      .sort(
        (left, right) => right.date.localeCompare(left.date) || right.key.localeCompare(left.key),
      )
      .slice(0, 30);
  }, [
    checkIns.data?.items,
    measurements.data,
    onOpenCheckIn,
    onOpenProgress,
    onOpenWorkout,
    workouts.data,
  ]);

  if (!enabled) return null;
  const loading = workouts.isLoading || checkIns.isLoading || measurements.isLoading;
  const error = workouts.error || checkIns.error || measurements.error;
  return (
    <section
      className="coach-client-timeline"
      data-testid="coach-client-timeline"
      aria-labelledby="coach-client-timeline-title"
    >
      <div className="coach-os-section-heading">
        <div>
          <span className="eyebrow">Авторитетные события клиента</span>
          <h3 id="coach-client-timeline-title">Лента активности</h3>
        </div>
        {events.length > 0 && <Badge>{events.length}</Badge>}
      </div>
      {loading ? (
        <LoadingState label="Собираем события клиента…" />
      ) : error ? (
        <ErrorState
          message="Лента временно недоступна. Остальные разделы клиента продолжают работать."
          retry={() => {
            void workouts.refetch();
            void checkIns.refetch();
            void measurements.refetch();
          }}
        />
      ) : events.length === 0 ? (
        <EmptyState
          title="Событий пока нет"
          text="Здесь появятся тренировки, итоги и замеры клиента."
        />
      ) : (
        <ol className="coach-client-timeline__list">
          {events.map((event) => (
            <li
              className="coach-client-timeline__item"
              key={event.key}
              data-event-kind={event.kind}
            >
              <div className="coach-client-timeline__marker" aria-hidden="true" />
              <div className="coach-client-timeline__body">
                <div className="coach-client-timeline__meta">
                  <time dateTime={event.date}>{formatDate(event.date)}</time>
                  <Badge tone="neutral">
                    {event.kind === 'workout'
                      ? 'Тренировка'
                      : event.kind === 'check_in'
                        ? 'Итог'
                        : 'Замер'}
                  </Badge>
                </div>
                <strong>{event.title}</strong>
                <p>{event.detail}</p>
                <button type="button" className="text-button" onClick={event.action}>
                  {event.actionLabel} <Icon name="arrow-right" size={16} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
