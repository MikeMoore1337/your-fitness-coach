import { useState } from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { ProgramPeriodization } from '../../../../src/features/programs/ProgramPeriodization';
import type { ProgramTemplateCreate } from '../../../../src/shared/api/types';

function Example() {
  const [cycle, setCycle] = useState<NonNullable<ProgramTemplateCreate['week_cycle']> | null>(null);
  const [duration, setDuration] = useState(4);
  return (
    <ProgramPeriodization
      cycle={cycle}
      onChange={setCycle}
      duration={duration}
      onDurationChange={setDuration}
      days={[{ title: 'Тренировка 1', exercises: [] }]}
      disabled={false}
    />
  );
}

describe('Настройка периодизации', () => {
  afterEach(cleanup);
  it('показывает 16-ю неделю и не назначает тип по умолчанию', async () => {
    const user = userEvent.setup();
    render(<Example />);
    await user.click(screen.getByRole('checkbox', { name: /Включить периодизацию/ }));
    const length = screen.getByRole('spinbutton', { name: 'Исходных недель' });
    await user.clear(length);
    await user.type(length, '3');
    const duration = screen.getByRole('spinbutton', { name: 'Всего недель' });
    await user.clear(duration);
    await user.type(duration, '16');
    expect(screen.getByRole('button', { name: 'Посмотреть план на 16 недель' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /Повторять исходный цикл/ }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Неделя 1' }), 'heavy');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Неделя 2' }), 'heavy');
    expect(screen.getByRole('combobox', { name: 'Неделя 3' })).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Посмотреть план на 16 недель' }));
    const preview = screen.getByText('План на 16 недель').parentElement!;
    expect(within(preview).getByText(/Неделя 1 · исходная 1 · проход 1/)).toBeVisible();
    const thirdWeek = within(preview).getByText(/Неделя 3 · исходная 3 · проход 1/).parentElement!;
    expect(within(thirdWeek).getByText(/Тип не задан · Тренировка 1/)).toBeVisible();
    await user.click(within(preview).getByRole('button', { name: 'Следующие недели' }));
    expect(within(preview).getByText(/Неделя 16 · исходная 1 · проход 6/)).toBeVisible();
  });

  it('для одной исходной недели показывает шестнадцатый проход', async () => {
    const user = userEvent.setup();
    render(<Example />);
    await user.click(screen.getByRole('checkbox', { name: /Включить периодизацию/ }));
    await user.click(screen.getByRole('checkbox', { name: /Повторять исходный цикл/ }));
    const duration = screen.getByRole('spinbutton', { name: 'Всего недель' });
    await user.clear(duration);
    await user.type(duration, '16');
    await user.click(screen.getByRole('button', { name: 'Посмотреть план на 16 недель' }));
    const preview = screen.getByText('План на 16 недель').parentElement!;
    await user.click(within(preview).getByRole('button', { name: 'Следующие недели' }));
    expect(within(preview).getByText(/Неделя 16 · исходная 1 · проход 16/)).toBeVisible();
  });
});
