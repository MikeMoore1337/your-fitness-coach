import { describe, expect, it } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import {
  formatSetResult,
  formatWorkoutDuration,
  resolvePreviousSetValues,
  shouldCollapseCompletedExercise,
} from '../../../../src/features/workouts/TodayWorkout';
import type { ActiveWorkoutMutation } from '../../../../src/features/workouts/activeWorkoutQueue';

describe('formatWorkoutDuration', () => {
  it('formats a workout shorter than one hour', () => {
    expect(formatWorkoutDuration(754)).toBe('12:34');
  });

  it('includes hours for a long workout', () => {
    expect(formatWorkoutDuration(3_661)).toBe('1:01:01');
  });

  it('does not display a negative duration', () => {
    expect(formatWorkoutDuration(-10)).toBe('0:00');
  });
});

describe('shouldCollapseCompletedExercise', () => {
  const completedSets = [
    { id: 1, is_completed: true },
    { id: 2, is_completed: true },
  ];

  it('collapses only a fully persisted exercise', () => {
    expect(shouldCollapseCompletedExercise(completedSets, () => false)).toBe(true);
    expect(shouldCollapseCompletedExercise(completedSets, (id) => id === 2)).toBe(false);
    expect(
      shouldCollapseCompletedExercise(
        [
          { id: 1, is_completed: true },
          { id: 2, is_completed: false },
        ],
        () => false,
      ),
    ).toBe(false);
  });
});

describe('formatSetResult', () => {
  it('formats a previous set without inventing missing values', () => {
    expect(formatSetResult(8, 40)).toBe('40 кг × 8');
    expect(formatSetResult(8, null)).toBe('8 повт.');
    expect(formatSetResult(null, 40)).toBe('40 кг');
    expect(formatSetResult(null, null)).toBeNull();
  });
});

describe('resolvePreviousSetValues', () => {
  it('keeps nullable pending values instead of restoring stale server values', () => {
    const set: Pick<
      Workout['exercises'][number]['sets'][number],
      'actual_reps' | 'actual_weight' | 'duration_minutes' | 'distance_km'
    > = {
      actual_reps: 8,
      actual_weight: 40,
      duration_minutes: 25,
      distance_km: 5,
    };
    const pending: Pick<ActiveWorkoutMutation, 'values'> = {
      values: {
        actual_reps: null,
        actual_weight: null,
        duration_minutes: null,
        distance_km: null,
        is_completed: false,
      },
    };

    expect(resolvePreviousSetValues(set, pending)).toEqual({
      actual_reps: null,
      actual_weight: null,
      duration_minutes: null,
      distance_km: null,
    });
    expect(resolvePreviousSetValues(set)).toMatchObject({
      actual_reps: 8,
      actual_weight: 40,
      duration_minutes: 25,
      distance_km: 5,
    });
  });
});
