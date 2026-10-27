import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Diary } from '../../../../src/features/diary/Diary';
import { dateInputValue } from '../../../../src/shared/dateTime';
import { queryKeys } from '../../../../src/shared/queryKeys';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';
import { createTelegramMock } from '../../../helpers/telegramMock';

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
  onExit?: () => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        {options?.dependentQuery && (
          <QueryProbe clientId={options.clientId} queryFn={options.dependentQuery} />
        )}
        <Diary
          clientId={options?.clientId}
          embedded={options?.embedded}
          timeZone={options?.timeZone}
          onExit={options?.onExit}
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

  afterEach(() => {
    cleanup();
    delete window.Telegram;
    vi.restoreAllMocks();
  });

  it('leaves an empty quick form without confirmation or writes', async () => {
    const onExit = vi.fn();
    renderDiary({ embedded: true, onExit });
    await screen.findByText('Замеров пока нет');

    fireEvent.click(screen.getByRole('button', { name: 'Вернуться' }));

    expect(onExit).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(apiMock.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it('blocks repeated measurement saves and exit while the request is pending', async () => {
    const telegram = createTelegramMock();
    window.Telegram = { WebApp: telegram.webApp };
    let resolveSave!: () => void;
    const pendingSave = new Promise<void>((resolve) => {
      resolveSave = resolve;
    });
    apiMock.mockImplementation((_path: string, options?: { method?: string }) =>
      options?.method === 'POST' ? pendingSave : Promise.resolve([]),
    );
    const onExit = vi.fn();
    renderDiary({ embedded: true, onExit });
    await screen.findByText('Замеров пока нет');
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '72' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить замер' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Вернуться' })).toBeDisabled());
    fireEvent.submit(document.querySelector('.measurement-diary__form')!);
    act(() => telegram.clickBack());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(apiMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
    expect(onExit).not.toHaveBeenCalled();
    resolveSave();
    await waitFor(() => expect(screen.getByLabelText('Вес, кг')).toHaveValue(''));
  });

  it('keeps a dirty editing draft on cancelled exit and restores its edit context on re-entry', async () => {
    const row = { id: 5, measured_on: '2026-08-20', weight_kg: 74.2, note: null };
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(path.includes('custom-definitions') ? [] : [row]),
    );
    const onExit = vi.fn();
    const view = renderDiary({ embedded: true, onExit });
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '74.6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Вернуться' }));
    const dialog = await screen.findByRole('dialog', { name: 'Вернуться без сохранения?' });
    expect(dialog).toHaveTextContent('останутся в черновике на этом устройстве');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('74.6');
    expect(onExit).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Вернуться' }));
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Вернуться' }),
    );
    await waitFor(() => expect(onExit).toHaveBeenCalledOnce());
    view.unmount();
    renderDiary({ embedded: true, onExit });
    expect(await screen.findByRole('heading', { name: 'Изменить замер' })).toBeVisible();
    expect(screen.getByLabelText('Дата')).toHaveValue(row.measured_on);
    expect(screen.getByLabelText('Дата')).toBeDisabled();
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('74.6');
    expect(apiMock.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it('does not confirm an unchanged edit after null fields, note whitespace and custom-field reordering', async () => {
    const row = {
      id: 5,
      measured_on: '2026-08-20',
      weight_kg: 74.2,
      note: null,
      custom_values: [
        { definition_id: 17, label: 'Живот', value: 86 },
        { definition_id: 18, label: 'Шея', value: 38 },
      ],
    };
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(
        path.includes('custom-definitions')
          ? row.custom_values.map((item) => ({
              id: item.definition_id,
              label: item.label,
              archived: false,
            }))
          : [row],
      ),
    );
    const onExit = vi.fn();
    renderDiary({ embedded: true, onExit });
    fireEvent.click(await screen.findByRole('button', { name: 'Изменить' }));
    fireEvent.change(screen.getByLabelText('Грудь, см'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('Грудь, см'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Заметка'), { target: { value: ' ' } });
    fireEvent.change(screen.getByLabelText('Живот, см'), { target: { value: '85' } });
    fireEvent.change(screen.getByLabelText('Живот, см'), { target: { value: '86' } });
    fireEvent.click(screen.getByRole('button', { name: 'Вернуться' }));

    expect(onExit).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('protects a draft when opening history and discards it only after confirmation', async () => {
    const row = { id: 5, measured_on: '2026-08-20', weight_kg: 74.2 };
    apiMock.mockImplementation((path: string) =>
      Promise.resolve(path.includes('custom-definitions') ? [] : [row]),
    );
    renderDiary({ embedded: true });
    await screen.findByRole('button', { name: 'Изменить' });
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '72' } });
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    fireEvent.click(
      within(await screen.findByRole('dialog', { name: 'Открыть другой замер?' })).getByRole(
        'button',
        { name: 'Отмена' },
      ),
    );
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('72');
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Открыть замер' }),
    );
    await waitFor(() => expect(screen.getByLabelText('Вес, кг')).toHaveValue('74.2'));
  });

  it('preserves the draft and date when deleting a historical record with confirmation', async () => {
    let rows = [{ id: 5, measured_on: '2026-08-20', weight_kg: 74.2 }];
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'DELETE') {
        rows = [];
        return Promise.resolve();
      }
      return Promise.resolve(path.includes('custom-definitions') ? [] : rows);
    });
    renderDiary({ embedded: true });
    await screen.findByRole('button', { name: 'Удалить' });
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '72' } });
    fireEvent.change(screen.getByLabelText('Дата'), { target: { value: '2026-08-19' } });
    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Отмена' }),
    );
    expect(rows).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Удалить' }),
    );
    await screen.findByText('Замеров пока нет');
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('72');
    expect(screen.getByLabelText('Дата')).toHaveValue('2026-08-19');
    expect(apiMock.mock.calls.filter(([, options]) => options?.method === 'DELETE')).toHaveLength(
      1,
    );
  });

  it('warns about actual data loss when local draft storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Unavailable');
    });
    const onExit = vi.fn();
    renderDiary({ embedded: true, onExit });
    await screen.findByText('Замеров пока нет');
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '72' } });
    fireEvent.click(screen.getByRole('button', { name: 'Вернуться' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Не удалось сохранить черновик');
    expect(dialog).toHaveTextContent('будут потеряны');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    expect(onExit).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('72');
  });

  it('clears only the deleted editing draft after explaining the loss of its unsaved changes', async () => {
    let rows = [
      { id: 5, measured_on: '2026-08-20', weight_kg: 74.2 },
      { id: 6, measured_on: '2026-08-19', weight_kg: 74.3 },
    ];
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === 'DELETE') {
        rows = rows.filter((item) => item.id !== 5);
        return Promise.resolve();
      }
      return Promise.resolve(path.includes('custom-definitions') ? [] : rows);
    });
    renderDiary({ embedded: true });
    fireEvent.click((await screen.findAllByRole('button', { name: 'Изменить' }))[0]!);
    fireEvent.change(screen.getByLabelText('Вес, кг'), { target: { value: '73' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Удалить' })[0]!);
    const dialog = await screen.findByRole('dialog', { name: 'Удалить замер?' });
    expect(dialog).toHaveTextContent('Несохранённые изменения этого замера также будут удалены.');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('73');
    expect(rows).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'Удалить' })[0]!);
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Удалить' }),
    );
    await waitFor(() => expect(screen.getByLabelText('Вес, кг')).toHaveValue(''));
    expect(screen.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
    expect(rows).toEqual([{ id: 6, measured_on: '2026-08-19', weight_kg: 74.3 }]);
  });

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

    expect(await screen.findByText(/Вес: 74,2 кг · Талия: 81,4 см/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    expect(screen.getByRole('heading', { name: 'Изменить замер' })).toBeVisible();
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('74.2');
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

    expect(await screen.findByLabelText('Живот, см')).toHaveValue('');
    expect(screen.getByText('Живот: 86 см')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить' }));
    expect(await screen.findByLabelText('Живот, см')).toHaveValue('86');
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
    expect(screen.getByLabelText('Вес, кг')).toHaveValue('73.8');
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
