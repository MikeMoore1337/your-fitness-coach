import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { YFC_PLATFORM_ACTIVATED_EVENT } from '../../shared/telegram/layout';
import {
  flushExerciseNotes,
  NOTE_QUEUE_EVENT,
  sameNoteIdentity,
  type NoteResponse,
} from './exerciseNoteQueue';

export function useExerciseNoteSync(userId: number | undefined, enabled: boolean): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!userId || !enabled) return;
    let active = true;
    let running = false;
    let rerun = false;
    const run = () => {
      if (!active || !navigator.onLine) return;
      if (running) {
        rerun = true;
        return;
      }
      running = true;
      void flushExerciseNotes(userId, (workoutId, occurrenceId, response) => {
        if (response) {
          queryClient.setQueriesData<NoteResponse>(
            { queryKey: ['exercise-note', userId, workoutId, occurrenceId] },
            (current) => (current && sameNoteIdentity(current, response) ? response : current),
          );
          void queryClient.invalidateQueries({
            queryKey: ['exercise-note', userId, workoutId, occurrenceId],
          });
        } else {
          void queryClient.invalidateQueries({ queryKey: ['exercise-note', userId] });
        }
        void queryClient.invalidateQueries({
          queryKey: ['exercise-note-history', userId, workoutId],
        });
      })
        .catch(() => undefined)
        .finally(() => {
          running = false;
          if (rerun && active) {
            rerun = false;
            run();
          }
        });
    };
    window.addEventListener('online', run);
    window.addEventListener('focus', run);
    window.addEventListener('storage', run);
    window.addEventListener(NOTE_QUEUE_EVENT, run);
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, run);
    run();
    return () => {
      active = false;
      window.removeEventListener('online', run);
      window.removeEventListener('focus', run);
      window.removeEventListener('storage', run);
      window.removeEventListener(NOTE_QUEUE_EVENT, run);
      window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, run);
    };
  }, [enabled, queryClient, userId]);
}
