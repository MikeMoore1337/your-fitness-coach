import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../app/AuthProvider';
import { api, ApiError } from '../../shared/api/client';
import type {
  ExerciseHistory,
  Workout,
  WorkoutScheduleItem,
  WorkoutSetHistory,
} from '../../shared/api/types';
import { haptic } from '../../shared/telegram/useTelegram';
import { useFeedback } from '../../shared/ui/FeedbackProvider';
import { ContextualHelp } from '../../shared/ui/ContextualHelp';
import { Icon } from '../../shared/ui/Icon';
import { glassProps } from '../../shared/ui/Glass';
import { useModalA11y } from '../../shared/ui/useModalA11y';
import { TaskProgress } from '../../shared/ui/DataViz';
import {
  DisclosureIcon,
  Badge,
  Button,
  Card,
  CheckIcon,
  CloseIcon,
  IconButton,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../../shared/ui/common';
import { readStorage, removeStorage, writeStorage } from '../../shared/storage';
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
  restartMeasuredRest,
  markRestBackground,
  recoverRestAfterAbsence,
  syncRestJournal,
  updateMeasuredRest,
} from './restSessions';
import { hasWorkoutExecutionEvidence, WorkoutAdaptation } from './WorkoutAdaptation';
import { WorkoutCompletionSummary } from './WorkoutCompletionSummary';
import { PreviousWorkoutNote } from './PreviousWorkoutNote';
import { WorkoutRecovery } from './WorkoutRecovery';
import { reconcileFinishedWorkout } from './finishWorkoutRecovery';
import { useActiveWorkoutQueue } from './useActiveWorkoutQueue';
import { useRuntimeCapabilities } from '../../shared/runtime/runtime';
import { useOnlineStatus } from '../../shared/ui/OnlineStatus';
import { formatCalendarDate } from '../../shared/dateTime';
import {
  productEventSurface,
  trackCoreProductEvent,
  trackGrowthEvent,
  trackProductEvent,
} from '../../shared/analytics/productEvents';
import {
  isPwaStandalone,
  isTelegramSurface,
  PWA_SAFE_UPDATE_EVENT,
} from '../../shared/pwa/pwaRuntime';
import { ProgressionGuidance } from './ProgressionGuidance';
import { weekTypeLabels } from './weekTypes';
import { useScreenWakeLock } from './useScreenWakeLock';
import { AiCoachContextualEntry } from '../ai/AiCoachContextualEntry';
import { WarmupProposal } from './WarmupProposal';
import { PlateCalculator } from './PlateCalculator';
import { ExerciseSetupMemory } from './ExerciseSetupMemory';
import { ExerciseExecutionNote } from './ExerciseExecutionNote';
import { ExerciseNoteRecovery } from './ExerciseNoteRecovery';
import { noteIdentity } from './exerciseNoteQueue';
import { ActiveSessionSummary } from './ActiveSessionSummary';
import { boundSetHistory, previousCompletedSet } from './workoutSetHistory';
import {
  hasDecimalScale,
  isCompleteDecimalDraft,
  parseDecimalDraft,
} from '../../shared/numeric/decimalDraft';
import './SideWorkout.css';

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
type SetHistoryState = 'ready' | 'loading' | 'offline' | 'unavailable';

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

