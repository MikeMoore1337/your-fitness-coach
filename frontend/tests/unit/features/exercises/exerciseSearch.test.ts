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

describe('Issue 1202 typo suggestions', () => {
  const rows = [
    { id: 1, title: 'Жим гантелей лёжа', aliases: ['dumbbell bench press'] },
    { id: 2, title: 'Жим штанги лёжа', aliases: ['barbell bench press'] },
    { id: 3, title: 'Жим гантелей на наклонной скамье', aliases: ['incline dumbbell press'] },
    { id: 4, title: 'Ягодичный мост в рычажном тренажёре', aliases: ['glute drive'] },
    { id: 5, title: 'Жим в машине Смита', aliases: ['smith press'] },
    { id: 6, title: 'Тяга обратным хватом', aliases: ['reverse grip row'] },
    { id: 7, title: 'Тяга прямым хватом', aliases: ['straight grip row'] },
    { id: 8, title: 'Жим одной ногой', aliases: ['unilateral leg press'] },
    { id: 9, title: 'Жим двумя ногами', aliases: ['bilateral leg press'] },
    { id: 10, title: 'Жим гантелей с отрицательным наклоном', aliases: ['decline dumbbell press'] },
  ];

  it.each([
    ['жим гантелй', 1],
    ['рычажнй', 4],
    ['гантелей жим лёжа', 1],
    ['dumbell bench press', 1],
    ['жим лежа', 1],
    ['глют', null],
  ])('finds %s without changing canonical identity', (query, id) => {
    const results = rankExercisesForSearch(rows, query);
    if (id === null) expect(results).toEqual([]);
    else expect(results.some((item) => item.id === id)).toBe(true);
  });

  it.each([
    ['barbel bench press', 2, 1],
    ['inclne dumbbell press', 3, 1],
    ['smtih press', 5, 2],
    ['revrse grip row', 6, 7],
    ['unilaterl leg press', 8, 9],
    ['declne dumbbell press', 10, 1],
    ['declne dumbbell press', 10, 3],
  ])('does not suggest a conflicting variant for %s', (query, intended, excluded) => {
    const ids = rankExercisesForSearch(rows, query).map((item) => item.id);
    expect(ids).toContain(intended);
    expect(ids).not.toContain(excluded);
  });

  it('uses typo matches only when exact, alias, prefix and token matches fail', () => {
    const candidates = [
      { id: 1, title: 'bench press' },
      { id: 2, title: 'A', aliases: ['bench press'] },
      { id: 3, title: 'bench press wide' },
      { id: 4, title: 'bench presx wide' },
    ];
    expect(rankExercisesForSearch(candidates, 'bench press').map((item) => item.id)).toEqual([
      1, 2, 3,
    ]);
    expect(rankExercisesForSearch([candidates[3]!], 'bench press').map((item) => item.id)).toEqual([
      4,
    ]);
  });

  it('does not return an exercise just because its alternative has the searched name', () => {
    const candidates = [{ ...rows[0]!, alternatives: [{ title: 'Жим штанги лёжа' }] }, rows[1]!];
    expect(rankExercisesForSearch(candidates, 'жим штанги').map((item) => item.id)).toEqual([2]);
    expect(rankExercisesForSearch(candidates, 'жим штангй').map((item) => item.id)).toEqual([2]);
  });
});
