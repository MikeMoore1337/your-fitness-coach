import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NutritionTargets } from '../../../../src/features/nutrition/NutritionTargets';
import { addCalendarDays, dateInputValue } from '../../../../src/shared/dateTime';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/features/nutrition/NutritionForm', () => ({ NutritionForm: () => null }));

const today = dateInputValue(new Date(), 'Europe/Moscow');
const tomorrow = addCalendarDays(today, 1);
const values = { calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 180 };
const program = {
  program_id: 1,
  revision_number: 1,
  title: 'Программа',
  start_date: today,
  duration_weeks: 20,
  schedule_mode: 'calendar',
  week_types: ['light', 'medium', 'heavy'],
};

function renderTargets(mode: 'settings' | 'override') {
  const onClose = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <NutritionTargets
        mode={mode}
        date={tomorrow}
        dateTarget={{ ...values, id: 123, user_id: 7 } as never}
        timeZone="Europe/Moscow"
        readOnly={false}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { onClose };
}

describe('NutritionTargets', () => {
  beforeEach(() => {
    apiMock.mockReset();
    apiMock.mockImplementation((path: string) => {
      if (path.endsWith('/schedule/program')) return Promise.resolve(program);
      if (path.endsWith('/schedule')) return Promise.resolve([]);
      if (path.includes('/schedule/binding?')) return Promise.resolve(null);
      if (path.includes('/program-day?'))
        return Promise.resolve({ day_type: 'training', week_type: 'light' });
      if (path.includes('/for-date?'))
        return Promise.resolve({ target: { id: 1, ...values }, origin: 'base', frozen: false });
      if (path.endsWith('/schedule/preview'))
        return Promise.resolve({
          changes: [
            {
              date: tomorrow,
              before: { id: 1, ...values },
              after: { id: 2, ...values, calories: 2100 },
            },
          ],
          expected_binding_id: null,
          expected_target_version: 1,
        });
      if (path.endsWith('/dates') || path.endsWith('/schedule')) return Promise.resolve({});
      throw new Error(`Unexpected API call: ${path}`);
    });
  });
  afterEach(cleanup);

  it('previews a single date before saving and preserves its explicit type', async () => {
    const { onClose } = renderTargets('override');
    await screen.findByText(/Сейчас: 2/);
    const later = addCalendarDays(tomorrow, 1);
    fireEvent.change(screen.getByLabelText('Выбранная дата'), { target: { value: later } });
    fireEvent.change(screen.getByLabelText('Тип дня'), { target: { value: 'recovery' } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Проверить изменения' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(
      await screen.findByRole('heading', { name: 'Цель на выбранную дату' }),
    ).toBeInTheDocument();
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/dates'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Применить к этой дате' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledWith(later));
    const call = apiMock.mock.calls.find(([path]) => path.endsWith('/dates'));
    expect(call?.[1].body).toMatchObject({
      ...values,
      effective_from: later,
      day_type: 'recovery',
      expected_target_id: 1,
    });
    expect(call?.[1].body).not.toHaveProperty('user_id');
    expect(call?.[1].headers['Idempotency-Key']).toBeTruthy();
  });

  it('requests a server preview before applying a day template', async () => {
    const { onClose } = renderTargets('settings');
    const buttons = await screen.findAllByRole('button', { name: 'Изменить' });
    await waitFor(() => expect(buttons[1]).toBeEnabled());
    fireEvent.click(buttons[1]!);
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByRole('heading', { name: 'Будущие цели' })).toBeInTheDocument();
    expect(screen.getByText(/Станет: 2/)).toBeInTheDocument();
    const previewCall = apiMock.mock.calls.find(([path]) => path.endsWith('/schedule/preview'));
    expect(previewCall?.[1].body).toMatchObject({
      scope: 'template',
      day_type: 'training',
      program_id: 1,
      revision_number: 1,
    });
    expect(
      apiMock.mock.calls.filter(
        ([path, options]) => path.endsWith('/schedule') && options?.method === 'POST',
      ),
    ).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Применить к будущим датам' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const saved = apiMock.mock.calls.find(
      ([path, options]) => path.endsWith('/schedule') && options?.method === 'POST',
    );
    expect(saved?.[1].body).toMatchObject({
      expected_binding_id: null,
      expected_target_version: 1,
    });
  });
});
