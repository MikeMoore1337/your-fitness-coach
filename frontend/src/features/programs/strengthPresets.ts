import type { Exercise, ProgramTemplateCreate } from '../../shared/api/types';

export type StrengthSplit = 'fullbody' | 'upper_lower' | 'push_pull_legs' | 'split';
export type AthleteLevel = ProgramTemplateCreate['level'];

export const strengthTemplateRules = {
  beginner: {
    fullbody: { min: 2, max: 3, recommended: 3, warning: '' },
    upper_lower: { min: 3, max: 4, recommended: 3, warning: '' },
    push_pull_legs: {
      min: 3,
      max: 4,
      recommended: 3,
      warning:
        'Для новичка схема «толкай/тяни/ноги» (PPL) требует уверенной техники и контроля объёма.',
    },
    split: {
      min: 3,
      max: 4,
      recommended: 4,
      warning:
        'Для новичка тренировки всего тела или схема «верх/низ» обычно эффективнее классического сплита.',
    },
  },
  intermediate: {
    fullbody: { min: 3, max: 4, recommended: 3, warning: '' },
    upper_lower: { min: 4, max: 5, recommended: 4, warning: '' },
    push_pull_legs: { min: 4, max: 6, recommended: 5, warning: '' },
    split: { min: 4, max: 5, recommended: 5, warning: '' },
  },
  advanced: {
    fullbody: { min: 3, max: 5, recommended: 4, warning: '' },
    upper_lower: { min: 4, max: 6, recommended: 4, warning: '' },
    push_pull_legs: { min: 5, max: 6, recommended: 6, warning: '' },
    split: { min: 5, max: 6, recommended: 5, warning: '' },
  },
} as const;

type PresetExercise = [slug: string, sets: number, reps: string, rest: number];
interface PresetDay {
  title: string;
  exercises: PresetExercise[];
}

const library: Record<string, PresetDay> = {
  fullbodyA: {
    title: 'Всё тело A · грудь и квадрицепс',
    exercises: [
      ['squat', 4, '6-8', 150],
      ['bench-press', 4, '6-8', 150],
      ['seated-cable-row', 3, '10-12', 90],
      ['romanian-deadlift', 3, '8-10', 120],
      ['plank', 3, '30-60 сек', 60],
    ],
  },
  fullbodyB: {
    title: 'Всё тело B · спина и бёдра',
    exercises: [
      ['deadlift', 3, '3-5', 180],
      ['overhead-press', 4, '6-8', 150],
      ['lat-pulldown', 3, '10-12', 90],
      ['leg-press', 3, '10-12', 120],
      ['hanging-leg-raise', 3, '10-15', 60],
    ],
  },
  fullbodyC: {
    title: 'Всё тело C · ягодицы и спина',
    exercises: [
      ['front-squat', 4, '6-8', 150],
      ['incline-dumbbell-press', 3, '8-10', 120],
      ['barbell-row', 4, '6-8', 150],
      ['hip-thrust', 3, '8-10', 120],
      ['face-pull', 3, '12-15', 60],
    ],
  },
  fullbodyD: {
    title: 'Всё тело D · облегчённая',
    exercises: [
      ['leg-press', 3, '10-12', 120],
      ['machine-chest-press', 3, '10-12', 90],
      ['chest-supported-row', 3, '10-12', 90],
      ['dumbbell-lateral-raise', 3, '12-15', 60],
      ['cable-crunch', 3, '12-15', 60],
    ],
  },
  fullbodyE: {
    title: 'Всё тело E · плечи и руки',
    exercises: [
      ['goblet-squat', 3, '10-12', 90],
      ['dumbbell-bench-press', 3, '8-10', 90],
      ['seated-cable-row', 3, '10-12', 90],
      ['machine-shoulder-press', 3, '10-12', 90],
      ['cable-curl', 3, '12-15', 60],
      ['rope-pushdown', 3, '12-15', 60],
    ],
  },
  upperA: {
    title: 'Верх A',
    exercises: [
      ['bench-press', 4, '5-8', 150],
      ['barbell-row', 4, '6-8', 150],
      ['overhead-press', 3, '6-8', 120],
      ['lat-pulldown', 3, '10-12', 90],
      ['rope-pushdown', 3, '10-12', 75],
      ['barbell-curl', 3, '10-12', 75],
    ],
  },
  lowerA: {
    title: 'Низ A',
    exercises: [
      ['squat', 4, '5-8', 180],
      ['romanian-deadlift', 4, '8-10', 150],
      ['leg-press', 3, '10-12', 120],
      ['leg-curl', 3, '10-12', 90],
      ['standing-calf-raise', 4, '12-15', 60],
    ],
  },
  upperB: {
    title: 'Верх B',
    exercises: [
      ['incline-dumbbell-press', 4, '8-10', 120],
      ['pull-up', 4, '6-10', 120],
      ['seated-dumbbell-press', 3, '8-10', 120],
      ['seated-cable-row', 3, '10-12', 90],
      ['face-pull', 3, '12-15', 60],
    ],
  },
  lowerB: {
    title: 'Низ B',
    exercises: [
      ['front-squat', 4, '6-8', 150],
      ['hip-thrust', 4, '8-10', 120],
      ['bulgarian-split-squat', 3, '8-10', 120],
      ['seated-leg-curl', 3, '10-12', 90],
      ['seated-calf-raise', 4, '12-15', 60],
    ],
  },
  upperSpecialization: {
    title: 'Верх · специализация плеч и рук',
    exercises: [
      ['machine-chest-press', 3, '10-12', 90],
      ['chest-supported-row', 3, '10-12', 90],
      ['machine-shoulder-press', 4, '8-10', 120],
      ['dumbbell-lateral-raise', 3, '12-15', 60],
      ['rope-pushdown', 3, '10-12', 75],
      ['hammer-curl', 3, '10-12', 75],
    ],
  },
  lowerSpecialization: {
    title: 'Низ · специализация ягодиц',
    exercises: [
      ['hip-thrust', 4, '8-10', 120],
      ['bulgarian-split-squat', 3, '8-10', 120],
      ['seated-leg-curl', 3, '10-12', 90],
      ['hip-abduction', 3, '12-15', 60],
      ['seated-calf-raise', 4, '12-15', 60],
    ],
  },
  push: {
    title: 'Толкай',
    exercises: [
      ['bench-press', 4, '5-8', 150],
      ['incline-dumbbell-press', 3, '8-10', 120],
      ['overhead-press', 3, '6-8', 150],
      ['dumbbell-lateral-raise', 3, '12-15', 60],
      ['rope-pushdown', 3, '10-12', 75],
    ],
  },
  pull: {
    title: 'Тяни',
    exercises: [
      ['pull-up', 4, '6-10', 120],
      ['barbell-row', 4, '6-8', 150],
      ['lat-pulldown', 3, '10-12', 90],
      ['face-pull', 3, '12-15', 75],
      ['barbell-curl', 3, '8-10', 90],
    ],
  },
  legs: {
    title: 'Ноги',
    exercises: [
      ['squat', 4, '5-8', 180],
      ['leg-press', 3, '10-12', 150],
      ['romanian-deadlift', 3, '8-10', 150],
      ['leg-curl', 3, '10-12', 90],
      ['standing-calf-raise', 4, '12-15', 60],
    ],
  },
  chestArms: {
    title: 'Грудь и руки',
    exercises: [
      ['bench-press', 4, '6-8', 150],
      ['incline-dumbbell-press', 4, '8-10', 120],
      ['cable-fly', 3, '12-15', 75],
      ['rope-pushdown', 3, '10-12', 75],
      ['barbell-curl', 3, '8-10', 90],
    ],
  },
  back: {
    title: 'Спина',
    exercises: [
      ['pull-up', 4, '6-10', 120],
      ['barbell-row', 4, '6-8', 150],
      ['seated-cable-row', 3, '10-12', 90],
      ['lat-pulldown', 3, '10-12', 90],
      ['face-pull', 3, '12-15', 75],
    ],
  },
  shoulders: {
    title: 'Плечи',
    exercises: [
      ['overhead-press', 4, '6-8', 150],
      ['dumbbell-lateral-raise', 4, '12-15', 60],
      ['reverse-pec-deck', 3, '12-15', 75],
      ['face-pull', 3, '12-15', 75],
      ['dumbbell-shrug', 3, '10-12', 90],
    ],
  },
};

