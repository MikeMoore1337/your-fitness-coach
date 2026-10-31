import type { ApiSchemas } from '../../shared/api/types';

type Sides = ApiSchemas['WorkoutSideResults'];

export function formatWorkoutSides(sides: Sides): string {
  return (['left', 'right'] as const)
    .map((key) => {
      const side = sides[key];
      const label = key === 'left' ? 'Левая' : 'Правая';
      if (!side) return `${label}: нет данных`;
      const weight = side.actual_weight == null ? 'вес не указан' : `${side.actual_weight} кг`;
      const reps = side.actual_reps == null ? 'повторы не указаны' : `${side.actual_reps} повт.`;
      const failure =
        side.reached_failure == null ? '' : side.reached_failure ? ' · до отказа' : ' · без отказа';
      return `${label}: ${weight} × ${reps}${side.rir == null ? '' : ` · RIR ${side.rir}`}${failure}${side.is_completed ? '' : ' · не завершена'}`;
    })
    .join('; ');
}
