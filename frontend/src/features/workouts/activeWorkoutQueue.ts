import type { Workout } from '../../shared/api/types';
import {
  ACTIVE_WORKOUT_STORAGE_PREFIXES,
  LEGACY_ACTIVE_WORKOUT_STORAGE_PREFIXES,
  activeWorkoutPointerStorageKey,
  activeWorkoutQueueStorageKey,
  activeWorkoutRestStorageKey,
  legacyWorkoutPendingStorageKey,
  legacyWorkoutSetStorageKey,
} from '../../shared/userScopedStorage';
import { getApiRuntime } from '../../shared/runtime/runtime';

type WorkoutSet = Workout['exercises'][number]['sets'][number];

export const ACTIVE_WORKOUT_QUEUE_VERSION = 3 as const;
const LEGACY_ACTIVE_WORKOUT_QUEUE_VERSION = 1 as const;
const PREVIOUS_ACTIVE_WORKOUT_QUEUE_VERSION = 2 as const;
const MAX_QUEUE_LENGTH = 256;

export interface ActiveWorkoutSetValues {
  actual_reps: number | null;
  actual_weight: number | null;
  duration_minutes?: number | null;
  distance_km?: number | null;
  average_heart_rate_bpm?: number | null;
  heart_rate_zone?: number | null;
  rir?: WorkoutSet['rir'];
  set_kind?: WorkoutSet['set_kind'];
  reached_failure?: WorkoutSet['reached_failure'];
  execution_mode?: WorkoutSet['execution_mode'];
  first_side?: WorkoutSet['first_side'];
  sides?: WorkoutSet['sides'];
  confirm_mode_change?: boolean;
  is_completed: boolean;
}

export interface ActiveWorkoutMutation {
  mutation_id: string;
  origin_id?: string;
  set_id: number;
  expected_version: number;
  values: ActiveWorkoutSetValues;
  created_at: number;
}

export interface ActiveWorkoutQueue {
  schema_version: typeof ACTIVE_WORKOUT_QUEUE_VERSION;
  user_id: number;
  workout_id: number;
  queue: ActiveWorkoutMutation[];
  accepted_versions?: Record<string, { origin_id: string; version: number }>;
  workout_snapshot?: Workout;
}

function runtimeStorageKey(key: string): string {
  const runtime = getApiRuntime();
  return runtime.kind === 'demo' ? `fit-demo:${runtime.sessionToken}:${key}` : key;
}

function activeWorkoutPointerKey(userId: number): string {
  return runtimeStorageKey(activeWorkoutPointerStorageKey(userId));
}

type StoredActiveWorkoutQueue = Omit<ActiveWorkoutQueue, 'schema_version'> & {
  schema_version: number;
};

export function activeWorkoutQueueKey(userId: number, workoutId: number): string {
  return `${legacyActiveWorkoutQueueKey(userId, workoutId)}:v3`;
}

export function legacyActiveWorkoutQueueKey(userId: number, workoutId: number): string {
  return runtimeStorageKey(activeWorkoutQueueStorageKey(userId, workoutId));
}

export function activeWorkoutLockName(userId: number, workoutId: number): string {
  return `fit-active-workout-${legacyActiveWorkoutQueueKey(userId, workoutId)}`;
}

export function activeWorkoutRestKey(userId: number, workoutId: number): string {
  return runtimeStorageKey(activeWorkoutRestStorageKey(userId, workoutId));
}

export function emptyActiveWorkoutQueue(userId: number, workoutId: number): ActiveWorkoutQueue {
  return {
    schema_version: ACTIVE_WORKOUT_QUEUE_VERSION,
    user_id: userId,
    workout_id: workoutId,
    queue: [],
  };
}

function validNullableNumber(value: unknown, integer: boolean): value is number | null {
  return (
    value === null ||
    (typeof value === 'number' &&
      Number.isFinite(value) &&
      value >= 0 &&
      (!integer || Number.isInteger(value)))
  );
}

function validOptionalNumber(
  value: unknown,
  { integer = false, min = 0, max = Number.POSITIVE_INFINITY } = {},
): boolean {
  return (
    value === undefined ||
    value === null ||
    (typeof value === 'number' &&
      Number.isFinite(value) &&
      value >= min &&
      value <= max &&
      (!integer || Number.isInteger(value)))
  );
}

