import { describe, expect, it } from 'vitest';
import {
  matchesExerciseSearch,
  normalizeExerciseSearchText,
  rankExercisesForSearch,
} from '../../../../src/features/exercises/exerciseSearch';
import type { Exercise } from '../../../../src/shared/api/types';

const lowerBodyExercises = [
  ['pendulum-squat', 'Маятниковый присед в тренажёре', ['pendulum squat', 'маятник в тренажере']],
  [
    'plate-loaded-leg-press',
    'Жим ногами в тренажёре с дисками',
    ['жим ногами на блинах', 'plate loaded leg press'],
  ],
  ['unilateral-leg-press', 'Жим одной ногой в тренажёре', ['single leg press']],
  [
    'machine-hip-thrust',
    'Ягодичный мост в рычажном тренажёре',
    ['ягодичный тренажер', 'glute drive'],
  ],
  ['smith-split-squat', 'Сплит-присед в машине Смита', ['смит сплит', 'smith lunge']],
  ['machine-glute-kickback', 'Разгибание бедра назад в тренажёре', ['machine glute kickback']],
  ['v-squat-machine', 'V-присед в рычажном тренажёре', ['v squat machine']],
  ['reverse-hyperextension', 'Обратная гиперэкстензия', ['reverse hyper']],
] as const;

const exercises = lowerBodyExercises.map(
  ([slug, title, aliases], index) =>
    ({
      id: 12020 + index,
      edit_target_id: 12020 + index,
      title,
      slug,
      metric_type: 'strength',
      primary_muscle: 'Ноги',
      equipment: 'Тренажёр',
      primary_muscle_ids: ['legs'],
      secondary_muscle_ids: [],
      equipment_ids: ['machine'],
      aliases: [...aliases],
      movement_pattern: 'squat',
      machine_variant_tags: ['lever'],
      execution_variant_tags: ['bilateral'],
      alternatives: [],
      difficulty_level: 'beginner',
      is_custom: false,
      is_personalized: false,
      has_guide: true,
      source_exercise_id: null,
    }) satisfies Exercise,
);

const baseExercise = exercises[0]!;

const approvedCanonicalExercises = [
  {
    ...baseExercise,
    id: 14001,
    slug: 'floor-press',
    title: 'Жим с пола',
    aliases: ['floor press', 'barbell floor press'],
    movement_pattern: 'chest_press',
  },
  {
    ...baseExercise,
    id: 14002,
    slug: 'assisted-pull-ups',
    title: 'Подтягивания с противовесом',
    aliases: ['подтягивания в гравитроне', 'assisted pull up'],
    movement_pattern: 'vertical_pull',
  },
  {
    ...baseExercise,
    id: 14003,
    slug: 'trap-bar-deadlift',
    title: 'Тяга с трэп-грифом',
    aliases: ['тяга трэп-гриф', 'hex bar deadlift'],
    movement_pattern: 'hinge',
  },
  {
    ...baseExercise,
    id: 14004,
    slug: 'machine-seated-crunch',
    title: 'Скручивания в тренажёре сидя',
    aliases: ['machine crunch', 'пресс в тренажере сидя'],
    movement_pattern: 'trunk_flexion',
  },
] satisfies Exercise[];

describe('lower-body exercise aliases', () => {
  it.each([
    ['pendulum squat', 'pendulum-squat'],
    ['жим ногами на блинах', 'plate-loaded-leg-press'],
    ['single leg press', 'unilateral-leg-press'],
    ['ягодичный тренажер', 'machine-hip-thrust'],
    ['smith lunge', 'smith-split-squat'],
    ['machine glute kickback', 'machine-glute-kickback'],
    ['v squat machine', 'v-squat-machine'],
    ['reverse hyper', 'reverse-hyperextension'],
  ])('finds %s as one canonical record', (query, expectedSlug) => {
    expect(exercises.filter((exercise) => matchesExerciseSearch(exercise, query))).toMatchObject([
      { slug: expectedSlug },
    ]);
  });
});