function focusWorkoutControl(
  row: HTMLDivElement | null,
  field: 'reps' | 'distance' | 'rir' | 'done',
) {
  if (field === 'rir') {
    row
      ?.querySelector<HTMLElement>('.active-workout-set__rir-row button')
      ?.focus({ preventScroll: true });
    return;
  }
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
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, '');
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
  sideLabel,
}: {
  compact?: boolean;
  disabled: boolean;
  value: RirValue | null;
  onChange: (value: RirValue | null) => void;
  sideLabel?: string;
}) {
  return (
    <fieldset className={`active-workout-rir${compact ? ' active-workout-rir--quick' : ''}`}>
      <legend>
        Повторы в запасе
        {sideLabel ? ` · ${sideLabel}` : ''}
      </legend>
      <div className="active-workout-rir__options">
        {rirOptions.map((option) => (
          <button
            type="button"
            disabled={disabled}
            aria-label={sideLabel ? `${sideLabel}: ${option.label}` : option.label}
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
  previousSetNumber,
  previousPending,
  pastHistory,
  historyState,
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
  exerciseNote,
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
  previousSetNumber?: number;
  previousPending: boolean;
  pastHistory?: WorkoutSetHistory['sets'][number];
  historyState: SetHistoryState;
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
  exerciseNote?: ReactNode;
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
  const canPrefill =
    isCurrent &&
    !disabled &&
    !completed &&
    previousResult !== null &&
    (canPrefillReps || canPrefillWeight);
  const past =
    historyState === 'ready' && pastHistory?.history_status === 'matched'
      ? pastHistory.previous_workout
      : null;
  const pastResult = past?.sides
    ? sideHistoryText(past.sides)
    : past
      ? formatSetResult(past.actual_reps, past.actual_weight)
      : null;
  const canPrefillPast =
    isCurrent &&
    !disabled &&
    !completed &&
    past != null &&
    !past.sides &&
    ((reps === '' && past.actual_reps != null) || (weight === '' && past.actual_weight != null));
  const pastMessage = {
    offline: 'История недоступна без сети',
    loading: 'Обновляем историю…',
    unavailable: 'История временно недоступна',
    ready: pastResult ?? 'Нет прошлого результата',
  }[historyState];
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
    const nextReps = next.reps ?? reps;
    const nextWeight = next.weight ?? weight;
    const nextRir = next.rir === undefined ? rir : next.rir;
    const nextSetKind = next.setKind ?? setKind;
    const nextReachedFailure = next.reachedFailure ?? reachedFailure;
    const nextCompleted = next.completed ?? completed;
    const parsedWeight = nextWeight.trim() === '' ? null : parseDecimalDraft(nextWeight);
    if (
      nextWeight.trim() !== '' &&
      (parsedWeight == null || !hasDecimalScale(nextWeight, 2) || parsedWeight < 0)
    ) {
      return false;
    }
    if (immediate) {
      completionInFlight.current = true;
      setCompleting(true);
    }
    try {
      const accepted = await enqueue(
        set.id,
        serverVersion,
        {
          actual_reps: nextReps === '' ? null : Number(nextReps),
          actual_weight: parsedWeight,
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
          aria-label="Управление выполненным подходом"
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
            <Button
              type="button"
              disabled={disabled || completing}
              data-workout-action="reopen-completed"
              variant="secondary"
              onClick={() => void requestReopen()}
            >
              Вернуть в работу
            </Button>
          )}
        </div>
      )}

      <div
        className="active-workout-set__history"
        role="group"
        aria-label={`История подхода ${set.set_number}`}
      >
        <div className="active-workout-set__history-row">
          <span>
            <b>Предыдущий сегодня</b>
            <small>
              {previousSetNumber == null
                ? 'В этом упражнении'
                : `Подход ${previousSetNumber} · ${previousPending ? (durable ? 'сохранён на устройстве' : 'не синхронизирован') : 'завершён'}`}
            </small>
          </span>
          <strong className="active-workout-sides__history-value">
            {previousResult ?? 'Нет завершённого подхода'}
          </strong>
        </div>
        <div className="active-workout-set__history-row">
          <span>
            <b>Прошлая тренировка</b>
            <small>
              {past
                ? `Этот подход · №${past.set_number} · ${formatCalendarDate(past.performed_on, { day: '2-digit', month: '2-digit', year: 'numeric' })}`
                : 'Этот подход'}
            </small>
            {past && <small>Справочно: тип недели может отличаться</small>}
          </span>
          <strong className="active-workout-sides__history-value">{pastMessage}</strong>
        </div>
      </div>
      {isCurrent && (
        <p className="active-workout-set__context">
          <span>{prescribedReps ? `${prescribedReps} повторений` : 'Повторы по плану'}</span>
          <span aria-hidden="true">·</span>
          <span>Отдых {restSeconds} с</span>
        </p>
      )}

      <div className={`active-workout-set__controls${isCurrent ? ' has-rir' : ''}`}>
        <label className="active-workout-input">
          <span>Вес, кг</span>
          <input
            data-workout-field="weight"
            disabled={completedFieldsDisabled}
            aria-label={`Вес, ${exerciseTitle}, подход ${set.set_number}`}
            enterKeyHint="next"
            inputMode="decimal"
            type="text"
            min="0"
            step="0.01"
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
                focusWorkoutControl(rowRef.current, 'rir');
              }
            }}
            onChange={(event) => {
              const nextReps = event.target.value;
              editing.current = true;
              setReps(nextReps);
              if (!editingCompleted) enqueueSave({ reps: nextReps });
            }}
          />
        </label>
        {isCurrent && (
          <div className="active-workout-set__rir-row">
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
          </div>
        )}
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

      {isCurrent && !completed && (
        <div className="active-workout-set__prefill-actions active-workout-set__prefill-actions--history">
          <button
            className="active-workout-set__prefill"
            disabled={!canPrefill || completing}
            type="button"
            onClick={() => {
              const nextReps = canPrefillReps ? String(previousValues?.actual_reps) : reps;
              const nextWeight = canPrefillWeight ? String(previousValues?.actual_weight) : weight;
              editing.current = true;
              setReps(nextReps);
              setWeight(nextWeight);
              trackProductEvent({
                name: 'previous_set_reuse_used',
                surface: productEventSurface(),
              });
            }}
          >
            Подставить предыдущий подход сегодня
          </button>
          <button
            className="active-workout-set__prefill"
            disabled={!canPrefillPast || completing}
            type="button"
            onClick={() => {
              if (!past) return;
              const nextReps =
                reps === '' && past.actual_reps != null ? String(past.actual_reps) : reps;
              const nextWeight =
                weight === '' && past.actual_weight != null ? String(past.actual_weight) : weight;
              editing.current = true;
              setReps(nextReps);
              setWeight(nextWeight);
              void enqueueSave({ reps: nextReps, weight: nextWeight });
            }}
          >
            Подставить из прошлой тренировки
          </button>
        </div>
      )}

      {isCurrent && (
        <div className="active-workout-set__contextual-help">
          <RirContextualHelp />
        </div>
      )}

      {isCurrent && exerciseNote}

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
              disabled={disabled || completing}
              value={rir}
              onChange={(nextRir) => {
                editing.current = true;
                setRir(nextRir);
                // Completed sets allow quick metadata edits without reopening the set.
                // Keep the explicit completed state and do not start a second rest period.
                if (!editingCompleted) void enqueueSave({ rir: nextRir }, false, false);
              }}
            />
          )}

          <label className="active-workout-failure">
            <input
              type="checkbox"
              disabled={disabled || completing}
              checked={reachedFailure}
              onChange={(event) => {
                const nextReachedFailure = event.target.checked;
                editing.current = true;
                setReachedFailure(nextReachedFailure);
                if (!editingCompleted) {
                  void enqueueSave({ reachedFailure: nextReachedFailure }, false, false);
                }
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

type SideMode = 'per_side' | 'alternating';
type SideName = 'left' | 'right';
type SideFact = NonNullable<NonNullable<WorkoutSet['sides']>['left']>;
type SideDraft = {
  reps: string;
  weight: string;
  rir: RirValue | null;
  failure: boolean | null;
  completed: boolean;
  present: boolean;
};
type SidesDraft = Record<SideName, SideDraft>;

function sideDraft(value: SideFact | null | undefined): SideDraft {
  return {
    reps: value?.actual_reps == null ? '' : String(value.actual_reps),
    weight: value?.actual_weight == null ? '' : String(value.actual_weight),
    rir: value?.rir ?? null,
    failure: value?.reached_failure ?? null,
    completed: value?.is_completed ?? false,
    present: value != null,
  };
}

function sideDrafts(values: WorkoutSet['sides']): SidesDraft {
  return { left: sideDraft(values?.left), right: sideDraft(values?.right) };
}

function encodeSide(value: SideDraft): SideFact | null | undefined {
  if (!value.present) return null;
  const reps = value.reps.trim() === '' ? null : Number(value.reps);
  const weight = value.weight.trim() === '' ? null : parseDecimalDraft(value.weight);
  if (
    (reps !== null && (!Number.isInteger(reps) || reps < 0 || reps > 2147483647)) ||
    (value.weight.trim() !== '' &&
      (weight == null || weight < 0 || weight > 99999999.99 || !hasDecimalScale(value.weight, 2)))
  )
    return undefined;
  return {
    actual_reps: reps,
    actual_weight: weight,
    rir: value.rir,
    reached_failure: value.failure,
    is_completed: value.completed,
  };
}

function sideHistoryText(sides: WorkoutSet['sides']): string {
  if (!sides) return 'Нет данных по сторонам';
  return (['left', 'right'] as const)
    .map((key) => {
      const side = sides[key];
      const label = key === 'left' ? 'Левая' : 'Правая';
      if (!side) return `${label}: нет данных`;
      const value = formatSetResult(side.actual_reps, side.actual_weight) ?? 'значения не указаны';
      return `${label}: ${value}${side.rir == null ? '' : ` · RIR ${side.rir}`}${side.reached_failure ? ' · до отказа' : ''}${side.is_completed ? '' : ' · не завершена'}`;
    })
    .join('\n');
}

function sideVersionText(value: {
  execution_mode?: WorkoutSet['execution_mode'];
  first_side?: WorkoutSet['first_side'];
  sides?: WorkoutSet['sides'];
  actual_reps?: number | null;
  actual_weight?: number | null;
  rir?: RirValue | null;
  reached_failure?: boolean | null;
  is_completed: boolean;
}): string {
  const mode =
    value.execution_mode === 'per_side'
      ? 'По сторонам'
      : value.execution_mode === 'alternating'
        ? 'Поочерёдно'
        : 'Обычное';
  const first = value.first_side
    ? ` · первая: ${value.first_side === 'left' ? 'левая' : 'правая'}`
    : '';
  const state = value.is_completed ? 'подход завершён' : 'подход не завершён';
  const effort = (rir: RirValue | null | undefined, failure: boolean | null | undefined) =>
    `RIR ${rir ?? 'не указан'} · отказ ${failure == null ? 'не указан' : failure ? 'да' : 'нет'}`;
  if (!value.sides)
    return `${mode}${first} · ${state}\n${formatSetResult(value.actual_reps, value.actual_weight) ?? 'значения не указаны'} · ${effort(value.rir, value.reached_failure)}`;
  return `${mode}${first} · ${state}\n${(['left', 'right'] as const)
    .map((key) => {
      const side = value.sides?.[key];
      const label = key === 'left' ? 'Левая' : 'Правая';
      return side
        ? `${label}: ${formatSetResult(side.actual_reps, side.actual_weight) ?? 'значения не указаны'} · ${effort(side.rir, side.reached_failure)} · ${side.is_completed ? 'выполнена' : 'не завершена'}`
        : `${label}: нет данных`;
    })
    .join('\n')}`;
}

function SideWorkoutSetRow({
  set,
  mode,
  setPosition,
  setTotal,
  prescribedReps,
  disabled,
  isCurrent,
  previousSet,
  previousPending,
  pastHistory,
  historyState,
  restSeconds,
  userId,
  workoutId,
  exerciseTitle,
  pending,
  durable,
  syncing,
  exerciseNote,
  enqueue,
}: {
  set: WorkoutSet;
  mode: SideMode;
  setPosition: number;
  setTotal: number;
  prescribedReps: string | null;
  disabled: boolean;
  isCurrent: boolean;
  previousSet?: WorkoutSet;
  previousPending?: ActiveWorkoutMutation;
  pastHistory?: WorkoutSetHistory['sets'][number];
  historyState: SetHistoryState;
  restSeconds: number;
  userId?: number;
  workoutId: number;
  exerciseTitle: string;
  pending?: ActiveWorkoutMutation;
  durable: boolean;
  syncing: boolean;
  exerciseNote?: ReactNode;
  enqueue: (
    setId: number,
    serverVersion: number,
    values: ActiveWorkoutSetValues,
    immediate?: boolean,
    completing?: boolean,
  ) => Promise<boolean>;
}) {
  const { confirm } = useFeedback();
  const sourceSides = pending?.values.sides ?? set.sides;
  const [draft, setDraft] = useState<SidesDraft>(() => sideDrafts(sourceSides));
  const [splitRequested, setSplitRequested] = useState(
    () => JSON.stringify(sourceSides?.left ?? null) !== JSON.stringify(sourceSides?.right ?? null),
  );
  const [firstSide, setFirstSide] = useState<SideName | ''>(
    pending?.values.first_side ?? set.first_side ?? '',
  );
  const [editingCompleted, setEditingCompleted] = useState(false);
  const [saving, setSaving] = useState(false);
  const activeInput = useRef(false);
  const inFlight = useRef(false);
  const completed = pending?.values.is_completed ?? set.is_completed;
  const split = splitRequested || JSON.stringify(draft.left) !== JSON.stringify(draft.right);
  const setKind = pending?.values.set_kind ?? set.set_kind ?? 'working';
  const past =
    historyState === 'ready' && pastHistory?.history_status === 'matched'
      ? pastHistory.previous_workout
      : null;
  const previousMode = previousPending?.values.execution_mode ?? previousSet?.execution_mode;
  const previousSides = previousPending?.values.sides ?? previousSet?.sides;
  const pastSides = past?.execution_mode === mode ? past.sides : null;
  const canUsePrevious = previousMode === mode && !!previousSides;
  const canUsePast = past?.execution_mode === mode && !!pastSides;

  useEffect(() => {
    if (activeInput.current || editingCompleted) return;
    const incoming = pending?.values.sides ?? set.sides;
    setDraft(sideDrafts(incoming));
    setFirstSide(pending?.values.first_side ?? set.first_side ?? '');
  }, [pending, set.sides, set.first_side, set.version, editingCompleted]);

  const persist = async (
    next: SidesDraft,
    parentCompleted: boolean,
    immediate = false,
    startRest = false,
    nextFirstSide = firstSide,
  ) => {
    const left = encodeSide(next.left);
    const right = encodeSide(next.right);
    if (left === undefined || right === undefined || inFlight.current) return false;
    if (immediate) {
      inFlight.current = true;
      setSaving(true);
    }
    try {
      const accepted = await enqueue(
        set.id,
        set.version ?? 1,
        {
          actual_reps: null,
          actual_weight: null,
          rir: null,
          reached_failure: null,
          execution_mode: mode,
          first_side: mode === 'alternating' ? nextFirstSide || null : null,
          sides: { left, right },
          set_kind: setKind,
          is_completed: parentCompleted,
          confirm_mode_change: pending?.values.confirm_mode_change ?? false,
        },
        immediate,
        startRest && parentCompleted,
      );
      if (accepted && startRest && parentCompleted) {
        haptic('success');
        if (
          userId &&
          setKind === 'working' &&
          !['warmup', 'activation'].includes(set.planned_role ?? '')
        ) {
          const rest = beginMeasuredRest(userId, workoutId, set.id, restSeconds, Date.now());
          if (rest)
            window.dispatchEvent(
              new CustomEvent('fit:rest', {
                detail: {
                  workoutId,
                  setId: set.id,
                  seconds: restSeconds,
                  deadline: rest.deadline,
                },
              }),
            );
        }
      }
      return accepted;
    } finally {
      if (immediate) {
        inFlight.current = false;
        setSaving(false);
      }
    }
  };

  const update = (next: SidesDraft) => {
    setDraft(next);
    if (!editingCompleted) void persist(next, false);
  };
  const updateOne = (key: SideName, changes: Partial<SideDraft>) => {
    const next = { ...draft, [key]: { ...draft[key], ...changes, present: true } };
    update(next);
  };
  const updateBoth = (changes: Partial<SideDraft>) => {
    const shared = { ...draft.left, ...changes, present: true };
    update({ left: shared, right: { ...shared } });
  };
  const applyHistory = (sides: WorkoutSet['sides']) => {
    if (!sides) return;
    const copy = (value: SideFact | null, current: SideDraft): SideDraft => {
      if (!value?.is_completed || current.completed) return current;
      return {
        ...current,
        reps: current.reps || (value.actual_reps == null ? '' : String(value.actual_reps)),
        weight: current.weight || (value.actual_weight == null ? '' : String(value.actual_weight)),
        present: true,
      };
    };
    const next = { left: copy(sides.left, draft.left), right: copy(sides.right, draft.right) };
    setSplitRequested(JSON.stringify(next.left) !== JSON.stringify(next.right));
    update(next);
  };
  const switchToSame = async () => {
    if (JSON.stringify(draft.left) !== JSON.stringify(draft.right)) {
      const accepted = await confirm({
        title: 'Сделать значения одинаковыми?',
        message: 'Данные левой стороны заменят данные правой. Подтвердите изменение.',
        confirmText: 'Использовать левую',
        danger: false,
      });
      if (!accepted) return;
    }
    const shared = { ...draft.left, completed: completed && editingCompleted };
    setSplitRequested(false);
    update({ left: shared, right: { ...shared } });
  };
  const finish = async () => {
    const next = split
      ? draft
      : {
          left: { ...draft.left, present: true, completed: true },
          right: { ...draft.left, present: true, completed: true },
        };
    setDraft(next);
    await persist(next, true, true, true);
  };
  const reopen = async () => {
    if (
      !(await confirm({
        title: 'Вернуть подход в работу?',
        message: 'Сохранённые результаты сторон останутся.',
        confirmText: 'Вернуть в работу',
        danger: false,
      }))
    )
      return;
    await persist(draft, false, true);
  };
  const locked = disabled || saving || (completed && !editingCompleted);
  const inputs = (key: SideName, label: string, shared: boolean) => {
    const value = draft[key];
    const blocked = locked || (!shared && value.completed && !editingCompleted);
    const change = (changes: Partial<SideDraft>) =>
      shared ? updateBoth(changes) : updateOne(key, changes);
    return (
      <>
        <div className="active-workout-set__controls has-rir active-workout-sides__inputs">
          <label className="active-workout-input">
            <span>Вес · {shared ? 'на сторону' : label}, кг</span>
            <input
              data-workout-field="weight"
              aria-label={`Вес, ${shared ? 'на сторону' : label}, ${exerciseTitle}, подход ${set.set_number}`}
              type="text"
              inputMode="decimal"
              value={value.weight}
              disabled={blocked}
              onFocus={() => {
                activeInput.current = true;
              }}
              onBlur={() => {
                activeInput.current = false;
              }}
              onChange={(event) => change({ weight: event.target.value })}
            />
          </label>
          <label className="active-workout-input">
            <span>Повторы · {shared ? 'на сторону' : label}</span>
            <input
              data-workout-field="reps"
              aria-label={`Повторы, ${shared ? 'на сторону' : label}, ${exerciseTitle}, подход ${set.set_number}`}
              type="number"
              min="0"
              step="1"
              inputMode="numeric"
              value={value.reps}
              disabled={blocked}
              onFocus={() => {
                activeInput.current = true;
              }}
              onBlur={() => {
                activeInput.current = false;
              }}
              onChange={(event) => change({ reps: event.target.value })}
            />
          </label>
        </div>
        <RirSelector
          compact
          sideLabel={shared ? undefined : label}
          disabled={blocked}
          value={value.rir}
          onChange={(rir) => change({ rir })}
        />
        <label className="active-workout-failure">
          <input
            type="checkbox"
            aria-label={shared ? 'До отказа на обе стороны' : `До отказа · ${label}`}
            disabled={blocked}
            checked={value.failure === true}
            onChange={(event) => change({ failure: event.target.checked })}
          />
          <span>До отказа{shared ? ' на обе стороны' : ''}</span>
        </label>
      </>
    );
  };

  return (
    <div
      className={`active-workout-set ${isCurrent ? 'is-current' : ''} ${completed ? 'is-completed' : ''}`}
      data-workout-set-id={set.id}
      aria-current={isCurrent ? 'step' : undefined}
      aria-busy={syncing || undefined}
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
        {(formatPlannedSetRole(set.planned_role) ||
          formatPlannedGroupKind(set.planned_group_kind)) && (
          <div className="active-workout-set__roles" aria-label="Структура подхода">
            {formatPlannedSetRole(set.planned_role) && (
              <span className="active-workout-set__role">
                {formatPlannedSetRole(set.planned_role)}
              </span>
            )}
            {formatPlannedGroupKind(set.planned_group_kind) && (
              <span className="active-workout-set__role active-workout-set__role--group">
                {formatPlannedGroupKind(set.planned_group_kind)}
              </span>
            )}
          </div>
        )}
        {completed && (
          <span className="active-workout-set__complete-label">
            <CheckIcon />
            {pending ? (durable ? 'Сохранено на устройстве' : 'Не сохранено') : 'Выполнен'}
          </span>
        )}
      </div>
      <div
        className="active-workout-set__history"
        role="group"
        aria-label={`История подхода ${set.set_number}`}
      >
        <div className="active-workout-set__history-row">
          <span>
            <b>Предыдущий сегодня</b>
            <small>{previousSet ? `Подход ${previousSet.set_number}` : 'В этом упражнении'}</small>
          </span>
          <strong className="active-workout-sides__history-value">
            {canUsePrevious
              ? sideHistoryText(previousSides)
              : previousSet
                ? 'Другой способ выполнения'
                : 'Нет завершённого подхода'}
          </strong>
        </div>
        <div className="active-workout-set__history-row">
          <span>
            <b>Прошлая тренировка</b>
            <small>
              {past
                ? `Этот подход · №${past.set_number} · ${formatCalendarDate(past.performed_on, { day: '2-digit', month: '2-digit', year: 'numeric' })}`
                : 'Этот подход'}
            </small>
          </span>
          <strong className="active-workout-sides__history-value">
            {canUsePast
              ? sideHistoryText(pastSides)
              : historyState !== 'ready'
                ? 'История временно недоступна'
                : past
                  ? 'Результат без сопоставимых сторон'
                  : 'Нет прошлого результата'}
          </strong>
        </div>
      </div>
      {isCurrent && (
        <p className="active-workout-set__context">
          <span>{prescribedReps ? `${prescribedReps} повторений` : 'Повторы по плану'}</span>
          <span aria-hidden="true">·</span>
          <span>Отдых {restSeconds} с</span>
        </p>
      )}
      {completed && (
        <div className="active-workout-set__completed-actions app-action-group">
          {editingCompleted ? (
            <>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraft(sideDrafts(sourceSides));
                  setEditingCompleted(false);
                }}
              >
                Отмена
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() =>
                  void persist(draft, true, true).then((ok) => {
                    if (ok) setEditingCompleted(false);
                  })
                }
              >
                Сохранить
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                variant="ghost"
                disabled={disabled || saving}
                onClick={() => setEditingCompleted(true)}
              >
                Редактировать
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={disabled || saving}
                onClick={() => void reopen()}
              >
                Вернуть в работу
              </Button>
            </>
          )}
        </div>
      )}
      {mode === 'alternating' && (
        <label className="active-workout-advanced-field">
          <span>Первая сторона</span>
          <select
            value={firstSide}
            disabled={locked}
            onChange={(event) => {
              const next = event.target.value as SideName | '';
              setFirstSide(next);
              if (!editingCompleted) void persist(draft, false, false, false, next);
            }}
          >
            <option value="">Не указана</option>
            <option value="left">Левая</option>
            <option value="right">Правая</option>
          </select>
        </label>
      )}
      <div className="active-workout-sides__heading">
        <span>
          <b>{split ? 'Раздельно по сторонам' : 'Одинаково на обе стороны'}</b>
          <small>
            {split ? 'Вес и повторы для каждой стороны' : 'Значения относятся к каждой стороне'}
          </small>
        </span>
        <button
          type="button"
          disabled={locked}
          onClick={() => (split ? void switchToSame() : setSplitRequested(true))}
        >
          {split ? 'Одинаково' : 'Указать раздельно'}
        </button>
      </div>
      {split ? (
        (['left', 'right'] as const).map((key) => {
          const label = key === 'left' ? 'Левая' : 'Правая';
          return (
            <section
              className="active-workout-sides__side"
              key={key}
              aria-label={`${label} сторона`}
            >
              <div className="active-workout-sides__side-heading">
                <strong>{label} сторона</strong>
                <span className={draft[key].completed ? 'is-completed' : undefined}>
                  {draft[key].completed ? 'Выполнена' : 'Не завершена'}
                </span>
              </div>
              {inputs(key, label, false)}
              {!completed && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={disabled || saving}
                  onClick={() => {
                    const next = {
                      ...draft,
                      [key]: { ...draft[key], present: true, completed: !draft[key].completed },
                    };
                    setDraft(next);
                    void persist(next, false, true);
                  }}
                >
                  {draft[key].completed ? 'Изменить' : 'Отметить выполненной'}
                </Button>
              )}
            </section>
          );
        })
      ) : (
        <div className="active-workout-sides__side">
          {inputs('left', 'Левая', true)}
          <small>Завершая подход, подтверждаете обе стороны.</small>
        </div>
      )}
      {!completed && (
        <Button
          type="button"
          variant="primary"
          data-workout-field="done"
          disabled={
            disabled || saving || (split && (!draft.left.completed || !draft.right.completed))
          }
          onClick={() => void finish()}
        >
          {saving ? 'Сохраняем…' : 'Завершить подход'}
        </Button>
      )}
      {!completed && split && (!draft.left.completed || !draft.right.completed) && (
        <small>Подход будет завершён после подтверждения обеих сторон.</small>
      )}
      {isCurrent && !completed && (
        <div className="active-workout-set__prefill-actions active-workout-set__prefill-actions--history">
          <button
            className="active-workout-set__prefill"
            type="button"
            disabled={!canUsePrevious || disabled || saving}
            onClick={() => applyHistory(previousSides)}
          >
            Подставить предыдущий подход сегодня
          </button>
          <button
            className="active-workout-set__prefill"
            type="button"
            disabled={!canUsePast || disabled || saving}
            onClick={() => applyHistory(pastSides)}
          >
            Подставить из прошлой тренировки
          </button>
        </div>
      )}
      {isCurrent && <RirContextualHelp />}
      {isCurrent && exerciseNote}
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
  exerciseNote,
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
  exerciseNote?: ReactNode;
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
    const parsedDistance = nextDistance.trim() ? parseDecimalDraft(nextDistance) : null;
    if (
      nextDistance.trim() &&
      (!isCompleteDecimalDraft(nextDistance) ||
        !hasDecimalScale(nextDistance, 2) ||
        parsedDistance == null ||
        parsedDistance <= 0 ||
        parsedDistance > 1000)
    ) {
      if (immediate) {
        setValidation('Укажите дистанцию больше 0 и не больше 1000 км, до двух знаков.');
        completionInFlight.current = false;
        setCompleting(false);
      }
      return false;
    }
    try {
      const accepted = await enqueue(
        set.id,
        serverVersion,
        {
          actual_reps: null,
          actual_weight: null,
          duration_minutes: nextDuration === '' ? null : Number(nextDuration),
          distance_km: parsedDistance,
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
          aria-label="Управление выполненным интервалом"
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
            <Button
              type="button"
              disabled={disabled || completing}
              data-workout-action="reopen-completed"
              variant="secondary"
              onClick={() => void requestReopen()}
            >
              Вернуть в работу
            </Button>
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
            type="text"
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

      {isCurrent && exerciseNote}

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
  nextPosition,
  eligibleRestSourceSetIds = [],
}: {
  userId: number;
  workoutId: number;
  nextLabel: string;
  nextPosition: string;
  eligibleRestSourceSetIds?: readonly number[];
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
  const [terminalNoticeDismissed, setTerminalNoticeDismissed] = useState(false);
  const [collapsed, setCollapsed] = useState(() =>
    readStorage<boolean>(`${activeWorkoutRestKey(userId, workoutId)}:panel-collapsed`, false),
  );
  const [restRecords, setRestRecords] = useState(() => loadRestJournal(userId, workoutId));
  const [restSaveError, setRestSaveError] = useState<string | null>(null);
  const [restDialog, setRestDialog] = useState<'sync' | { recoveryId: string } | null>(null);
  const [compact, setCompact] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const panel = useRef<HTMLElement>(null);
  const restSpacer = useRef<HTMLDivElement>(null);
  const pressedPointers = useRef(new Set<number>());
  const compactWhenPointersRelease = useRef(false);
  const layoutAnchor = useRef<{ element: Element; top: number } | null>(null);
  const wasBackgrounded = useRef(
    typeof document !== 'undefined' && document.visibilityState === 'hidden',
  );
  const seconds = Math.max(0, Math.ceil((deadline - now) / 1000));
  const hasDeadline = Boolean(deadline);
  const latestRest = restRecords.at(-1) ?? null;
  const restartCandidate =
    !measuredRest &&
    latestRest &&
    (latestRest.status === 'completed' || latestRest.status === 'skipped') &&
    eligibleRestSourceSetIds.includes(latestRest.source_set_id) &&
    !restRecords.some((row) => row.restart_of_start_mutation_id === latestRest.start_mutation_id)
      ? latestRest
      : null;
  const restIsUnconfirmed = Boolean(
    measuredRest && (!measuredRest.server_id || measuredRest.pending.length),
  );
  const isRunningRest = measuredRest?.status === 'running';
  const isCompletedLatestRest = latestRest?.status === 'completed';
  const isSkippedLatestRest = latestRest?.status === 'skipped';
  const isOfflineRest = typeof navigator !== 'undefined' && !navigator.onLine;
  const restPendingLabel = isOfflineRest
    ? 'Нет сети · отдых ожидает сохранения'
    : 'Отдых сохраняется…';
  const needsReview = Boolean(measuredRest?.needs_review);
  const recoveryDialogOpen =
    needsReview &&
    typeof restDialog === 'object' &&
    restDialog?.recoveryId === measuredRest?.start_mutation_id;
  const syncDialogOpen = restDialog === 'sync';
  const restDialogOpen = recoveryDialogOpen || syncDialogOpen;
  const restDialogTitle = recoveryDialogOpen ? 'Сколько отдыхали?' : 'Сохранение отдыха';
  const restDialogRef = useModalA11y<HTMLDivElement>(
    restDialogOpen,
    () => setRestDialog(null),
    recoveryDialogOpen ? 'input' : '.active-workout-rest-dialog__close',
  );
  const terminalRestLabel =
    completedNotice === 'Отдых завершён по отметке' ||
    completedNotice === 'Отдых сохранён по вашей отметке'
      ? 'Отдых завершён'
      : (completedNotice?.split(' · ')[0] ??
        (isSkippedLatestRest ? 'Отдых пропущен' : 'Отдых завершён'));
  const hasPendingRest =
    restIsUnconfirmed ||
    Boolean(!measuredRest && latestRest && (!latestRest.server_id || latestRest.pending.length));
  let collapsedRestStatus = seconds === 0 ? 'План готов' : 'Отдых идёт';
  if (restSaveError) {
    collapsedRestStatus = restSaveError.startsWith('Конфликт')
      ? 'Конфликт сохранения'
      : 'Ошибка сохранения';
  } else if (isOfflineRest) {
    collapsedRestStatus = 'Нет сети';
  } else if (hasPendingRest) {
    collapsedRestStatus = 'Сохраняется…';
  }
  const restoredTerminal = !deadline && !completedNotice && Boolean(restartCandidate);
  const showCompact = compact || restoredTerminal;
  const restPanelClassName = [
    'active-workout-rest',
    completedNotice || restoredTerminal ? 'active-workout-rest--complete' : null,
    isRunningRest && seconds === 0 && !needsReview ? 'active-workout-rest--expired' : null,
    showCompact || collapsed || needsReview ? 'is-compact' : null,
    needsReview ? 'active-workout-rest--review' : null,
    terminalNoticeDismissed ? 'active-workout-rest--dismissed' : null,
    showCompact && !(collapsed && isRunningRest) ? 'active-workout-rest--terminal' : null,
    showCompact && !restartCandidate && !terminalNoticeDismissed
      ? 'active-workout-rest--terminal-single'
      : null,
  ]
    .filter(Boolean)
    .join(' ');
  const measuredElapsedSeconds =
    measuredRest && !measuredRest.needs_review
      ? Math.max(0, Math.floor((now - Date.parse(measuredRest.started_at)) / 1000))
      : 0;
  const captureLayoutAnchor = useCallback(() => {
    const element = panel.current?.parentElement?.querySelector('.active-workout-exercises');
    if (element) layoutAnchor.current = { element, top: element.getBoundingClientRect().top };
  }, []);
  const restoreLayoutAnchor = useCallback(() => {
    const anchor = layoutAnchor.current;
    if (!anchor) return;
    const spacer = restSpacer.current;
    // WebKit can resize the fixed panel before its inherited spacer height is committed.
    if (
      spacer?.getClientRects().length &&
      spacer.getBoundingClientRect().height !== panel.current?.getBoundingClientRect().height
    )
      return;
    layoutAnchor.current = null;
    if (anchor.element.isConnected) {
      const delta = anchor.element.getBoundingClientRect().top - anchor.top;
      if (delta) window.scrollBy({ top: delta, behavior: 'instant' });
    }
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
      setTerminalNoticeDismissed(false);
      setCompact(false);
      setCollapsed(false);
      writeStorage(`${storageKey}:panel-collapsed`, false);
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
      void syncRestJournal(userId, workoutId, (status) => {
        setRestSaveError(
          status === 409
            ? 'Конфликт сохранения отдыха. Данные сохранены на устройстве.'
            : 'Сервер временно недоступен. Данные отдыха сохранены на устройстве и ожидают синхронизации.',
        );
      })
        .then(() => {
          if (!hasPending()) setRestSaveError(null);
        })
        .catch((error: unknown) => {
          setRestSaveError(
            error instanceof ApiError && error.status === 409
              ? 'Конфликт сохранения отдыха. Данные сохранены на устройстве.'
              : 'Не удалось сохранить отдых. Запись остаётся на устройстве.',
          );
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
      setRestRecords(loadRestJournal(userId, workoutId));
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
    window.addEventListener('offline', reconcile);
    window.addEventListener('pageshow', reconcile);
    return () => {
      unsubscribe();
      window.removeEventListener('online', reconcile);
      window.removeEventListener('offline', reconcile);
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
    const element = panel.current;
    const parent = element?.parentElement;
    if (!element || !parent) return;
    const updateClearance = () => {
      const height = element.getBoundingClientRect().height;
      if (height > 0) {
        // A viewport-fixed mobile timer still reserves its full height in the workout grid.
        // The focus clearance remains larger than the visible panel for keyboard access.
        parent.style.setProperty('--yfc-active-workout-rest-clearance', `${height + 20}px`);
        parent.style.setProperty('--yfc-active-workout-rest-spacer-height', `${height}px`);
      }
      // Measure the workout column rather than the viewport: the panel must keep the
      // same horizontal alignment without tracking vertical scroll frame by frame.
      const bounds = parent.getBoundingClientRect();
      if (bounds.width > 0) {
        element.style.setProperty('--yfc-active-workout-rest-fixed-width', `${bounds.width}px`);
        const width = Math.min(bounds.width, element.getBoundingClientRect().width);
        element.style.setProperty(
          '--yfc-active-workout-rest-fixed-left',
          `${bounds.left + (bounds.width - width) / 2}px`,
        );
      }
    };
    updateClearance();
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            updateClearance();
            restoreLayoutAnchor();
          });
    observer?.observe(element);
    observer?.observe(parent);
    window.addEventListener('resize', updateClearance);
    window.visualViewport?.addEventListener('resize', updateClearance);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', updateClearance);
      window.visualViewport?.removeEventListener('resize', updateClearance);
      parent.style.removeProperty('--yfc-active-workout-rest-clearance');
      parent.style.removeProperty('--yfc-active-workout-rest-spacer-height');
      element.style.removeProperty('--yfc-active-workout-rest-fixed-left');
      element.style.removeProperty('--yfc-active-workout-rest-fixed-width');
    };
  }, [hasDeadline, collapsed, showCompact, completedNotice, restoreLayoutAnchor]);

  useLayoutEffect(() => {
    restoreLayoutAnchor();
  }, [collapsed, showCompact, completedNotice, restoreLayoutAnchor]);

  useEffect(() => {
    const element = panel.current;
    const root = element?.parentElement;
    if (!element || !root) return;
    // Telegram owns keyboard resizing but not the sticky timer's occlusion area.
    // Recheck when an input takes focus and when the WebView keyboard changes size.
    const keepFocusedInputClear = () => {
      if (document.documentElement.dataset.yfcLayoutSurface !== 'telegram') return;
      const focused = document.activeElement;
      if (!(focused instanceof HTMLInputElement) || !root.contains(focused)) return;
      const top = focused.getBoundingClientRect().top;
      const clearance = element.getBoundingClientRect().bottom + 12;
      if (top < clearance) window.scrollBy({ top: top - clearance, behavior: 'instant' });
    };
    root.addEventListener('focusin', keepFocusedInputClear);
    window.visualViewport?.addEventListener('resize', keepFocusedInputClear);
    return () => {
      root.removeEventListener('focusin', keepFocusedInputClear);
      window.visualViewport?.removeEventListener('resize', keepFocusedInputClear);
    };
  }, [hasDeadline, collapsed, showCompact, completedNotice]);

  if (!deadline && !completedNotice && !restartCandidate) return null;
  const restStatus = (
    <button
      type="button"
      className="active-workout-rest__status"
      aria-haspopup="dialog"
      aria-label={`Состояние отдыха: ${collapsedRestStatus}. Подробнее`}
      onClick={(event) => {
        // A second click from restart must not activate a newly placed control.
        if (event.detail > 1) return;
        event.currentTarget.focus();
        setRestDialog('sync');
      }}
    >
      {(hasPendingRest || restSaveError || isOfflineRest) && (
        <Icon name={restSaveError || isOfflineRest ? 'warning' : 'sync'} size={16} />
      )}
      <span role="status">{collapsedRestStatus}</span>
    </button>
  );
  const restPanel = (
    <aside
      ref={panel}
      {...glassProps('tinted')}
      className={restPanelClassName}
      aria-label="Отдых между подходами"
      onMouseDown={(event) => {
        if (event.target instanceof Element && event.target.closest('button'))
          event.preventDefault();
      }}
      onClick={(event) => event.stopPropagation()}
    >
      {needsReview ? (
        <div className="active-workout-rest__review">
          <Icon name="warning" size={20} />
          <div>
            <strong>Уточнить отдых</strong>
            <span>Время в фоне не засчитано</span>
          </div>
          <Button
            type="button"
            aria-haspopup="dialog"
            onClick={(event) => {
              if (event.detail > 1) return;
              event.currentTarget.focus();
              if (measuredRest) setRestDialog({ recoveryId: measuredRest.start_mutation_id });
            }}
          >
            Уточнить
          </Button>
        </div>
      ) : collapsed && isRunningRest ? (
        <div className="active-workout-rest__collapsed">
          <div>
            <strong role="status">{collapsedRestStatus}</strong>
            <span className="active-workout-rest__collapsed-times">
              Осталось{' '}
              <span role="timer" aria-label="Отдых" aria-live="off">
                {formatWorkoutDuration(seconds)}
              </span>
              {' · '}
              <span>ФАКТ {formatWorkoutDuration(measuredElapsedSeconds)}</span>
            </span>
          </div>
          <Button
            type="button"
            variant="secondary"
            aria-label="Развернуть таймер"
            onClick={(event) => {
              if (event.detail > 1) return;
              captureLayoutAnchor();
              setCollapsed(false);
              writeStorage(`${storageKey}:panel-collapsed`, false);
            }}
          >
            Развернуть
          </Button>
        </div>
      ) : (
        <>
          {!showCompact && (
            <div className="active-workout-rest__top">
              <div className="active-workout-rest__time">
                <span>ОСТАЛОСЬ</span>
                <strong
                  role={completedNotice ? undefined : 'timer'}
                  aria-label="Отдых"
                  aria-live="off"
                >
                  {formatWorkoutDuration(seconds)}
                </strong>
              </div>
              {measuredRest && (
                <div className="active-workout-rest__actual">
                  <div className="active-workout-rest__actual-value">
                    <span>ФАКТ</span>
                    <strong aria-label="Время по отметке пользователя" aria-live="off">
                      {formatWorkoutDuration(measuredElapsedSeconds)}
                    </strong>
                  </div>
                </div>
              )}
              {restStatus}
              {isRunningRest && (
                <Button
                  type="button"
                  variant="ghost"
                  className="active-workout-rest__collapse"
                  aria-label="Свернуть таймер"
                  onClick={(event) => {
                    if (event.detail > 1) return;
                    captureLayoutAnchor();
                    setCollapsed(true);
                    writeStorage(`${storageKey}:panel-collapsed`, true);
                  }}
                >
                  <Icon name="chevron-up" size={20} />
                </Button>
              )}
            </div>
          )}
          <div className="active-workout-rest__actions" hidden={showCompact}>
            {[30, 60].map((extraSeconds) => (
              <Button
                key={extraSeconds}
                aria-label={`+${extraSeconds} сек`}
                type="button"
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
            {measuredRest && !measuredRest.needs_review && (
              <Button
                className="active-workout-rest__stop"
                type="button"
                aria-label="Стоп: завершить отдых"
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
              </Button>
            )}
            <Button
              type="button"
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
          {showCompact && (
            <>
              {!terminalNoticeDismissed && (
                <button
                  type="button"
                  className="active-workout-rest__complete-summary"
                  aria-haspopup="dialog"
                  onClick={(event) => {
                    if (event.detail > 1) return;
                    event.currentTarget.focus();
                    setRestDialog('sync');
                  }}
                >
                  {(hasPendingRest ||
                    restSaveError ||
                    isOfflineRest ||
                    terminalRestLabel.startsWith('Нет')) && (
                    <span className="active-workout-rest__complete-mark" aria-hidden="true">
                      <Icon
                        name={
                          restSaveError || isOfflineRest || terminalRestLabel.startsWith('Нет')
                            ? 'warning'
                            : 'sync'
                        }
                        size={16}
                      />
                    </span>
                  )}
                  <span className="active-workout-rest__complete-copy">{terminalRestLabel}</span>
                  {isCompletedLatestRest && latestRest?.measured_seconds != null && (
                    <span className="active-workout-rest__complete-copy">
                      ФАКТ {formatWorkoutDuration(latestRest.measured_seconds)}
                    </span>
                  )}
                </button>
              )}
              {(restartCandidate || !terminalNoticeDismissed) && (
                <div className="active-workout-rest__complete-actions">
                  {restartCandidate && (
                    <Button
                      type="button"
                      onClick={() => {
                        if (
                          !restartCandidate ||
                          restRecords.some((row) => row.status === 'running')
                        )
                          return;
                        const started = restartMeasuredRest(
                          userId,
                          workoutId,
                          restartCandidate.start_mutation_id,
                          Date.now(),
                        );
                        if (!started) return;
                        setNow(Date.now());
                        setMeasuredRest(started);
                        setDeadline(started.deadline);
                        setCompletedNotice(null);
                        setTerminalNoticeDismissed(false);
                        setCompact(false);
                        setCollapsed(false);
                        setRestSaveError(null);
                        setAnnouncement('Новый интервал отдыха');
                        writeStorage(storageKey, started.deadline);
                        writeStorage(`${storageKey}:panel-collapsed`, false);
                      }}
                    >
                      Новый отдых
                    </Button>
                  )}
                  {!terminalNoticeDismissed && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => {
                        captureLayoutAnchor();
                        setTerminalNoticeDismissed(Boolean(restartCandidate));
                        setCompletedNotice(null);
                        setCompact(false);
                      }}
                    >
                      Скрыть
                    </Button>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
      <span className="sr-only" role="status" aria-atomic="true">
        {needsReview
          ? 'Уточните длительность отдыха или не учитывайте замер'
          : (completedNotice ?? announcement)}
      </span>
    </aside>
  );
  return (
    <>
      {restPanel}
      <div ref={restSpacer} className="active-workout-rest-spacer" aria-hidden="true" />
      {restDialogOpen &&
        createPortal(
          <div
            className="modal app-section--design-v2 active-workout-rest-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`rest-dialog-title-${workoutId}`}
            aria-describedby={`rest-dialog-description-${workoutId}`}
          >
            <button
              type="button"
              className="modal__backdrop"
              aria-label="Закрыть сведения об отдыхе"
              onClick={(event) => {
                if (event.detail <= 1) setRestDialog(null);
              }}
            />
            <div
              className="modal__panel active-workout-rest-dialog__panel"
              ref={restDialogRef}
              tabIndex={-1}
            >
              <header className="active-workout-rest-dialog__header">
                <h2 id={`rest-dialog-title-${workoutId}`}>{restDialogTitle}</h2>
                <IconButton
                  type="button"
                  className="active-workout-rest-dialog__close"
                  aria-label="Закрыть сведения об отдыхе"
                  onClick={() => setRestDialog(null)}
                >
                  <CloseIcon />
                </IconButton>
              </header>
              {recoveryDialogOpen && measuredRest?.needs_review && (
                <section
                  className="active-workout-rest__recovery"
                  role="group"
                  aria-label="Уточнение фактического отдыха"
                >
                  <p id={`rest-dialog-description-${workoutId}`}>
                    Приложение было неактивно, поэтому прошедшее время не считается достоверным
                    замером.
                  </p>
                  <label htmlFor={`rest-recovery-${workoutId}`}>Фактическое время, минуты</label>
                  <input
                    aria-invalid={Boolean(recoveryValidation)}
                    aria-describedby={
                      recoveryValidation ? `rest-recovery-error-${workoutId}` : undefined
                    }
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
                  {recoveryValidation && (
                    <span id={`rest-recovery-error-${workoutId}`} role="alert">
                      {recoveryValidation}
                    </span>
                  )}
                  <div className="active-workout-rest__recovery-actions">
                    <Button
                      variant="secondary"
                      type="button"
                      onClick={() => {
                        updateMeasuredRest(userId, workoutId, measuredRest.source_set_id, 'skip');
                        setMeasuredRest(null);
                        removeStorage(storageKey);
                        setDeadline(0);
                        setCompletedNotice('Отдых не учитывается');
                        setRestDialog(null);
                        compactNotice();
                      }}
                    >
                      Не учитывать
                    </Button>
                    <Button
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
                          setRecoveryValidation(
                            'Не удалось сохранить уточнение. Попробуйте ещё раз.',
                          );
                          return;
                        }
                        setMeasuredRest(null);
                        removeStorage(storageKey);
                        setDeadline(0);
                        setCompletedNotice('Отдых сохранён по вашей отметке');
                        setRestDialog(null);
                        compactNotice();
                      }}
                    >
                      Сохранить время
                    </Button>
                  </div>
                </section>
              )}

              {syncDialogOpen && (
                <p
                  id={`rest-dialog-description-${workoutId}`}
                  role={restSaveError ? 'alert' : 'status'}
                >
                  {restSaveError ??
                    (hasPendingRest
                      ? `${restPendingLabel}. Данные сохранены на устройстве и ожидают синхронизации.`
                      : isOfflineRest
                        ? 'Нет сети. Таймер продолжает работать. Данные сохранены на устройстве.'
                        : 'Данные отдыха синхронизированы.')}
                </p>
              )}
            </div>
          </div>,
          document.body,
        )}
    </>
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
  const [executionModes, setExecutionModes] = useState<Record<number, 'bilateral' | SideMode>>({});
  const [modeChoicesOpen, setModeChoicesOpen] = useState<Set<number>>(() => new Set());
  const [modeSaving, setModeSaving] = useState<Set<number>>(() => new Set());
  const workout = useQuery({
    queryKey: ['workout', 'today'],
    queryFn: () => api<Workout>('/api/v1/workouts/today'),
    initialData: () => (user ? loadCurrentActiveWorkoutSnapshot(user.id) : undefined),
    initialDataUpdatedAt: 0,
    refetchOnReconnect: false,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 1,
  });
  const activeSync = useActiveWorkoutQueue(user?.id, workout.data);
  const online = useOnlineStatus();
  const historyEnabled = Boolean(
    user?.id &&
    workout.data &&
    online &&
    !workout.isFetching &&
    !workout.isError &&
    activeSync.pendingCount === 0 &&
    !['pending', 'syncing', 'offline', 'error', 'conflict'].includes(activeSync.syncState),
  );
  const setHistory = useQuery({
    queryKey: ['workout', 'set-history', user?.id, workout.data?.id, workout.dataUpdatedAt],
    queryFn: ({ signal }) =>
      api<WorkoutSetHistory>(`/api/v1/workouts/${workout.data!.id}/set-history`, {
        signal,
        cache: 'no-store',
      }),
    enabled: historyEnabled,
    retry: false,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  });
  const historyState: SetHistoryState = !online
    ? 'offline'
    : workout.isError || ['error', 'conflict'].includes(activeSync.syncState) || setHistory.isError
      ? 'unavailable'
      : !historyEnabled || setHistory.isFetching || setHistory.isPending
        ? 'loading'
        : 'ready';
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
    let manualScroll = false;
    let pointerStartY = 0;
    let correctionPending = false;
    let focusedRow: Element | null = null;
    let focusResetFrame: number | undefined;
    const telegramSurface = isTelegramSurface();
    const standalonePwa = !telegramSurface && isPwaStandalone();
    const root = document.documentElement;
    let focusPlacementPending = false;
    let focusGeometry: number[] = [];
    if (standalonePwa) root.dataset.yfcPwaFocusPlacement = 'true';
    const safeArea = standalonePwa ? document.createElement('div') : null;
    if (safeArea) {
      safeArea.style.cssText =
        'position:fixed;visibility:hidden;pointer-events:none;height:var(--yfc-layout-safe-top,0px)';
      document.body.append(safeArea);
    }
    const keepFieldsVisible = () => {
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (manualScroll) return;
        // Only focus owns PWA placement; typing/ACK and native pan must not restart it.
        if (standalonePwa && !focusPlacementPending) return;
        // A pressed control must stay under the pointer until its click is delivered.
        if (pointerActive) {
          correctionPending = true;
          return;
        }
        correctionPending = false;
        const editingRir = document.activeElement?.matches('.active-workout-rir button');
        if (!editingWorkoutField() && !editingRir) return;
        if (standalonePwa && editingWorkoutField()) {
          // Standalone iOS owns focus visibility; app scroll would compete with native keyboard pan.
          focusPlacementPending = false;
          return;
        }
        const input = document.activeElement as HTMLElement;
        const controls = input.closest('.active-workout-set__controls') ?? input;
        const box = controls.getBoundingClientRect();
        const inputBox = input.getBoundingClientRect();
        // iOS can settle the visual viewport by a small fraction of the field height.
        const visibilityTolerance = standalonePwa ? Math.max(1, inputBox.height * 0.05) : 1;
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop ?? 0;
        let bottom = top + (viewport?.height ?? window.innerHeight);
        const timer = document.querySelector('.active-workout-rest')?.getBoundingClientRect();
        let safeTop = top + (safeArea?.getBoundingClientRect().height ?? 0);
        if (!standalonePwa && timer && timer.bottom > top && timer.top < bottom)
          safeTop = Math.max(safeTop, timer.bottom);
        if (standalonePwa) {
          const dockElement = document.getElementById('appBottomNav');
          const dock = dockElement?.getBoundingClientRect();
          if (
            dockElement &&
            getComputedStyle(dockElement).visibility !== 'hidden' &&
            dock &&
            dock.height > 0 &&
            dock.top > safeTop
          )
            bottom = Math.min(bottom, dock.top);
          // Do not reserve a sticky panel that is not covering the active field.
          if (
            timer &&
            timer.bottom > top &&
            timer.top < bottom &&
            timer.bottom > inputBox.top &&
            timer.top < inputBox.bottom
          )
            safeTop = Math.max(safeTop, timer.bottom);
          const geometry = [top, bottom, safeTop, window.scrollY, inputBox.top, inputBox.bottom];
          if (
            geometry.some(
              (value, index) => Math.abs(value - (focusGeometry[index] ?? Infinity)) > 0.5,
            )
          ) {
            focusGeometry = geometry;
            // Measure native focus geometry before correcting an occluded field.
            keepFieldsVisible();
            return;
          }
          if (
            inputBox.top >= safeTop - visibilityTolerance &&
            inputBox.bottom <= bottom + visibilityTolerance
          )
            return;
        }
        const topOccluded = inputBox.top < safeTop - visibilityTolerance;
        const target =
          standalonePwa && !topOccluded
            ? inputBox
            : box.height <= bottom - safeTop
              ? box
              : inputBox;
        const delta =
          target.top < safeTop ? target.top - safeTop : Math.max(0, target.bottom - bottom);
        // Ignore subpixel observer noise; visible displacement still gets corrected.
        if (Math.abs(delta) > 1) {
          window.scrollBy({ top: delta, behavior: 'instant' });
        }
      });
    };
    const pointerDown = (event: PointerEvent) => {
      pointerActive = true;
      manualScroll = false;
      pointerStartY = event.clientY;
    };
    const pointerMove = (event: PointerEvent) => {
      if (!pointerActive || Math.abs(event.clientY - pointerStartY) <= 8) return;
      manualScroll = true;
      focusPlacementPending = false;
      correctionPending = false;
    };
    const pointerEnd = () => {
      pointerActive = false;
      if (manualScroll) {
        correctionPending = false;
        return;
      }
      if (correctionPending) keepFieldsVisible();
    };
    const viewport = window.visualViewport;
    let viewportTop = viewport?.offsetTop;
    let viewportHeight = viewport?.height ?? window.innerHeight;
    let windowHeight = window.innerHeight;
    const panViewport = () => {
      const nextTop = viewport?.offsetTop ?? 0;
      if (nextTop === viewportTop) return;
      viewportTop = nextTop;
      if (standalonePwa) {
        if (focusPlacementPending) keepFieldsVisible();
        return;
      }
      keepFieldsVisible();
    };
    const resizeViewport = () => {
      const nextHeight = viewport?.height ?? window.innerHeight;
      const changed = Math.abs(nextHeight - viewportHeight) > 0.5;
      viewportHeight = nextHeight;
      if (!standalonePwa || changed) {
        keepFieldsVisible();
      }
    };
    const resizeWindow = () => {
      const changed = Math.abs(window.innerHeight - windowHeight) > 0.5;
      windowHeight = window.innerHeight;
      if (!standalonePwa || changed) {
        keepFieldsVisible();
      }
    };
    const observer = new ResizeObserver(keepFieldsVisible);
    const scrollWindow = () => {
      if (standalonePwa && focusPlacementPending) keepFieldsVisible();
    };
    const focus = () => {
      manualScroll = false;
      focusPlacementPending = true;
      focusGeometry = [];
      observer.disconnect();
      const row = document.activeElement?.closest('.active-workout-set');
      if (
        row &&
        (editingWorkoutField() || document.activeElement?.matches('.active-workout-rir button'))
      ) {
        if (focusedRow !== row) {
          // Stop an in-flight completion scroll before the keyboard takes over positioning.
          if (!standalonePwa)
            window.scrollTo({ top: window.scrollY, left: window.scrollX, behavior: 'instant' });
          focusedRow = row;
        }
        observer.observe(row);
      } else {
        focusedRow = null;
      }
      keepFieldsVisible();
    };
    const focusOut = () => {
      if (focusResetFrame !== undefined) window.cancelAnimationFrame(focusResetFrame);
      focusResetFrame = window.requestAnimationFrame(() => {
        focusResetFrame = undefined;
        if (
          !editingWorkoutField() &&
          !document.activeElement?.matches('.active-workout-rir button')
        ) {
          focusedRow = null;
          focusPlacementPending = false;
        }
      });
    };
    const input = () => {
      focusPlacementPending = false;
    };
    document.addEventListener('focusin', focus);
    document.addEventListener('focusout', focusOut);
    document.addEventListener('input', input, true);
    document.addEventListener('pointerdown', pointerDown, true);
    document.addEventListener('pointermove', pointerMove, true);
    document.addEventListener('pointerup', pointerEnd, true);
    document.addEventListener('pointercancel', pointerEnd, true);
    viewport?.addEventListener('resize', resizeViewport);
    viewport?.addEventListener('scroll', panViewport);
    window.addEventListener('resize', resizeWindow);
    window.addEventListener('scroll', scrollWindow, { passive: true });
    return () => {
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      if (focusResetFrame !== undefined) window.cancelAnimationFrame(focusResetFrame);
      observer.disconnect();
      safeArea?.remove();
      if (standalonePwa) delete root.dataset.yfcPwaFocusPlacement;
      document.removeEventListener('focusin', focus);
      document.removeEventListener('focusout', focusOut);
      document.removeEventListener('input', input, true);
      document.removeEventListener('pointerdown', pointerDown, true);
      document.removeEventListener('pointermove', pointerMove, true);
      document.removeEventListener('pointerup', pointerEnd, true);
      document.removeEventListener('pointercancel', pointerEnd, true);
      viewport?.removeEventListener('resize', resizeViewport);
      viewport?.removeEventListener('scroll', panViewport);
      window.removeEventListener('resize', resizeWindow);
      window.removeEventListener('scroll', scrollWindow);
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
    // Let the newly-current RIR row and the rest timer settle before taking
    // the one allowed completion-navigation scroll measurement.
    let layoutFrame: number | null = null;
    const frame = window.requestAnimationFrame(() => {
      layoutFrame = window.requestAnimationFrame(() => {
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
        // Keep the newly active controls fully within the available viewport.
        // Taller RIR controls must not be pushed under the sticky timer just to
        // clear the following (non-current) set from the dock.
        const minScroll = box.bottom - safeBottom;
        const maxScroll = box.top - safeTop;
        if (minScroll <= maxScroll) {
          delta = Math.max(minScroll, Math.min(delta, maxScroll));
        }
        window.scrollBy({ top: Math.ceil(delta), behavior: 'instant' });
      });
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (layoutFrame !== null) window.cancelAnimationFrame(layoutFrame);
    };
  }, [completionNavigation, currentSetId]);

  useEffect(() => {
    if (!isTelegramSurface() && isPwaStandalone()) return;
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
      const viewportBottom = (viewport?.offsetTop ?? 0) + (viewport?.height ?? innerHeight);
      const bottom = Math.min(viewportBottom, dock.top) - 8;
      const nextRow = row.nextElementSibling;
      const next = nextRow?.querySelector('[data-workout-field="done"]')?.getBoundingClientRect();
      const nextTop = nextRow?.getBoundingClientRect().top;
      const visibleNext = nextTop != null && nextTop < viewportBottom;
      const rir = row.querySelector('.active-workout-rir--quick')?.getBoundingClientRect();
      const overlap = Math.max(
        0,
        controls.bottom - bottom,
        visibleNext && next ? next.bottom - bottom : 0,
      );
      const availableScroll = Math.min(controls.top, rir?.top ?? controls.top) - top;
      // Keep current controls visible when both sets cannot fit above the dock.
      if (visibleNext && next && next.bottom > bottom && overlap > availableScroll) {
        const hideNext = viewportBottom - nextTop + 1;
        if (hideNext <= bottom - controls.bottom) {
          window.scrollBy({ top: -Math.ceil(hideNext), behavior: 'instant' });
          return;
        }
      }
      const delta = Math.min(overlap, availableScroll);
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
              {data.source_cycle_week != null && data.week_type_known && (
                <p>
                  Неделя {data.week_number} ·{' '}
                  {data.week_type
                    ? `${weekTypeLabels[data.week_type]} неделя`
                    : 'тип недели не задан'}
                </p>
              )}
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
            nextPosition={
              currentSet
                ? `Подход ${currentSet.set.set_number} из ${currentSet.exercise.sets.length}`
                : 'Все подходы отмечены'
            }
            eligibleRestSourceSetIds={data.exercises.flatMap((exercise) =>
              exercise.metric_type === 'cardio' || exercise.rest_seconds <= 0
                ? []
                : exercise.sets
                    .filter(
                      (set) =>
                        set.is_completed &&
                        (set.set_kind ?? 'working') === 'working' &&
                        !['warmup', 'activation'].includes(set.planned_role ?? ''),
                    )
                    .map((set) => set.id),
            )}
          />
        )}

        <PreviousWorkoutNote workoutId={data.id} />

        {user && capabilities.canMutatePrograms && (
          <ExerciseNoteRecovery userId={user.id} workout={data} />
        )}

        <div className="active-workout-exercises">
          {data.exercises.map((exercise, exerciseIndex) => {
            const metricType = exercise.metric_type === 'cardio' ? 'cardio' : 'strength';
            const modeTarget =
              currentSet?.exercise.id === exercise.id
                ? currentSet.set
                : exercise.sets.find(
                    (item) =>
                      !(
                        activeSync.pendingBySet.get(item.id)?.values.is_completed ??
                        item.is_completed
                      ),
                  );
            const targetPending = modeTarget
              ? activeSync.pendingBySet.get(modeTarget.id)?.values
              : undefined;
            const targetMode = targetPending?.execution_mode ?? modeTarget?.execution_mode;
            const lastExplicitMode = [...exercise.sets]
              .reverse()
              .map(
                (item) =>
                  activeSync.pendingBySet.get(item.id)?.values.execution_mode ??
                  item.execution_mode,
              )
              .find((mode) => mode != null);
            const executionMode =
              executionModes[exercise.id] ?? targetMode ?? lastExplicitMode ?? 'bilateral';
            const supportsSides = !!modeTarget && Object.hasOwn(modeTarget, 'sides');
            const modeBusy = modeSaving.has(exercise.id);
            const chooseExecutionMode = async (nextMode: 'bilateral' | SideMode) => {
              if (!modeTarget || !supportsSides || !started || activeSync.sideConflict || modeBusy)
                return;
              if (nextMode === targetMode) {
                setExecutionModes((current) => ({ ...current, [exercise.id]: nextMode }));
                setModeChoicesOpen((current) => {
                  const next = new Set(current);
                  next.delete(exercise.id);
                  return next;
                });
                return;
              }
              const existing = targetPending ?? modeTarget;
              const hasFacts =
                existing.is_completed ||
                existing.actual_reps != null ||
                existing.actual_weight != null ||
                existing.rir != null ||
                existing.reached_failure != null ||
                (!!existing.sides &&
                  [existing.sides.left, existing.sides.right].some(
                    (side) =>
                      side &&
                      (side.is_completed ||
                        side.actual_reps != null ||
                        side.actual_weight != null ||
                        side.rir != null ||
                        side.reached_failure != null),
                  ));
              if (
                hasFacts &&
                !(await confirm({
                  title: 'Изменить способ выполнения?',
                  message:
                    'Введённые данные этого незавершённого подхода будут очищены. Завершённые подходы не изменятся.',
                  confirmText: 'Изменить и очистить',
                  danger: false,
                }))
              )
                return;
              setModeSaving((current) => new Set(current).add(exercise.id));
              try {
                const accepted = await enqueueSet(
                  modeTarget.id,
                  modeTarget.version ?? 1,
                  {
                    actual_reps: null,
                    actual_weight: null,
                    rir: null,
                    reached_failure: null,
                    execution_mode: nextMode,
                    first_side: null,
                    sides: nextMode === 'bilateral' ? null : { left: null, right: null },
                    confirm_mode_change: true,
                    set_kind: existing.set_kind ?? 'working',
                    is_completed: false,
                  },
                  true,
                  false,
                );
                if (accepted) {
                  for (const other of exercise.sets) {
                    if (other.id === modeTarget.id) continue;
                    const pending = activeSync.pendingBySet.get(other.id)?.values;
                    const value = pending ?? other;
                    const sideHasFacts =
                      value.sides &&
                      [value.sides.left, value.sides.right].some(
                        (side) =>
                          side &&
                          (side.is_completed ||
                            side.actual_reps != null ||
                            side.actual_weight != null ||
                            side.rir != null ||
                            side.reached_failure != null),
                      );
                    if (
                      value.is_completed ||
                      value.actual_reps != null ||
                      value.actual_weight != null ||
                      value.rir != null ||
                      value.reached_failure != null ||
                      sideHasFacts
                    )
                      continue;
                    const saved = await activeSync.enqueue(
                      other.id,
                      other.version ?? 1,
                      {
                        actual_reps: null,
                        actual_weight: null,
                        rir: null,
                        reached_failure: null,
                        execution_mode: nextMode,
                        first_side: null,
                        sides: nextMode === 'bilateral' ? null : { left: null, right: null },
                        confirm_mode_change: true,
                        set_kind: value.set_kind ?? 'working',
                        is_completed: false,
                      },
                      true,
                      true,
                    );
                    if (!saved) {
                      toast(
                        'Не удалось сохранить способ выполнения для всех незаполненных подходов.',
                        'error',
                      );
                      break;
                    }
                  }
                  setExecutionModes((current) => ({ ...current, [exercise.id]: nextMode }));
                  setModeChoicesOpen((current) => {
                    const next = new Set(current);
                    next.delete(exercise.id);
                    return next;
                  });
                  if (navigator.onLine)
                    void queryClient.invalidateQueries({
                      queryKey: ['workout', 'today'],
                      exact: true,
                    });
                }
              } finally {
                setModeSaving((current) => {
                  const next = new Set(current);
                  next.delete(exercise.id);
                  return next;
                });
              }
            };
            const exerciseCompleted = exercise.sets.filter(
              (set) => activeSync.pendingBySet.get(set.id)?.values.is_completed ?? set.is_completed,
            ).length;
            const canReplaceExercise =
              started &&
              capabilities.canMutatePrograms &&
              !hasWorkoutExecutionEvidence(exercise, activeSync.pendingBySet);
            const replacementBlockedByExecution =
              started && capabilities.canMutatePrograms && !canReplaceExercise;
            const isPersistedComplete = shouldCollapseCompletedExercise(exercise.sets, (setId) =>
              activeSync.pendingBySet.has(setId),
            );
            const isCurrentExercise = currentSet?.exercise.id === exercise.id;
            const exerciseOpen = isCurrentExercise || expandedExercises.has(exercise.id);
            const exerciseNote =
              user && started && capabilities.canMutatePrograms ? (
                <ExerciseExecutionNote
                  key={`${user.id}-${data.id}-${exercise.id}-${JSON.stringify(noteIdentity(data, exercise))}`}
                  userId={user.id}
                  workout={data}
                  exercise={exercise}
                  visible={exerciseOpen}
                />
              ) : null;
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
              metricType === 'strength' && executionMode === 'bilateral'
                ? (exercise.progression_guidance?.suggested_weight ?? null)
                : null;
            const targetSetUpdates =
              exercise.progression_guidance?.proposal?.target_set_updates ?? [];
            const sideProposal = exercise.progression_guidance?.proposal?.proposed_side_weights
              ? exercise.progression_guidance.proposal
              : null;
            const guidanceApplied =
              !sideProposal &&
              targetSetUpdates.length > 0 &&
              targetSetUpdates.every((update) => {
                const set = exercise.sets.find((item) => item.id === update.set_id);
                const pending = set ? activeSync.pendingBySet.get(set.id)?.values : undefined;
                return (
                  set != null &&
                  (pending?.actual_weight ?? set.actual_weight) === update.proposed_weight
                );
              });
            const applyScalarGuidance =
              started && suggestedWeight != null && targetSetUpdates.length > 0
                ? () => {
                    for (const update of targetSetUpdates) {
                      const set = exercise.sets.find((item) => item.id === update.set_id);
                      if (!set) continue;
                      const pending = activeSync.pendingBySet.get(set.id)?.values;
                      if (pending?.is_completed ?? set.is_completed) continue;
                      activeSync.enqueue(set.id, update.set_version, {
                        actual_reps: pending?.actual_reps ?? set.actual_reps ?? null,
                        actual_weight: update.proposed_weight ?? null,
                        rir: pending?.rir ?? set.rir ?? null,
                        set_kind: pending?.set_kind ?? set.set_kind ?? 'working',
                        reached_failure: pending?.reached_failure ?? set.reached_failure ?? false,
                        is_completed: pending?.is_completed ?? set.is_completed,
                      });
                    }
                  }
                : undefined;
            const applySideGuidance =
              started && sideProposal?.eligibility_status === 'eligible'
                ? async () => {
                    if (!(await activeSync.flushNow())) {
                      toast('Сначала синхронизируйте сохранённые подходы.', 'error');
                      throw new Error('Очередь не синхронизирована');
                    }
                    try {
                      await api(
                        `/api/v1/programs/assigned/${sideProposal.target_program_id}/progression-proposals/${sideProposal.proposal_id}/review`,
                        {
                          method: 'POST',
                          body: {
                            decision: 'confirm',
                            workout_id: sideProposal.target_workout_id,
                            exercise_id: sideProposal.target_exercise_id,
                            expected_revision_number: sideProposal.target_revision_number,
                            expected_set_versions: Object.fromEntries(
                              targetSetUpdates.map((item) => [item.set_id, item.set_version]),
                            ),
                          },
                        },
                      );
                      await queryClient.invalidateQueries({
                        queryKey: ['workout', 'today'],
                        exact: true,
                      });
                    } catch (error) {
                      toast(
                        'Не удалось применить рекомендации. Обновите тренировку и проверьте данные.',
                        'error',
                      );
                      throw error;
                    }
                  }
                : undefined;
            const guidanceElement =
              metricType === 'strength' &&
              exercise.progression_guidance &&
              (executionMode === 'bilateral' || exercise.progression_guidance.side_guidance) &&
              !dismissedGuidance.has(exercise.id) ? (
                <ProgressionGuidance
                  applied={guidanceApplied}
                  exerciseKey={exercise.id}
                  guidance={exercise.progression_guidance}
                  onApply={sideProposal ? applySideGuidance : applyScalarGuidance}
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
                    {replacementBlockedByExecution && (
                      <span
                        className="ui-button ui-button--secondary ui-button--full active-workout-exercise__replacement-slot"
                        aria-hidden="true"
                      >
                        Заменить только в этой тренировке
                      </span>
                    )}
                  </div>
                </header>

                {metricType === 'strength' && supportsSides && exerciseOpen && started && (
                  <div className="active-workout-sides__mode">
                    <button
                      type="button"
                      aria-expanded={modeChoicesOpen.has(exercise.id)}
                      aria-controls={`workout-mode-${exercise.id}`}
                      onClick={() =>
                        setModeChoicesOpen((current) => {
                          const next = new Set(current);
                          if (next.has(exercise.id)) next.delete(exercise.id);
                          else next.add(exercise.id);
                          return next;
                        })
                      }
                    >
                      Выполнение упражнения:{' '}
                      {executionMode === 'per_side'
                        ? 'по сторонам'
                        : executionMode === 'alternating'
                          ? 'поочерёдно'
                          : 'обычное'}{' '}
                      · изменить
                    </button>
                    <fieldset
                      id={`workout-mode-${exercise.id}`}
                      hidden={!modeChoicesOpen.has(exercise.id)}
                    >
                      <legend>Как выполняется упражнение?</legend>
                      {(
                        [
                          ['bilateral', 'Обычное'],
                          ['per_side', 'По сторонам'],
                          ['alternating', 'Поочерёдно'],
                        ] as const
                      ).map(([value, label]) => (
                        <label key={value}>
                          <input
                            type="radio"
                            name={`workout-mode-${exercise.id}`}
                            value={value}
                            checked={executionMode === value}
                            disabled={!!activeSync.sideConflict || modeBusy}
                            onChange={() => void chooseExecutionMode(value)}
                          />
                          {label}
                        </label>
                      ))}
                      <small>Завершённые результаты не изменятся.</small>
                    </fieldset>
                  </div>
                )}

                {activeSync.sideConflict &&
                  exercise.sets.some((item) => item.id === activeSync.sideConflict?.setId) && (
                    <div className="active-workout-sides__conflict" role="alert">
                      <strong>Сравнить версии подхода</strong>
                      <p>
                        Эта вкладка: <span>{sideVersionText(activeSync.sideConflict.local)}</span>
                      </p>
                      <p>
                        Другая вкладка:{' '}
                        <span>{sideVersionText(activeSync.sideConflict.server)}</span>
                      </p>
                      <p>Выберите полный вариант для обеих сторон.</p>
                      <div className="app-action-group">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => void activeSync.resolveSideConflict('local')}
                        >
                          Оставить эту версию
                        </Button>
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => void activeSync.resolveSideConflict('server')}
                        >
                          Выбрать другую версию
                        </Button>
                      </div>
                    </div>
                  )}

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
                      const previousStrength =
                        metricType === 'strength'
                          ? previousCompletedSet(exercise.sets, setIndex, activeSync.pendingBySet)
                          : undefined;
                      const previousSet =
                        metricType === 'strength'
                          ? previousStrength?.set
                          : setIndex > 0
                            ? exercise.sets[setIndex - 1]
                            : undefined;
                      const previousPending =
                        metricType === 'strength'
                          ? previousStrength?.pending
                          : previousSet
                            ? activeSync.pendingBySet.get(previousSet.id)
                            : undefined;
                      const previousValues = previousSet
                        ? resolvePreviousSetValues(previousSet, previousPending)
                        : undefined;
                      const previousSides = previousPending?.values.sides ?? previousSet?.sides;
                      const previousResult =
                        previousSides && metricType === 'strength'
                          ? sideHistoryText(previousSides)
                          : previousValues
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
                      const pastHistory =
                        metricType === 'strength' && historyState === 'ready'
                          ? boundSetHistory(setHistory.data, data.id, exercise, set)
                          : undefined;
                      const pendingValues = activeSync.pendingBySet.get(set.id)?.values;
                      const savedMode = pendingValues?.execution_mode ?? set.execution_mode;
                      const scalar = pendingValues ?? set;
                      const hasScalarFacts =
                        scalar.actual_reps != null ||
                        scalar.actual_weight != null ||
                        scalar.rir != null ||
                        scalar.reached_failure != null;
                      const rowMode =
                        savedMode === 'per_side' || savedMode === 'alternating'
                          ? savedMode
                          : savedMode === 'bilateral' || hasScalarFacts || set.is_completed
                            ? 'bilateral'
                            : executionMode;
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
                          exerciseNote={currentSet?.set.id === set.id ? exerciseNote : undefined}
                          enqueue={enqueueSet}
                        />
                      ) : rowMode === 'per_side' || rowMode === 'alternating' ? (
                        <SideWorkoutSetRow
                          key={set.id}
                          set={set}
                          mode={rowMode}
                          setPosition={setIndex + 1}
                          setTotal={exercise.sets.length}
                          prescribedReps={exercise.prescribed_reps}
                          disabled={
                            !started || modeBusy || activeSync.sideConflict?.setId === set.id
                          }
                          isCurrent={currentSet?.set.id === set.id}
                          previousSet={previousSet}
                          previousPending={previousPending}
                          pastHistory={pastHistory}
                          historyState={
                            historyState === 'ready' && !pastHistory ? 'unavailable' : historyState
                          }
                          restSeconds={exercise.rest_seconds}
                          userId={user?.id}
                          workoutId={data.id}
                          exerciseTitle={exercise.exercise_title}
                          pending={activeSync.pendingBySet.get(set.id)}
                          durable={activeSync.durable}
                          syncing={activeSync.syncState === 'syncing'}
                          exerciseNote={currentSet?.set.id === set.id ? exerciseNote : undefined}
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
                          disabled={!started || modeBusy}
                          workoutId={data.id}
                          workoutExerciseId={exercise.id}
                          exerciseTitle={exercise.exercise_title}
                          hasWarmupRows={exercise.sets.some(
                            (item) => item.set_kind === 'warmup' || item.planned_role === 'warmup',
                          )}
                          isCurrent={currentSet?.set.id === set.id}
                          previousResult={previousResult}
                          previousValues={previousValues}
                          previousSetNumber={previousSet?.set_number}
                          previousPending={Boolean(previousPending)}
                          pastHistory={pastHistory}
                          historyState={
                            historyState === 'ready' && !pastHistory ? 'unavailable' : historyState
                          }
                          pending={activeSync.pendingBySet.get(set.id)}
                          durable={activeSync.durable}
                          syncing={activeSync.syncState === 'syncing'}
                          syncFailed={syncFailed}
                          exerciseNote={currentSet?.set.id === set.id ? exerciseNote : undefined}
                          enqueue={enqueueSet}
                        />
                      );
                    })}
                  </div>
                  {!isCurrentExercise && exerciseNote}
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
