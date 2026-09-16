export const ONE_REP_MAX_MIN_WEIGHT_KG = 0.5;
export const ONE_REP_MAX_MAX_WEIGHT_KG = 500;
export const ONE_REP_MAX_MIN_REPETITIONS = 1;
export const ONE_REP_MAX_MAX_REPETITIONS = 10;

export const ONE_REP_MAX_PERCENTAGES = [95, 90, 85, 80, 75, 70] as const;

export type OneRepMaxInput = {
  weightKg: number;
  repetitions: number;
};

export type OneRepMaxErrorField = 'weightKg' | 'repetitions';

export type OneRepMaxValidationError = {
  field: OneRepMaxErrorField;
  message: string;
};

export type OneRepMaxWorkingWeight = {
  percentage: (typeof ONE_REP_MAX_PERCENTAGES)[number];
  weightKg: number;
};

export type OneRepMaxEstimate = {
  estimated1rmKg: number;
  workingWeights: OneRepMaxWorkingWeight[];
};

export type OneRepMaxCalculationResult =
  | { valid: true; estimate: OneRepMaxEstimate; errors: [] }
  | { valid: false; estimate: null; errors: OneRepMaxValidationError[] };

// Полкило — формат отображения, а не заявление о точности формулы.
export function roundOneRepMaxWeight(valueKg: number): number {
  return Math.max(0, Math.round(valueKg * 2) / 2);
}

function formatBoundary(value: number): string {
  return String(value).replace('.', ',');
}

export function calculateOneRepMax(input: OneRepMaxInput): OneRepMaxCalculationResult {
  const errors: OneRepMaxValidationError[] = [];

  if (
    !Number.isFinite(input.weightKg) ||
    input.weightKg < ONE_REP_MAX_MIN_WEIGHT_KG ||
    input.weightKg > ONE_REP_MAX_MAX_WEIGHT_KG
  ) {
    errors.push({
      field: 'weightKg',
      message: `Укажите вес от ${formatBoundary(ONE_REP_MAX_MIN_WEIGHT_KG)} до ${formatBoundary(ONE_REP_MAX_MAX_WEIGHT_KG)} кг.`,
    });
  }

  if (
    !Number.isFinite(input.repetitions) ||
    !Number.isInteger(input.repetitions) ||
    input.repetitions < ONE_REP_MAX_MIN_REPETITIONS ||
    input.repetitions > ONE_REP_MAX_MAX_REPETITIONS
  ) {
    errors.push({
      field: 'repetitions',
      message: `Укажите целое число повторений от ${ONE_REP_MAX_MIN_REPETITIONS} до ${ONE_REP_MAX_MAX_REPETITIONS}.`,
    });
  }

  if (errors.length > 0) return { valid: false, estimate: null, errors };

  const rawEstimate = input.weightKg / (1.0278 - 0.0278 * input.repetitions);
  const estimated1rmKg = roundOneRepMaxWeight(rawEstimate);
  const workingWeights = ONE_REP_MAX_PERCENTAGES.map((percentage) => ({
    percentage,
    weightKg: roundOneRepMaxWeight((estimated1rmKg * percentage) / 100),
  }));

  return {
    valid: true,
    errors: [],
    estimate: { estimated1rmKg, workingWeights },
  };
}
