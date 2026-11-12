import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import {
  ClientNutritionProposals,
  TrainerNutritionProposals,
} from '../../../../src/features/nutrition/CoachNutritionProposals';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => ({ toast: vi.fn() }),
}));

function setup(element: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  apiMock.mockReset();
});

it('не даёт вводить цели до загрузки плана', () => {
  apiMock.mockImplementation((path: string) =>
    path.includes('/day?')
      ? new Promise(() => {})
      : Promise.resolve(path.includes('/target-assignments') ? { dates: [], schedule: [] } : []),
  );
  setup(<TrainerNutritionProposals clientId={123} timeZone="Europe/Moscow" />);
  fireEvent.click(screen.getByRole('button', { name: 'Предложить изменение' }));
  expect(screen.getByLabelText('Энергия, ккал')).toBeDisabled();
});

it('тренер проверяет сравнение перед отправкой предложения', async () => {
  apiMock.mockImplementation(
    (path: string, options?: { method?: string; body?: Record<string, unknown> }) => {
      if (options?.method === 'POST')
        return Promise.resolve({
          id: 1,
          status: 'pending',
          target_date: options.body?.target_date,
          request: options.body,
          before: { target: null, item: null },
        });
      if (path.includes('/target-assignments')) return Promise.resolve({ dates: [], schedule: [] });
      if (path.includes('/day?'))
        return Promise.resolve({ target_id: null, day: { revision: 0, targets: null, slots: [] } });
      return Promise.resolve([]);
    },
  );
  setup(<TrainerNutritionProposals clientId={123} timeZone="Europe/Moscow" />);
  fireEvent.click(screen.getByRole('button', { name: 'Предложить изменение' }));
  await screen.findByText(/Текущая цель/);
  fireEvent.change(screen.getByLabelText('Энергия, ккал'), { target: { value: '2000' } });
  fireEvent.change(screen.getByLabelText('Белки, г'), { target: { value: '150' } });
  fireEvent.change(screen.getByLabelText('Жиры, г'), { target: { value: '70' } });
  fireEvent.change(screen.getByLabelText('Углеводы, г'), { target: { value: '180' } });
  fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
  const preview = screen.getByRole('region', { name: 'Проверка предложения' });
  expect(within(preview).getByText('2000')).toBeInTheDocument();
  expect(apiMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false);
  fireEvent.click(within(preview).getByRole('button', { name: 'Отправить предложение' }));
  await waitFor(() =>
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/coach-nutrition-proposals/clients/123',
      expect.objectContaining({
        method: 'POST',
        body: expect.objectContaining({
          expected_target_id: null,
          expected_plan_revision: 0,
          calories: 2000,
        }),
      }),
    ),
  );
});

it.each([
  ['accept', 'Принять изменения'],
  ['reject', 'Отклонить'],
] as const)('клиент явно выбирает %s', async (decision, label) => {
  let status = 'pending';
  const proposal = {
    id: 7,
    version: 1,
    status,
    target_date: '2030-05-01',
    before: { target: null, item: null },
    request: { target_date: '2030-05-01', calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 180 },
  };
  apiMock.mockImplementation((_path: string, options?: { method?: string }) => {
    if (options?.method === 'POST') status = decision === 'accept' ? 'accepted' : 'rejected';
    return Promise.resolve(
      options?.method === 'POST' ? { ...proposal, status } : [{ ...proposal, status }],
    );
  });
  setup(<ClientNutritionProposals />);
  fireEvent.click(await screen.findByRole('button', { name: label }));
  await waitFor(() =>
    expect(apiMock).toHaveBeenCalledWith(
      '/api/v1/coach-nutrition-proposals/7/decision',
      expect.objectContaining({ method: 'POST', body: { decision, version: 1 } }),
    ),
  );
  expect(
    await screen.findByText(decision === 'accept' ? 'Принято' : 'Отклонено'),
  ).toBeInTheDocument();
});

it('показывает ошибку загрузки вместо пустого состояния', async () => {
  apiMock.mockRejectedValue(new Error('нет доступа'));
  setup(<ClientNutritionProposals />);
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Не удалось загрузить предложения тренера',
  );
});

it('позволяет вернуться к дневнику, если открытое предложение исчезло', async () => {
  apiMock.mockResolvedValue([]);
  const onClose = vi.fn();
  setup(<ClientNutritionProposals focused onClose={onClose} />);
  expect(await screen.findByText('Предложений пока нет.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'К питанию' }));
  expect(onClose).toHaveBeenCalledOnce();
});

it('объясняет устаревшее предложение и предлагает обновить данные', async () => {
  const proposal = {
    id: 7,
    version: 1,
    status: 'pending',
    target_date: '2030-05-01',
    before: { target: null, item: null },
    request: { target_date: '2030-05-01', calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 180 },
  };
  apiMock.mockImplementation((_path: string, options?: { method?: string }) =>
    options?.method === 'POST'
      ? Promise.reject(Object.assign(new Error('Цель изменилась'), { status: 409 }))
      : Promise.resolve([proposal]),
  );
  setup(<ClientNutritionProposals />);
  fireEvent.click(await screen.findByRole('button', { name: 'Принять изменения' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Данные изменились');
  expect(screen.getByRole('button', { name: 'Обновить данные' })).toBeInTheDocument();
});