function validMutation(value: unknown): value is ActiveWorkoutMutation {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<ActiveWorkoutMutation>;
  return Boolean(
    typeof item.mutation_id === 'string' &&
    item.mutation_id.length >= 16 &&
    item.mutation_id.length <= 64 &&
    (item.origin_id === undefined ||
      (typeof item.origin_id === 'string' &&
        item.origin_id.length >= 16 &&
        item.origin_id.length <= 64)) &&
    Number.isInteger(item.set_id) &&
    Number(item.set_id) > 0 &&
    Number.isInteger(item.expected_version) &&
    Number(item.expected_version) >= 1 &&
    Number.isFinite(item.created_at) &&
    item.values &&
    validNullableNumber(item.values.actual_reps, true) &&
    validNullableNumber(item.values.actual_weight, false) &&
    validOptionalNumber(item.values.duration_minutes, { integer: true, min: 1, max: 600 }) &&
    validOptionalNumber(item.values.distance_km, { min: Number.EPSILON, max: 1000 }) &&
    validOptionalNumber(item.values.average_heart_rate_bpm, {
      integer: true,
      min: 30,
      max: 250,
    }) &&
    validOptionalNumber(item.values.heart_rate_zone, { integer: true, min: 1, max: 5 }) &&
    (item.values.rir === undefined ||
      item.values.rir === null ||
      ['0', '1', '2', '3', '4+'].includes(item.values.rir)) &&
    (item.values.set_kind === undefined ||
      item.values.set_kind === null ||
      ['warmup', 'working', 'drop'].includes(item.values.set_kind)) &&
    (item.values.reached_failure === undefined ||
      item.values.reached_failure === null ||
      typeof item.values.reached_failure === 'boolean') &&
    validSides(item.values) &&
    typeof item.values.is_completed === 'boolean',
  );
}

function validSides(values: ActiveWorkoutSetValues): boolean {
  if (
    values.execution_mode !== undefined &&
    values.execution_mode !== null &&
    !['bilateral', 'per_side', 'alternating'].includes(values.execution_mode)
  )
    return false;
  if (
    values.first_side != null &&
    (!['left', 'right'].includes(values.first_side) || values.execution_mode !== 'alternating')
  )
    return false;
  if (values.confirm_mode_change !== undefined && typeof values.confirm_mode_change !== 'boolean')
    return false;
  const sideMode = values.execution_mode === 'per_side' || values.execution_mode === 'alternating';
  if (!sideMode) return values.sides == null;
  if (
    !values.sides ||
    typeof values.sides !== 'object' ||
    !Object.hasOwn(values.sides, 'left') ||
    !Object.hasOwn(values.sides, 'right') ||
    values.actual_reps != null ||
    values.actual_weight != null
  )
    return false;
  for (const side of [values.sides.left, values.sides.right]) {
    if (side === null) continue;
    if (
      !side ||
      typeof side !== 'object' ||
      typeof side.is_completed !== 'boolean' ||
      !validOptionalNumber(side.actual_reps, { integer: true, max: 2147483647 }) ||
      !validOptionalNumber(side.actual_weight, { max: 99999999.99 }) ||
      (side.rir != null && !['0', '1', '2', '3', '4+'].includes(side.rir)) ||
      (side.reached_failure != null && typeof side.reached_failure !== 'boolean')
    )
      return false;
  }
  return (
    !values.is_completed || !!(values.sides.left?.is_completed && values.sides.right?.is_completed)
  );
}

function validWorkoutSnapshot(
  value: unknown,
  workoutId: number,
  requireMetricType = false,
): value is Workout {
  if (!value || typeof value !== 'object') return false;
  const workout = value as Partial<Workout>;
  return Boolean(
    workout.id === workoutId &&
    workout.status === 'in_progress' &&
    typeof workout.title === 'string' &&
    typeof workout.scheduled_date === 'string' &&
    Array.isArray(workout.exercises) &&
    workout.exercises.every(
      (exercise) =>
        exercise &&
        Number.isInteger(exercise.id) &&
        typeof exercise.exercise_title === 'string' &&
        (!requireMetricType || ['strength', 'cardio'].includes(exercise.metric_type)) &&
        Array.isArray(exercise.sets) &&
        exercise.sets.every(
          (set) =>
            set &&
            Number.isInteger(set.id) &&
            Number.isInteger(set.set_number) &&
            typeof set.is_completed === 'boolean',
        ),
    ),
  );
}

function workoutSnapshotForStorage(workout: Workout): Workout {
  return {
    ...workout,
    exercises: workout.exercises.map((exercise) => {
      const exerciseSnapshot = { ...exercise };
      delete exerciseSnapshot.progression_guidance;
      return exerciseSnapshot;
    }),
  };
}

