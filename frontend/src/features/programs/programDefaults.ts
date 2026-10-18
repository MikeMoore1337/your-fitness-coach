import type { ProgramTemplateCreate } from '../../shared/api/types';

export const SIMPLE_PROGRAM_DEFAULTS = {
  title: 'Моя программа',
  goal: 'maintenance' as ProgramTemplateCreate['goal'],
  level: 'beginner' as ProgramTemplateCreate['level'],
  durationWeeks: 1,
  restSeconds: 90,
} as const;

export function simpleTrainingTitle(index: number): string {
  return `Тренировка ${index}`;
}

export function russianCountLabel(count: number, one: string, few: string, many: string): string {
  const modulo100 = count % 100;
  const modulo10 = count % 10;
  const noun =
    modulo100 >= 11 && modulo100 <= 14
      ? many
      : modulo10 === 1
        ? one
        : modulo10 >= 2 && modulo10 <= 4
          ? few
          : many;
  return `${count} ${noun}`;
}

export function trainingCountLabel(count: number): string {
  return russianCountLabel(count, 'тренировка', 'тренировки', 'тренировок');
}

export function exerciseCountLabel(count: number): string {
  return russianCountLabel(count, 'упражнение', 'упражнения', 'упражнений');
}
