import { useEffect, useRef, useState } from 'react';
import { ApiError, getUserFacingErrorMessage } from '../../shared/api/client';
import type { Workout } from '../../shared/api/types';
import { hasDecimalScale, parseDecimalDraft } from '../../shared/numeric/decimalDraft';
import { Button } from '../../shared/ui/common';
import { createWorkoutMutationId, type ActiveWorkoutMutation } from './activeWorkoutQueue';
import './WorkoutSetPlanEditor.css';

type Exercise = Workout['exercises'][number];
type WorkoutSet = Exercise['sets'][number];
type Target = { weight_kg: number; reps: number; confirmed: true };

export function WorkoutSetPlanEditor({
  exercise,
  set,
  pendingBySet,
  online,
  ready,
  onClose,
  onApply,
}: {
  exercise: Exercise;
  set: WorkoutSet;
  pendingBySet: Map<number, ActiveWorkoutMutation | undefined>;
  online: boolean;
  ready: boolean;
  onClose: () => void;
  onApply: (setId: number, version: number, mutationId: string, target: Target) => Promise<void>;
}) {
  const [initialVersion] = useState(set.version);
  const heading = useRef<HTMLHeadingElement>(null);
  const segment = exercise.prescription?.segments.find(
    (item) => item.position === (set.planned_position ?? set.set_number),
  );
  const oldWeight = segment?.load_target?.kind === 'absolute' ? segment.load_target.value : null;
  const oldReps = segment?.rep_target?.kind === 'exact' ? segment.rep_target.value : null;
  const [weight, setWeight] = useState(oldWeight == null ? '' : String(oldWeight));
  const [reps, setReps] = useState(oldReps == null ? '' : String(oldReps));
  const [preview, setPreview] = useState<{
    target: Target;
    version: number;
    mutationId: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const parsedWeight = parseDecimalDraft(weight);
  const parsedReps = Number(reps);
  const valid =
    parsedWeight !== null &&
    parsedWeight >= 0 &&
    parsedWeight <= 99999999.99 &&
    hasDecimalScale(weight, 2) &&
    /^\d+$/.test(reps.trim()) &&
    Number.isSafeInteger(parsedReps) &&
    parsedReps >= 1 &&
    parsedReps <= 1000;
  const stale = set.version !== initialVersion;
  useEffect(() => heading.current?.focus(), [preview]);

  const apply = async () => {
    if (!preview || busy || !online || !ready || stale) return;
    setBusy(true);
    setError('');
    try {
      await onApply(set.id, preview.version, preview.mutationId, preview.target);
      onClose();
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 409
          ? 'План или подход уже изменился. Вернитесь к тренировке и проверьте его заново.'
          : getUserFacingErrorMessage(reason, 'Не удалось изменить план подхода.'),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="workout-plan-editor" aria-label="Изменение плана подхода">
      <header className="workout-plan-editor__header">
        <button
          type="button"
          className="workout-plan-editor__back"
          disabled={busy}
          onClick={onClose}
        >
          Назад
        </button>
        <h2 ref={heading} tabIndex={-1}>
          {preview ? 'Проверить подход' : 'Начатая тренировка'}
        </h2>
      </header>
      <div className="workout-plan-editor__panel">
        <h3>{preview ? 'Начатая тренировка' : exercise.exercise_title}</h3>
        <p className="muted">
          {preview
            ? `${exercise.exercise_title} · подход ${set.set_number} · ещё не выполнен`
            : 'Изменение только незавершённого подхода'}
        </p>
        {!preview &&
          exercise.sets
            .filter((item) => pendingBySet.get(item.id)?.values.is_completed ?? item.is_completed)
            .map((item) => {
              const values = pendingBySet.get(item.id)?.values;
              const actualWeight = values?.actual_weight ?? item.actual_weight;
              const actualReps = values?.actual_reps ?? item.actual_reps;
              const actualRir = values?.rir ?? item.rir;
              return (
                <div className="workout-plan-editor__item" key={item.id}>
                  <strong>Подход {item.set_number} · выполнен</strong>
                  <p>
                    {actualWeight ?? '—'} кг · {actualReps ?? '—'} повторов
                    {actualRir ? ` · повторов в запасе: ${actualRir}` : ''}
                  </p>
                </div>
              );
            })}
        {preview ? (
          <>
            <div className="workout-plan-editor__item">
              <strong>Было</strong>
              <p>
                {oldWeight == null ? 'Вес не задан' : `${oldWeight} кг`} ·{' '}
                {oldReps == null
                  ? (exercise.prescribed_reps ?? 'повторы не заданы')
                  : `${oldReps} повторов`}
              </p>
            </div>
            <div className="workout-plan-editor__item">
              <strong>Станет</strong>
              <p>
                {preview.target.weight_kg} кг · {preview.target.reps} повторов
              </p>
            </div>
          </>
        ) : (
          <div className="workout-plan-editor__item">
            <strong>Подход {set.set_number} · ещё не выполнен</strong>
            <div className="workout-plan-editor__fields">
              <label className="field">
                <span>Плановый вес, кг</span>
                <input
                  inputMode="decimal"
                  value={weight}
                  onChange={(event) => setWeight(event.target.value)}
                />
              </label>
              <label className="field">
                <span>План повторов</span>
                <input
                  inputMode="numeric"
                  value={reps}
                  onChange={(event) => setReps(event.target.value)}
                />
              </label>
            </div>
          </div>
        )}
        <div
          className="workout-plan-editor__warning"
          role={!online || !ready ? 'status' : undefined}
        >
          <strong>
            {!online || !ready
              ? 'Дождитесь синхронизации'
              : preview
                ? 'Записанный результат сохранится'
                : 'Ваше подтверждение'}
          </strong>
          <p>
            {!online || !ready
              ? 'Перед изменением плана нужно отправить сохранённые результаты и проверить актуальную версию подхода.'
              : preview
                ? 'Выполненные подходы не изменятся. Подтверждение относится только к выбранному подходу.'
                : 'Изменится только план незавершённого подхода. Записанный результат останется прежним.'}
          </p>
        </div>
        {(error || stale) && (
          <p className="field-error" role="alert">
            {stale ? 'Подход изменился. Вернитесь к тренировке и проверьте его заново.' : error}
          </p>
        )}
        {preview ? (
          <>
            <Button
              fullWidth
              type="button"
              disabled={busy || !online || !ready || stale}
              onClick={() => void apply()}
            >
              {busy ? 'Применяем…' : 'Применить к подходу'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setPreview(null);
                setError('');
              }}
            >
              Вернуться
            </Button>
          </>
        ) : (
          <>
            <Button
              fullWidth
              type="button"
              disabled={!valid || !online || !ready || stale}
              onClick={() => {
                if (parsedWeight === null) return;
                setPreview({
                  target: { weight_kg: parsedWeight, reps: parsedReps, confirmed: true },
                  version: set.version,
                  mutationId: createWorkoutMutationId(),
                });
              }}
            >
              Проверить изменение
            </Button>
            <Button type="button" variant="secondary" onClick={onClose}>
              Оставить как есть
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
