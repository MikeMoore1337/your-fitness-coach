import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type { ExerciseHistory, Workout, WorkoutScheduleItem } from '../../shared/api/types';
import { haptic } from '../../shared/telegram/useTelegram';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { Icon } from '../../shared/ui/Icon';
import { glassProps } from '../../shared/ui/Glass';
import { TaskProgress } from '../../shared/ui/DataViz';
import {
  DisclosureIcon,
  Badge,
  Button,
  Card,
  CheckIcon,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { removeStorage, writeStorage } from '../../shared/storage';
import { ExerciseGuideDialog } from '../exercises/ExerciseGuideDialog';
import { ExerciseMediaAsset } from '../exercises/ExerciseMediaAsset';
import {
  activeWorkoutRestKey,
  loadCurrentActiveWorkoutSnapshot,
  type ActiveWorkoutMutation,
  type ActiveWorkoutSetValues,
} from './activeWorkoutQueue';
import { legacyWorkoutRestStorageKey } from '../../shared/userScopedStorage';
import {
  acknowledgeRestPlan,
  activeRestJournalSession,
  beginMeasuredRest,
  loadRestJournal,
  listenToRestJournal,
  markRestBackground,
  recoverRestAfterAbsence,
  syncRestJournal,
  updateMeasuredRest,
} from './restSessions';
import { hasWorkoutExecutionEvidence, WorkoutAdaptation } from './WorkoutAdaptation';
import { WorkoutCompletionSummary } from './WorkoutCompletionSummary';
import { WorkoutRecovery } from './WorkoutRecovery';
import { reconcileFinishedWorkout } from './finishWorkoutRecovery';
import { useActiveWorkoutQueue } from './useActiveWorkoutQueue';
import { useRuntimeCapabilities } from '../../shared/runtime/runtime';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import { PWA_SAFE_UPDATE_EVENT } from '../../shared/pwa/pwaRuntime';
import { ProgressionGuidance } from './ProgressionGuidance';
import { useScreenWakeLock } from './useScreenWakeLock';
import { AiCoachContextualEntry } from '../ai/AiCoachContextualEntry';
import { WarmupProposal } from './WarmupProposal';
import { PlateCalculator } from './PlateCalculator';
import { ExerciseSetupMemory } from './ExerciseSetupMemory';
import { ActiveSessionSummary } from './ActiveSessionSummary';

type WorkoutSet = Workout['exercises'][number]['sets'][number];
type RirValue = NonNullable<WorkoutSet['rir']>;
type SetKind = NonNullable<WorkoutSet['set_kind']>;
type PlannedRole = NonNullable<WorkoutSet['planned_role']>;
type PlannedGroupKind = NonNullable<WorkoutSet['planned_group_kind']>;
type PreviousSetValues = {
  actual_reps: number | null | undefined;
  actual_weight: number | null | undefined;
  duration_minutes: number | null | undefined;
  distance_km: number | null | undefined;
};
type PreviousSetSource = Pick<
  WorkoutSet,
  'actual_reps' | 'actual_weight' | 'duration_minutes' | 'distance_km'
>;

export function resolvePreviousSetValues(
  set: PreviousSetSource,
  pending?: Pick<ActiveWorkoutMutation, 'values'>,
): PreviousSetValues {
  if (pending) {
    return {
      actual_reps: pending.values.actual_reps,
      actual_weight: pending.values.actual_weight,
      duration_minutes: pending.values.duration_minutes,
      distance_km: pending.values.distance_km,
    };
  }
  return {
    actual_reps: set.actual_reps,
    actual_weight: set.actual_weight,
    duration_minutes: set.duration_minutes,
    distance_km: set.distance_km,
  };
}

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

const plannedRoleLabels: Record<PlannedRole, string> = {
  warmup: 'Разминка',
  working: 'Рабочий подход',
  top: 'Тяжёлый подход',
  backoff: 'Облегчённый подход',
  drop: 'Подход со снижением веса',
  activation: 'Активация',
  mini_set: 'Мини-сет',
  cluster_member: 'Кластерный мини-сет',
};

const plannedGroupKindLabels: Record<PlannedGroupKind, string> = {
  sequence: 'Последовательность',
  superset: 'Суперсет',
  rest_pause: 'Rest-pause',
  myo_reps: 'Myo-reps',
  cluster: 'Кластер',
  drop_chain: 'Подход со снижением веса',
  circuit: 'Круг',
};

export function formatPlannedSetRole(role: WorkoutSet['planned_role']): string | null {
  return role ? plannedRoleLabels[role] : null;
}

export function formatPlannedGroupKind(kind: WorkoutSet['planned_group_kind']): string | null {
  return kind ? plannedGroupKindLabels[kind] : null;
}

function focusWorkoutControl(row: HTMLDivElement | null, field: 'reps' | 'distance' | 'done') {
  const control = row?.querySelector<HTMLElement>(`[data-workout-field="${field}"]`);
  control?.focus();
}

function editingWorkoutField(): boolean {
  return (
    document.activeElement?.matches(
      '.active-workout-set input, .active-workout-set select, .active-workout-set textarea',
    ) ?? false
  );
}

function formatWorkoutNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
}

function RirContextualHelp() {
  return (
    <ContextualHelp
      articlePath="/knowledge/training/repetitions-in-reserve"
      summary="Что такое RIR?"
    >
      <p>
        Повторы в запасе — субъективная оценка того, сколько качественных повторов вы ещё могли бы
        выполнить после подхода. Поле необязательное: отсутствие оценки не равно нулю.
      </p>
    </ContextualHelp>
  );
}

function RirSelector({
  compact = false,
  disabled,
  value,
  onChange,
}: {
  compact?: boolean;
  disabled: boolean;
  value: RirValue | null;
  onChange: (value: RirValue | null) => void;
}) {
  return (
    <fieldset className={`active-workout-rir${compact ? ' active-workout-rir--quick' : ''}`}>
      <legend>{compact ? 'Повторы в запасе (RIR)' : 'Повторы в запасе'}</legend>
      <div className="active-workout-rir__options">
        {rirOptions.map((option) => (
          <button
            type="button"
            disabled={disabled}
            aria-label={option.label}
            aria-pressed={value === option.value}
            data-yfc-choice="compact"
            className={value === option.value ? 'is-selected' : ''}
            key={option.value}
            onClick={() => onChange(value === option.value ? null : option.value)}
          >
            {option.value}
          </button>
        ))}
      </div>
      {!compact && <RirContextualHelp />}
    </fieldset>
  );
}

function WorkoutSetHelpers({
  disabled,
  weight,
  workoutId,
  workoutExerciseId,
  targetSetId,
  exerciseTitle,
  hasWarmupRows,
}: {
  disabled: boolean;
  weight: string;
  workoutId: number;
  workoutExerciseId: number;
  targetSetId: number;
  exerciseTitle: string;
  hasWarmupRows: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className="active-workout-set__helpers"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="yfc-disclosure-summary">
        Разминка и блины
        <DisclosureIcon />
      </summary>
      <div className="active-workout-set__helpers-body">
        <div className="active-workout-helper-block">
          <div>
            <strong>Разминочные подходы</strong>
            <p>Расчёт от рабочего веса. Вы сможете изменить предложение перед добавлением.</p>
          </div>
          <WarmupProposal
            disabled={disabled}
            exerciseTitle={exerciseTitle}
            hasWarmupRows={hasWarmupRows}
            targetSetId={targetSetId}
            workoutExerciseId={workoutExerciseId}
            workoutId={workoutId}
            workingWeight={weight}
          />
        </div>

        <div className="active-workout-helper-block">
          <div>
            <strong>Блины на сторону</strong>
            <p>Подберите доступные блины для целевого веса; журнал и прогресс не меняются.</p>
          </div>
          <PlateCalculator disabled={disabled} initialTargetWeight={weight} />
        </div>
      </div>
    </details>
  );
}