function migrateLegacyQueue(
  parsed: StoredActiveWorkoutQueue,
  workout: Workout,
): ActiveWorkoutQueue {
  const metricBySetId = new Map<number, 'strength' | 'cardio'>();
  for (const exercise of workout.exercises) {
    const metricType = exercise.metric_type === 'cardio' ? 'cardio' : 'strength';
    for (const set of exercise.sets) metricBySetId.set(set.id, metricType);
  }
  const queue: ActiveWorkoutMutation[] = [];
  for (const mutation of parsed.queue) {
    const metricType = metricBySetId.get(mutation.set_id);
    if (!metricType) continue;
    if (metricType === 'cardio') {
      const durationMinutes = mutation.values.duration_minutes;
      queue.push({
        ...mutation,
        values: {
          actual_reps: null,
          actual_weight: null,
          duration_minutes: durationMinutes,
          distance_km: mutation.values.distance_km,
          average_heart_rate_bpm: mutation.values.average_heart_rate_bpm,
          heart_rate_zone: mutation.values.heart_rate_zone,
          is_completed: mutation.values.is_completed && durationMinutes != null,
        },
      });
      continue;
    }
    queue.push({
      ...mutation,
      values: {
        actual_reps: mutation.values.actual_reps,
        actual_weight: mutation.values.actual_weight,
        rir: mutation.values.rir,
        set_kind: mutation.values.set_kind,
        reached_failure: mutation.values.reached_failure,
        is_completed: mutation.values.is_completed,
      },
    });
  }
  return {
    schema_version: ACTIVE_WORKOUT_QUEUE_VERSION,
    user_id: parsed.user_id,
    workout_id: parsed.workout_id,
    queue,
    workout_snapshot: workoutSnapshotForStorage(workout),
  };
}

function mergePreviousQueue(state: ActiveWorkoutQueue, workout?: Workout): ActiveWorkoutQueue {
  try {
    const raw = localStorage.getItem(legacyActiveWorkoutQueueKey(state.user_id, state.workout_id));
    if (!raw) return state;
    const previous = JSON.parse(raw) as StoredActiveWorkoutQueue;
    if (
      previous.user_id !== state.user_id ||
      previous.workout_id !== state.workout_id ||
      ![LEGACY_ACTIVE_WORKOUT_QUEUE_VERSION, PREVIOUS_ACTIVE_WORKOUT_QUEUE_VERSION].includes(
        previous.schema_version as 1 | 2,
      ) ||
      !Array.isArray(previous.queue) ||
      previous.queue.length > MAX_QUEUE_LENGTH ||
      !previous.queue.every(validMutation)
    )
      return state;
    if (previous.schema_version === LEGACY_ACTIVE_WORKOUT_QUEUE_VERSION && !workout) return state;
    const items =
      previous.schema_version === LEGACY_ACTIVE_WORKOUT_QUEUE_VERSION
        ? migrateLegacyQueue(previous, workout!).queue
        : previous.queue;
    const known = new Set(state.queue.map((item) => item.mutation_id));
    const added = items.filter((item) => !known.has(item.mutation_id));
    return added.length
      ? { ...state, queue: [...state.queue, ...added].sort((a, b) => a.created_at - b.created_at) }
      : state;
  } catch {
    return state;
  }
}

