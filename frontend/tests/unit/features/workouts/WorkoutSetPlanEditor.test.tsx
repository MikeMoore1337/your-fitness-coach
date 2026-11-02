import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { WorkoutSetPlanEditor } from '../../../../src/features/workouts/WorkoutSetPlanEditor';
import type { Workout } from '../../../../src/shared/api/types';

type Exercise = Workout['exercises'][number];
const exercise = {
  id: 11,
  exercise_id: 7,
  exercise_title: 'Приседания',
  metric_type: 'strength',
  sort_order: 1,
  prescribed_sets: 2,
  prescribed_reps: '8',
  rest_seconds: 90,
  has_guide: false,
  progression_guidance: null,
  sets: [
    {
      id: 31,
      set_number: 1,
      actual_reps: 8,
      actual_weight: 40,
      rir: '2',
      is_completed: true,
      version: 2,
    },
    {
      id: 32,
      set_number: 2,
      actual_reps: null,
      actual_weight: null,
      is_completed: false,
      version: 1,
    },
  ],
} as Exercise;

afterEach(cleanup);

it('показывает факты и применяет подтверждённый план только выбранного подхода', async () => {
  const user = userEvent.setup();
  const onApply = vi.fn().mockResolvedValue(undefined);
  const onClose = vi.fn();
  render(
    <WorkoutSetPlanEditor
      exercise={exercise}
      set={exercise.sets[1]!}
      pendingBySet={new Map()}
      online
      ready
      onApply={onApply}
      onClose={onClose}
    />,
  );
  expect(screen.getByText(/40 кг · 8 повторов · RIR 2/)).toBeVisible();
  await user.type(screen.getByLabelText('Плановый вес, кг'), '37,5');
  await user.type(screen.getByLabelText('План повторов'), '8');
  await user.click(screen.getByRole('button', { name: 'Проверить изменение' }));
  expect(screen.getByText('37.5 кг · 8 повторов')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Применить к подходу' }));
  expect(onApply).toHaveBeenCalledWith(32, 1, expect.any(String), {
    weight_kg: 37.5,
    reps: 8,
    confirmed: true,
  });
  expect(onClose).toHaveBeenCalledOnce();
});

it('не предлагает проверить план до синхронизации', () => {
  const onApply = vi.fn();
  render(
    <WorkoutSetPlanEditor
      exercise={exercise}
      set={exercise.sets[1]!}
      pendingBySet={new Map()}
      online={false}
      ready={false}
      onApply={onApply}
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByRole('status')).toHaveTextContent('Дождитесь синхронизации');
  expect(screen.getByRole('button', { name: 'Проверить изменение' })).toBeDisabled();
  expect(onApply).not.toHaveBeenCalled();
});