function ExerciseHistoryContext({ exerciseId, enabled }: { exerciseId: number; enabled: boolean }) {
  const history = useQuery({
    queryKey: ['workout', 'exercise-history', exerciseId],
    queryFn: () => api<ExerciseHistory>(`/api/v1/programs/exercises/${exerciseId}/history`),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
  if (!enabled || history.isError) return null;
  if (history.isPending) {
    return (
      <p className="active-workout-history active-workout-history--loading" role="status">
        Загружаем последний результат…
      </p>
    );
  }
  const session = history.data?.recent_sessions?.[0];
  const result = session?.sets.find(
    (set) => set.pr_eligible && (set.load_kg != null || set.reps != null),
  );
  const estimated = history.data?.estimated_1rm;
  if (!result && !estimated) return null;
  return (
    <aside className="active-workout-history" aria-label="Контекст упражнения">
      <div>
        <span>Последний рабочий результат</span>
        <strong>
          {result ? formatSetResult(result.reps, result.load_kg) : 'Нет рабочего подхода'}
        </strong>
      </div>
      {estimated && (
        <div>
          <span>Расчётный максимум на 1 повтор</span>
          <strong>{formatWorkoutNumber(estimated.value_kg)} кг</strong>
        </div>
      )}
    </aside>
  );
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

type CompletedStrengthDraft = {
  reps: string;
  weight: string;
  rir: RirValue | null;
  setKind: SetKind;
  reachedFailure: boolean;
};

function WorkoutSetRow({
  set,
  setPosition,
  setTotal,
  prescribedReps,
  disabled,
  isCurrent,
  previousResult,
  previousValues,
  restSeconds,
  userId,
  workoutId,
  workoutExerciseId,
  exerciseTitle,
  hasWarmupRows,
  pending,
  durable,
  syncing,
  syncFailed,
  enqueue,
}: {
  set: WorkoutSet;
  setPosition: number;
  setTotal: number;
  prescribedReps: string | null;
  disabled: boolean;
  isCurrent: boolean;
  previousResult: string | null;
  previousValues?: PreviousSetValues;
  restSeconds: number;
  userId?: number;
  workoutId: number;
  workoutExerciseId: number;
  exerciseTitle: string;
  hasWarmupRows: boolean;
  pending?: ActiveWorkoutMutation;
  durable: boolean;
  syncing: boolean;
  syncFailed: boolean;
  enqueue: (
    setId: number,
    serverVersion: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
    completing?: boolean,
  ) => Promise<boolean>;
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
  const completed = pending?.values.is_completed ?? set.is_completed;
  const { confirm } = useFeedback();
  const [editingCompleted, setEditingCompleted] = useState(false);
  const editingCompletedSnapshot = useRef<CompletedStrengthDraft | null>(null);
  const [completing, setCompleting] = useState(false);
  const completionInFlight = useRef(false);
  const reopenInFlight = useRef(false);
  const retryCompletion = syncFailed && pending?.values.is_completed;
  const [justConfirmed, setJustConfirmed] = useState(false);
  const editing = useRef(false);
  const rowRef = useRef<HTMLDivElement | null>(null);
  const serverVersion = set.version ?? 1;
  const canPrefillReps = reps === '' && previousValues?.actual_reps != null;
  const canPrefillWeight = weight === '' && previousValues?.actual_weight != null;
  const [prefillDismissed, setPrefillDismissed] = useState(false);
  const canPrefill =
    isCurrent &&
    !disabled &&
    !completed &&
    previousResult !== null &&
    !prefillDismissed &&
    (canPrefillReps || canPrefillWeight);
  const prefillSpaceReserved =
    prefillDismissed && isCurrent && !disabled && !completed && previousResult !== null;
  const completedFieldsDisabled = disabled || completing || (completed && !editingCompleted);

  const canStartRest = (nextSetKind: SetKind, nextCompleted: boolean) =>
    nextCompleted &&
    nextSetKind === 'working' &&
    set.planned_role !== 'warmup' &&
    set.planned_role !== 'activation';

  const enqueueSave = async (
    next: Partial<{
      reps: string;
      weight: string;
      rir: RirValue | null;
      setKind: SetKind;
      reachedFailure: boolean;
      completed: boolean;
    }>,
    immediate = false,
    startRest = immediate,
  ) => {
    if (completionInFlight.current) return false;
    if (immediate) {
      completionInFlight.current = true;
      setCompleting(true);
    }
    const nextReps = next.reps ?? reps;
    const nextWeight = next.weight ?? weight;
    const nextRir = next.rir === undefined ? rir : next.rir;
    const nextSetKind = next.setKind ?? setKind;
    const nextReachedFailure = next.reachedFailure ?? reachedFailure;
    const nextCompleted = next.completed ?? completed;
    try {
      const accepted = await enqueue(
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
        immediate && startRest && nextCompleted,
      );
      if (accepted && immediate && startRest && nextCompleted) {
        haptic('success');
        setJustConfirmed(true);
      }
      if (accepted && immediate && startRest && canStartRest(nextSetKind, nextCompleted)) {
        // Persist measured rest before the UI event so freeze/resume cannot leave a bare deadline.
        const started = userId
          ? beginMeasuredRest(userId, workoutId, set.id, restSeconds, Date.now())
          : null;
        if (started) {
          window.dispatchEvent(
            new CustomEvent('fit:rest', {
              detail: {
                workoutId,
                setId: set.id,
                seconds: restSeconds,
                deadline: started.deadline,
              },
            }),
          );
        }
      }
      return accepted;
    } finally {
      if (immediate) {
        completionInFlight.current = false;
        setCompleting(false);
      }
    }
  };

  const beginEditingCompleted = () => {
    if (disabled || completing || !completed) return;
    editingCompletedSnapshot.current = {
      reps,
      weight,
      rir,
      setKind,
      reachedFailure,
    };
    editing.current = true;
    setEditingCompleted(true);
  };

  const cancelEditingCompleted = () => {
    const snapshot = editingCompletedSnapshot.current;
    if (snapshot) {
      setReps(snapshot.reps);
      setWeight(snapshot.weight);
      setRir(snapshot.rir);
      setSetKind(snapshot.setKind);
      setReachedFailure(snapshot.reachedFailure);
    }
    editing.current = false;
    editingCompletedSnapshot.current = null;
    setEditingCompleted(false);
  };

  const saveCompletedEdits = async () => {
    if (disabled || completing || !editingCompleted || !completed) return;
    editing.current = true;
    const accepted = await enqueueSave(
      {
        reps,
        weight,
        rir,
        setKind,
        reachedFailure,
        completed: true,
      },
      true,
      false,
    );
    if (accepted) {
      editingCompletedSnapshot.current = null;
      setEditingCompleted(false);
    }
  };

  const requestReopen = async () => {
    if (disabled || completing || reopenInFlight.current || !completed) return;
    reopenInFlight.current = true;
    try {
      const approved = await confirm({
        title: 'Вернуть подход в работу?',
        message: `Вернуть подход ${set.set_number} в работу? Статус изменится на „Не завершён“. Сохранённые результаты останутся.`,
        confirmText: 'Вернуть в работу',
        danger: false,
      });
      if (!approved) return;
      editing.current = true;
      const accepted = await enqueueSave({ completed: false }, true, false);
      if (accepted) {
        editingCompletedSnapshot.current = null;
        setEditingCompleted(false);
      }
    } finally {
      reopenInFlight.current = false;
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
  const plannedRoleLabel = formatPlannedSetRole(set.planned_role);
  const plannedGroupLabel = formatPlannedGroupKind(set.planned_group_kind);

  return (
    <div
      ref={rowRef}
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
            <strong>
              {isCurrent ? `Подход ${setPosition} из ${setTotal}` : `Подход ${set.set_number}`}
            </strong>
            {isCurrent && <span>Сначала вес, затем повторы</span>}
          </div>
        </div>
        {(plannedRoleLabel || plannedGroupLabel) && (
          <div className="active-workout-set__roles" aria-label="Структура подхода">
            {plannedRoleLabel && (
              <span className="active-workout-set__role">{plannedRoleLabel}</span>
            )}
            {plannedGroupLabel && (
              <span className="active-workout-set__role active-workout-set__role--group">
                {plannedGroupLabel}
              </span>
            )}
          </div>
        )}
        {completed && (
          <span className="active-workout-set__complete-label">
            {(!pending || durable) && <CheckIcon />}
            {pending ? (durable ? 'Сохранено на устройстве' : 'Не сохранено') : 'Выполнен'}
          </span>
        )}
      </div>

      {completed && (
        <div
          className="active-workout-set__completed-actions app-action-group"
          aria-label="Действия с выполненным подходом"
        >
          {editingCompleted ? (
            <>
              <Button
                type="button"
                disabled={disabled || completing}
                data-workout-action="cancel-edit-completed"
                variant="ghost"
                onClick={cancelEditingCompleted}
              >
                Отмена
              </Button>
              <Button
                type="button"
                disabled={disabled || completing}
                data-workout-action="save-edit-completed"
                variant="secondary"
                onClick={() => void saveCompletedEdits()}
              >
                Сохранить
              </Button>
            </>
          ) : (
            <Button
              type="button"
              disabled={disabled || completing}
              data-workout-action="edit-completed"
              variant="ghost"
              onClick={beginEditingCompleted}
            >
              Редактировать
            </Button>
          )}
          {!editingCompleted && (
            <details className="active-workout-set__more-actions">
              <summary className="yfc-disclosure-summary">
                Действия
                <DisclosureIcon />
              </summary>
              <div className="active-workout-set__more-actions-body">
                <Button
                  type="button"
                  disabled={disabled || completing}
                  data-workout-action="reopen-completed"
                  variant="secondary"
                  onClick={() => void requestReopen()}
                >
                  Вернуть в работу
                </Button>
              </div>
            </details>
          )}
        </div>
      )}

      {isCurrent && previousResult && (
        <p className="active-workout-set__previous">Предыдущий подход: {previousResult}</p>
      )}
      {(canPrefill || prefillSpaceReserved) && (
        <div
          className={`active-workout-set__prefill-actions${prefillSpaceReserved ? ' is-hidden' : ''}`}
          aria-hidden={prefillSpaceReserved || undefined}
        >
          <button
            className="active-workout-set__prefill"
            disabled={completing}
            type="button"
            onClick={() => {
              const nextReps = canPrefillReps ? String(previousValues?.actual_reps) : reps;
              const nextWeight = canPrefillWeight ? String(previousValues?.actual_weight) : weight;
              setPrefillDismissed(nextReps !== '' && nextWeight !== '');
              editing.current = true;
              setReps(nextReps);
              setWeight(nextWeight);
              trackProductEvent({
                name: 'previous_set_reuse_used',
                surface: productEventSurface(),
              });
            }}
          >
            Подставить предыдущий результат
          </button>
          <button
            className="active-workout-set__prefill active-workout-set__prefill--commit"
            disabled={completing}
            type="button"
            onClick={() => {
              const nextReps = canPrefillReps ? String(previousValues?.actual_reps) : reps;
              const nextWeight = canPrefillWeight ? String(previousValues?.actual_weight) : weight;
              setPrefillDismissed(nextReps !== '' && nextWeight !== '');
              editing.current = true;
              setReps(nextReps);
              setWeight(nextWeight);
              enqueueSave({ reps: nextReps, weight: nextWeight, completed: true }, true);
              trackProductEvent({
                name: 'previous_set_reuse_used',
                surface: productEventSurface(),
              });
            }}
          >
            Подставить и завершить
          </button>
        </div>
      )}

      {isCurrent && (
        <p className="active-workout-set__context">
          <span>{prescribedReps ? `${prescribedReps} повторений` : 'Повторы по плану'}</span>
          <span aria-hidden="true">·</span>
          <span>Отдых {restSeconds} с</span>
        </p>
      )}

      {isCurrent && (
        <RirSelector
          compact
          disabled={completedFieldsDisabled}
          value={rir}
          onChange={(nextRir) => {
            editing.current = true;
            setRir(nextRir);
            if (!editingCompleted) enqueueSave({ rir: nextRir });
          }}
        />
      )}

      <div className="active-workout-set__controls">
        <label className="active-workout-input">
          <span>Вес, кг</span>
          <input
            data-workout-field="weight"
            disabled={completedFieldsDisabled}
            aria-label={`Вес, ${exerciseTitle}, подход ${set.set_number}`}
            enterKeyHint="next"
            inputMode="decimal"
            type="number"
            min="0"
            step="0.5"
            value={weight}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                focusWorkoutControl(rowRef.current, 'reps');
              }
            }}
            onChange={(event) => {
              const nextWeight = event.target.value;
              editing.current = true;
              setPrefillDismissed(nextWeight !== '' && reps !== '');
              setWeight(nextWeight);
              if (!editingCompleted) enqueueSave({ weight: nextWeight });
            }}
          />
        </label>
        <label className="active-workout-input">
          <span>Повторы</span>
          <input
            data-workout-field="reps"
            disabled={completedFieldsDisabled}
            aria-label={`Повторы, ${exerciseTitle}, подход ${set.set_number}`}
            enterKeyHint="done"
            inputMode="numeric"
            type="number"
            min="0"
            step="1"
            value={reps}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                focusWorkoutControl(rowRef.current, 'done');
              }
            }}
            onChange={(event) => {
              const nextReps = event.target.value;
              editing.current = true;
              setPrefillDismissed(nextReps !== '' && weight !== '');
              setReps(nextReps);
              if (!editingCompleted) enqueueSave({ reps: nextReps });
            }}
          />
        </label>
        <Button
          type="button"
          disabled={disabled || completing || (completed && !retryCompletion)}
          aria-busy={completing || undefined}
          aria-label={`${completing ? 'Сохраняем…' : retryCompletion ? 'Повторить сохранение' : completed ? 'Выполнен' : 'Завершить'}: ${exerciseTitle}, подход ${set.set_number}`}
          aria-pressed={completed}
          className="active-workout-set__done"
          data-workout-field="done"
          variant={completed ? 'secondary' : 'primary'}
          onClick={(event) => {
            if (event.detail > 1) return;
            const nextCompleted = retryCompletion || !completed;
            editing.current = true;
            enqueueSave({ completed: nextCompleted }, true);
          }}
        >
          {completing ? (
            'Сохраняем…'
          ) : retryCompletion ? (
            'Повторить сохранение'
          ) : completed ? (
            <>
              <CheckIcon /> Готово
            </>
          ) : (
            'Завершить подход'
          )}
        </Button>
      </div>

      {isCurrent && (
        <div className="active-workout-set__contextual-help">
          <RirContextualHelp />
        </div>
      )}

      {isCurrent && set.set_kind !== 'warmup' && set.planned_role !== 'warmup' && (
        <WorkoutSetHelpers
          disabled={disabled || completing}
          exerciseTitle={exerciseTitle}
          hasWarmupRows={hasWarmupRows}
          targetSetId={set.id}
          weight={weight}
          workoutExerciseId={workoutExerciseId}
          workoutId={workoutId}
        />
      )}

      <details className="active-workout-set__advanced">
        <summary className="yfc-disclosure-summary">
          Дополнительно
          <DisclosureIcon />
        </summary>
        <div className="active-workout-set__advanced-body">
          <label className="active-workout-advanced-field">
            <span>Вид подхода</span>
            <select
              disabled={completedFieldsDisabled}
              value={setKind}
              onChange={(event) => {
                const nextSetKind = event.target.value as SetKind;
                editing.current = true;
                setSetKind(nextSetKind);
                if (!editingCompleted) enqueueSave({ setKind: nextSetKind });
              }}
            >
              <option value="working">Рабочий подход</option>
              <option value="warmup">Разминочный подход</option>
              <option value="drop">Подход со снижением веса</option>
            </select>
          </label>

          {!isCurrent && (
            <RirSelector
              disabled={completedFieldsDisabled}
              value={rir}
              onChange={(nextRir) => {
                editing.current = true;
                setRir(nextRir);
                if (!editingCompleted) enqueueSave({ rir: nextRir });
              }}
            />
          )}

          <label className="active-workout-failure">
            <input
              type="checkbox"
              disabled={completedFieldsDisabled}
              checked={reachedFailure}
              onChange={(event) => {
                const nextReachedFailure = event.target.checked;
                editing.current = true;
                setReachedFailure(nextReachedFailure);
                if (!editingCompleted) enqueueSave({ reachedFailure: nextReachedFailure });
              }}
            />
            <span>Подход до отказа</span>
          </label>
          {setKind === 'drop' && (
            <p className="active-workout-advanced-note">
              Подход со снижением веса — дополнительный подход с уменьшенной нагрузкой без
              полноценного отдыха.
            </p>
          )}
        </div>
      </details>
    </div>
  );
}

