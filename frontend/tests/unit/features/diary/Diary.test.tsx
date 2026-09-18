import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Diary } from '../../../../src/features/diary/Diary';
import { dateInputValue } from '../../../../src/shared/dateTime';
import { queryKeys } from '../../../../src/shared/queryKeys';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/app/AuthProvider', () => ({
  useAuth: () => ({ user: { id: 10, profile: { timezone: 'Europe/Moscow' } } }),
}));

function QueryProbe({ clientId, queryFn }: { clientId?: number; queryFn: () => Promise<unknown> }) {
  useQuery({
    queryKey:
      clientId == null
        ? queryKeys.progress.summary(30)
        : queryKeys.trainer.clientAnalytics(clientId),
    queryFn,
  });
  return null;
}

function renderDiary(options?: {
  clientId?: number;
  timeZone?: string;
  dependentQuery?: () => Promise<unknown>;
  embedded?: boolean;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        {options?.dependentQuery && (
          <QueryProbe clientId={options.clientId} queryFn={options.dependentQuery} />
        )}
        <Diary
          clientId={options?.clientId}
          embedded={options?.embedded}
          timeZone={options?.timeZone}
        />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('Diary measurement guidance', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    apiMock.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('uses honest circumference labels and consistency guidance', async () => {
    renderDiary({ embedded: true });

    expect(screen.getByLabelText('Плечо (окружность), см')).toBeInTheDocument();
    expect(screen.getByLabelText('Бедро (окружность), см')).toBeInTheDocument();
    expect(screen.getByLabelText('Вес, кг')).toHaveAttribute('inputmode', 'decimal');
    expect(screen.getByLabelText('Как делать замеры')).toHaveTextContent(
      'Окружность плеча не показывает отдельно размер бицепса',
    );
    expect(await screen.findByText('Замеров пока нет')).toBeInTheDocument();
  });

  it('keeps units in history and supports an explicit same-date edit', async () => {
    const row = {
      id: 5,
      measured_on: '2026-08-20',
      weight_kg: 74.2,
      chest_cm: null,
      waist_cm: 81.4,
      hips_cm: null,
      biceps_cm: null,
      thigh_cm: null,
      note: 'После тренировки',
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path === '/api/v1/workouts/diary' && options?.method === 'POST') {
        return Promise.resolve({ ...row, ...(options.body as object) });
      }
      return Promise.resolve([row]);
    });
    renderDiary({ embedded: true });

    expect(await screen.findByText(/Вес: 74\.2 кг · Талия: 81\.4 см/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    expect(screen.getByRole('heading', { name: 'Изменить замер' })).toBeVisible();
    expect(screen.getByLabelText('Вес, кг')).toHaveValue(74.2);
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '74.6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/workouts/diary',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({ measured_on: '2026-08-20', weight_kg: 74.6 }),
        }),
      ),
    );
  });

  it('renders owner-scoped custom centimetre fields and keeps their values in the save payload', async () => {
    const definition = {
      id: 17,
      label: 'Живот',
      unit: 'cm' as const,
      archived: false,
      created_at: '2026-08-01T10:00:00Z',
      updated_at: '2026-08-01T10:00:00Z',
    };
    const row = {
      id: 8,
      measured_on: '2026-08-20',
      weight_kg: null,
      chest_cm: null,
      waist_cm: null,
      hips_cm: null,
      biceps_cm: null,
      thigh_cm: null,
      note: null,
      custom_values: [
        { definition_id: 17, label: 'Живот', unit: 'cm' as const, value: 86, archived: false },
      ],
    };
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path === '/api/v1/workouts/diary/custom-definitions?include_archived=true') {
        return Promise.resolve([definition]);
      }
      if (path === '/api/v1/workouts/diary' && options?.method === 'POST') {
        return Promise.resolve({ ...row, ...(options.body as object) });
      }
      return Promise.resolve([row]);
    });

    renderDiary({ embedded: true });

    expect(await screen.findByLabelText('Живот, см')).toHaveValue(null);
    expect(screen.getByText('Живот: 86 см')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    expect(await screen.findByLabelText('Живот, см')).toHaveValue(86);
    fireEvent.change(screen.getByLabelText('Живот, см'), { target: { value: '85.5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить изменения' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/workouts/diary',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            custom_values: [{ definition_id: 17, value: 85.5 }],
          }),
        }),
      ),
    );
  });

  it('preserves a recoverable draft and shows the save error beside the form', async () => {
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === '/api/v1/workouts/diary' && options?.method === 'POST') {
        return Promise.reject(new Error('Сеть временно недоступна'));
      }
      return Promise.resolve([]);
    });
    renderDiary({ embedded: true });

    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '73.8' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить замер' }));

    expect(await screen.findByText(/Введённые значения сохранены/)).toHaveTextContent(
      'Сеть временно недоступна',
    );
    expect(screen.getByLabelText('Вес, кг')).toHaveValue(73.8);
  });

  it('refetches personal progress after a measurement mutation', async () => {
    const dependentQuery = vi.fn().mockResolvedValue({});
    renderDiary({ dependentQuery });
    await waitFor(() => expect(dependentQuery).toHaveBeenCalledOnce());

    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '74' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить замер' }));

    await waitFor(() => expect(dependentQuery).toHaveBeenCalledTimes(2));
  });

  it('uses the client timezone and refetches trainer analytics', async () => {
    const dependentQuery = vi.fn().mockResolvedValue({});
    const timeZone = 'Pacific/Kiritimati';
    renderDiary({ clientId: 42, timeZone, dependentQuery });
    const dateInput = screen.getByLabelText('Дата');
    const clientToday = dateInputValue(new Date(), timeZone);
    expect(dateInput).toHaveValue(clientToday);
    expect(dateInput).toHaveAttribute('max', clientToday);
    await waitFor(() => expect(dependentQuery).toHaveBeenCalledOnce());

    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '75' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить замер' }));

    await waitFor(() => expect(dependentQuery).toHaveBeenCalledTimes(2));
  });
});
