import { describe, expect, it } from 'vitest';
import {
  calculatePlateLoad,
  DEFAULT_PLATE_INVENTORY,
  warmupSuggestions,
} from '../../../../src/features/workouts/workoutExecution';

describe('workout execution helpers', () => {
  it('keeps warm-up suggestions deterministic and distinct', () => {
    expect(warmupSuggestions(80)).toEqual([32, 48, 60]);
    expect(warmupSuggestions(20)).toEqual([]);
  });

  it('calculates plates per side without changing workout data', () => {
    expect(calculatePlateLoad(20)).toEqual({
      perSide: 0,
      plates: [],
      remainder: 0,
    });
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

  it('returns an exact bounded-inventory result for the standard 20 kg bar', () => {
    expect(calculatePlateLoad(80, 20, DEFAULT_PLATE_INVENTORY)).toEqual({
      ok: true,
      calculation: {
        targetTotal: 80,
        barWeight: 20,
        requestedPerSide: 30,
        achievedPerSide: 30,
        achievedTotal: 80,
        difference: 0,
        exact: true,
        plates: [25, 5],
      },
    });
  });

  it('chooses the lower load for an equal-distance tie and finds an above-target nearest load', () => {
    const inventory = [
      { weight: 10, count: 1 },
      { weight: 5, count: 1 },
    ];
    expect(calculatePlateLoad(35, 20, inventory)).toMatchObject({
      ok: true,
      calculation: {
        achievedTotal: 30,
        difference: -5,
        exact: false,
        plates: [5],
      },
    });
    expect(calculatePlateLoad(37, 20, inventory)).toMatchObject({
      ok: true,
      calculation: {
        achievedTotal: 40,
        difference: 3,
        exact: false,
        plates: [10],
      },
    });
  });

  it('supports a different bar and respects limited inventory without mutating it', () => {
    const inventory = [
      { weight: 25, count: 1 },
      { weight: 10, count: 1 },
      { weight: 5, count: 0 },
    ];
    const snapshot = structuredClone(inventory);
    expect(calculatePlateLoad(85, 15, inventory)).toMatchObject({
      ok: true,
      calculation: {
        achievedTotal: 85,
        achievedPerSide: 35,
        exact: true,
        plates: [25, 10],
      },
    });
    expect(calculatePlateLoad(80, 20, inventory)).toMatchObject({
      ok: true,
      calculation: {
        achievedTotal: 70,
        difference: -10,
        exact: false,
        plates: [25],
      },
    });
    expect(inventory).toEqual(snapshot);
  });

  it('rejects invalid values and precision instead of claiming an exact result', () => {
    expect(calculatePlateLoad(Number.NaN, 20, DEFAULT_PLATE_INVENTORY)).toMatchObject({
      ok: false,
      error: { code: 'invalid_target' },
    });
    expect(calculatePlateLoad(80, 0, DEFAULT_PLATE_INVENTORY)).toMatchObject({
      ok: false,
      error: { code: 'invalid_bar' },
    });
    expect(calculatePlateLoad(10, 20, DEFAULT_PLATE_INVENTORY)).toMatchObject({
      ok: false,
      error: { code: 'target_below_bar' },
    });
    expect(calculatePlateLoad(80.005, 20, DEFAULT_PLATE_INVENTORY)).toMatchObject({
      ok: false,
      error: { code: 'unsupported_precision' },
    });
    expect(calculatePlateLoad(80, 20, [{ weight: 5, count: 1.5 }])).toMatchObject({
      ok: false,
      error: { code: 'invalid_count' },
    });
    expect(
      calculatePlateLoad(80, 20, [
        { weight: 5, count: 1 },
        { weight: 5, count: 1 },
      ]),
    ).toMatchObject({
      ok: false,
      error: { code: 'duplicate_denomination' },
    });
  });

  it('handles decimal floating-point input without a false exact match', () => {
    const result = calculatePlateLoad(20.1 + 0.2, 20, DEFAULT_PLATE_INVENTORY);
    expect(result).toMatchObject({
      ok: true,
      calculation: { exact: false, achievedTotal: 20, difference: -0.3 },
    });
  });
});
