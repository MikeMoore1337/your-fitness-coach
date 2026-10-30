import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ActiveProgramPeriodization } from '../../../../src/features/programs/ActiveProgramPeriodization';
import { ApiError } from '../../../../src/shared/api/client';

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));
vi.mock('../../../../src/shared/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../src/shared/api/client')>()),
  api: (...args: unknown[]) => apiMock(...args),
}));

const week = (number: number, changeable = true) => ({
  week_number: number,
  source_cycle_week: 1,
  cycle_iteration: Math.floor((number - 1) / 3) + 1,
  cycle_length: 3,
  repeat: true,
  periodization_enabled: true,
  workouts: [
    {
      id: number,
      day_number: 1,
      title: 'Тренировка 1',
      scheduled_date: '2026-12-14',
      status: changeable ? 'planned' : 'completed',
      changeable,
      week_type: 'heavy',
      exercises: [],
    },
  ],
});

function setup(onChanged = vi.fn(), readOnly = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ActiveProgramPeriodization
        programId={9}
        revision={4}
        duration={16}
        initialWeek={7}
        exercises={[]}
        dirty={false}
        readOnly={readOnly}
        onChanged={onChanged}
      />
    </QueryClientProvider>,
  );
  return onChanged;
}

describe('Изменение назначенной периодизации', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string, options: { body: Record<string, unknown> }) => {
      if (path.endsWith('/preview'))
        return Promise.resolve({
          weeks: options.body.from_week ? [week(7, false), week(10)] : [week(7)],
          total_weeks: options.body.from_week ? 2 : 1,
          offset: 0,
        });
      if (path.endsWith('/week-type')) return Promise.resolve({ current_revision_number: 5 });
      throw new Error('Unexpected path');
    });
  });
  afterEach(cleanup);

  it('показывает защищённую тренировку и применяет только проверенную ревизию', async () => {
    const user = userEvent.setup();
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Новый тип недели' }), 'light');
    await user.click(screen.getByRole('radio', { name: /Будущие повторы/ }));
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    const preview = screen.getByRole('heading', { name: 'Проверить изменения' }).parentElement!;
    expect(within(preview).getByText(/не изменится/)).toBeVisible();
    expect(within(preview).getByText(/Тяжёлая → Лёгкая/)).toBeVisible();
    await user.click(within(preview).getByRole('button', { name: 'Применить изменения' }));
    expect(apiMock).toHaveBeenCalledWith('/api/v1/programs/assigned/9/cycle/week-type', {
      method: 'POST',
      body: {
        expected_revision_number: 4,
        week_type: 'light',
        from_week: 7,
        source_cycle_week: 1,
        offset: 0,
      },
    });
    expect(changed).toHaveBeenCalledWith(5);
  });

  it('сохраняет выбор и сообщает о конфликте ревизии', async () => {
    const user = userEvent.setup();
    const changed = setup();
    await screen.findByText(/Неделя 7 · исходная 1 · проход 3/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Новый тип недели' }), 'light');
    await user.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    apiMock.mockRejectedValueOnce(new ApiError('conflict', 409));
    await user.click(screen.getByRole('button', { name: 'Применить изменения' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('План уже изменился');
    expect(screen.getByRole('combobox', { name: 'Новый тип недели' })).toHaveValue('light');
    expect(changed).not.toHaveBeenCalled();
  });

  it('показывает программу тренера без действий изменения', async () => {
    setup(vi.fn(), true);
    expect(await screen.findByText(/План подготовлен тренером/)).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Проверить изменения' })).not.toBeInTheDocument();
  });
});
