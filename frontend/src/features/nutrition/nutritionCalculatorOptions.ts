import type { NutritionAccuracy, NutritionCalculatorInput } from './nutritionCalculator';

export type CardioTraining = NutritionCalculatorInput['cardio_trainings'][number];

export const nutritionCalculatorDefaults: NutritionCalculatorInput = {
  sex: 'male',
  weight_kg: 75,
  height_cm: 175,
  age: 30,
  daily_routine: 'mixed',
  steps_range: 'from_7000_to_10000',
  strength_trainings_per_week: 3,
  strength_training_duration_minutes: 60,
  strength_training_type: 'regular',
  strength_rest: 'one_to_two',
  cardio_trainings: [],
  goal: 'maintenance',
};

export const goalOptions = {
  fat_loss: {
    label: 'Снижение жира',
    description: 'Постепенно снижать вес и максимально сохранять мышцы.',
  },
  recomposition: {
    label: 'Рекомпозиция',
    description:
      'Снижать количество жира и сохранять или набирать мышцы без выраженного изменения веса.',
  },
  maintenance: {
    label: 'Поддержание',
    description: 'Сохранять текущий вес и форму.',
  },
  muscle_gain: {
    label: 'Набор мышечной массы',
    description: 'Постепенно увеличивать массу с минимальным набором жира.',
  },
} as const;

export const routineOptions = {
  mostly_sitting: {
    label: 'В основном сижу',
    description: 'Офис, удалённая работа, учёба, мало перемещений.',
  },
  mixed: {
    label: 'Периодически хожу и стою',
    description: 'Часть дня сижу, часть дня нахожусь на ногах.',
  },
  mostly_on_feet: {
    label: 'Большую часть дня на ногах',
    description: 'Много хожу по работе, редко сижу.',
  },
  physical_work: {
    label: 'Физическая работа',
    description: 'Регулярно переношу тяжести или выполняю физическую работу.',
  },
} as const;

export const stepsOptions = {
  up_to_4000: 'До 4 000',
  from_4000_to_7000: '4 000–7 000',
  from_7000_to_10000: '7 000–10 000',
  from_10000_to_14000: '10 000–14 000',
  over_14000: 'Более 14 000',
  unknown: 'Не знаю',
} as const;

export const strengthTypeOptions = {
  calm: {
    label: 'Спокойная',
    description: 'Небольшие веса, тренажёры и изолирующие упражнения, длинные паузы.',
  },
  regular: {
    label: 'Обычная силовая',
    description: 'Рабочие подходы, отдых преимущественно 1–3 минуты.',
  },
  heavy: {
    label: 'Тяжёлая силовая с длинными паузами',
    description: 'Тяжёлые базовые упражнения, мало повторений, отдых от 3 минут.',
  },
  dense: {
    label: 'Плотная силовая',
    description: 'Короткие паузы, суперсеты, высокая плотность работы.',
  },
  circuit: {
    label: 'Круговая тренировка',
    description: 'Упражнения выполняются последовательно с минимальным отдыхом.',
  },
} as const;

export const strengthRestOptions = {
  under_60: 'До 60 секунд',
  one_to_two: '1–2 минуты',
  two_to_three: '2–3 минуты',
  over_three: 'Более 3 минут',
  varied: 'По-разному',
} as const;

export const cardioKindOptions = {
  walking: 'Ходьба',
  running: 'Бег',
  elliptical: 'Эллипсоид',
  stationary_bike: 'Велотренажёр',
  cycling: 'Велосипед',
  rowing: 'Гребной тренажёр',
  stepper: 'Степпер',
  swimming: 'Плавание',
  other: 'Другое',
} as const;

export const cardioIntensityOptions = {
  very_light: {
    label: 'Очень легко',
    description: 'Дышу спокойно, могу свободно разговаривать.',
  },
  light: {
    label: 'Легко',
    description: 'Дыхание немного учащено, могу говорить длинными предложениями.',
  },
  moderate: {
    label: 'Умеренно',
    description: 'Дышу заметно чаще, могу говорить короткими предложениями.',
  },
  hard: {
    label: 'Тяжело',
    description: 'Могу произнести только несколько слов подряд.',
  },
  very_hard: {
    label: 'Очень тяжело',
    description: 'Разговаривать почти невозможно.',
  },
} as const;

export const goalAdjustmentLabels = {
  fat_loss: '−15%',
  recomposition: '0%',
  maintenance: '0%',
  muscle_gain: '+5%',
} as const;

export const accuracyLabels: Record<NutritionAccuracy, string> = {
  high: 'высокая',
  medium: 'средняя',
  low: 'низкая',
};

export const newCardioTraining = (): CardioTraining => ({
  kind: 'walking',
  trainings_per_week: 2,
  duration_minutes: 30,
  intensity: 'moderate',
});