export function loadActiveWorkoutQueue(
  userId: number,
  workoutId: number,
  _validSetIds?: ReadonlySet<number>,
  workout?: Workout,
): ActiveWorkoutQueue {
  const key = activeWorkoutQueueKey(userId, workoutId);
  const oldKey = legacyActiveWorkoutQueueKey(userId, workoutId);
  try {
    const currentRaw = localStorage.getItem(key);
    const raw = currentRaw ?? localStorage.getItem(oldKey);
    if (raw === null) return emptyActiveWorkoutQueue(userId, workoutId);
    const parsed = JSON.parse(raw) as Partial<StoredActiveWorkoutQueue>;
    const isLegacy = parsed.schema_version === LEGACY_ACTIVE_WORKOUT_QUEUE_VERSION;
    const isPrevious = parsed.schema_version === PREVIOUS_ACTIVE_WORKOUT_QUEUE_VERSION;
    const snapshotValid =
      parsed.workout_snapshot === undefined ||
      validWorkoutSnapshot(parsed.workout_snapshot, workoutId, !isLegacy);
    const valid =
      (parsed.schema_version === ACTIVE_WORKOUT_QUEUE_VERSION || isLegacy || isPrevious) &&
      parsed.user_id === userId &&
      parsed.workout_id === workoutId &&
      Array.isArray(parsed.queue) &&
      parsed.queue.length <= MAX_QUEUE_LENGTH * 2 &&
      snapshotValid &&
      parsed.queue.every(validMutation);
    if (valid && isPrevious) {
      const migrated = {
        ...parsed,
        schema_version: ACTIVE_WORKOUT_QUEUE_VERSION,
      } as ActiveWorkoutQueue;
      saveActiveWorkoutQueue(migrated);
      return migrated;
    }
    if (valid && !isLegacy) return mergePreviousQueue(parsed as ActiveWorkoutQueue, workout);
    if (valid && workout && validWorkoutSnapshot(workout, workoutId, true)) {
      const migrated = migrateLegacyQueue(parsed as StoredActiveWorkoutQueue, workout);
      saveActiveWorkoutQueue(migrated);
      return migrated;
    }
    if (valid && isLegacy) return emptyActiveWorkoutQueue(userId, workoutId);
    if (currentRaw !== null) localStorage.removeItem(key);
  } catch {
    try {
      localStorage.removeItem(key);
    } catch {
      // Storage can be unavailable in restrictive webviews.
    }
  }
  return emptyActiveWorkoutQueue(userId, workoutId);
}

export function acknowledgeLegacyWorkoutMutation(
  userId: number,
  workoutId: number,
  mutationId: string,
): void {
  const key = legacyActiveWorkoutQueueKey(userId, workoutId);
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return;
    const previous = JSON.parse(raw) as Partial<StoredActiveWorkoutQueue>;
    if (
      previous.user_id !== userId ||
      previous.workout_id !== workoutId ||
      !Array.isArray(previous.queue) ||
      !previous.queue.some((item) => item.mutation_id === mutationId)
    )
      return;
    localStorage.setItem(
      key,
      JSON.stringify({
        ...previous,
        queue: previous.queue.filter((item) => item.mutation_id !== mutationId),
      }),
    );
  } catch {
    // Keep unreadable legacy data for recovery.
  }
}

export function saveActiveWorkoutQueue(state: ActiveWorkoutQueue): boolean {
  const key = activeWorkoutQueueKey(state.user_id, state.workout_id);
  try {
    if (state.queue.length === 0 && !state.workout_snapshot && !state.accepted_versions)
      localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(state));
    return true;
  } catch {
    // The live form still works when durable storage is unavailable.
    return false;
  }
}

