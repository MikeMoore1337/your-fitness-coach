import type { NutritionTargetSave } from '../../shared/api/types';

type DailyRoutine = NonNullable<NutritionTargetSave['daily_routine']>;
type StepsRange = NonNullable<NutritionTargetSave['steps_range']>;
type StrengthTrainingType = NonNullable<NutritionTargetSave['strength_training_type']>;
type StrengthRest = NonNullable<NutritionTargetSave['strength_rest']>;
type CardioTraining = NonNullable<NutritionTargetSave['cardio_trainings']>[number];

export type NutritionCalculatorInput = Omit<
  NutritionTargetSave,
  | 'daily_activity_level'
  | 'record_weight_measurement'
  | 'cardio_trainings_per_week'
  | 'cardio_training_duration_minutes'
  | 'cardio_intensity'
  | 'daily_routine'
  | 'steps_range'
  | 'strength_training_type'
  | 'cardio_trainings'
> & {
  daily_routine: DailyRoutine;
  steps_range: StepsRange;
  strength_training_type: StrengthTrainingType;
  cardio_trainings: CardioTraining[];
};

const activityCoefficients: Record<DailyRoutine, Record<StepsRange, number>> = {
  mostly_sitting: {
    up_to_4000: 1.2,
    from_4000_to_7000: 1.25,
    from_7000_to_10000: 1.3,
    from_10000_to_14000: 1.35,
    over_14000: 1.4,
    unknown: 1.2,
  },
  mixed: {
    up_to_4000: 1.25,
    from_4000_to_7000: 1.3,
    from_7000_to_10000: 1.35,
    from_10000_to_14000: 1.4,
    over_14000: 1.45,
    unknown: 1.3,
  },
  mostly_on_feet: {
    up_to_4000: 1.3,
    from_4000_to_7000: 1.35,
    from_7000_to_10000: 1.4,
    from_10000_to_14000: 1.45,
    over_14000: 1.5,
    unknown: 1.4,
  },
  physical_work: {
    up_to_4000: 1.4,
    from_4000_to_7000: 1.45,
    from_7000_to_10000: 1.5,
    from_10000_to_14000: 1.55,
    over_14000: 1.6,
    unknown: 1.5,
  },
};

const strengthMetValues: Record<StrengthTrainingType, number> = {
  calm: 3.5,
  regular: 5,
  heavy: 5,
  dense: 6,
  circuit: 7,
};

const strengthRestAdjustments: Record<StrengthRest, number> = {
  under_60: 0.5,
  one_to_two: 0.25,
  two_to_three: 0,
  over_three: -0.5,
  varied: 0,
};

const cardioMetValues: Record<CardioTraining['kind'], number> = {
  walking: 3.5,
  running: 8,
  elliptical: 5,
  stationary_bike: 5.5,
  cycling: 6,
  rowing: 6,
  stepper: 6,
  swimming: 6,
  other: 5,
};

const cardioIntensityMultipliers: Record<CardioTraining['intensity'], number> = {
  very_light: 0.7,
  light: 0.85,
  moderate: 1,
  hard: 1.2,
  very_hard: 1.4,
};

const legacyDailyRoutines = {
  sedentary: 'mostly_sitting',
  low: 'mixed',
  moderate: 'mostly_on_feet',
  high: 'physical_work',
} as const;

const legacyCardioIntensities = {
  low: 'light',
  moderate: 'moderate',
  high: 'hard',
} as const;

export const goalMultipliers = {
  fat_loss: 0.85,
  recomposition: 0.95,
  maintenance: 1,
  muscle_gain: 1.05,
} as const;

export type NutritionAccuracy = 'high' | 'medium' | 'low';

export type NutritionEstimate = {
  bmr: number;
  activityCoefficient: number;
  baseTdee: number;
  strengthDailyCalories: number;
  cardioDailyCalories: number;
  maintenanceCalories: number;
  goalMultiplier: number;
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
  macroWarning: boolean;
  accuracy: NutritionAccuracy;
};

export type NutritionCalculationResult =
  | { valid: true; estimate: NutritionEstimate; errors: [] }
  | { valid: false; estimate: null; errors: string[] };

const roundNumber = (value: number) => Math.max(0, Math.floor(value + 0.5));
const roundToTen = (value: number) => Math.max(0, Math.floor(value / 10 + 0.5) * 10);
const roundUpToTen = (value: number) => Math.max(0, Math.ceil(value / 10) * 10);

const netExerciseCalories = (met: number, weightKg: number, durationMinutes: number) =>
  Math.max(0, (met - 1) * 3.5 * weightKg * durationMinutes) / 200;

const calculationAccuracy = (form: NutritionCalculatorInput): NutritionAccuracy => {
  if (form.steps_range === 'unknown') return 'low';
  if (
    (form.strength_trainings_per_week > 0 &&
      (!form.strength_rest || form.strength_rest === 'varied')) ||
    form.cardio_trainings.some((training) => training.kind === 'other')
  ) {
    return 'medium';
  }
  return 'high';
};

