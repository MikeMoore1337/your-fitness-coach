import { describe, expect, it } from 'vitest';
import {
  calculateOneRepMax,
  ONE_REP_MAX_PERCENTAGES,
} from '../../../../src/features/workouts/oneRepMaxCalculator';

describe('calculateOneRepMax', () => {
  it.each([
    [1, 100],
    [3, 106],
    [5, 112.5],
    [8, 124],
    [10, 133.5],
  ])('calculates a rounded estimate for %s repetitions', (repetitions, expected) => {
    const result = calculateOneRepMax({ weightKg: 100, repetitions });

    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('Expected a valid one-rep-max calculation');
    expect(result.estimate.estimated1rmKg).toBe(expected);
  });

  it('keeps the one-rep input unchanged and returns the agreed percentage rows', () => {
    const result = calculateOneRepMax({ weightKg: 100, repetitions: 1 });

    expect(result).toMatchObject({
      valid: true,
      estimate: {
        estimated1rmKg: 100,
        workingWeights: [
          { percentage: 95, weightKg: 95 },
          { percentage: 90, weightKg: 90 },
          { percentage: 85, weightKg: 85 },
          { percentage: 80, weightKg: 80 },
          { percentage: 75, weightKg: 75 },
          { percentage: 70, weightKg: 70 },
        ],
      },
      errors: [],
    });
    expect(ONE_REP_MAX_PERCENTAGES).toEqual([95, 90, 85, 80, 75, 70]);
  });

  it('rounds percentage weights from the displayed estimate', () => {
    const result = calculateOneRepMax({ weightKg: 100, repetitions: 5 });

    expect(result.valid).toBe(true);
    if (!result.valid) throw new Error('Expected a valid one-rep-max calculation');
    expect(result.estimate.workingWeights.map(({ weightKg }) => weightKg)).toEqual([
      107, 101.5, 95.5, 90, 84.5, 79,
    ]);
  });

  it.each([
    [{ weightKg: Number.NaN, repetitions: Number.NaN }, ['weightKg', 'repetitions']],
    [{ weightKg: 0.4, repetitions: 5 }, ['weightKg']],
    [{ weightKg: 501, repetitions: 5 }, ['weightKg']],
    [{ weightKg: 80, repetitions: 0 }, ['repetitions']],
    [{ weightKg: 80, repetitions: 10.5 }, ['repetitions']],
    [{ weightKg: 80, repetitions: 11 }, ['repetitions']],
  ])('rejects invalid input %o', (input, fields) => {
    const result = calculateOneRepMax(input);

    expect(result).toMatchObject({ valid: false, estimate: null });
    if (result.valid) throw new Error('Expected an invalid one-rep-max calculation');
    expect(result.errors.map((error) => error.field)).toEqual(fields);
  });
});