describe('Task 120D hardened exercise search', () => {
  const baseExercise = exercises[0] as Exercise;
  const remaining = [
    {
      ...baseExercise,
      id: 13001,
      slug: 'bodyweight-squat',
      title: 'Приседания с собственным весом',
      equipment: 'Собственный вес',
      equipment_ids: ['bodyweight'],
      aliases: ['воздушные приседания', 'air squat', 'bodyweight squat'],
      machine_variant_tags: [],
    },
    {
      ...baseExercise,
      id: 13002,
      slug: 'dead-hang',
      title: 'Вис на перекладине',
      primary_muscle: 'Хват',
      primary_muscle_ids: ['grip'],
      equipment: 'Турник',
      equipment_ids: ['bodyweight'],
      aliases: ['вис на турнике', 'пассивный вис', 'dead hang'],
      movement_pattern: 'grip',
      machine_variant_tags: [],
      execution_variant_tags: ['isometric'],
    },
    {
      ...baseExercise,
      id: 13003,
      slug: 'rowing-machine',
      title: 'Гребля на кардиотренажёре',
      aliases: ['гребля тренажер', 'rowing machine', 'row erg'],
      movement_pattern: 'cardio_row',
      equipment: 'Гребной тренажёр',
      equipment_ids: ['cardio'],
      metric_type: 'cardio',
      machine_variant_tags: [],
      execution_variant_tags: ['cyclic'],
    },
    {
      ...baseExercise,
      id: 13004,
      slug: 'goblet-squat',
      title: 'Гоблет-присед с гирей',
      aliases: ['гоблет', 'goblet squat', 'kettlebell goblet squat'],
      equipment: 'Гиря',
      equipment_ids: ['kettlebell'],
      machine_variant_tags: [],
    },
    {
      ...baseExercise,
      id: 13005,
      slug: 'kettlebell-goblet-squat',
      canonical_slug: 'goblet-squat',
      title: 'Гоблет-присед с гирей',
      aliases: [],
      equipment: 'Гиря',
      equipment_ids: ['kettlebell'],
      machine_variant_tags: [],
    },
  ] satisfies Exercise[];

  it('normalizes Unicode, punctuation, hyphens and ё consistently', () => {
    expect(normalizeExerciseSearchText('  ГРЕБЛЯ-на/тренажёре  ')).toBe('гребля на тренажере');
  });

  it.each([
    ['Приседания с собственным весом', 'bodyweight-squat'],
    ['приседания с собств', 'bodyweight-squat'],
    ['air squat', 'bodyweight-squat'],
    ['пассивный вис', 'dead-hang'],
    ['dead hang', 'dead-hang'],
    ['кардиотренажер гребля', 'rowing-machine'],
    ['row erg', 'rowing-machine'],
    ['гоблет', 'goblet-squat'],
  ])('ranks query %s with the intended canonical result first', (query, expectedSlug) => {
    expect(rankExercisesForSearch(remaining, query)[0]?.slug).toBe(expectedSlug);
  });

  it('collapses a legacy redirect into one canonical result', () => {
    expect(rankExercisesForSearch(remaining, 'goblet squat')).toMatchObject([
      { slug: 'goblet-squat' },
    ]);
    expect(rankExercisesForSearch(remaining, '')).toHaveLength(4);
  });

  it('keeps deterministic relevance ahead of alphabetical order', () => {
    expect(rankExercisesForSearch(remaining, 'гребля').map((item) => item.slug)).toEqual([
      'rowing-machine',
    ]);
  });
});

describe('Issue 395 canonical exercise search', () => {
  it.each([
    ['floor press', 'floor-press'],
    ['подтягивания в гравитроне', 'assisted-pull-ups'],
    ['трэп гриф', 'trap-bar-deadlift'],
    ['machine crunch', 'machine-seated-crunch'],
  ])('keeps %s attached to one approved canonical', (query, expectedSlug) => {
    expect(rankExercisesForSearch(approvedCanonicalExercises, query)[0]?.slug).toBe(expectedSlug);
  });
});
