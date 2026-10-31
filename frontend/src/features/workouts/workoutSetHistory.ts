import type { Workout, WorkoutSetHistory } from '../../shared/api/types';
import type { ActiveWorkoutMutation } from './activeWorkoutQueue';

type Exercise = Workout['exercises'][number];
type WorkoutSet = Exercise['sets'][number];

function hasRecordedSides(sides: WorkoutSet['sides']): boolean {
  return (
    !!sides &&
    [sides.left, sides.right].some(
      (side) =>
        side &&
        (side.is_completed ||
          side.actual_reps != null ||
          side.actual_weight != null ||
          side.rir != null ||
          side.reached_failure != null),
    )
  );
}

export function previousCompletedSet(
  sets: WorkoutSet[],
  index: number,
  pendingBySet: ReadonlyMap<number, ActiveWorkoutMutation | undefined>,
) {
  for (let position = index - 1; position >= 0; position -= 1) {
    const set = sets[position]!;
    const pending = pendingBySet.get(set.id);
    const completed = pending?.values.is_completed ?? set.is_completed;
    const weight = pending ? pending.values.actual_weight : set.actual_weight;
    const reps = pending ? pending.values.actual_reps : set.actual_reps;
    const sides = pending ? pending.values.sides : set.sides;
    if (completed && (weight != null || reps != null || hasRecordedSides(sides)))
      return { set, pending };
  }
  return undefined;
}

export function boundSetHistory(
  history: WorkoutSetHistory | undefined,
  workoutId: number,
  exercise: Exercise,
  set: WorkoutSet,
) {
  if (!history || history.workout_id !== workoutId || !Array.isArray(history.sets))
    return undefined;
  const rows = history.sets.filter((item) => item.set_id === set.id);
  if (rows.length !== 1) return undefined;
  const item = rows[0]!;
  if (
    item.set_number !== set.set_number ||
    item.set_version !== (set.version ?? 1) ||
    item.workout_exercise_id !== exercise.id ||
    item.exercise_id !== exercise.exercise_id ||
    item.source_template_exercise_id !== (exercise.source_template_exercise_id ?? null)
  )
    return undefined;
  if (item.history_status === 'matched') {
    const past = item.previous_workout;
    if (
      item.source_template_exercise_id == null ||
      !past ||
      past.set_number !== set.set_number ||
      past.workout_id === workoutId ||
      past.workout_exercise_id === exercise.id ||
      past.set_id === set.id ||
      (past.actual_weight == null && past.actual_reps == null && !hasRecordedSides(past.sides))
    )
      return undefined;
  }
  return item;
}
