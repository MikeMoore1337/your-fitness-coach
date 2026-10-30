import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api } from '../../shared/api/client';
import type { components } from '../../shared/api/schema';
import { formatCalendarDate } from '../../shared/dateTime';
import { useRuntime } from '../../shared/runtime/runtime';
import { Icon } from '../../shared/ui/Icon';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import './PreviousWorkoutNote.css';

type PreviousNoteResponse = components['schemas']['PreviousWorkoutNoteResponse'];

export function PreviousWorkoutNote({ workoutId }: { workoutId: number }) {
  const { user } = useAuth();
  const runtime = useRuntime();
  const online = useOnlineStatus();
  const previous = useQuery({
    queryKey: ['workout', 'previous-completion-note', user?.id, workoutId],
    queryFn: ({ signal }) =>
      api<PreviousNoteResponse>(`/api/v1/workouts/${workoutId}/previous-completion-note`, {
        signal,
      }),
    enabled: Boolean(user && online && runtime.kind === 'production'),
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchOnReconnect: 'always',
    refetchOnWindowFocus: 'always',
  });
  const note = previous.data?.previous_note;
  if (
    !user ||
    runtime.kind !== 'production' ||
    !online ||
    previous.fetchStatus !== 'idle' ||
    previous.isError ||
    !note
  )
    return null;

  const completedOn = formatCalendarDate(note.completed_on, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).replace(/\s*г\.$/u, '');

  return (
    <details className="previous-workout-note" open>
      <summary className="yfc-disclosure-summary">
        <span className="previous-workout-note__heading">
          <strong>
            {note.is_latest_completion
              ? 'Заметка с прошлого выполнения'
              : 'Последняя сохранённая заметка'}
          </strong>
          <small>
            День {note.day_number} «{note.workout_title}» · {completedOn}
          </small>
        </span>
        <Icon name="chevron-down" size={20} />
      </summary>
      <p>{note.note}</p>
    </details>
  );
}