export function createWorkoutMutationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `fallback-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

export const queueContextId = createWorkoutMutationId();

function hasSideValues(values: ActiveWorkoutSetValues): boolean {
  return (
    values.execution_mode === 'per_side' ||
    values.execution_mode === 'alternating' ||
    values.confirm_mode_change === true
  );
}

export function enqueueWorkoutMutation(
  state: ActiveWorkoutQueue,
  input: {
    setId: number;
    serverVersion: number;
    values: ActiveWorkoutSetValues;
    inFlightMutationId?: string | null;
    originId?: string;
    now?: number;
  },
): ActiveWorkoutQueue {
  const queue = [...state.queue];
  const originId = input.originId ?? queueContextId;
  const accepted = state.accepted_versions?.[String(input.setId)];
  const serverVersion =
    accepted?.origin_id === originId && Number.isInteger(accepted.version)
      ? Math.max(input.serverVersion, accepted.version)
      : input.serverVersion;
  const previous = [...queue].reverse().find((item) => item.set_id === input.setId);
  const sideConflictPossible = Boolean(
    previous && (hasSideValues(previous.values) || hasSideValues(input.values)),
  );
  let replaceIndex = -1;
  for (let index = queue.length - 1; index >= 0; index -= 1) {
    const item = queue[index]!;
    if (item.set_id === input.setId) {
      if (
        item.mutation_id !== input.inFlightMutationId &&
        (!sideConflictPossible || item.origin_id === originId)
      )
        replaceIndex = index;
      break;
    }
  }
  const expectedVersion =
    replaceIndex >= 0
      ? queue[replaceIndex]!.expected_version
      : sideConflictPossible && previous?.origin_id !== originId
        ? serverVersion
        : Math.max(serverVersion, previous ? previous.expected_version + 1 : 1);
  const mutation: ActiveWorkoutMutation = {
    mutation_id: createWorkoutMutationId(),
    origin_id: originId,
    set_id: input.setId,
    expected_version: expectedVersion,
    values: input.values,
    created_at: input.now ?? Date.now(),
  };
  if (replaceIndex >= 0) queue[replaceIndex] = mutation;
  else {
    if (queue.length >= MAX_QUEUE_LENGTH)
      throw new Error('Очередь сохранения заполнена. Синхронизируйте тренировку.');
    queue.push(mutation);
  }
  return { ...state, queue };
}

export function acknowledgeWorkoutMutation(
  state: ActiveWorkoutQueue,
  mutationId: string,
  serverVersion: number,
): ActiveWorkoutQueue {
  const acknowledged = state.queue.find((item) => item.mutation_id === mutationId);
  if (!acknowledged) return state;
  const queue = state.queue.filter((item) => item.mutation_id !== mutationId);
  const nextIndex = queue.findIndex((item) => item.set_id === acknowledged.set_id);
  if (
    nextIndex >= 0 &&
    !(
      (hasSideValues(acknowledged.values) || hasSideValues(queue[nextIndex]!.values)) &&
      acknowledged.origin_id !== queue[nextIndex]!.origin_id
    )
  ) {
    queue[nextIndex] = { ...queue[nextIndex]!, expected_version: serverVersion };
  }
  const acceptedVersions =
    acknowledged.origin_id && hasSideValues(acknowledged.values)
      ? {
          ...state.accepted_versions,
          [String(acknowledged.set_id)]: {
            origin_id: acknowledged.origin_id,
            version: serverVersion,
          },
        }
      : state.accepted_versions;
  return { ...state, queue, accepted_versions: acceptedVersions };
}

export function resolveWorkoutVersionConflict(
  state: ActiveWorkoutQueue,
  mutationId: string,
  serverVersion: number,
): ActiveWorkoutQueue {
  const index = state.queue.findIndex((item) => item.mutation_id === mutationId);
  if (index < 0) return state;
  const current = state.queue[index]!;
  const queue = [...state.queue];
  const newerIndex = queue.findIndex(
    (item, itemIndex) => itemIndex > index && item.set_id === current.set_id,
  );
  if (newerIndex >= 0) {
    queue.splice(index, 1);
    const adjustedIndex = newerIndex - 1;
    queue[adjustedIndex] = { ...queue[adjustedIndex]!, expected_version: serverVersion };
  } else {
    queue[index] = { ...current, expected_version: serverVersion };
  }
  return { ...state, queue };
}

export function resolveSideWorkoutConflict(
  state: ActiveWorkoutQueue,
  setId: number,
  serverVersion: number,
  choice: 'local' | 'server',
): ActiveWorkoutQueue {
  const index = state.queue.findIndex((item) => item.set_id === setId);
  const latest = latestMutationForSet(state, setId);
  if (index < 0 || !latest) return state;
  const queue = state.queue.filter((item) => item.set_id !== setId);
  if (choice === 'local') {
    const values =
      latest.values.execution_mode === 'per_side' || latest.values.execution_mode === 'alternating'
        ? { ...latest.values, confirm_mode_change: true }
        : {
            ...latest.values,
            execution_mode: 'bilateral' as const,
            first_side: null,
            sides: null,
            confirm_mode_change: true,
          };
    queue.splice(index, 0, {
      ...latest,
      mutation_id: createWorkoutMutationId(),
      expected_version: serverVersion,
      values,
    });
  }
  return { ...state, queue };
}

export function latestMutationForSet(
  state: ActiveWorkoutQueue,
  setId: number,
): ActiveWorkoutMutation | undefined {
  return [...state.queue].reverse().find((item) => item.set_id === setId);
}

export function clearActiveWorkoutDataForUser(userId: number): void {
  const prefixes = [
    `${ACTIVE_WORKOUT_STORAGE_PREFIXES.queue}user_${userId}_`,
    `${ACTIVE_WORKOUT_STORAGE_PREFIXES.rest}user_${userId}_`,
    ...LEGACY_ACTIVE_WORKOUT_STORAGE_PREFIXES,
  ];
  try {
    const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index));
    for (const key of keys) {
      if (key && prefixes.some((prefix) => key.startsWith(prefix))) localStorage.removeItem(key);
    }
    localStorage.removeItem(activeWorkoutPointerKey(userId));
  } catch {
    // Storage is optional in restrictive webviews.
  }
}

function readLegacySetValue(key: string): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function legacyField(
  primary: Record<string, unknown> | null,
  secondary: Record<string, unknown> | null,
  field: string,
  fallback: unknown,
): unknown {
  if (primary && Object.hasOwn(primary, field)) return primary[field];
  if (secondary && Object.hasOwn(secondary, field)) return secondary[field];
  return fallback;
}

export function saveActiveWorkoutSnapshot(
  userId: number,
  workout: Workout,
): ActiveWorkoutQueue | undefined {
  if (workout.status !== 'in_progress') return undefined;
  const pointerKey = activeWorkoutPointerKey(userId);
  try {
    const previousWorkoutId = Number(localStorage.getItem(pointerKey));
    if (
      Number.isInteger(previousWorkoutId) &&
      previousWorkoutId > 0 &&
      previousWorkoutId !== workout.id
    ) {
      if (loadActiveWorkoutQueue(userId, previousWorkoutId).queue.length === 0) {
        localStorage.removeItem(activeWorkoutQueueKey(userId, previousWorkoutId));
        localStorage.removeItem(activeWorkoutRestKey(userId, previousWorkoutId));
      }
    }
    const setIds = new Set(
      workout.exercises.flatMap((exercise) => exercise.sets.map((set) => set.id)),
    );
    const metricBySetId = new Map(
      workout.exercises.flatMap((exercise) =>
        exercise.sets.map((set) => [set.id, exercise.metric_type] as const),
      ),
    );
    let current = loadActiveWorkoutQueue(userId, workout.id, setIds, workout);
    const legacyKeys: string[] = [];
    for (const set of workout.exercises.flatMap((exercise) => exercise.sets)) {
      const draftKey = legacyWorkoutSetStorageKey(set.id);
      const pendingKey = legacyWorkoutPendingStorageKey(set.id);
      const draft = readLegacySetValue(draftKey);
      const pending = readLegacySetValue(pendingKey);
      if (draft === null && pending === null) continue;
      legacyKeys.push(draftKey, pendingKey);
      if (current.queue.some((item) => item.set_id === set.id)) continue;
      if (metricBySetId.get(set.id) === 'cardio') continue;
      const actualReps = legacyField(pending, draft, 'actual_reps', set.actual_reps ?? null);
      const actualWeight = legacyField(pending, draft, 'actual_weight', set.actual_weight ?? null);
      const isCompleted = legacyField(pending, null, 'is_completed', set.is_completed);
      if (
        !validNullableNumber(actualReps, true) ||
        !validNullableNumber(actualWeight, false) ||
        typeof isCompleted !== 'boolean'
      )
        continue;
      current = enqueueWorkoutMutation(current, {
        setId: set.id,
        serverVersion: set.version,
        values: {
          actual_reps: actualReps,
          actual_weight: actualWeight,
          is_completed: isCompleted,
        },
      });
    }
    const workoutSnapshot = workoutSnapshotForStorage(workout);
    const next = { ...current, workout_snapshot: workoutSnapshot };
    if (saveActiveWorkoutQueue(next)) {
      for (const legacyKey of legacyKeys) localStorage.removeItem(legacyKey);
      localStorage.setItem(pointerKey, String(workout.id));
      return next;
    }
  } catch {
    // The live form still works when durable storage is unavailable.
  }
  return undefined;
}

export function loadCurrentActiveWorkoutSnapshot(userId: number): Workout | undefined {
  try {
    const pointerKey = activeWorkoutPointerKey(userId);
    const workoutId = Number(localStorage.getItem(pointerKey));
    if (!Number.isInteger(workoutId) || workoutId <= 0) {
      localStorage.removeItem(pointerKey);
      return undefined;
    }
    return loadActiveWorkoutQueue(userId, workoutId).workout_snapshot;
  } catch {
    return undefined;
  }
}

export function clearActiveWorkoutData(userId: number, workoutId: number): boolean {
  try {
    if (loadActiveWorkoutQueue(userId, workoutId).queue.length > 0) return false;
    localStorage.removeItem(activeWorkoutQueueKey(userId, workoutId));
    localStorage.removeItem(activeWorkoutRestKey(userId, workoutId));
    const pointerKey = activeWorkoutPointerKey(userId);
    if (localStorage.getItem(pointerKey) === String(workoutId)) localStorage.removeItem(pointerKey);
    return true;
  } catch {
    // Storage is optional in restrictive webviews.
    return false;
  }
}
