import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type { Workout } from '../../shared/api/types';
import { haptic } from '../../shared/telegram/useTelegram';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { glassProps } from '../../shared/ui/Glass';
import { TaskProgress } from '../../shared/ui/DataViz';
import {
  Badge,
  Button,
  Card,
  CheckIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import {
  activeWorkoutRestKey,
  loadCurrentActiveWorkoutSnapshot,
  type ActiveWorkoutMutation,
  type ActiveWorkoutSetValues,
} from './activeWorkoutQueue';
import { legacyWorkoutRestStorageKey } from '../../shared/userScopedStorage';
import { WorkoutAdaptation } from './WorkoutAdaptation';
import { WorkoutCompletionSummary } from './WorkoutCompletionSummary';
import { reconcileFinishedWorkout } from './finishWorkoutRecovery';
import { useActiveWorkoutQueue } from './useActiveWorkoutQueue';
import { productEventSurface, trackCoreProductEvent } from '../../shared/analytics/productEvents';
import { PWA_SAFE_UPDATE_EVENT } from '../../shared/pwa/pwaRuntime';
import { ProgressionGuidance } from './ProgressionGuidance';

type WorkoutSet = Workout['exercises'][number]['sets'][number];
type RirValue = NonNullable<WorkoutSet['rir']>;
type SetKind = NonNullable<WorkoutSet['set_kind']>;

const rirOptions: readonly { value: RirValue; label: string }[] = [
  { value: '0', label: '0 — больше не смог бы' },
  { value: '1', label: '1 — ещё примерно 1 повтор' },
  { value: '2', label: '2 — ещё примерно 2 повтора' },
  { value: '3', label: '3 — ещё примерно 3 повтора' },
  { value: '4+', label: '4+ — осталось много сил' },
];

export function formatWorkoutDuration(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function shouldCollapseCompletedExercise(
  sets: readonly { id: number; is_completed: boolean }[],
  hasPending: (setId: number) => boolean,
): boolean {
  return sets.length > 0 && sets.every((set) => set.is_completed && !hasPending(set.id));
}

export function formatSetResult(
  reps: number | null | undefined,
  weight: number | null | undefined,
): string | null {
  if (reps == null && weight == null) return null;
  if (weight == null) return `${reps} повт.`;
  if (reps == null) return `${weight} кг`;
  return `${weight} кг × ${reps}`;
}

export function formatCardioResult(
  durationMinutes: number | null | undefined,
  distanceKm: number | null | undefined,
): string | null {
  if (durationMinutes == null && distanceKm == null) return null;
  return [
    durationMinutes == null ? null : `${durationMinutes} мин`,
    distanceKm == null ? null : `${distanceKm} км`,
  ]
    .filter(Boolean)
    .join(' · ');
}

function WorkoutDuration({ startedAt, completedAt }: { startedAt: string; completedAt?: string }) {
  const [now, setNow] = useState(() => Date.now());
  const startTime = new Date(startedAt).getTime();
  const endTime = completedAt ? new Date(completedAt).getTime() : now;
  const elapsedSeconds = Number.isFinite(startTime)
    ? Math.max(0, Math.floor((endTime - startTime) / 1000))
    : 0;

  useEffect(() => {
    if (completedAt) return;
    const update = () => setNow(Date.now());
    const timer = window.setInterval(update, 1000);
    document.addEventListener('visibilitychange', update);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [completedAt]);

  return (
    <span className="active-workout-duration" role="timer" aria-label="Длительность тренировки">
      {formatWorkoutDuration(elapsedSeconds)}
    </span>
  );
}

function WorkoutSetRow({
  set,
  disabled,
  isCurrent,
  previousResult,
  restSeconds,
  workoutId,
  exerciseTitle,
  pending,
  syncing,
  enqueue,
}: {
  set: WorkoutSet;
  disabled: boolean;
  isCurrent: boolean;
  previousResult: string | null;
  restSeconds: number;
  workoutId: number;
  exerciseTitle: string;
  pending?: ActiveWorkoutMutation;
  syncing: boolean;
  enqueue: (
    setId: number,
    serverVersion: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
  ) => void;
}) {
  const [reps, setReps] = useState<string>(
    String(pending?.values.actual_reps ?? set.actual_reps ?? ''),
  );
  const [weight, setWeight] = useState<string>(
    String(pending?.values.actual_weight ?? set.actual_weight ?? ''),
  );
  const [rir, setRir] = useState<RirValue | null>(pending?.values.rir ?? set.rir ?? null);
  const [setKind, setSetKind] = useState<SetKind>(
    pending?.values.set_kind ?? set.set_kind ?? 'working',
  );
  const [reachedFailure, setReachedFailure] = useState(
    pending?.values.reached_failure ?? set.reached_failure ?? false,
  );
  const [completed, setCompleted] = useState(pending?.values.is_completed ?? set.is_completed);
  const [justConfirmed, setJustConfirmed] = useState(false);
  const editing = useRef(false);
  const lastCompletionActionAt = useRef(0);
  const serverVersion = set.version ?? 1;

  const enqueueSave = (
    next: Partial<{
      reps: string;
      weight: string;
      rir: RirValue | null;
      setKind: SetKind;
      reachedFailure: boolean;
      completed: boolean;
    }>,
    immediate = false,
  ) => {
    const nextReps = next.reps ?? reps;
    const nextWeight = next.weight ?? weight;
    const nextRir = next.rir === undefined ? rir : next.rir;
    const nextSetKind = next.setKind ?? setKind;
    const nextReachedFailure = next.reachedFailure ?? reachedFailure;
    const nextCompleted = next.completed ?? completed;
    enqueue(
      set.id,
      serverVersion,
      {
        actual_reps: nextReps === '' ? null : Number(nextReps),
        actual_weight: nextWeight === '' ? null : Number(nextWeight),
        rir: nextRir,
        set_kind: nextSetKind,
        reached_failure: nextReachedFailure,
        is_completed: nextCompleted,
      },
      immediate,
    );
    if (immediate && nextCompleted) {
      haptic('success');
      window.dispatchEvent(
        new CustomEvent('fit:rest', { detail: { workoutId, seconds: restSeconds } }),
      );
    }
  };

  useEffect(() => {
    if (pending) {
      if (editing.current) return;
      setReps(String(pending.values.actual_reps ?? ''));
      setWeight(String(pending.values.actual_weight ?? ''));
      setRir(pending.values.rir ?? set.rir ?? null);
      setSetKind(pending.values.set_kind ?? set.set_kind ?? 'working');
      setReachedFailure(pending.values.reached_failure ?? set.reached_failure ?? false);
      setCompleted(pending.values.is_completed);
    } else {
      if (editing.current) {
        editing.current = false;
        return;
      }
      setReps(String(set.actual_reps ?? ''));
      setWeight(String(set.actual_weight ?? ''));
      setRir(set.rir ?? null);
      setSetKind(set.set_kind ?? 'working');
      setReachedFailure(set.reached_failure ?? false);
      setCompleted(set.is_completed);
    }
  }, [
    pending,
    set.actual_reps,
    set.actual_weight,
    set.is_completed,
    set.reached_failure,
    set.rir,
    set.set_kind,
  ]);

  const classes = [
    'active-workout-set',
    isCurrent ? 'is-current' : '',
    completed ? 'is-completed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={classes}
      data-workout-set-id={set.id}
      data-motion-confirm={justConfirmed || undefined}
      aria-busy={syncing || undefined}
      aria-current={isCurrent ? 'step' : undefined}
      onAnimationEnd={(event) => {
        if (event.animationName === 'active-workout-set-confirm') setJustConfirmed(false);
      }}
    >
      <div className="active-workout-set__head">
        <div className="active-workout-set__identity">
          <span className="active-workout-set__number">{set.set_number}</span>
          <div>
            <strong>{isCurrent ? 'Текущий подход' : `Подход ${set.set_number}`}</strong>
            {isCurrent && <span>Сначала вес, затем повторы</span>}
          </div>
        </div>
        {completed && (
          <span className="active-workout-set__complete-label">
            <CheckIcon /> Выполнен
          </span>
        )}
      </div>

      {isCurrent && previousResult && (
        <p className="active-workout-set__previous">Предыдущий подход: {previousResult}</p>
      )}

      <div className="active-workout-set__controls">
        <label className="active-workout-input">
          <span>Вес, кг</span>
          <input
            disabled={disabled}
            aria-label={`Вес, ${exerciseTitle}, подход ${set.set_number}`}
            enterKeyHint="next"
            inputMode="decimal"
            type="number"
            min="0"
            step="0.5"
            value={weight}
            onChange={(event) => {
              const nextWeight = event.target.value;
              editing.current = true;
              setWeight(nextWeight);
              enqueueSave({ weight: nextWeight });
            }}
          />
        </label>
        <label className="active-workout-input">
          <span>Повторы</span>
          <input
            disabled={disabled}
            aria-label={`Повторы, ${exerciseTitle}, подход ${set.set_number}`}
            enterKeyHint="done"
            inputMode="numeric"
            type="number"
            min="0"
            step="1"
            value={reps}
            onChange={(event) => {
              const nextReps = event.target.value;
              editing.current = true;
              setReps(nextReps);
              enqueueSave({ reps: nextReps });
            }}
          />
        </label>
        <Button
          type="button"
          disabled={disabled}
          aria-label={`${completed ? 'Отметить невыполненным' : 'Завершить'}: ${exerciseTitle}, подход ${set.set_number}`}
          aria-pressed={completed}
          className="active-workout-set__done"
          variant={completed ? 'secondary' : 'primary'}
          onClick={() => {
            const now = Date.now();
            if (now - lastCompletionActionAt.current < 600) return;
            lastCompletionActionAt.current = now;
            const nextCompleted = !completed;
            editing.current = true;
            setCompleted(nextCompleted);
            setJustConfirmed(nextCompleted);
            enqueueSave({ completed: nextCompleted }, true);
          }}
        >
          {completed ? (
            <>
              <CheckIcon /> Готово
            </>
          ) : (
            'Завершить подход'
          )}
        </Button>
      </div>

      <details className="active-workout-set__advanced">
        <summary>Дополнительно</summary>
        <div className="active-workout-set__advanced-body">
          <label className="active-workout-advanced-field">
            <span>Вид подхода</span>
            <select
              disabled={disabled}
              value={setKind}
              onChange={(event) => {
                const nextSetKind = event.target.value as SetKind;
                editing.current = true;
                setSetKind(nextSetKind);
                enqueueSave({ setKind: nextSetKind });
              }}
            >
              <option value="working">Рабочий подход</option>
              <option value="warmup">Разминочный подход</option>
              <option value="drop">Дроп-сет</option>
            </select>
          </label>

          <fieldset className="active-workout-rir">
            <legend>Повторы в запасе</legend>
            <div className="active-workout-rir__options">
              {rirOptions.map((option) => (
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={option.label}
                  aria-pressed={rir === option.value}
                  className={rir === option.value ? 'is-selected' : ''}
                  key={option.value}
                  onClick={() => {
                    const nextRir = rir === option.value ? null : option.value;
                    editing.current = true;
                    setRir(nextRir);
                    enqueueSave({ rir: nextRir });
                  }}
                >
                  {option.value}
                </button>
              ))}
            </div>
            <ContextualHelp articlePath="/knowledge/training/repetitions-in-reserve">
              <p>
                Сколько повторов вы ещё могли бы сделать с хорошей техникой после завершения
                подхода? Поле необязательное.
              </p>
            </ContextualHelp>
          </fieldset>

          <label className="active-workout-failure">
            <input
              type="checkbox"
              disabled={disabled}
              checked={reachedFailure}
              onChange={(event) => {
                const nextReachedFailure = event.target.checked;
                editing.current = true;
                setReachedFailure(nextReachedFailure);
                enqueueSave({ reachedFailure: nextReachedFailure });
              }}
            />
            <span>Подход до отказа</span>
          </label>
          {setKind === 'drop' && (
            <p className="active-workout-advanced-note">
              Дроп-сет — подход со снижением веса без полноценного отдыха.
            </p>
          )}
        </div>
      </details>
    </div>
  );
}

function CardioWorkoutRow({
  set,
  disabled,
  isCurrent,
  previousResult,
  exerciseTitle,
  pending,
  syncing,
  enqueue,
}: {
  set: WorkoutSet;
  disabled: boolean;
  isCurrent: boolean;
  previousResult: string | null;
  exerciseTitle: string;
  pending?: ActiveWorkoutMutation;
  syncing: boolean;
  enqueue: (
    setId: number,
    serverVersion: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
  ) => void;
}) {
  const [duration, setDuration] = useState(
    String(pending?.values.duration_minutes ?? set.duration_minutes ?? ''),
  );
  const [distance, setDistance] = useState(
    String(pending?.values.distance_km ?? set.distance_km ?? ''),
  );
  const [averageHeartRate, setAverageHeartRate] = useState(
    String(pending?.values.average_heart_rate_bpm ?? set.average_heart_rate_bpm ?? ''),
  );
  const [heartRateZone, setHeartRateZone] = useState(
    String(pending?.values.heart_rate_zone ?? set.heart_rate_zone ?? ''),
  );
  const [completed, setCompleted] = useState(pending?.values.is_completed ?? set.is_completed);
  const [validation, setValidation] = useState<string | null>(null);
  const editing = useRef(false);
  const lastCompletionActionAt = useRef(0);
  const serverVersion = set.version ?? 1;

  const enqueueSave = (
    next: Partial<{
      duration: string;
      distance: string;
      averageHeartRate: string;
      heartRateZone: string;
      completed: boolean;
    }>,
    immediate = false,
  ) => {
    const nextDuration = next.duration ?? duration;
    const nextDistance = next.distance ?? distance;
    const nextAverageHeartRate = next.averageHeartRate ?? averageHeartRate;
    const nextHeartRateZone = next.heartRateZone ?? heartRateZone;
    const nextCompleted = next.completed ?? completed;
    enqueue(
      set.id,
      serverVersion,
      {
        actual_reps: null,
        actual_weight: null,
        duration_minutes: nextDuration === '' ? null : Number(nextDuration),
        distance_km: nextDistance === '' ? null : Number(nextDistance),
        average_heart_rate_bpm: nextAverageHeartRate === '' ? null : Number(nextAverageHeartRate),
        heart_rate_zone: nextHeartRateZone === '' ? null : Number(nextHeartRateZone),
        rir: null,
        set_kind: null,
        reached_failure: null,
        is_completed: nextCompleted,
      },
      immediate,
    );
    if (immediate && nextCompleted) haptic('success');
  };

  useEffect(() => {
    if (editing.current) {
      if (!pending) editing.current = false;
      return;
    }
    setDuration(String(pending?.values.duration_minutes ?? set.duration_minutes ?? ''));
    setDistance(String(pending?.values.distance_km ?? set.distance_km ?? ''));
    setAverageHeartRate(
      String(pending?.values.average_heart_rate_bpm ?? set.average_heart_rate_bpm ?? ''),
    );
    setHeartRateZone(String(pending?.values.heart_rate_zone ?? set.heart_rate_zone ?? ''));
    setCompleted(pending?.values.is_completed ?? set.is_completed);
  }, [
    pending,
    set.average_heart_rate_bpm,
    set.distance_km,
    set.duration_minutes,
    set.heart_rate_zone,
    set.is_completed,
  ]);

  const intervalLabel = set.set_number > 1 ? `Интервал ${set.set_number}` : 'Результат кардио';
  return (
    <div
      className={`active-workout-set active-workout-set--cardio ${isCurrent ? 'is-current' : ''} ${completed ? 'is-completed' : ''}`}
      data-workout-set-id={set.id}
      aria-busy={syncing || undefined}
      aria-current={isCurrent ? 'step' : undefined}
    >
      <div className="active-workout-set__head">
        <div className="active-workout-set__identity">
          <div>
            <strong>{isCurrent ? 'Кардио сейчас' : intervalLabel}</strong>
            {isCurrent && <span>Запишите время, затем завершите</span>}
          </div>
        </div>
        {completed && (
          <span className="active-workout-set__complete-label">
            <CheckIcon /> Выполнено
          </span>
        )}
      </div>

      {isCurrent && previousResult && (
        <p className="active-workout-set__previous">Предыдущий интервал: {previousResult}</p>
      )}

      <div className="active-workout-set__controls active-workout-set__controls--cardio">
        <label className="active-workout-input">
          <span>Длительность, мин</span>
          <input
            disabled={disabled}
            aria-label={`Длительность, ${exerciseTitle}`}
            enterKeyHint="next"
            inputMode="numeric"
            type="number"
            min="1"
            max="600"
            step="1"
            value={duration}
            onChange={(event) => {
              editing.current = true;
              setValidation(null);
              setDuration(event.target.value);
              enqueueSave({ duration: event.target.value });
            }}
          />
        </label>
        <label className="active-workout-input">
          <span>Дистанция, км</span>
          <input
            disabled={disabled}
            aria-label={`Дистанция, ${exerciseTitle}`}
            enterKeyHint="done"
            inputMode="decimal"
            type="number"
            min="0.01"
            max="1000"
            step="0.01"
            value={distance}
            onChange={(event) => {
              editing.current = true;
              setDistance(event.target.value);
              enqueueSave({ distance: event.target.value });
            }}
          />
        </label>
        <Button
          type="button"
          disabled={disabled}
          aria-label={`${completed ? 'Отметить кардио незавершённым' : 'Завершить кардио'}: ${exerciseTitle}`}
          aria-pressed={completed}
          className="active-workout-set__done"
          variant={completed ? 'secondary' : 'primary'}
          onClick={() => {
            const now = Date.now();
            if (now - lastCompletionActionAt.current < 600) return;
            lastCompletionActionAt.current = now;
            const nextCompleted = !completed;
            if (nextCompleted && !duration) {
              setValidation('Укажите длительность кардио.');
              return;
            }
            editing.current = true;
            setValidation(null);
            setCompleted(nextCompleted);
            enqueueSave({ completed: nextCompleted }, true);
          }}
        >
          {completed ? (
            <>
              <CheckIcon /> Готово
            </>
          ) : (
            'Завершить кардио'
          )}
        </Button>
      </div>
      {validation && (
        <p className="active-workout-set__validation" role="alert">
          {validation}
        </p>
      )}

      <details className="active-workout-set__advanced">
        <summary>Пульс (необязательно)</summary>
        <div className="active-workout-set__advanced-body active-workout-cardio-advanced">
          <label className="active-workout-advanced-field">
            <span>Средний пульс, уд/мин</span>
            <input
              disabled={disabled}
              inputMode="numeric"
              type="number"
              min="30"
              max="250"
              value={averageHeartRate}
              onChange={(event) => {
                editing.current = true;
                setAverageHeartRate(event.target.value);
                enqueueSave({ averageHeartRate: event.target.value });
              }}
            />
          </label>
          <label className="active-workout-advanced-field">
            <span>Зона пульса</span>
            <select
              disabled={disabled}
              value={heartRateZone}
              onChange={(event) => {
                editing.current = true;
                setHeartRateZone(event.target.value);
                enqueueSave({ heartRateZone: event.target.value });
              }}
            >
              <option value="">Не указана</option>
              {[1, 2, 3, 4, 5].map((zone) => (
                <option value={zone} key={zone}>
                  Зона {zone}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>
    </div>
  );
}

function RestTimer({
  userId,
  workoutId,
  nextLabel,
}: {
  userId: number;
  workoutId: number;
  nextLabel: string;
}) {
  const storageKey = activeWorkoutRestKey(userId, workoutId);
  const legacyStorageKey = legacyWorkoutRestStorageKey(workoutId);
  const [deadline, setDeadline] = useState(() => {
    const scoped = readStorage<number>(storageKey, 0);
    if (scoped) return scoped;
    const legacy = readStorage<number>(legacyStorageKey, 0);
    if (legacy) writeStorage(storageKey, legacy);
    removeStorage(legacyStorageKey);
    return legacy;
  });
  const [now, setNow] = useState(() => Date.now());
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000));
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ workoutId: number; seconds: number }>).detail;
      if (!detail || detail.workoutId !== workoutId) return;
      const nextDeadline = Date.now() + detail.seconds * 1000;
      setNow(Date.now());
      setDeadline(nextDeadline);
      writeStorage(storageKey, nextDeadline);
    };
    window.addEventListener('fit:rest', handler);
    return () => window.removeEventListener('fit:rest', handler);
  }, [storageKey, workoutId]);
  useEffect(() => {
    if (!deadline) return;
    const update = () => {
      const currentTime = Date.now();
      setNow(currentTime);
      if (deadline <= currentTime) {
        removeStorage(storageKey);
        setDeadline(0);
        haptic('success');
      }
    };
    const timer = window.setInterval(update, 1000);
    document.addEventListener('visibilitychange', update);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', update);
    };
  }, [deadline, storageKey]);
  if (!seconds) return null;
  return (
    <aside
      {...glassProps('tinted')}
      className="active-workout-rest"
      role="timer"
      aria-live="polite"
    >
      <div className="active-workout-rest__time">
        <span>Отдых</span>
        <strong>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
        </strong>
      </div>
      <span className="active-workout-rest__next">Дальше: {nextLabel}</span>
      <div className="active-workout-rest__actions">
        <button
          {...glassProps('clear', true)}
          type="button"
          className="secondary"
          onClick={() => {
            const nextDeadline = deadline + 30_000;
            setDeadline(nextDeadline);
            writeStorage(storageKey, nextDeadline);
          }}
        >
          +30 сек
        </button>
        <button
          {...glassProps('clear', true)}
          type="button"
          className="secondary"
          onClick={() => {
            removeStorage(storageKey);
            setDeadline(0);
          }}
        >
          Пропустить
        </button>
      </div>
    </aside>
  );
}

