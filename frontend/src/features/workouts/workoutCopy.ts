import type { WorkoutCopy } from '../../shared/api/types';

type CopyExercise = WorkoutCopy['exercises'][number];
type CopySet = Omit<CopyExercise['sets'][number], 'is_completed'> & {
  is_completed?: boolean;
};

export type WorkoutCopyInput = Omit<WorkoutCopy, 'exercises'> & {
  exercises: Array<Omit<CopyExercise, 'sets'> & { sets: CopySet[] }>;
};

function number(value: number): string {
  return String(value).replace('.', ',');
}

function repetitions(value: number): string {
  const mod10 = value % 10;
  const mod100 = value % 100;
  const word =
    mod10 === 1 && mod100 !== 11
      ? 'повторение'
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? 'повторения'
        : 'повторений';
  return `${value} ${word}`;
}

function isWarmup(set: CopySet): boolean {
  return set.set_kind === 'warmup' || (set.set_kind !== 'drop' && set.planned_role === 'warmup');
}

function setLabel(set: CopySet): string {
  if (set.set_kind === 'drop') return 'Подход со снижением веса';
  if (isWarmup(set)) return 'Разминка';
  return set.set_kind === 'working' ? 'Рабочий подход' : 'Подход';
}

function strengthResult(set: Pick<CopySet, 'actual_weight' | 'actual_reps'>): string {
  const weight = set.actual_weight == null ? null : `${number(set.actual_weight)} кг`;
  const reps = set.actual_reps == null ? null : repetitions(set.actual_reps);
  if (weight && reps) return `${weight} × ${reps}`;
  if (weight) return `${weight} · повторы не записаны`;
  if (reps) return `${reps} · вес не записан`;
  return 'вес и повторы не записаны';
}

function sideResult(label: string, side: NonNullable<CopySet['sides']>['left']): string {
  if (!side) return `${label}: нет данных`;
  return [
    `${label}: ${strengthResult(side)}`,
    side.rir == null ? null : `RIR ${side.rir}`,
    side.reached_failure ? 'до отказа' : null,
    side.is_completed ? null : 'не завершена',
  ]
    .filter(Boolean)
    .join(' · ');
}

function hasSideFacts(set: CopySet): boolean {
  return (
    !!set.sides &&
    [set.sides.left, set.sides.right].some(
      (side) =>
        side &&
        (side.is_completed ||
          side.actual_reps != null ||
          side.actual_weight != null ||
          side.rir != null ||
          side.reached_failure != null),
    )
  );
}

function cardioResult(set: CopySet): string {
  return [
    set.duration_minutes == null ? 'длительность не записана' : `${set.duration_minutes} мин`,
    set.distance_km == null ? null : `${number(set.distance_km)} км`,
    set.average_heart_rate_bpm == null
      ? null
      : `средний пульс ${set.average_heart_rate_bpm} уд/мин`,
    set.heart_rate_zone == null ? null : `пульсовая зона ${set.heart_rate_zone}`,
  ]
    .filter((value) => value !== null)
    .join(' · ');
}

function dateText(value: string): string {
  const [year, month, day] = value.slice(0, 10).split('-');
  return `${day}.${month}.${year}`;
}

export function formatWorkoutCopy(workout: WorkoutCopyInput): string {
  const date = workout.completed_at?.slice(0, 10);
  const lines = [
    workout.title,
    date ? dateText(date) : `По расписанию: ${dateText(workout.scheduled_date)}`,
  ];
  const exercises = [...workout.exercises].sort(
    (left, right) => left.sort_order - right.sort_order,
  );
  for (const exercise of exercises) {
    const sets = exercise.sets
      .filter((set) => set.is_completed === true || hasSideFacts(set))
      .sort((left, right) => {
        return (
          Number(isWarmup(right)) - Number(isWarmup(left)) || left.set_number - right.set_number
        );
      });
    if (!sets.length) continue;
    lines.push('', exercise.exercise_title);
    for (const set of sets) {
      if (
        exercise.metric_type === 'strength' &&
        set.sides &&
        (set.execution_mode === 'per_side' || set.execution_mode === 'alternating')
      ) {
        const state = set.is_completed ? '' : ' · не завершён';
        lines.push(
          `${setLabel(set)} ${set.set_number}${state}: ${sideResult('Левая', set.sides.left)}; ${sideResult('Правая', set.sides.right)}`,
        );
      } else {
        lines.push(
          exercise.metric_type === 'cardio'
            ? `Этап ${set.set_number}: ${cardioResult(set)}`
            : `${setLabel(set)} ${set.set_number}: ${strengthResult(set)}`,
        );
      }
    }
  }
  if (lines.length === 2) lines.push('', 'Выполненные подходы не записаны.');
  return lines.join('\n');
}
