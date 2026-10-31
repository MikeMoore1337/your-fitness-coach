import { describe, expect, it } from 'vitest';
import type { Workout, WorkoutSetHistory } from '../../../../src/shared/api/types';
import type { ActiveWorkoutMutation } from '../../../../src/features/workouts/activeWorkoutQueue';
import {
  boundSetHistory,
  previousCompletedSet,
} from '../../../../src/features/workouts/workoutSetHistory';

const exercise: Workout['exercises'][number] = {
  id: 101,
  exercise_id: 11,
  exercise_title: 'Приседания',
  metric_type: 'strength',
  sort_order: 1,
  prescribed_sets: 4,
  prescribed_reps: '5–8',
  rest_seconds: 120,
  source_template_exercise_id: 71,
  has_guide: false,
  sets: [
    { id: 201, set_number: 1, version: 2, is_completed: true, actual_weight: 160, actual_reps: 8 },
    { id: 202, set_number: 2, version: 3, is_completed: false, actual_weight: 180, actual_reps: 6 },
    {
      id: 203,
      set_number: 3,
      version: 1,
      is_completed: false,
      actual_weight: null,
      actual_reps: null,
    },
  ],
};

function history(): WorkoutSetHistory {
  return {
    workout_id: 42,
    user_program_id: 4,
    program_revision_number: 2,
    sets: [
      {
        set_id: 203,
        set_number: 3,
        set_version: 1,
        workout_exercise_id: 101,
        exercise_id: 11,
        source_template_exercise_id: 71,
        history_status: 'matched',
        previous_workout: {
          set_id: 303,
          set_number: 3,
          set_version: 2,
          is_completed: true,
          workout_id: 41,
          workout_exercise_id: 100,
          completed_at: '2030-01-03T12:00:00',
          performed_on: '2030-01-03',
          actual_weight: 200,
          actual_reps: 5,
        },
      },
    ],
  };
}

function pending(
  setId: number,
  completed: boolean,
  weight: number | null,
  reps: number | null,
): ActiveWorkoutMutation {
  return {
    mutation_id: 'local-mutation-1234',
    set_id: setId,
    expected_version: 1,
    created_at: 1,
    values: { is_completed: completed, actual_weight: weight, actual_reps: reps },
  };
}

describe('per-set history bindings', () => {
  it('accepts explicit asymmetric or partial side facts without scalar values', () => {
    const result = history();
    const past = result.sets[0]!.previous_workout!;
    past.actual_weight = null;
    past.actual_reps = null;
    past.execution_mode = 'per_side';
    past.sides = {
      left: { actual_weight: 18, actual_reps: 10, is_completed: true },
      right: { actual_weight: 16, actual_reps: 8, is_completed: false },
    };
    expect(
      boundSetHistory(result, 42, exercise, exercise.sets[2]!)?.previous_workout?.sides,
    ).toEqual(past.sides);
  });
  it('accepts the matching workout, exercise, slot, set and version including zero and partial facts', () => {
    const result = history();
    result.sets[0]!.previous_workout!.actual_weight = 0;
    result.sets[0]!.previous_workout!.actual_reps = null;
    expect(
      boundSetHistory(result, 42, exercise, exercise.sets[2]!)?.previous_workout,
    ).toMatchObject({
      actual_weight: 0,
      actual_reps: null,
    });
  });

  it.each([
    [
      'workout',
      (item: WorkoutSetHistory) => {
        item.workout_id = 43;
      },
    ],
    [
      'exercise',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.exercise_id = 12;
      },
    ],
    [
      'exercise slot',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.workout_exercise_id = 102;
      },
    ],
    [
      'template position',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.source_template_exercise_id = 72;
      },
    ],
    [
      'set number',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.set_number = 2;
      },
    ],
    [
      'set version',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.set_version = 2;
      },
    ],
    [
      'past set number',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.previous_workout!.set_number = 2;
      },
    ],
    [
      'current workout as past',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.previous_workout!.workout_id = 42;
      },
    ],
    [
      'duplicate set',
      (item: WorkoutSetHistory) => {
        item.sets.push(item.sets[0]!);
      },
    ],
    [
      'no actual result',
      (item: WorkoutSetHistory) => {
        item.sets[0]!.previous_workout!.actual_weight = null;
        item.sets[0]!.previous_workout!.actual_reps = null;
      },
    ],
  ])('rejects a stale or ambiguous %s', (_label, change) => {
    const result = history();
    change(result);
    expect(boundSetHistory(result, 42, exercise, exercise.sets[2]!)).toBeUndefined();
  });

  it('preserves a proven empty result without inventing a neighboring set', () => {
    const result = history();
    result.sets[0]!.history_status = 'no_matching_set';
    result.sets[0]!.previous_workout = null;
    expect(boundSetHistory(result, 42, exercise, exercise.sets[2]!)?.history_status).toBe(
      'no_matching_set',
    );
  });
});

describe('previous completed set today', () => {
  it('finds a completed side-specific set even when scalar facts are empty', () => {
    const sets = structuredClone(exercise.sets);
    Object.assign(sets[0]!, {
      actual_weight: null,
      actual_reps: null,
      execution_mode: 'per_side',
      sides: {
        left: { actual_weight: 18, actual_reps: 10, is_completed: true },
        right: { actual_weight: 16, actual_reps: 8, is_completed: true },
      },
    });
    expect(previousCompletedSet(sets, 2, new Map())?.set.id).toBe(201);
  });
  it('skips unfinished results and uses the latest actual completed set', () => {
    expect(previousCompletedSet(exercise.sets, 2, new Map())?.set.id).toBe(201);
    expect(previousCompletedSet(exercise.sets, 0, new Map())).toBeUndefined();
  });

  it('uses locally completed facts and skips locally reopened or empty sets', () => {
    const queue = new Map([[202, pending(202, true, 0, 6)]]);
    expect(previousCompletedSet(exercise.sets, 2, queue)?.pending?.values.actual_weight).toBe(0);
    queue.set(202, pending(202, true, null, null));
    expect(previousCompletedSet(exercise.sets, 2, queue)?.set.id).toBe(201);
    queue.set(201, pending(201, false, 160, 8));
    expect(previousCompletedSet(exercise.sets, 2, queue)).toBeUndefined();
  });
});