export function TodayWorkout({
  embedded = false,
  onCompletionClose,
}: {
  embedded?: boolean;
  onCompletionClose?: () => void;
}) {
  const { toast, confirm } = useFeedback();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [dismissedGuidance, setDismissedGuidance] = useState<Set<number>>(() => new Set());
  const [expandedCompletedExercises, setExpandedCompletedExercises] = useState<Set<number>>(
    () => new Set(),
  );
  const workout = useQuery({
    queryKey: ['workout', 'today'],
    queryFn: () => api<Workout>('/api/v1/workouts/today'),
    initialData: () => (user ? loadCurrentActiveWorkoutSnapshot(user.id) : undefined),
    initialDataUpdatedAt: 0,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const activeSync = useActiveWorkoutQueue(user?.id, workout.data);
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api<Workout | void>(path, { method, body }),
    onSuccess: async (result, variables) => {
      if (variables.path.endsWith('/finish')) {
        trackCoreProductEvent(
          { name: 'workout_completed', surface: productEventSurface() },
          'workout_completed',
        );
        if (result) await reconcileFinishedWorkout(queryClient, result, activeSync.clear);
        else {
          await activeSync.clear();
          await queryClient.invalidateQueries({ queryKey: ['workout'] });
        }
        window.dispatchEvent(new Event(PWA_SAFE_UPDATE_EVENT));
        haptic('success');
      } else {
        if (variables.path.endsWith('/start')) {
          trackCoreProductEvent(
            { name: 'workout_started', surface: productEventSurface() },
            'workout_started',
          );
        }
        await queryClient.invalidateQueries({ queryKey: ['workout'] });
      }
    },
    onError: (reason) => {
      haptic('error');
      toast((reason as Error).message, 'error');
    },
  });
  const completed = useMemo(
    () =>
      workout.data?.exercises
        .flatMap((item) => item.sets)
        .filter(
          (item) => activeSync.pendingBySet.get(item.id)?.values.is_completed ?? item.is_completed,
        ).length ?? 0,
    [activeSync.pendingBySet, workout.data],
  );
  const total = useMemo(
    () => workout.data?.exercises.flatMap((item) => item.sets).length ?? 0,
    [workout.data],
  );
  const currentSet = (() => {
    if (!workout.data) return null;
    for (const exercise of workout.data.exercises) {
      for (const set of exercise.sets) {
        const isCompleted =
          activeSync.pendingBySet.get(set.id)?.values.is_completed ?? set.is_completed;
        if (!isCompleted) return { exercise, set };
      }
    }
    return null;
  })();
  const currentSetId = currentSet?.set.id;
  const clearActiveState = activeSync.clear;
  const pendingActiveCount = activeSync.pendingCount;

  useEffect(() => {
    if (
      user &&
      pendingActiveCount === 0 &&
      workout.error instanceof ApiError &&
      workout.error.status === 404
    ) {
      const stale = loadCurrentActiveWorkoutSnapshot(user.id);
      if (stale) void clearActiveState();
    }
  }, [clearActiveState, pendingActiveCount, user, workout.error]);

  useEffect(() => {
    if (!currentSetId || completed === 0) return;
    const currentElement = document.querySelector<HTMLElement>(
      `[data-workout-set-id="${currentSetId}"]`,
    );
    if (!currentElement) return;
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    currentElement.scrollIntoView?.({
      behavior: reducedMotion ? 'auto' : 'smooth',
      block: 'nearest',
    });
  }, [completed, currentSetId]);

  if (workout.isLoading)
    return (
      <Card title="Тренировка сегодня">
        <LoadingState />
      </Card>
    );
  if (
    workout.error instanceof ApiError &&
    workout.error.status === 404 &&
    activeSync.pendingCount === 0
  )
    return (
      <Card title="Тренировка сегодня">
        <EmptyState title="Сегодня отдых" text="На сегодня тренировка не назначена." />
      </Card>
    );
  if (
    !workout.data ||
    (workout.error &&
      !(
        workout.error instanceof ApiError &&
        (workout.error.status === 0 ||
          (workout.error.status === 404 && activeSync.pendingCount > 0))
      ))
  )
    return (
      <Card title="Тренировка сегодня">
        <ErrorState
          message={(workout.error as Error)?.message || 'Нет данных'}
          retry={() => void workout.refetch()}
        />
      </Card>
    );

  const data = workout.data;
  const started = data.status === 'in_progress';
  const hasCardio = data.exercises.some((exercise) => exercise.metric_type === 'cardio');
  const nextLabel = currentSet
    ? currentSet.exercise.metric_type === 'cardio'
      ? currentSet.exercise.exercise_title
      : `${currentSet.exercise.exercise_title}, подход ${currentSet.set.set_number}`
    : 'завершить тренировку';
  const syncText =
    activeSync.syncState === 'syncing'
      ? 'Синхронизация…'
      : activeSync.pendingCount > 0
        ? activeSync.syncState === 'offline'
          ? 'Сохранено на устройстве'
          : activeSync.syncState === 'error' || activeSync.syncState === 'conflict'
            ? 'Требуется действие'
            : 'Сохранение…'
        : 'Синхронизировано';
  const syncNeedsAction =
    activeSync.pendingCount > 0 &&
    activeSync.syncState !== 'syncing' &&
    activeSync.syncState !== 'pending';

  if (data.status === 'completed') {
    return <WorkoutCompletionSummary workout={data} onReturnToday={onCompletionClose} />;
  }

  return (
    <>
      <section
        className={`active-workout active-workout--design-v2 ${embedded ? 'is-embedded' : ''}`}
      >
        <header className="active-workout-hero">
          <div className="active-workout-hero__top">
            <div className="active-workout-hero__copy">
              <span className="eyebrow">Тренировка · день {data.day_number}</span>
              <h2>{data.title}</h2>
              <p>
                {data.scheduled_date}
                {data.scheduled_time ? ` · ${data.scheduled_time.slice(0, 5)}` : ''}
                {data.started_at && (
                  <>
                    {' · '}
                    <WorkoutDuration
                      startedAt={data.started_at}
                      completedAt={data.completed_at ?? undefined}
                    />
                  </>
                )}
              </p>
            </div>
            <Badge tone={data.status === 'completed' ? 'success' : 'neutral'}>
              {data.status === 'completed' ? 'Завершена' : started ? 'В процессе' : 'Запланирована'}
            </Badge>
          </div>

          <div className="active-workout-progress">
            <TaskProgress completed={completed} label="Прогресс тренировки" total={total} />
            <div className="active-workout-progress__next" aria-live="polite">
              <span>{currentSet ? 'Сейчас' : 'Следующий шаг'}</span>
              <strong>{nextLabel}</strong>
            </div>
          </div>

          {started && (
            <div
              className={`active-workout-sync is-${activeSync.syncState}`}
              role={syncNeedsAction ? 'alert' : 'status'}
              aria-live="polite"
            >
              <span className="active-workout-sync__dot" aria-hidden="true" />
              <div>
                <strong>{syncText}</strong>
                {activeSync.message && <span>{activeSync.message}</span>}
              </div>
              {syncNeedsAction && navigator.onLine && (
                <button className="secondary" type="button" onClick={() => void activeSync.retry()}>
                  Повторить
                </button>
              )}
            </div>
          )}
        </header>

        {data.status === 'planned' && (
          <Button
            fullWidth
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate({ path: `/api/v1/workouts/${data.id}/start`, method: 'POST' })
            }
          >
            Начать тренировку
          </Button>
        )}

        {(data.status === 'planned' || started) && (
          <WorkoutAdaptation workout={data} safetyOnly={started} />
        )}

        <div className="active-workout-exercises">
          {data.exercises.map((exercise, exerciseIndex) => {
            const metricType = exercise.metric_type === 'cardio' ? 'cardio' : 'strength';
            const exerciseCompleted = exercise.sets.filter(
              (set) => activeSync.pendingBySet.get(set.id)?.values.is_completed ?? set.is_completed,
            ).length;
            const isPersistedComplete = shouldCollapseCompletedExercise(exercise.sets, (setId) =>
              activeSync.pendingBySet.has(setId),
            );
            const exerciseOpen =
              !isPersistedComplete || expandedCompletedExercises.has(exercise.id);
            const isCurrentExercise = currentSet?.exercise.id === exercise.id;
            const supersetLabel = exercise.superset_group
              ? `Суперсет — упражнение ${exercise.superset_order ?? exerciseIndex + 1} из 2`
              : null;
            const suggestedWeight =
              metricType === 'strength'
                ? (exercise.progression_guidance?.suggested_weight ?? null)
                : null;
            const applicableSets = exercise.sets.filter((set) => {
              const pending = activeSync.pendingBySet.get(set.id)?.values;
              const completedSet = pending?.is_completed ?? set.is_completed;
              const kind = pending?.set_kind ?? set.set_kind ?? 'working';
              return !completedSet && kind === 'working';
            });
            const guidanceApplied =
              suggestedWeight != null &&
              applicableSets.length > 0 &&
              applicableSets.every((set) => {
                const pending = activeSync.pendingBySet.get(set.id)?.values;
                return (pending?.actual_weight ?? set.actual_weight) === suggestedWeight;
              });

            return (
              <article
                className={`active-workout-exercise ${isCurrentExercise ? 'is-current' : ''} ${exerciseCompleted === exercise.sets.length ? 'is-completed' : ''} ${supersetLabel ? 'is-superset' : ''}`}
                key={exercise.id}
              >
                <header className="active-workout-exercise__head">
                  <div className="active-workout-exercise__copy">
                    <span className="active-workout-exercise__step">
                      Упражнение {exerciseIndex + 1} из {data.exercises.length}
                    </span>
                    <h3>{exercise.exercise_title}</h3>
                    {metricType === 'cardio' ? (
                      <p>
                        {exercise.prescribed_duration_minutes
                          ? `План: ${exercise.prescribed_duration_minutes} мин`
                          : 'Запишите фактическую длительность'}
                      </p>
                    ) : (
                      <p>
                        {exercise.prescribed_sets} × {exercise.prescribed_reps} · отдых{' '}
                        {exercise.rest_seconds} сек
                      </p>
                    )}
                    {supersetLabel && (
                      <span className="active-workout-superset">{supersetLabel}</span>
                    )}
                    {exercise.notes && <p className="exercise-note">{exercise.notes}</p>}
                  </div>
                  <div className="active-workout-exercise__head-actions">
                    {isPersistedComplete && (
                      <button
                        type="button"
                        className="secondary active-workout-exercise__toggle"
                        aria-expanded={exerciseOpen}
                        aria-controls={`workout-exercise-${exercise.id}-details`}
                        onClick={() =>
                          setExpandedCompletedExercises((current) => {
                            const next = new Set(current);
                            if (next.has(exercise.id)) next.delete(exercise.id);
                            else next.add(exercise.id);
                            return next;
                          })
                        }
                      >
                        {exerciseOpen
                          ? metricType === 'cardio'
                            ? 'Скрыть результат'
                            : 'Скрыть подходы'
                          : metricType === 'cardio'
                            ? 'Кардио сохранено'
                            : `${exerciseCompleted} из ${exercise.sets.length} сохранено`}
                      </button>
                    )}
                    <button
                      type="button"
                      className="exercise-guide-trigger compact"
                      onClick={() =>
                        setGuide({ id: exercise.exercise_id, title: exercise.exercise_title })
                      }
                    >
                      <span>{exercise.has_guide ? 'Техника' : 'Подробнее'}</span>
                    </button>
                  </div>
                </header>

                <div id={`workout-exercise-${exercise.id}-details`} hidden={!exerciseOpen}>
                  {metricType === 'strength' &&
                    exercise.progression_guidance &&
                    !dismissedGuidance.has(exercise.id) && (
                      <ProgressionGuidance
                        applied={guidanceApplied}
                        exerciseKey={exercise.id}
                        guidance={exercise.progression_guidance}
                        onApply={
                          started && suggestedWeight != null && applicableSets.length > 0
                            ? () => {
                                for (const set of applicableSets) {
                                  const pending = activeSync.pendingBySet.get(set.id)?.values;
                                  activeSync.enqueue(set.id, set.version ?? 1, {
                                    actual_reps: pending?.actual_reps ?? set.actual_reps ?? null,
                                    actual_weight: suggestedWeight,
                                    rir: pending?.rir ?? set.rir ?? null,
                                    set_kind: pending?.set_kind ?? set.set_kind ?? 'working',
                                    reached_failure:
                                      pending?.reached_failure ?? set.reached_failure ?? false,
                                    is_completed: pending?.is_completed ?? set.is_completed,
                                  });
                                }
                              }
                            : undefined
                        }
                        onDismiss={() =>
                          setDismissedGuidance((current) => new Set(current).add(exercise.id))
                        }
                      />
                    )}

                  <div className="active-workout-exercise__sets">
                    {exercise.sets.map((set, setIndex) => {
                      const previousSet = setIndex > 0 ? exercise.sets[setIndex - 1] : undefined;
                      const previousPending = previousSet
                        ? activeSync.pendingBySet.get(previousSet.id)
                        : undefined;
                      const previousResult = previousSet
                        ? metricType === 'cardio'
                          ? formatCardioResult(
                              previousPending?.values.duration_minutes ??
                                previousSet.duration_minutes,
                              previousPending?.values.distance_km ?? previousSet.distance_km,
                            )
                          : formatSetResult(
                              previousPending?.values.actual_reps ?? previousSet.actual_reps,
                              previousPending?.values.actual_weight ?? previousSet.actual_weight,
                            )
                        : null;
                      return metricType === 'cardio' ? (
                        <CardioWorkoutRow
                          key={set.id}
                          set={set}
                          disabled={!started}
                          exerciseTitle={exercise.exercise_title}
                          isCurrent={currentSet?.set.id === set.id}
                          previousResult={previousResult}
                          pending={activeSync.pendingBySet.get(set.id)}
                          syncing={activeSync.syncState === 'syncing'}
                          enqueue={activeSync.enqueue}
                        />
                      ) : (
                        <WorkoutSetRow
                          key={set.id}
                          set={set}
                          restSeconds={exercise.rest_seconds}
                          disabled={!started}
                          workoutId={data.id}
                          exerciseTitle={exercise.exercise_title}
                          isCurrent={currentSet?.set.id === set.id}
                          previousResult={previousResult}
                          pending={activeSync.pendingBySet.get(set.id)}
                          syncing={activeSync.syncState === 'syncing'}
                          enqueue={activeSync.enqueue}
                        />
                      );
                    })}
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        {started && (
          <footer className="active-workout-finish">
            <div>
              <strong>{currentSet ? 'Закончить раньше' : 'Тренировка готова'}</strong>
              <span>
                {currentSet
                  ? `${total - completed} ${hasCardio ? 'незаполненных этапов' : 'незаполненных подходов'} останутся в плане без результата.`
                  : hasCardio
                    ? 'Все результаты отмечены — можно завершать.'
                    : 'Все подходы отмечены — можно завершать.'}
              </span>
            </div>
            <Button
              variant={currentSet ? 'secondary' : 'primary'}
              glass={currentSet ? 'regular' : undefined}
              disabled={mutation.isPending}
              onClick={async () => {
                if (!(await activeSync.flushNow())) {
                  haptic('error');
                  toast('Сначала синхронизируйте сохранённые на устройстве подходы.', 'error');
                  return;
                }
                const incomplete = total - completed;
                if (
                  incomplete > 0 &&
                  !(await confirm({
                    title: 'Завершить неполную тренировку?',
                    message: `Не отмечено ${hasCardio ? 'этапов' : 'подходов'}: ${incomplete}. Их можно оставить незаполненными и завершить тренировку.`,
                    confirmText: 'Завершить',
                    danger: false,
                  }))
                )
                  return;
                mutation.mutate({
                  path: `/api/v1/workouts/${data.id}/finish`,
                  method: 'POST',
                  body: incomplete > 0 ? { confirm_incomplete: true } : undefined,
                });
              }}
            >
              Завершить тренировку
            </Button>
          </footer>
        )}

        {data.status !== 'in_progress' && data.status !== 'completed' && (
          <button
            className="active-workout-skip"
            onClick={async () => {
              if (
                await confirm({
                  title: 'Пропустить тренировку?',
                  message:
                    'Она останется в истории как пропущенная. Если хотите выполнить её позже, перенесите дату в разделе «Прогресс».',
                  confirmText: 'Пропустить',
                })
              )
                mutation.mutate({ path: `/api/v1/workouts/${data.id}/skip`, method: 'POST' });
            }}
          >
            Пропустить тренировку
          </button>
        )}
      </section>

      {user && started && <RestTimer userId={user.id} workoutId={data.id} nextLabel={nextLabel} />}
      {guide && (
        <ExerciseGuideDialog
          exerciseId={guide.id}
          exerciseTitle={guide.title}
          onClose={() => setGuide(null)}
        />
      )}
    </>
  );
}