const normalizeInput = (
  form: NutritionCalculatorInput | NutritionTargetSave,
): NutritionCalculatorInput => {
  const legacy = form as NutritionTargetSave;
  return {
    target_telegram_user_id: form.target_telegram_user_id,
    sex: form.sex,
    weight_kg: form.weight_kg,
    height_cm: form.height_cm,
    age: form.age,
    daily_routine:
      form.daily_routine ?? legacyDailyRoutines[legacy.daily_activity_level ?? 'sedentary'],
    steps_range: form.steps_range ?? 'unknown',
    strength_trainings_per_week: form.strength_trainings_per_week,
    strength_training_duration_minutes: form.strength_training_duration_minutes,
    strength_training_type: form.strength_training_type ?? 'regular',
    strength_rest: form.strength_rest ?? 'varied',
    cardio_trainings:
      form.cardio_trainings ??
      ((legacy.cardio_trainings_per_week ?? 0) > 0
        ? [
            {
              kind: 'other',
              trainings_per_week: legacy.cardio_trainings_per_week ?? 0,
              duration_minutes: legacy.cardio_training_duration_minutes ?? 30,
              intensity: legacyCardioIntensities[legacy.cardio_intensity ?? 'moderate'],
            },
          ]
        : []),
    goal: form.goal,
  };
};

export function calculateNutritionEstimate(
  form: NutritionCalculatorInput | NutritionTargetSave,
): NutritionCalculationResult {
  const input = normalizeInput(form);
  const errors: string[] = [];
  const inRange = (value: number, min: number, max: number, label: string) => {
    if (!Number.isFinite(value) || value < min || value > max) {
      errors.push(`${label}: допустимо от ${min} до ${max}`);
    }
  };

  inRange(input.weight_kg, 20, 350, 'Вес');
  inRange(input.height_cm, 100, 250, 'Рост');
  inRange(input.age, 18, 100, 'Возраст');
  inRange(input.strength_trainings_per_week, 0, 14, 'Силовые тренировки');
  if (input.strength_trainings_per_week > 0) {
    inRange(input.strength_training_duration_minutes, 10, 300, 'Длительность силовой');
  }

  if (!Number.isInteger(input.strength_trainings_per_week)) {
    errors.push('Количество силовых тренировок должно быть целым');
  }
  input.cardio_trainings.forEach((training, index) => {
    const prefix = `Кардио ${index + 1}`;
    inRange(training.trainings_per_week, 1, 14, `${prefix}: тренировок в неделю`);
    inRange(training.duration_minutes, 10, 300, `${prefix}: продолжительность`);
    if (!Number.isInteger(training.trainings_per_week)) {
      errors.push(`${prefix}: количество тренировок должно быть целым`);
    }
  });
  if (errors.length) return { valid: false, estimate: null, errors };

  const bmrExact =
    10 * input.weight_kg +
    6.25 * input.height_cm -
    5 * input.age +
    (input.sex === 'male' ? 5 : -161);
  const activityCoefficient = activityCoefficients[input.daily_routine][input.steps_range];
  const baseTdeeExact = bmrExact * activityCoefficient;
  const strengthMet =
    strengthMetValues[input.strength_training_type] +
    (input.strength_rest ? strengthRestAdjustments[input.strength_rest] : 0);
  const strengthDailyExact =
    (netExerciseCalories(strengthMet, input.weight_kg, input.strength_training_duration_minutes) *
      input.strength_trainings_per_week) /
    7;
  const cardioDailyExact =
    input.cardio_trainings.reduce((weeklyCalories, training) => {
      const met = cardioMetValues[training.kind] * cardioIntensityMultipliers[training.intensity];
      return (
        weeklyCalories +
        netExerciseCalories(met, input.weight_kg, training.duration_minutes) *
          training.trainings_per_week
      );
    }, 0) / 7;
  const maintenanceExact = baseTdeeExact + strengthDailyExact + cardioDailyExact;
  const goalMultiplier = goalMultipliers[input.goal];
  let calories = roundToTen(maintenanceExact * goalMultiplier);

  const proteinPerKg = {
    fat_loss: 2.2,
    muscle_gain: 1.8,
    maintenance: 1.8,
    recomposition: 2,
  }[input.goal];
  const fatPerKg = input.goal === 'maintenance' || input.goal === 'muscle_gain' ? 0.9 : 0.8;
  const protein = roundNumber(input.weight_kg * proteinPerKg);
  const fat = roundNumber(input.weight_kg * fatPerKg);
  let remainingCalories = calories - protein * 4 - fat * 9;
  const macroWarning = remainingCalories < 0;
  if (macroWarning) {
    calories = roundUpToTen(protein * 4 + fat * 9);
    remainingCalories = calories - protein * 4 - fat * 9;
  }

  return {
    valid: true,
    errors: [],
    estimate: {
      bmr: roundNumber(bmrExact),
      activityCoefficient,
      baseTdee: roundNumber(baseTdeeExact),
      strengthDailyCalories: roundNumber(strengthDailyExact),
      cardioDailyCalories: roundNumber(cardioDailyExact),
      maintenanceCalories: roundNumber(maintenanceExact),
      goalMultiplier,
      calories,
      protein,
      fat,
      carbs: roundNumber(remainingCalories / 4),
      macroWarning,
      accuracy: calculationAccuracy(input),
    },
  };
}
