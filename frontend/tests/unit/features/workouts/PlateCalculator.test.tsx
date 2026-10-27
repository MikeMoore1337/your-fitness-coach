import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { PlateCalculator } from '../../../../src/features/workouts/PlateCalculator';

afterEach(cleanup);

describe('PlateCalculator', () => {
  it('shows the current set load as a local exact calculation without an apply action', () => {
    render(<PlateCalculator disabled={false} initialTargetWeight="80" />);

    expect(screen.getByRole('status')).toHaveTextContent('Точный результат');
    expect(screen.getByRole('group', { name: 'Доступные блины на сторону' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Итог80 кг');
    expect(screen.getByRole('status')).toHaveTextContent('На сторону: 25 кг + 5 кг');
    expect(screen.queryByRole('button', { name: 'Применить' })).not.toBeInTheDocument();
  });

  it('shows an actionable local validation message and can reset temporary inventory edits', async () => {
    const user = userEvent.setup();
    render(<PlateCalculator disabled={false} initialTargetWeight="80" />);

    const targetInput = screen.getByRole('spinbutton', { name: 'Целевой вес, кг' });
    await user.clear(targetInput);
    await user.type(targetInput, '10');
    expect(screen.getByRole('alert')).toHaveTextContent('не может быть меньше веса грифа');

    await user.clear(targetInput);
    await user.type(targetInput, '80');
    const inventoryInputs = screen.getAllByRole('spinbutton').slice(2);
    for (const input of inventoryInputs) {
      await user.clear(input);
      await user.type(input, '0');
    }
    expect(screen.getByRole('status')).toHaveTextContent('Ближайший доступный результат');

    await user.click(screen.getByRole('button', { name: 'Сбросить' }));
    expect(screen.getByRole('status')).toHaveTextContent('Точный результат');
    expect(
      screen.getByRole('spinbutton', { name: 'Количество блинов 25 кг на сторону' }),
    ).toHaveValue(2);
  });
});
