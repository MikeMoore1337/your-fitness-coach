import { describe, expect, it } from 'vitest';
import {
  calculatePlateLoad,
  warmupSuggestions,
} from '../../../../src/features/workouts/workoutExecution';

describe('workout execution helpers', () => {
  it('keeps warm-up suggestions deterministic and distinct', () => {
    expect(warmupSuggestions(80)).toEqual([32, 48, 60]);
    expect(warmupSuggestions(20)).toEqual([]);
  });

  it('calculates plates per side without changing workout data', () => {
    expect(calculatePlateLoad(80)).toEqual({
      perSide: 30,
      plates: [25, 5],
      remainder: 0,
    });
    expect(calculatePlateLoad(21)).toEqual({
      perSide: 0.5,
      plates: [0.5],
      remainder: 0,
    });
    expect(calculatePlateLoad(10)).toBeNull();
  });
});
