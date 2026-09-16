import { describe, expect, it } from 'vitest';
import {
  calculateNutritionEstimate,
  type NutritionCalculatorInput,
} from '../../../../src/features/nutrition/nutritionCalculator';

const payload = (overrides: Partial<NutritionCalculatorInput> = {}): NutritionCalculatorInput => ({
  sex: 'male',
  weight_kg: 78,
  height_cm: 165,
  age: 34,
  daily_routine: 'mixed',
  steps_range: 'from_4000_to_7000',
  strength_trainings_per_week: 4,
  strength_training_duration_minutes: 60,
  strength_training_type: 'regular',
  strength_rest: 'two_to_three',
  cardio_trainings: [
    {
      kind: 'running',
      trainings_per_week: 3,
      duration_minutes: 30,
      intensity: 'moderate',
    },
  ],
  goal: 'recomposition',
  ...overrides,
});

describe('nutrition calculator', () => {
  it('calculates routine, steps and net training expenditure', () => {
    const result = calculateNutritionEstimate(payload());

    expect(result.valid).toBe(true);
    if (!result.valid) return;
    expect(result.estimate).toEqual({
      bmr: 1646,
      activityCoefficient: 1.3,
      baseTdee: 2140,
      strengthDailyCalories: 187,
      cardioDailyCalories: 123,
      maintenanceCalories: 2450,
      goalMultiplier: 1,
      calories: 2450,
      protein: 156,
      fat: 62,
      carbs: 317,
      macroWarning: false,
      accuracy: 'high',
    });
  });

  it('supports the female equation and the documented adult boundaries', () => {
    const result = calculateNutritionEstimate(
      payload({
        sex: 'female',
        weight_kg: 20,
        height_cm: 100,
        age: 18,
        strength_trainings_per_week: 0,
        cardio_trainings: [],
      }),
    );

    expect(result.valid).toBe(true);
    if (!result.valid) return;
    expect(result.estimate.bmr).toBe(574);
    expect(result.estimate.calories).toBeGreaterThan(0);
    expect(Number.isFinite(result.estimate.carbs)).toBe(true);
  });

  it('rejects values outside every public numeric boundary', () => {
    const result = calculateNutritionEstimate(
      payload({
        weight_kg: 19,
        height_cm: 99,
        age: 17,
        strength_trainings_per_week: 14.5,
      }),
    );

    expect(result.valid).toBe(false);
    expect(result.errors).toEqual(
      expect.arrayContaining([
        'Вес: допустимо от 20 до 350',
        'Рост: допустимо от 100 до 250',
        'Возраст: допустимо от 18 до 100',
        'Силовые тренировки: допустимо от 0 до 14',
        'Количество силовых тренировок должно быть целым',
      ]),
    );
  });

  it.each([
    ['mostly_sitting', 'up_to_4000', 1976],
    ['mostly_sitting', 'over_14000', 2305],
    ['mixed', 'from_7000_to_10000', 2222],
    ['mostly_on_feet', 'unknown', 2305],
    ['physical_work', 'from_10000_to_14000', 2552],
  ] as const)('combines %s and %s into one ordinary-day estimate', (routine, steps, expected) => {
    const result = calculateNutritionEstimate(
      payload({
        daily_routine: routine,
        steps_range: steps,
        strength_trainings_per_week: 0,
        cardio_trainings: [],
      }),
    );

    expect(result.valid && result.estimate.baseTdee).toBe(expected);
  });

  it('uses training type, rest and duration for strength net calories', () => {
    const result = calculateNutritionEstimate(
      payload({
        strength_training_type: 'dense',
        strength_rest: 'under_60',
        strength_training_duration_minutes: 75,
        cardio_trainings: [],
      }),
    );

    expect(result.valid && result.estimate.strengthDailyCalories).toBe(322);
  });

  it('sums separate kinds of cardio as net calories', () => {
    const result = calculateNutritionEstimate(
      payload({
        strength_trainings_per_week: 0,
        cardio_trainings: [
          {
            kind: 'walking',
            trainings_per_week: 2,
            duration_minutes: 45,
            intensity: 'light',
          },
          {
            kind: 'swimming',
            trainings_per_week: 1,
            duration_minutes: 60,
            intensity: 'hard',
          },
        ],
      }),
    );

    expect(result.valid && result.estimate.cardioDailyCalories).toBe(107);
  });

  it.each([
    ['fat_loss', 172, 62],
    ['recomposition', 156, 62],
    ['maintenance', 140, 70],
    ['muscle_gain', 140, 70],
  ] as const)('uses weight-based macro targets for %s', (goal, protein, fat) => {
    const result = calculateNutritionEstimate(payload({ goal }));

    expect(result.valid && result.estimate.protein).toBe(protein);
    expect(result.valid && result.estimate.fat).toBe(fat);
    if (!result.valid) return;
    const macroCalories =
      result.estimate.protein * 4 + result.estimate.fat * 9 + result.estimate.carbs * 4;
    expect(Math.abs(macroCalories - result.estimate.calories)).toBeLessThanOrEqual(10);
  });

  it('reports confidence from the completeness of activity details', () => {
    const unknownSteps = calculateNutritionEstimate(payload({ steps_range: 'unknown' }));
    const approximateStrength = calculateNutritionEstimate(payload({ strength_rest: 'varied' }));
    const otherCardio = calculateNutritionEstimate(
      payload({ cardio_trainings: [{ ...payload().cardio_trainings[0]!, kind: 'other' }] }),
    );

    expect(unknownSteps.valid && unknownSteps.estimate.accuracy).toBe('low');
    expect(approximateStrength.valid && approximateStrength.estimate.accuracy).toBe('medium');
    expect(otherCardio.valid && otherCardio.estimate.accuracy).toBe('medium');
  });

  it('rejects empty-equivalent and unrealistic values without producing NaN', () => {
    const result = calculateNutritionEstimate(
      payload({
        weight_kg: 0,
        cardio_trainings: [{ ...payload().cardio_trainings[0]!, duration_minutes: 301 }],
      }),
    );

    expect(result.valid).toBe(false);
    expect(result.errors).toHaveLength(2);
    expect(result.estimate).toBeNull();
  });

  it('clamps negative carbohydrates and reports the macro warning', () => {
    const result = calculateNutritionEstimate(
      payload({
        weight_kg: 350,
        height_cm: 100,
        age: 100,
        daily_routine: 'mostly_sitting',
        steps_range: 'up_to_4000',
        strength_trainings_per_week: 0,
        cardio_trainings: [],
        goal: 'fat_loss',
      }),
    );

    expect(result.valid && result.estimate.carbs).toBe(0);
    expect(result.valid && result.estimate.macroWarning).toBe(true);
    expect(
      result.valid &&
        result.estimate.calories === result.estimate.protein * 4 + result.estimate.fat * 9,
    ).toBe(true);
  });
});
