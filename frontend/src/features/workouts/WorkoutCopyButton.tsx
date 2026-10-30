import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../../shared/api/client';
import type { Workout, WorkoutCopy } from '../../shared/api/types';
import { Button } from '../../shared/ui/common';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { glassProps } from '../../shared/ui/Glass';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { formatWorkoutCopy } from './workoutCopy';

type Props =
  | { workout: Workout; workoutId?: never; workoutTitle?: never }
  | { workout?: never; workoutId: number; workoutTitle: string };

async function writeText(text: string): Promise<boolean> {
  if (!navigator.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function WorkoutCopyButton({ workout, workoutId, workoutTitle }: Props) {
  const { toast } = useFeedback();
  const [pending, setPending] = useState(false);
  const [manualText, setManualText] = useState<string | null>(null);
  const inFlight = useRef(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useModalA11y<HTMLDivElement>(
    manualText !== null,
    () => setManualText(null),
    '[data-copy-select]',
  );

  const copy = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    try {
      let text: string;
      if (workout) {
        text = formatWorkoutCopy(workout);
      } else {
        const textPromise = api<WorkoutCopy>(`/api/v1/workouts/${workoutId}/copy`).then(
          formatWorkoutCopy,
        );
        if (navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
          const blob = textPromise.then((value) => new Blob([value], { type: 'text/plain' }));
          void blob.catch(() => undefined);
          try {
            await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]);
            await textPromise;
            toast('Тренировка скопирована');
            return;
          } catch {
            // A delayed read may lose clipboard permission; the text is still available below.
          }
        }
        text = await textPromise;
      }
      if (await writeText(text)) toast('Тренировка скопирована');
      else setManualText(text);
    } catch {
      toast('Не удалось загрузить тренировку. Попробуйте ещё раз.', 'error');
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        className={workoutId ? 'top-gap' : undefined}
        disabled={pending}
        aria-label={workoutTitle ? `Скопировать тренировку: ${workoutTitle}` : undefined}
        onClick={() => void copy()}
      >
        {pending ? 'Загружаем…' : 'Скопировать тренировку'}
      </Button>
      {manualText !== null &&
        createPortal(
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workout-copy-title"
            aria-describedby="workout-copy-hint"
          >
            <button
              type="button"
              className="modal__backdrop"
              aria-label="Закрыть"
              onClick={() => setManualText(null)}
            />
            <div
              {...glassProps('tinted')}
              className="modal__panel card"
              ref={panelRef}
              tabIndex={-1}
            >
              <h3 id="workout-copy-title" className="modal__title">
                Скопируйте текст вручную
              </h3>
              <p id="workout-copy-hint" className="modal__body muted">
                Не удалось получить доступ к буферу обмена. Выделите текст и скопируйте его.
              </p>
              <textarea
                ref={textRef}
                aria-label="Текст тренировки"
                rows={8}
                readOnly
                value={manualText}
              />
              <div className="modal__actions toolbar wrap">
                <Button type="button" variant="secondary" onClick={() => setManualText(null)}>
                  Закрыть
                </Button>
                <Button type="button" data-copy-select onClick={() => textRef.current?.select()}>
                  Выделить
                </Button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