const sequences: Record<StrengthSplit, string[]> = {
  fullbody: ['fullbodyA', 'fullbodyB', 'fullbodyC', 'fullbodyD', 'fullbodyE'],
  upper_lower: [
    'upperA',
    'lowerA',
    'upperB',
    'lowerB',
    'upperSpecialization',
    'lowerSpecialization',
  ],
  push_pull_legs: ['push', 'pull', 'legs', 'push', 'pull', 'legs'],
  split: ['chestArms', 'back', 'legs', 'shoulders', 'upperSpecialization', 'lowerSpecialization'],
};

export function resolveStrengthRule(level: AthleteLevel, split: StrengthSplit) {
  return strengthTemplateRules[level][split];
}

export function buildStrengthPreset(
  exercises: Exercise[],
  level: AthleteLevel,
  split: StrengthSplit,
  dayCount: number,
): ProgramTemplateCreate['days'] {
  const levelRows = exercises.filter((exercise) => exercise.difficulty_level === level);
  const pool = levelRows.length ? levelRows : exercises;
  return sequences[split].slice(0, dayCount).map((key) => {
    const day = library[key]!;
    const used = new Set<number>();
    return {
      title: day.title,
      exercises: day.exercises
        .map(([slug, sets, reps, rest], index) => {
          const source = exercises.find((exercise) => exercise.slug === slug);
          const sameMuscle = pool.filter(
            (exercise) =>
              source?.primary_muscle &&
              exercise.primary_muscle === source.primary_muscle &&
              !used.has(exercise.id),
          );
          const candidate =
            pool.find((exercise) => exercise.slug === slug && !used.has(exercise.id)) ??
            sameMuscle[0] ??
            pool.find((exercise) => !used.has(exercise.id)) ??
            pool[index % Math.max(pool.length, 1)];
          if (candidate) used.add(candidate.id);
          return {
            exercise_id: candidate?.id ?? 0,
            prescribed_sets: sets,
            prescribed_reps: reps,
            rest_seconds: rest,
            notes: null,
          };
        })
        .filter((item) => item.exercise_id > 0),
    };
  });
}
