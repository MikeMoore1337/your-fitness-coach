import { describe, expect, it } from 'vitest';
import {
  SIMPLE_PROGRAM_DEFAULTS,
  exerciseCountLabel,
  simpleTrainingTitle,
  trainingCountLabel,
} from '../../../../src/features/programs/programDefaults';

describe('simple program defaults', () => {
  it('keeps required API fields deterministic without asking the beginner first', () => {
    expect(SIMPLE_PROGRAM_DEFAULTS).toEqual({
      title: 'Моя программа',
      goal: 'maintenance',
      level: 'beginner',
      durationWeeks: 1,
      restSeconds: 90,
    });
    expect(simpleTrainingTitle(1)).toBe('Тренировка 1');
  });

  it('uses Russian plural forms for the available training count range', () => {
    expect(trainingCountLabel(1)).toBe('1 тренировка');
    expect(trainingCountLabel(2)).toBe('2 тренировки');
    expect(trainingCountLabel(5)).toBe('5 тренировок');
    expect(trainingCountLabel(8)).toBe('8 тренировок');
  });

  it.each([
    [0, '0 упражнений'],
    [1, '1 упражнение'],
    [2, '2 упражнения'],
    [5, '5 упражнений'],
    [10, '10 упражнений'],
    [11, '11 упражнений'],
    [12, '12 упражнений'],
    [14, '14 упражнений'],
    [21, '21 упражнение'],
    [22, '22 упражнения'],
    [25, '25 упражнений'],
    [101, '101 упражнение'],
    [111, '111 упражнений'],
    [112, '112 упражнений'],
    [114, '114 упражнений'],
  ])('uses the correct Russian exercise form for %s', (count, expected) => {
    expect(exerciseCountLabel(count)).toBe(expected);
  });
});
