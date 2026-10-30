import { describe, expect, it } from 'vitest';
import {
  formatWorkoutCopy,
  type WorkoutCopyInput,
} from '../../../../src/features/workouts/workoutCopy';

const workout: WorkoutCopyInput = {
  title: 'Силовая и кардио',
  scheduled_date: '2026-10-29',
  completed_at: '2026-10-30T08:15:00',
  exercises: [
    {
      exercise_title: 'Моё упражнение',
      metric_type: 'strength',
      sort_order: 2,
      sets: [
        { set_number: 4, actual_weight: 999, actual_reps: 999, is_completed: false },
        { set_number: 3, actual_weight: 25, actual_reps: 8, set_kind: 'drop', is_completed: true },
        {
          set_number: 2,
          actual_weight: 37.5,
          actual_reps: null,
          set_kind: 'working',
          is_completed: true,
        },
        {
          set_number: 1,
          actual_weight: 0,
          actual_reps: 12,
          planned_role: 'warmup',
          is_completed: true,
        },
        { set_number: 5, actual_weight: null, actual_reps: 1, is_completed: true },
        { set_number: 6, actual_weight: null, actual_reps: null, is_completed: true },
      ],
    },
    {
      exercise_title: 'Велотренажёр',
      metric_type: 'cardio',
      sort_order: 1,
      sets: [
        {
          set_number: 1,
          is_completed: true,
          duration_minutes: 24,
          distance_km: 3.25,
          average_heart_rate_bpm: 132,
          heart_rate_zone: 2,
        },
      ],
    },
    {
      exercise_title: 'Пропущенное упражнение',
      metric_type: 'strength',
      sort_order: 3,
      sets: [{ set_number: 1, actual_reps: 5, is_completed: false }],
    },
  ],
};

describe('formatWorkoutCopy', () => {
  it('formats only completed saved facts in exercise and set order', () => {
    expect(formatWorkoutCopy(workout)).toBe(
      [
        'Силовая и кардио',
        '30.10.2026',
        '',
        'Велотренажёр',
        'Этап 1: 24 мин · 3,25 км · средний пульс 132 уд/мин · пульсовая зона 2',
        '',
        'Моё упражнение',
        'Разминка 1: 0 кг × 12 повторений',
        'Рабочий подход 2: 37,5 кг · повторы не записаны',
        'Подход со снижением веса 3: 25 кг × 8 повторений',
        'Подход 5: 1 повторение · вес не записан',
        'Подход 6: вес и повторы не записаны',
      ].join('\n'),
    );
  });

  it('never includes private fields or incomplete sets even when present in the source', () => {
    const privateWorkout = {
      ...workout,
      id: 8675309,
      completion_note: 'ЛИЧНАЯ ЗАМЕТКА',
      completion_summary: { note: 'ЕЩЁ ОДНА ЗАМЕТКА' },
      exercises: workout.exercises.map((exercise) => ({
        ...exercise,
        notes: 'СЕКРЕТ ТРЕНЕРА',
        exercise_id: 8675309,
        sets: exercise.sets.map((set) => ({ ...set, id: 8675309, rir: '2' })),
      })),
    };
    const result = formatWorkoutCopy(privateWorkout);
    expect(result).not.toMatch(/ЛИЧНАЯ ЗАМЕТКА|ЕЩЁ ОДНА ЗАМЕТКА|СЕКРЕТ ТРЕНЕРА|8675309|999/);
    expect(result).not.toContain('Пропущенное упражнение');
  });

  it('labels a scheduled date and missing cardio duration without inventing values', () => {
    expect(
      formatWorkoutCopy({
        ...workout,
        completed_at: null,
        exercises: [
          {
            exercise_title: 'Ходьба',
            metric_type: 'cardio',
            sort_order: 1,
            sets: [{ set_number: 1, is_completed: true, distance_km: 1.5 }],
          },
        ],
      }),
    ).toBe(
      'Силовая и кардио\nПо расписанию: 29.10.2026\n\nХодьба\nЭтап 1: длительность не записана · 1,5 км',
    );
  });

  it('does not present planned exercises as performed when no set is completed', () => {
    expect(formatWorkoutCopy({ ...workout, exercises: [workout.exercises[2]!] })).toBe(
      'Силовая и кардио\n30.10.2026\n\nВыполненные подходы не записаны.',
    );
  });

  it('uses the recorded set kind when it differs from the planned role', () => {
    const result = formatWorkoutCopy({
      ...workout,
      exercises: [
        {
          exercise_title: 'Приседания',
          metric_type: 'strength',
          sort_order: 1,
          sets: [
            { set_number: 1, is_completed: true, set_kind: 'working', planned_role: 'drop' },
            { set_number: 2, is_completed: true, set_kind: 'drop', planned_role: 'warmup' },
          ],
        },
      ],
    });
    expect(result).toContain('Рабочий подход 1: вес и повторы не записаны');
    expect(result).toContain('Подход со снижением веса 2: вес и повторы не записаны');
  });
});