type CompletedCardioDraft = {
  duration: string;
  distance: string;
  averageHeartRate: string;
  heartRateZone: string;
};

function CardioWorkoutRow({
  set,
  disabled,
  isCurrent,
  previousResult,
  previousValues,
  exerciseTitle,
  pending,
  durable,
  syncing,
  syncFailed,
  enqueue,
}: {
  set: WorkoutSet;
  disabled: boolean;
  isCurrent: boolean;
  previousResult: string | null;
  previousValues?: PreviousSetValues;
  exerciseTitle: string;
  pending?: ActiveWorkoutMutation;
  durable: boolean;
  syncing: boolean;
  syncFailed: boolean;
  enqueue: (
    setId: number,
    serverVersion: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
    completing?: boolean,
  ) => Promise<boolean>;
}) {
  const [duration, setDuration] = useState(
    String(pending ? (pending.values.duration_minutes ?? '') : (set.duration_minutes ?? '')),
  );
  const [distance, setDistance] = useState(
    String(pending ? (pending.values.distance_km ?? '') : (set.distance_km ?? '')),
  );
  const [averageHeartRate, setAverageHeartRate] = useState(
    String(
      pending ? (pending.values.average_heart_rate_bpm ?? '') : (set.average_heart_rate_bpm ?? ''),
    ),
  );
  const [heartRateZone, setHeartRateZone] = useState(
    String(pending ? (pending.values.heart_rate_zone ?? '') : (set.heart_rate_zone ?? '')),
  );
  const completed = pending?.values.is_completed ?? set.is_completed;
  const { confirm } = useFeedback();
  const [editingCompleted, setEditingCompleted] = useState(false);
  const editingCompletedSnapshot = useRef<CompletedCardioDraft | null>(null);
  const [completing, setCompleting] = useState(false);
  const completionInFlight = useRef(false);
  const reopenInFlight = useRef(false);
  const retryCompletion = syncFailed && pending?.values.is_completed;
  const [validation, setValidation] = useState<string | null>(null);
  const editing = useRef(false);
  const rowRef = useRef<HTMLDivElement | null>(null);
  const serverVersion = set.version ?? 1;
  const canPrefillDuration = duration === '' && previousValues?.duration_minutes != null;
  const canPrefillDistance = distance === '' && previousValues?.distance_km != null;
  const canPrefill =
    isCurrent &&
    !disabled &&
    !completed &&
    previousResult !== null &&
    (canPrefillDuration || canPrefillDistance);
  const completedFieldsDisabled = disabled || completing || (completed && !editingCompleted);

  const enqueueSave = async (
    next: Partial<{
      duration: string;
      distance: string;
      averageHeartRate: string;
      heartRateZone: string;
      completed: boolean;
    }>,
    immediate = false,
    startRest = immediate,
  ) => {
    if (completionInFlight.current) return false;
    if (immediate) {
      completionInFlight.current = true;
      setCompleting(true);
    }
    const nextDuration = next.duration ?? duration;
    const nextDistance = next.distance ?? distance;
    const nextAverageHeartRate = next.averageHeartRate ?? averageHeartRate;
    const nextHeartRateZone = next.heartRateZone ?? heartRateZone;
    const nextCompleted = next.completed ?? completed;
    try {
      const accepted = await enqueue(
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
        immediate && startRest && nextCompleted,
      );
      if (accepted && immediate && startRest && nextCompleted) haptic('success');
      return accepted;
    } finally {
      if (immediate) {
        completionInFlight.current = false;
        setCompleting(false);
      }
    }
  };

  const beginEditingCompleted = () => {
    if (disabled || completing || !completed) return;
    editingCompletedSnapshot.current = {
      duration,
      distance,
      averageHeartRate,
      heartRateZone,
    };
    editing.current = true;
    setEditingCompleted(true);
  };

  const cancelEditingCompleted = () => {
    const snapshot = editingCompletedSnapshot.current;
    if (snapshot) {
      setDuration(snapshot.duration);
      setDistance(snapshot.distance);
      setAverageHeartRate(snapshot.averageHeartRate);
      setHeartRateZone(snapshot.heartRateZone);
    }
    editing.current = false;
    editingCompletedSnapshot.current = null;
    setEditingCompleted(false);
  };

  const saveCompletedEdits = async () => {
    if (disabled || completing || !editingCompleted || !completed) return;
    editing.current = true;
    const accepted = await enqueueSave(
      {
        duration,
        distance,
        averageHeartRate,
        heartRateZone,
        completed: true,
      },
      true,
      false,
    );
    if (accepted) {
      editingCompletedSnapshot.current = null;
      setEditingCompleted(false);
    }
  };

  const requestReopen = async () => {
    if (disabled || completing || reopenInFlight.current || !completed) return;
    reopenInFlight.current = true;
    try {
      const approved = await confirm({
        title: 'Вернуть кардио в работу?',
        message: `Вернуть интервал ${set.set_number} в работу? Статус изменится на „Не завершён“. Сохранённые результаты останутся.`,
        confirmText: 'Вернуть в работу',
        danger: false,
      });
      if (!approved) return;
      editing.current = true;
      const accepted = await enqueueSave({ completed: false }, true, false);
      if (accepted) {
        editingCompletedSnapshot.current = null;
        setEditingCompleted(false);
      }
    } finally {
      reopenInFlight.current = false;
    }
  };

  useEffect(() => {
    if (editing.current) {
      if (!pending) editing.current = false;
      return;
    }
    setDuration(
      String(pending ? (pending.values.duration_minutes ?? '') : (set.duration_minutes ?? '')),
    );
    setDistance(String(pending ? (pending.values.distance_km ?? '') : (set.distance_km ?? '')));
    setAverageHeartRate(
      String(
        pending
          ? (pending.values.average_heart_rate_bpm ?? '')
          : (set.average_heart_rate_bpm ?? ''),
      ),
    );
    setHeartRateZone(
      String(pending ? (pending.values.heart_rate_zone ?? '') : (set.heart_rate_zone ?? '')),
    );
  }, [
    pending,
    set.average_heart_rate_bpm,
    set.distance_km,
    set.duration_minutes,
    set.heart_rate_zone,
    set.is_completed,
  ]);

  const intervalLabel = set.set_number > 1 ? `Интервал ${set.set_number}` : 'Результат кардио';
  const plannedRoleLabel = formatPlannedSetRole(set.planned_role);
  const plannedGroupLabel = formatPlannedGroupKind(set.planned_group_kind);
  return (
    <div
      ref={rowRef}
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
        {(plannedRoleLabel || plannedGroupLabel) && (
          <div className="active-workout-set__roles" aria-label="Структура подхода">
            {plannedRoleLabel && (
              <span className="active-workout-set__role">{plannedRoleLabel}</span>
            )}
            {plannedGroupLabel && (
              <span className="active-workout-set__role active-workout-set__role--group">
                {plannedGroupLabel}
              </span>
            )}
          </div>
        )}
        {completed && (
          <span className="active-workout-set__complete-label">
            {(!pending || durable) && <CheckIcon />}
            {pending ? (durable ? 'Сохранено на устройстве' : 'Не сохранено') : 'Выполнено'}
          </span>
        )}
      </div>

      {completed && (
        <div
          className="active-workout-set__completed-actions app-action-group"
          aria-label="Действия с выполненным кардио"
        >
          {editingCompleted ? (
            <>
              <Button
                type="button"
                disabled={disabled || completing}
                data-workout-action="cancel-edit-completed"
                variant="ghost"
                onClick={cancelEditingCompleted}
              >
                Отмена
              </Button>
              <Button
                type="button"
                disabled={disabled || completing}
                data-workout-action="save-edit-completed"
                variant="secondary"
                onClick={() => void saveCompletedEdits()}
              >
                Сохранить
              </Button>
            </>
          ) : (
            <Button
              type="button"
              disabled={disabled || completing}
              data-workout-action="edit-completed"
              variant="ghost"
              onClick={beginEditingCompleted}
            >
              Редактировать
            </Button>
          )}
          {!editingCompleted && (
            <details className="active-workout-set__more-actions">
              <summary className="yfc-disclosure-summary">
                Действия
                <DisclosureIcon />
              </summary>
              <div className="active-workout-set__more-actions-body">
                <Button
                  type="button"
                  disabled={disabled || completing}
                  data-workout-action="reopen-completed"
                  variant="secondary"
                  onClick={() => void requestReopen()}
                >
                  Вернуть в работу
                </Button>
              </div>
            </details>
          )}
        </div>
      )}

      {isCurrent && previousResult && (
        <p className="active-workout-set__previous">Предыдущий интервал: {previousResult}</p>
      )}
      {canPrefill && (
        <div className="active-workout-set__prefill-actions">
          <button
            className="active-workout-set__prefill"
            type="button"
            disabled={disabled || completing}
            onClick={() => {
              const nextDuration = canPrefillDuration
                ? String(previousValues?.duration_minutes)
                : duration;
              const nextDistance = canPrefillDistance
                ? String(previousValues?.distance_km)
                : distance;
              editing.current = true;
              setDuration(nextDuration);
              setDistance(nextDistance);
              trackProductEvent({
                name: 'previous_set_reuse_used',
                surface: productEventSurface(),
              });
            }}
          >
            Подставить предыдущий результат
          </button>
          <button
            className="active-workout-set__prefill active-workout-set__prefill--commit"
            type="button"
            disabled={disabled || completing}
            onClick={() => {
              const nextDuration = canPrefillDuration
                ? String(previousValues?.duration_minutes)
                : duration;
              const nextDistance = canPrefillDistance
                ? String(previousValues?.distance_km)
                : distance;
              editing.current = true;
              setDuration(nextDuration);
              setDistance(nextDistance);
              enqueueSave(
                { duration: nextDuration, distance: nextDistance, completed: true },
                true,
              );
              trackProductEvent({
                name: 'previous_set_reuse_used',
                surface: productEventSurface(),
              });
            }}
          >
            Подставить и завершить
          </button>
        </div>
      )}

      <div className="active-workout-set__controls active-workout-set__controls--cardio">
        <label className="active-workout-input">
          <span>Длительность, мин</span>
          <input
            data-workout-field="duration"
            disabled={completedFieldsDisabled}
            aria-label={`Длительность, ${exerciseTitle}`}
            enterKeyHint="next"
            inputMode="numeric"
            type="number"
            min="1"
            max="600"
            step="1"
            value={duration}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                focusWorkoutControl(rowRef.current, 'distance');
              }
            }}
            onChange={(event) => {
              editing.current = true;
              setValidation(null);
              setDuration(event.target.value);
              if (!editingCompleted) enqueueSave({ duration: event.target.value });
            }}
          />
        </label>
        <label className="active-workout-input">
          <span>Дистанция, км</span>
          <input
            data-workout-field="distance"
            disabled={completedFieldsDisabled}
            aria-label={`Дистанция, ${exerciseTitle}`}
            enterKeyHint="done"
            inputMode="decimal"
            type="number"
            min="0.01"
            max="1000"
            step="0.01"
            value={distance}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                focusWorkoutControl(rowRef.current, 'done');
              }
            }}
            onChange={(event) => {
              editing.current = true;
              setDistance(event.target.value);
              if (!editingCompleted) enqueueSave({ distance: event.target.value });
            }}
          />
        </label>
        <Button
          type="button"
          disabled={disabled || completing || (completed && !retryCompletion)}
          aria-busy={completing || undefined}
          aria-label={`${completing ? 'Сохраняем…' : retryCompletion ? 'Повторить сохранение кардио' : completed ? 'Кардио выполнено' : 'Завершить кардио'}: ${exerciseTitle}`}
          aria-pressed={completed}
          className="active-workout-set__done"
          data-workout-field="done"
          variant={completed ? 'secondary' : 'primary'}
          onClick={(event) => {
            if (event.detail > 1) return;
            const nextCompleted = retryCompletion || !completed;
            if (nextCompleted && !duration) {
              setValidation('Укажите длительность кардио.');
              return;
            }
            editing.current = true;
            setValidation(null);
            enqueueSave({ completed: nextCompleted }, true);
          }}
        >
          {completing ? (
            'Сохраняем…'
          ) : retryCompletion ? (
            'Повторить сохранение'
          ) : completed ? (
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
        <summary className="yfc-disclosure-summary">
          Пульс (необязательно)
          <DisclosureIcon />
        </summary>
        <div className="active-workout-set__advanced-body active-workout-cardio-advanced">
          <label className="active-workout-advanced-field">
            <span>Средний пульс, уд/мин</span>
            <input
              disabled={completedFieldsDisabled}
              inputMode="numeric"
              type="number"
              min="30"
              max="250"
              value={averageHeartRate}
              onChange={(event) => {
                editing.current = true;
                setAverageHeartRate(event.target.value);
                if (!editingCompleted) enqueueSave({ averageHeartRate: event.target.value });
              }}
            />
          </label>
          <label className="active-workout-advanced-field">
            <span>Зона пульса</span>
            <select
              disabled={completedFieldsDisabled}
              value={heartRateZone}
              onChange={(event) => {
                editing.current = true;
                setHeartRateZone(event.target.value);
                if (!editingCompleted) enqueueSave({ heartRateZone: event.target.value });
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

export function RestTimer({
  userId,
  workoutId,
  nextLabel,
  nextExercise,
  nextPosition,
}: {
  userId: number;
  workoutId: number;
  nextLabel: string;
  nextExercise: string;
  nextPosition: string;
}) {
  const storageKey = activeWorkoutRestKey(userId, workoutId);
  const legacyStorageKey = legacyWorkoutRestStorageKey(workoutId);
  const [deadline, setDeadline] = useState(() => {
    const restored = activeRestJournalSession(userId, workoutId);
    removeStorage(legacyStorageKey);
    if (restored) return restored.deadline;
    removeStorage(storageKey);
    return 0;
  });
  const [now, setNow] = useState(() => Date.now());
  const [measuredRest, setMeasuredRest] = useState(() =>
    activeRestJournalSession(userId, workoutId),
  );
  const [recoveredMinutes, setRecoveredMinutes] = useState('');
  const [recoveryValidation, setRecoveryValidation] = useState('');
  const [completedNotice, setCompletedNotice] = useState<string | null>(null);
  const [compact, setCompact] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const panel = useRef<HTMLElement>(null);
  const pressedPointers = useRef(new Set<number>());
  const compactWhenPointersRelease = useRef(false);
  const layoutAnchor = useRef<{ element: Element; top: number } | null>(null);
  const wasBackgrounded = useRef(
    typeof document !== 'undefined' && document.visibilityState === 'hidden',
  );
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000));
  const measuredElapsedSeconds =
    measuredRest && !measuredRest.needs_review
      ? Math.max(0, Math.floor((now - Date.parse(measuredRest.started_at)) / 1000))
      : 0;
  const captureLayoutAnchor = useCallback(() => {
    const element = panel.current?.parentElement?.querySelector('.active-workout-exercises');
    if (element) layoutAnchor.current = { element, top: element.getBoundingClientRect().top };
  }, []);
  const compactNotice = useCallback(() => {
    if (pressedPointers.current.size) {
      // Keep the current hit surface until the active pointer sequence ends.
      compactWhenPointersRelease.current = true;
      return;
    }
    compactWhenPointersRelease.current = false;
    captureLayoutAnchor();
    setCompact(true);
  }, [captureLayoutAnchor]);
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (
        event as CustomEvent<{
          workoutId: number;
          setId?: number;
          seconds: number;
          deadline?: number;
        }>
      ).detail;
      if (!detail || detail.workoutId !== workoutId) return;
      const acceptedAt = Date.now();
      const started = detail.setId
        ? beginMeasuredRest(userId, workoutId, detail.setId, detail.seconds, acceptedAt)
        : null;
      if (detail.setId && !started) return;
      const nextDeadline =
        started?.deadline ?? detail.deadline ?? acceptedAt + detail.seconds * 1000;
      setMeasuredRest(started);
      setNow(acceptedAt);
      setDeadline(nextDeadline);
      setCompletedNotice(null);
      setCompact(false);
      setAnnouncement('');
      compactWhenPointersRelease.current = false;
      wasBackgrounded.current = document.visibilityState === 'hidden';
      writeStorage(storageKey, nextDeadline);
    };
    window.addEventListener('fit:rest', handler);
    return () => window.removeEventListener('fit:rest', handler);
  }, [storageKey, userId, workoutId]);
  useEffect(() => {
    let retryTimer: number | undefined;
    let syncInFlight = false;
    const hasPending = () =>
      loadRestJournal(userId, workoutId).some((item) => !item.server_id || item.pending.length > 0);
    const sync = () => {
      if (!hasPending() || syncInFlight) return;
      syncInFlight = true;
      void syncRestJournal(userId, workoutId)
        .catch(() => {
          // Keep the durable offline journal for the next retry.
        })
        .finally(() => {
          syncInFlight = false;
        });
    };
    const scheduleRetry = () => {
      if (hasPending() && retryTimer === undefined) {
        retryTimer = window.setInterval(() => {
          if (!hasPending()) {
            if (retryTimer !== undefined) window.clearInterval(retryTimer);
            retryTimer = undefined;
          } else if (navigator.onLine) sync();
        }, 15000);
      }
    };
    const refresh = () => {
      setMeasuredRest(activeRestJournalSession(userId, workoutId));
      scheduleRetry();
      sync();
    };
    const unsubscribe = listenToRestJournal(refresh);
    const reconcile = () => {
      refresh();
    };
    scheduleRetry();
    sync();
    window.addEventListener('online', reconcile);
    window.addEventListener('pageshow', reconcile);
    return () => {
      unsubscribe();
      window.removeEventListener('online', reconcile);
      window.removeEventListener('pageshow', reconcile);
      if (retryTimer !== undefined) window.clearInterval(retryTimer);
    };
  }, [userId, workoutId]);
  useEffect(() => {
    const markAway = () => {
      markRestBackground(userId, workoutId);
    };
    const restore = () => {
      if (document.visibilityState === 'hidden') return;
      const restored = recoverRestAfterAbsence(userId, workoutId);
      setMeasuredRest(restored);
      if (restored?.needs_review) {
        setRecoveryValidation('');
        setAnnouncement('Уточните длительность отдыха или не учитывайте замер');
      }
    };
    restore();
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') markAway();
      else restore();
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', markAway);
    window.addEventListener('pageshow', restore);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', markAway);
      window.removeEventListener('pageshow', restore);
    };
  }, [userId, workoutId]);
  useEffect(() => {
    const flushPendingCompact = () => {
      if (!compactWhenPointersRelease.current || pressedPointers.current.size) return;
      compactNotice();
    };
    const markBackgrounded = () => {
      if (document.visibilityState === 'hidden') {
        wasBackgrounded.current = true;
        pressedPointers.current.clear();
        flushPendingCompact();
      }
    };
    const markPageHidden = () => {
      wasBackgrounded.current = true;
      pressedPointers.current.clear();
      flushPendingCompact();
    };
    const startPointer = (event: PointerEvent) => pressedPointers.current.add(event.pointerId);
    const endPointer = (event: PointerEvent) => {
      pressedPointers.current.delete(event.pointerId);
      flushPendingCompact();
    };
    window.addEventListener('pageshow', markBackgrounded);
    window.addEventListener('pagehide', markPageHidden);
    document.addEventListener('visibilitychange', markBackgrounded);
    document.addEventListener('pointerdown', startPointer, true);
    document.addEventListener('pointerup', endPointer, true);
    document.addEventListener('pointercancel', endPointer, true);
    return () => {
      window.removeEventListener('pageshow', markBackgrounded);
      window.removeEventListener('pagehide', markPageHidden);
      document.removeEventListener('visibilitychange', markBackgrounded);
      document.removeEventListener('pointerdown', startPointer, true);
      document.removeEventListener('pointerup', endPointer, true);
      document.removeEventListener('pointercancel', endPointer, true);
    };
  }, [compactNotice]);
  useEffect(() => {
    if (!deadline) return;
    let timer: number | undefined;
    let expired = false;
    const update = () => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
      const currentTime = Date.now();
      setNow(currentTime);
      if (measuredRest?.status === 'running') {
        if (measuredRest.needs_review) return;
        if (deadline <= currentTime && !measuredRest.notified) {
          acknowledgeRestPlan(userId, workoutId, measuredRest.source_set_id);
          setAnnouncement('Плановый отдых завершён');
          const wasHidden = wasBackgrounded.current || document.visibilityState === 'hidden';
          if (
            wasHidden &&
            typeof Notification !== 'undefined' &&
            Notification.permission === 'granted'
          ) {
            new Notification('Плановый отдых завершён', {
              body: 'Далее: ' + nextLabel,
              tag: 'fit-rest-' + workoutId + '-' + measuredRest.source_set_id,
            });
          }
          wasBackgrounded.current = false;
          haptic('success');
        }
        // Keep counting until the user explicitly stops the interval.
        timer = window.setTimeout(update, 1000);
        return;
      }
      if (deadline <= currentTime) {
        if (expired) return;
        expired = true;
        const wasHidden = wasBackgrounded.current || document.visibilityState === 'hidden';
        removeStorage(storageKey);
        setDeadline(0);
        setCompletedNotice(`Отдых завершён · дальше: ${nextLabel}`);
        compactNotice();
        if (
          wasHidden &&
          typeof Notification !== 'undefined' &&
          Notification.permission === 'granted'
        ) {
          new Notification('Отдых завершён', {
            body: `Дальше: ${nextLabel}`,
            tag: `fit-rest-${workoutId}`,
          });
        }
        wasBackgrounded.current = false;
        haptic('success');
        return;
      }
      // Wake at the absolute deadline so timer drift cannot leave a stale 0:00 state.
      timer = window.setTimeout(update, Math.max(1, Math.min(1000, deadline - currentTime)));
    };
    update();
    document.addEventListener('visibilitychange', update);
    window.addEventListener('pageshow', update);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', update);
      window.removeEventListener('pageshow', update);
    };
  }, [compactNotice, deadline, measuredRest, nextLabel, storageKey, userId, workoutId]);
  useLayoutEffect(() => {
    const anchor = layoutAnchor.current;
    layoutAnchor.current = null;
    if (anchor?.element.isConnected) {
      const delta = anchor.element.getBoundingClientRect().top - anchor.top;
      if (delta) window.scrollBy({ top: delta, behavior: 'instant' });
    }
  }, [compact, completedNotice]);

  if (!deadline && !completedNotice) return null;
  return (
    <aside
      ref={panel}
      {...glassProps('tinted')}
      className={`active-workout-rest${completedNotice ? ' active-workout-rest--complete' : ''}${compact ? ' is-compact' : ''}`}
      aria-label="Отдых между подходами"
      onMouseDown={(event) => {
        if (event.target instanceof Element && event.target.closest('button'))
          event.preventDefault();
      }}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="active-workout-rest__time" hidden={compact}>
        <span>Отдых</span>
        <strong role={completedNotice ? undefined : 'timer'} aria-label="Отдых" aria-live="off">
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
        </strong>
      </div>
      <div className="active-workout-rest__next" hidden={compact}>
        <strong>{completedNotice?.split(' · ')[0] ?? `Далее: ${nextExercise}`}</strong>
        <span>{nextPosition}</span>
      </div>
      {measuredRest && !compact && (
        <div className="active-workout-rest__actual">
          <div className="active-workout-rest__actual-value">
            <span>ФАКТ</span>
            <strong aria-label="Время по отметке пользователя" aria-live="off">
              {measuredRest.needs_review ? '—' : formatWorkoutDuration(measuredElapsedSeconds)}
            </strong>
          </div>
          {!measuredRest.needs_review && (
            <button
              className="active-workout-rest__stop"
              type="button"
              aria-label="Завершить отдых"
              onClick={() => {
                const stoppedAt = Date.now();
                const result = updateMeasuredRest(
                  userId,
                  workoutId,
                  measuredRest.source_set_id,
                  'complete',
                  stoppedAt,
                );
                setMeasuredRest(null);
                removeStorage(storageKey);
                setDeadline(0);
                setNow(stoppedAt);
                setCompletedNotice(
                  result?.status === 'completed'
                    ? 'Отдых завершён по отметке'
                    : 'Нет достоверного замера отдыха',
                );
                compactNotice();
              }}
            >
              Стоп
            </button>
          )}
        </div>
      )}
      {measuredRest?.needs_review && !compact && (
        <section
          className="active-workout-rest__recovery"
          role="group"
          aria-label="Уточнение фактического отдыха"
        >
          <strong>Вы забыли завершить отдых?</strong>
          <p>
            Приложение было неактивно, поэтому прошедшее время не считается достоверным замером.
          </p>
          <label htmlFor={`rest-recovery-${workoutId}`}>
            Сколько вы фактически отдыхали (минуты)?
          </label>
          <input
            id={`rest-recovery-${workoutId}`}
            type="text"
            inputMode="decimal"
            className="ui-input"
            placeholder="Например, 2,5"
            value={recoveredMinutes}
            onChange={(event) => {
              setRecoveredMinutes(event.target.value);
              setRecoveryValidation('');
            }}
          />
          {recoveryValidation && <span role="alert">{recoveryValidation}</span>}
          <div className="active-workout-rest__recovery-actions">
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                const value = Number(recoveredMinutes.trim().replace(',', '.'));
                const correctedSeconds = Math.round(value * 60);
                if (
                  !recoveredMinutes.trim() ||
                  !Number.isFinite(value) ||
                  correctedSeconds < 0 ||
                  correctedSeconds > 86400
                ) {
                  setRecoveryValidation('Введите время от 0 до 1440 минут');
                  return;
                }
                const result = updateMeasuredRest(
                  userId,
                  workoutId,
                  measuredRest.source_set_id,
                  'complete',
                  Date.now(),
                  correctedSeconds,
                );
                if (result?.status !== 'completed') {
                  setRecoveryValidation('Не удалось сохранить уточнение. Попробуйте ещё раз.');
                  return;
                }
                setMeasuredRest(null);
                removeStorage(storageKey);
                setDeadline(0);
                setCompletedNotice('Отдых сохранён по вашей отметке');
                compactNotice();
              }}
            >
              Сохранить время
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                updateMeasuredRest(userId, workoutId, measuredRest.source_set_id, 'skip');
                setMeasuredRest(null);
                removeStorage(storageKey);
                setDeadline(0);
                setCompletedNotice('Отдых не учитывается');
                compactNotice();
              }}
            >
              Не учитывать
            </Button>
          </div>
        </section>
      )}
      <div
        className="active-workout-rest__actions"
        hidden={compact || Boolean(measuredRest?.needs_review)}
      >
        {[30, 60].map((extraSeconds) => (
          <Button
            key={extraSeconds}
            aria-label={`+${extraSeconds} сек`}
            type="button"
            glass="clear"
            variant="secondary"
            aria-disabled={Boolean(completedNotice)}
            tabIndex={completedNotice ? -1 : undefined}
            onClick={() => {
              if (!deadline || completedNotice) return;
              const currentTime = Date.now();
              const nextSession = measuredRest
                ? updateMeasuredRest(
                    userId,
                    workoutId,
                    measuredRest.source_set_id,
                    extraSeconds === 30 ? 'add30' : 'add60',
                    currentTime,
                  )
                : null;
              const nextDeadline =
                nextSession?.deadline ?? Math.max(deadline, currentTime) + extraSeconds * 1000;
              if (nextSession) setMeasuredRest(nextSession);
              setNow(currentTime);
              setDeadline(nextDeadline);
              writeStorage(storageKey, nextDeadline);
              setAnnouncement(`К отдыху добавлено ${extraSeconds} секунд`);
            }}
          >
            <Icon name="plus" size={16} /> {extraSeconds} сек
          </Button>
        ))}
        <Button
          type="button"
          glass="clear"
          variant="secondary"
          aria-disabled={Boolean(completedNotice)}
          tabIndex={completedNotice ? -1 : undefined}
          onClick={() => {
            if (completedNotice) return;
            if (measuredRest) {
              updateMeasuredRest(userId, workoutId, measuredRest.source_set_id, 'skip');
              setMeasuredRest(null);
            }
            removeStorage(storageKey);
            setDeadline(0);
            setNow(Date.now());
            setCompletedNotice(`Отдых пропущен · ${nextPosition}`);
            compactNotice();
          }}
        >
          Пропустить
        </Button>
      </div>
      {compact && (
        <>
          <span className="active-workout-rest__complete-copy">{completedNotice}</span>
          <Button
            type="button"
            variant="secondary"
            glass="clear"
            onClick={() => {
              captureLayoutAnchor();
              setCompletedNotice(null);
              setCompact(false);
            }}
          >
            Скрыть
          </Button>
        </>
      )}
      <span className="sr-only" role="status" aria-atomic="true">
        {completedNotice ?? announcement}
      </span>
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
  const capabilities = useRuntimeCapabilities();
  const queryClient = useQueryClient();
  const [guide, setGuide] = useState<{ id: number; title: string } | null>(null);
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [dismissedGuidance, setDismissedGuidance] = useState<Set<number>>(() => new Set());
  const [expandedExercises, setExpandedExercises] = useState<Set<number>>(() => new Set());
  const workout = useQuery({
    queryKey: ['workout', 'today'],
    queryFn: () => api<Workout>('/api/v1/workouts/today'),
    initialData: () => (user ? loadCurrentActiveWorkoutSnapshot(user.id) : undefined),
    initialDataUpdatedAt: 0,
    refetchOnReconnect: false,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const activeSync = useActiveWorkoutQueue(user?.id, workout.data);
  useScreenWakeLock(workout.data?.status === 'in_progress');
  const mutation = useMutation({
    mutationFn: ({ path, method, body }: { path: string; method: string; body?: unknown }) =>
      api<Workout | void>(path, { method, body }),
    onSuccess: async (result, variables) => {
      if (variables.path.endsWith('/finish')) {
        trackCoreProductEvent(
          { name: 'workout_completed', surface: productEventSurface() },
          'workout_completed',
        );
        trackProductEvent(
          {
            name: 'next_action_completed',
            surface: productEventSurface(),
            action_kind: 'active_workout',
            position: 'primary',
          },
          { dedupe: 'session', dedupeKey: 'next-action:active-workout:completed' },
        );
        if (user?.has_workout_history === false) {
          trackGrowthEvent('first_workout_completed', { dedupe: 'session' });
        }
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
          if (user?.has_workout_history === false) {
            trackGrowthEvent('first_workout_started', { dedupe: 'session' });
          }
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
  const [completionNavigation, setCompletionNavigation] = useState<{
    setId: number;
    accepted: boolean;
  } | null>(null);
  const navigatedCompletion = useRef<typeof completionNavigation>(null);
  const autosaveSetId = useRef<number | null>(null);
  const enqueueSet = async (
    setId: number,
    version: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
    completing = false,
  ) => {
    autosaveSetId.current = !immediate && !values.is_completed ? setId : null;
    const navigation = completing ? { setId, accepted: false } : null;
    if (navigation) setCompletionNavigation(navigation);
    const accepted = await activeSync.enqueue(setId, version, values, immediate);
    if (navigation)
      setCompletionNavigation((current) =>
        current === navigation ? (accepted ? { setId, accepted: true } : navigation) : current,
      );
    return accepted;
  };
  const currentSet = (() => {
    if (!workout.data) return null;
    for (const exercise of workout.data.exercises) {
      for (const set of exercise.sets) {
        const isCompleted =
          activeSync.pendingBySet.get(set.id)?.values.is_completed ?? set.is_completed;
        if (
          !isCompleted ||
          (completionNavigation?.setId === set.id && !completionNavigation.accepted)
        )
          return { exercise, set };
      }
    }
    return null;
  })();
  const currentSetId = currentSet?.set.id;
  const clearActiveState = activeSync.clear;
  const pendingActiveCount = activeSync.pendingCount;

  useEffect(() => {
    let frame: number | undefined;
    let pointerActive = false;
    let correctionPending = false;
    const keepFieldsVisible = () => {
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        // A pressed control must stay under the pointer until its click is delivered.
        if (pointerActive) {
          correctionPending = true;
          return;
        }
        correctionPending = false;
        const editingRir = document.activeElement?.matches('.active-workout-rir button');
        if (!editingWorkoutField() && !editingRir) return;
        const input = document.activeElement as HTMLElement;
        const controls = input.closest('.active-workout-set__controls') ?? input;
        const box = controls.getBoundingClientRect();
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop ?? 0;
        const bottom = top + (viewport?.height ?? window.innerHeight);
        const timer = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
        const safeTop = Math.max(
          top,
          timer && timer.bottom > top && timer.top < bottom ? timer.bottom : top,
        );
        const target = box.height <= bottom - safeTop ? box : input.getBoundingClientRect();
        const delta =
          target.top < safeTop ? target.top - safeTop : Math.max(0, target.bottom - bottom);
        // Ignore subpixel observer noise; visible displacement still gets corrected.
        if (Math.abs(delta) > 1) window.scrollBy({ top: delta, behavior: 'instant' });
      });
    };
    const pointerDown = () => {
      pointerActive = true;
    };
    const pointerEnd = () => {
      pointerActive = false;
      if (correctionPending) keepFieldsVisible();
    };
    const viewport = window.visualViewport;
    let viewportTop = viewport?.offsetTop;
    const panViewport = () => {
      if (viewport?.offsetTop === viewportTop) return;
      viewportTop = viewport?.offsetTop;
      keepFieldsVisible();
    };
    const observer = new ResizeObserver(keepFieldsVisible);
    const focus = () => {
      observer.disconnect();
      const row = document.activeElement?.closest('.active-workout-set');
      if (
        row &&
        (editingWorkoutField() || document.activeElement?.matches('.active-workout-rir button'))
      ) {
        // Stop an in-flight completion scroll before the keyboard takes over positioning.
        window.scrollTo({ top: window.scrollY, left: window.scrollX, behavior: 'instant' });
        observer.observe(row);
      }
      keepFieldsVisible();
    };
    document.addEventListener('focusin', focus);
    document.addEventListener('pointerdown', pointerDown, true);
    document.addEventListener('pointerup', pointerEnd, true);
    document.addEventListener('pointercancel', pointerEnd, true);
    viewport?.addEventListener('resize', keepFieldsVisible);
    viewport?.addEventListener('scroll', panViewport);
    window.addEventListener('resize', keepFieldsVisible);
    return () => {
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener('focusin', focus);
      document.removeEventListener('pointerdown', pointerDown, true);
      document.removeEventListener('pointerup', pointerEnd, true);
      document.removeEventListener('pointercancel', pointerEnd, true);
      viewport?.removeEventListener('resize', keepFieldsVisible);
      viewport?.removeEventListener('scroll', panViewport);
      window.removeEventListener('resize', keepFieldsVisible);
    };
  }, []);

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

  useLayoutEffect(() => {
    if (!completionNavigation?.accepted || navigatedCompletion.current === completionNavigation)
      return;
    const frame = window.requestAnimationFrame(() => {
      navigatedCompletion.current = completionNavigation;
      // Only acceptance owns navigation; autosave and later queue acknowledgements do not.
      const focused = document.activeElement;
      if (
        focused instanceof HTMLElement &&
        focused.closest(`[data-workout-set-id="${completionNavigation.setId}"]`)
      )
        focused.blur();
      if (!currentSetId || editingWorkoutField()) return;
      const row = document.querySelector<HTMLElement>(`[data-workout-set-id="${currentSetId}"]`);
      const controls = row?.querySelector<HTMLElement>('.active-workout-set__controls');
      if (!controls) return;
      const viewport = window.visualViewport;
      const top = viewport?.offsetTop ?? 0;
      const bottom = top + (viewport?.height ?? window.innerHeight);
      const timer = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
      const dock = document.getElementById('appBottomNav')?.getBoundingClientRect();
      const safeTop =
        Math.max(top, timer && timer.top < bottom && timer.bottom > top ? timer.bottom : top) + 8;
      const safeBottom = Math.min(bottom, dock && dock.height > 0 ? dock.top : bottom) - 8;
      const box = controls.getBoundingClientRect();
      const targetTop = safeTop + Math.max(0, (safeBottom - safeTop - box.height) / 2);
      let delta = box.top - targetTop;
      const nextRow = row?.nextElementSibling;
      const nextDone = nextRow?.querySelector<HTMLElement>('[data-workout-field="done"]');
      const rir = row?.querySelector('.active-workout-rir--quick')?.getBoundingClientRect();
      if (nextDone) {
        // Clear the adjacent set only within the space that keeps the current inputs visible.
        delta = Math.max(
          delta,
          Math.min(
            nextDone.getBoundingClientRect().bottom - safeBottom,
            Math.min(box.top, rir?.top ?? box.top) - safeTop,
          ),
        );
      }
      window.scrollBy({ top: Math.ceil(delta), behavior: 'instant' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [completionNavigation, currentSetId]);

  useEffect(() => {
    if (pendingActiveCount !== 0 || autosaveSetId.current !== currentSetId || editingWorkoutField())
      return;
    const frame = window.requestAnimationFrame(() => {
      if (editingWorkoutField() || autosaveSetId.current !== currentSetId) return;
      const row = document.querySelector<HTMLElement>(
        '[data-workout-set-id="' + currentSetId + '"]',
      );
      const controls = row?.querySelector('.active-workout-set__controls')?.getBoundingClientRect();
      const dock = document.getElementById('appBottomNav')?.getBoundingClientRect();
      const timer = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
      if (!row || !controls || !dock?.height || !timer) return;
      const viewport = window.visualViewport;
      const top = Math.max(viewport?.offsetTop ?? 0, timer.bottom);
      const bottom =
        Math.min((viewport?.offsetTop ?? 0) + (viewport?.height ?? innerHeight), dock.top) - 8;
      const nextRow = row.nextElementSibling;
      const next = nextRow?.querySelector('[data-workout-field="done"]')?.getBoundingClientRect();
      const visibleNext =
        nextRow &&
        nextRow.getBoundingClientRect().top <
          (viewport?.offsetTop ?? 0) + (viewport?.height ?? innerHeight);
      const rir = row.querySelector('.active-workout-rir--quick')?.getBoundingClientRect();
      const overlap = Math.max(
        0,
        controls.bottom - bottom,
        visibleNext && next ? next.bottom - bottom : 0,
      );
      const delta = Math.min(overlap, Math.min(controls.top, rir?.top ?? controls.top) - top);
      if (delta > 0) window.scrollBy({ top: Math.ceil(delta), behavior: 'instant' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [currentSetId, pendingActiveCount]);

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
  const recoveryWorkout: WorkoutScheduleItem = {
    id: data.id,
    scheduled_date: data.scheduled_date,
    scheduled_time: data.scheduled_time,
    title: data.title,
    status: data.status,
    day_number: data.day_number,
    week_number: data.week_number,
  };
  const started = data.status === 'in_progress';
  const hasCardio = data.exercises.some((exercise) => exercise.metric_type === 'cardio');
  const nextLabel = currentSet
    ? currentSet.exercise.metric_type === 'cardio'
      ? currentSet.exercise.exercise_title
      : `${currentSet.exercise.exercise_title}, подход ${currentSet.set.set_number}`
    : 'завершить тренировку';
  const syncFailed = activeSync.syncState === 'error' || activeSync.syncState === 'conflict';
  const syncInProgress = activeSync.syncState === 'syncing';
  const syncOffline = activeSync.syncState === 'offline';
  const syncText = syncFailed
    ? 'Требуется действие'
    : syncInProgress
      ? 'Синхронизация…'
      : activeSync.pendingCount > 0
        ? syncOffline
          ? 'Сохранено на устройстве'
          : 'Сохранение…'
        : 'Синхронизировано';
  const syncNeedsAction = syncFailed || (activeSync.pendingCount > 0 && syncOffline);
  const adaptationEntry =
    data.status === 'planned' || started ? (
      capabilities.canMutatePrograms ? (
        <WorkoutAdaptation workout={data} safetyOnly={started} />
      ) : (
        <p className="muted demo-capability-notice" role="status">
          Изменение плана тренировки доступно после входа.
        </p>
      )
    ) : null;

  if (data.status === 'completed') {
    return (
      <WorkoutCompletionSummary
        readOnly={!capabilities.canMutateProgress}
        workout={data}
        onReturnToday={onCompletionClose}
      />
    );
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
              {syncNeedsAction && activeSync.pendingCount > 0 && navigator.onLine && (
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

        <AiCoachContextualEntry
          actionLabel="Спросить про тренировку"
          context={{ surface: 'workout', resourceId: data.id }}
          entryPoint="workout"
        />

        {!currentSet && adaptationEntry}

        {user && started && (
          <RestTimer
            userId={user.id}
            workoutId={data.id}
            nextLabel={nextLabel}
            nextExercise={currentSet?.exercise.exercise_title ?? 'Завершите тренировку'}
            nextPosition={
              currentSet
                ? `Подход ${currentSet.set.set_number} из ${currentSet.exercise.sets.length}`
                : 'Все подходы отмечены'
            }
          />
        )}

        <div className="active-workout-exercises">
          {data.exercises.map((exercise, exerciseIndex) => {
            const metricType = exercise.metric_type === 'cardio' ? 'cardio' : 'strength';
            const exerciseCompleted = exercise.sets.filter(
              (set) => activeSync.pendingBySet.get(set.id)?.values.is_completed ?? set.is_completed,
            ).length;
            const canReplaceExercise =
              started &&
              capabilities.canMutatePrograms &&
              !hasWorkoutExecutionEvidence(exercise, activeSync.pendingBySet);
            const isPersistedComplete = shouldCollapseCompletedExercise(exercise.sets, (setId) =>
              activeSync.pendingBySet.has(setId),
            );
            const isCurrentExercise = currentSet?.exercise.id === exercise.id;
            const exerciseOpen = isCurrentExercise || expandedExercises.has(exercise.id);
            const groupKind =
              exercise.group_kind ?? (exercise.superset_group ? ('superset' as const) : null);
            const groupLabel =
              groupKind && groupKind !== 'sequence'
                ? `${formatPlannedGroupKind(groupKind)}${
                    exercise.group_order || exercise.superset_order
                      ? ` · ${exercise.group_order ?? exercise.superset_order}`
                      : ''
                  }`
                : null;
            const suggestedWeight =
              metricType === 'strength'
                ? (exercise.progression_guidance?.suggested_weight ?? null)
                : null;
            const targetSetUpdates =
              exercise.progression_guidance?.proposal?.target_set_updates ?? [];
            const guidanceApplied =
              targetSetUpdates.length > 0 &&
              targetSetUpdates.every((update) => {
                const set = exercise.sets.find((item) => item.id === update.set_id);
                const pending = set ? activeSync.pendingBySet.get(set.id)?.values : undefined;
                return (
                  set != null &&
                  (pending?.actual_weight ?? set.actual_weight) === update.proposed_weight
                );
              });
            const applyGuidance =
              started && suggestedWeight != null && targetSetUpdates.length > 0
                ? () => {
                    for (const update of targetSetUpdates) {
                      const set = exercise.sets.find((item) => item.id === update.set_id);
                      if (!set) continue;
                      const pending = activeSync.pendingBySet.get(set.id)?.values;
                      if (pending?.is_completed ?? set.is_completed) continue;
                      activeSync.enqueue(set.id, update.set_version, {
                        actual_reps: pending?.actual_reps ?? set.actual_reps ?? null,
                        actual_weight: update.proposed_weight,
                        rir: pending?.rir ?? set.rir ?? null,
                        set_kind: pending?.set_kind ?? set.set_kind ?? 'working',
                        reached_failure: pending?.reached_failure ?? set.reached_failure ?? false,
                        is_completed: pending?.is_completed ?? set.is_completed,
                      });
                    }
                  }
                : undefined;
            const guidanceElement =
              metricType === 'strength' &&
              exercise.progression_guidance &&
              !dismissedGuidance.has(exercise.id) ? (
                <ProgressionGuidance
                  applied={guidanceApplied}
                  exerciseKey={exercise.id}
                  guidance={exercise.progression_guidance}
                  onApply={applyGuidance}
                  onDismiss={() =>
                    setDismissedGuidance((current) => new Set(current).add(exercise.id))
                  }
                />
              ) : undefined;

            return (
              <article
                className={`active-workout-exercise ${isCurrentExercise ? 'is-current' : ''} ${exerciseCompleted === exercise.sets.length ? 'is-completed' : ''} ${groupLabel ? 'is-superset' : ''}`}
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
                    {groupLabel && <span className="active-workout-superset">{groupLabel}</span>}
                    {exercise.notes && <p className="exercise-note">{exercise.notes}</p>}
                    {!isCurrentExercise && (
                      <ExerciseSetupMemory
                        key={`setup-memory-${exercise.exercise_id}-${exercise.setup_memory?.version ?? 'none'}`}
                        canEdit={capabilities.canMutatePrograms}
                        exerciseId={exercise.exercise_id}
                        memory={exercise.setup_memory ?? null}
                        userId={user?.id ?? 0}
                      />
                    )}
                  </div>
                  <div className="active-workout-exercise__head-actions app-action-group">
                    {(!isCurrentExercise || isPersistedComplete) && (
                      <button
                        type="button"
                        className="secondary active-workout-exercise__toggle"
                        aria-expanded={exerciseOpen}
                        aria-controls={`workout-exercise-${exercise.id}-details`}
                        onClick={() =>
                          setExpandedExercises((current) => {
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
                          : isPersistedComplete
                            ? metricType === 'cardio'
                              ? 'Кардио сохранено'
                              : `${exerciseCompleted} из ${exercise.sets.length} сохранено`
                            : 'Открыть упражнение'}
                        <Icon name={exerciseOpen ? 'chevron-up' : 'chevron-down'} size={16} />
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
                    {canReplaceExercise && (
                      <WorkoutAdaptation
                        entryContext="workout"
                        entryLabel="Заменить только в этой тренировке"
                        initialTargetId={exercise.id}
                        safetyOnly={false}
                        workout={data}
                      />
                    )}
                  </div>
                </header>

                {isCurrentExercise && currentSet && (
                  <ActiveSessionSummary
                    key={`active-session-summary-${exercise.id}-${exercise.exercise_id}`}
                    adaptation={started ? undefined : adaptationEntry}
                    currentSet={currentSet.set}
                    exercise={exercise}
                    guidance={guidanceElement}
                    onFocusCurrentSet={() => {
                      const currentElement = document.querySelector<HTMLElement>(
                        `[data-workout-set-id="${currentSet.set.id}"]`,
                      );
                      if (!currentElement) return;
                      currentElement.scrollIntoView({ block: 'center' });
                      const field =
                        currentSet.exercise.metric_type === 'cardio' ? 'duration' : 'weight';
                      currentElement
                        .querySelector<HTMLElement>(`[data-workout-field="${field}"]`)
                        ?.focus({ preventScroll: true });
                    }}
                    pending={activeSync.pendingBySet.get(currentSet.set.id)}
                    safetyAction={started ? adaptationEntry : undefined}
                    setupMemory={
                      <ExerciseSetupMemory
                        key={`setup-memory-${exercise.exercise_id}-${exercise.setup_memory?.version ?? 'none'}`}
                        canEdit={capabilities.canMutatePrograms}
                        exerciseId={exercise.exercise_id}
                        memory={exercise.setup_memory ?? null}
                        userId={user?.id ?? 0}
                      />
                    }
                    started={started}
                  />
                )}

                {isCurrentExercise &&
                  (exercise.media_state === 'approved_animated' ||
                    exercise.media_state === 'approved_static' ||
                    exercise.media_state === 'blocked') && (
                    <div
                      className={`active-workout-exercise__media ${exercise.media_state === 'blocked' ? 'active-workout-exercise__media--blocked' : ''}`}
                    >
                      {exercise.media_state === 'blocked' ? (
                        <div
                          className="exercise-media-asset--missing"
                          role="img"
                          aria-label={`${exercise.exercise_title}: Изображение пока недоступно. Для этого упражнения нет проверенного визуального материала.`}
                        >
                          <strong>Изображение пока недоступно</strong>
                          <span>Для этого упражнения нет проверенного визуального материала.</span>
                        </div>
                      ) : (
                        <ExerciseMediaAsset
                          animationUrl={exercise.media_animation_url}
                          videoSources={exercise.media_video_sources}
                          alt={`${exercise.exercise_title}: техника движения`}
                          thumbnailUrl={exercise.media_thumbnail_url}
                          thumbnailSources={exercise.media_thumbnail_sources}
                          preferredMode={exercise.media_preferred_mode}
                          variant="animation"
                        />
                      )}
                    </div>
                  )}

                <div id={`workout-exercise-${exercise.id}-details`} hidden={!exerciseOpen}>
                  {metricType === 'strength' && (
                    <ExerciseHistoryContext
                      enabled={started && exerciseOpen}
                      exerciseId={exercise.exercise_id}
                    />
                  )}
                  {!isCurrentExercise && guidanceElement}

                  <div className="active-workout-exercise__sets">
                    {exercise.sets.map((set, setIndex) => {
                      const previousSet = setIndex > 0 ? exercise.sets[setIndex - 1] : undefined;
                      const previousPending = previousSet
                        ? activeSync.pendingBySet.get(previousSet.id)
                        : undefined;
                      const previousValues = previousSet
                        ? resolvePreviousSetValues(previousSet, previousPending)
                        : undefined;
                      const previousResult = previousValues
                        ? metricType === 'cardio'
                          ? formatCardioResult(
                              previousValues.duration_minutes,
                              previousValues.distance_km,
                            )
                          : formatSetResult(
                              previousValues.actual_reps,
                              previousValues.actual_weight,
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
                          previousValues={previousValues}
                          pending={activeSync.pendingBySet.get(set.id)}
                          durable={activeSync.durable}
                          syncing={activeSync.syncState === 'syncing'}
                          syncFailed={syncFailed}
                          enqueue={enqueueSet}
                        />
                      ) : (
                        <WorkoutSetRow
                          key={set.id}
                          set={set}
                          setPosition={setIndex + 1}
                          setTotal={exercise.sets.length}
                          prescribedReps={exercise.prescribed_reps}
                          restSeconds={exercise.rest_seconds}
                          userId={user?.id}
                          disabled={!started}
                          workoutId={data.id}
                          workoutExerciseId={exercise.id}
                          exerciseTitle={exercise.exercise_title}
                          hasWarmupRows={exercise.sets.some(
                            (item) => item.set_kind === 'warmup' || item.planned_role === 'warmup',
                          )}
                          isCurrent={currentSet?.set.id === set.id}
                          previousResult={previousResult}
                          previousValues={previousValues}
                          pending={activeSync.pendingBySet.get(set.id)}
                          durable={activeSync.durable}
                          syncing={activeSync.syncState === 'syncing'}
                          syncFailed={syncFailed}
                          enqueue={enqueueSet}
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
          <>
            {capabilities.canMutatePrograms ? (
              <WorkoutRecovery
                workout={recoveryWorkout}
                timeZone={user?.profile?.timezone}
                open={recoveryOpen}
                onOpenChange={setRecoveryOpen}
                triggerLabel="Изменить план или пропустить"
              />
            ) : (
              <p className="muted demo-capability-notice" role="status">
                Пропуск тренировки доступен после входа.
              </p>
            )}
          </>
        )}
      </section>

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
