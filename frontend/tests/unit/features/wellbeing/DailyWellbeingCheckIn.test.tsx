import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createTelegramMock } from '../../../helpers/telegramMock';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DailyWellbeingCheckIn,
  hoursFromMinutes,
  minutesFromSleepHours,
} from '../../../../src/features/wellbeing/DailyWellbeingCheckIn';
import type {
  DailyWellbeingCheckIn as DailyWellbeingRecord,
  DailyWellbeingSave,
} from '../../../../src/shared/api/types';

const apiMock = vi.hoisted(() => vi.fn());
const feedbackMock = vi.hoisted(() => ({
  confirm: vi.fn(async () => true),
  toast: vi.fn(),
}));

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));
vi.mock('../../../../src/shared/ui/FeedbackProvider', () => ({
  useFeedback: () => feedbackMock,
}));
vi.mock('../../../../src/shared/ui/OnlineStatus', () => ({
  useOnlineStatus: () => true,
}));

const baseRecord: DailyWellbeingRecord = {
  id: 12,
  user_id: 7,
  local_date: '2026-09-01',
  timezone_at_entry: 'Europe/Moscow',
  sleep_quality: 4,
  sleep_duration_minutes: 420,
  mood: 3,
  note: 'Личная заметка',
  source: 'manual',
  created_at: '2026-09-01T08:00:00',
  updated_at: '2026-09-01T08:00:00',
};

function renderCheckIn(autoFocus = false, onExit?: () => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DailyWellbeingCheckIn
        autoFocus={autoFocus}
        initialDate="2026-09-01"
        onExit={onExit}
        timeZone="Europe/Moscow"
        userId={7}
      />
    </QueryClientProvider>,
  );
}

describe('DailyWellbeingCheckIn', () => {
  let currentRecord: DailyWellbeingRecord | null;

  beforeEach(() => {
    currentRecord = null;
    apiMock.mockReset();
    feedbackMock.confirm.mockReset().mockResolvedValue(true);
    feedbackMock.toast.mockClear();
    apiMock.mockImplementation(
      (path: string, options?: { body?: DailyWellbeingSave; method?: string }) => {
        if (path.startsWith('/api/v1/check-ins/daily?')) {
          return Promise.resolve({
            local_date: '2026-09-01',
            today: '2026-09-02',
            timezone: 'Europe/Moscow',
            record: currentRecord,
          });
        }
        if (options?.method === 'PUT') {
          const payload = options.body ?? {};
          currentRecord = {
            ...baseRecord,
            ...payload,
            id: currentRecord?.id ?? baseRecord.id,
            note: payload.note ?? null,
            updated_at: '2026-09-02T08:00:00',
          };
          return Promise.resolve(currentRecord);
        }
        if (options?.method === 'DELETE') {
          currentRecord = null;
          return Promise.resolve(undefined);
        }
        return Promise.reject(new Error(`Unexpected request: ${path}`));
      },
    );
  });

  afterEach(() => {
    cleanup();
    delete window.Telegram;
  });

  it('exits an empty quick form without confirmation or saving', async () => {
    const user = userEvent.setup();
    const onExit = vi.fn();
    renderCheckIn(true, onExit);
    await user.click(await screen.findByRole('button', { name: 'Вернуться' }));
    expect(onExit).toHaveBeenCalledOnce();
    expect(feedbackMock.confirm).not.toHaveBeenCalled();
    expect(apiMock.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it('keeps dirty values after cancelled exit and leaves only after confirmation', async () => {
    const user = userEvent.setup();
    const onExit = vi.fn();
    feedbackMock.confirm.mockResolvedValueOnce(false);
    renderCheckIn(true, onExit);
    await screen.findByRole('button', { name: 'Вернуться' });
    await user.click(screen.getAllByRole('radio', { name: 'Хорошо' })[0]!);
    await user.type(screen.getByLabelText('Сколько спали, часов'), '7');
    await user.click(screen.getByRole('button', { name: 'Вернуться' }));
    expect(onExit).not.toHaveBeenCalled();
    expect(screen.getAllByRole('radio', { name: 'Хорошо' })[0]).toBeChecked();
    expect(screen.getByLabelText('Сколько спали, часов')).toHaveValue('7');
    expect(feedbackMock.confirm).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('будут потеряны') }),
    );
    await user.click(screen.getByRole('button', { name: 'Вернуться' }));
    expect(onExit).toHaveBeenCalledOnce();
    expect(apiMock.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it.each(['07', '7.0'])(
    'compares equivalent duration %s and trimmed notes without a false discard warning',
    async (duration) => {
      const user = userEvent.setup();
      const onExit = vi.fn();
      currentRecord = baseRecord;
      renderCheckIn(true, onExit);
      await screen.findByRole('button', { name: 'Вернуться' });
      fireEvent.change(screen.getByLabelText('Сколько спали, часов'), {
        target: { value: duration },
      });
      await user.click(screen.getByText('Добавить заметку'));
      fireEvent.change(screen.getByLabelText('Заметка для себя'), {
        target: { value: ' Личная заметка ' },
      });
      await user.click(screen.getByRole('button', { name: 'Вернуться' }));
      expect(onExit).toHaveBeenCalledOnce();
      expect(feedbackMock.confirm).not.toHaveBeenCalled();
    },
  );

  it('guards a date change and keeps current values and history when it is cancelled', async () => {
    const user = userEvent.setup();
    feedbackMock.confirm.mockResolvedValueOnce(false);
    currentRecord = baseRecord;
    renderCheckIn(true);
    await screen.findByRole('button', { name: 'Сохранить отметку' });
    await user.click(screen.getAllByRole('radio', { name: 'Отлично' })[0]!);
    fireEvent.change(screen.getByLabelText('День'), { target: { value: '2026-08-31' } });
    await waitFor(() => expect(feedbackMock.confirm).toHaveBeenCalledOnce());
    expect(screen.getByLabelText('День')).toHaveValue('2026-09-01');
    expect(screen.getAllByRole('radio', { name: 'Отлично' })[0]).toBeChecked();
    expect(currentRecord).toEqual(baseRecord);
    fireEvent.change(screen.getByLabelText('День'), { target: { value: '2026-08-31' } });
    await waitFor(() => expect(screen.getByLabelText('День')).toHaveValue('2026-08-31'));
    expect(await screen.findByLabelText('Сколько спали, часов')).toHaveValue('7');
    expect(screen.getAllByRole('radio', { name: 'Хорошо' })[0]).toBeChecked();
    expect(currentRecord).toEqual(baseRecord);
    expect(apiMock.mock.calls.every(([, options]) => !options?.method)).toBe(true);
  });

  it('blocks repeated submission and exit until the in-flight save completes', async () => {
    const telegram = createTelegramMock();
    window.Telegram = { WebApp: telegram.webApp };
    const user = userEvent.setup();
    const onExit = vi.fn();
    let resolveSave!: (record: DailyWellbeingRecord) => void;
    const pendingSave = new Promise<DailyWellbeingRecord>((resolve) => {
      resolveSave = resolve;
    });
    const implementation = apiMock.getMockImplementation()!;
    apiMock.mockImplementation((path: string, options?: { method?: string }) =>
      options?.method === 'PUT' ? pendingSave : implementation(path, options),
    );
    renderCheckIn(true, onExit);
    await screen.findByRole('button', { name: 'Вернуться' });
    await user.click(screen.getAllByRole('radio', { name: 'Хорошо' })[0]!);
    await user.click(screen.getByRole('button', { name: 'Сохранить отметку' }));
    expect(screen.getByRole('button', { name: 'Вернуться' })).toBeDisabled();
    expect(screen.getByLabelText('День')).toBeDisabled();
    fireEvent.submit(document.querySelector('form')!);
    act(() => telegram.clickBack());
    expect(feedbackMock.confirm).not.toHaveBeenCalled();
    expect(apiMock.mock.calls.filter(([, options]) => options?.method === 'PUT')).toHaveLength(1);
    expect(onExit).not.toHaveBeenCalled();
    currentRecord = baseRecord;
    resolveSave(baseRecord);
    expect(await screen.findByRole('button', { name: 'Изменить' })).toBeVisible();
  });

  it('round-trips every whole sleep duration minute through the Russian hour field', () => {
    for (let minutes = 1; minutes <= 1440; minutes += 1) {
      const hours = hoursFromMinutes(minutes);
      expect(minutesFromSleepHours(hours)).toBe(minutes);
    }
  });

  it('exposes a compact entry point on Today before the first check-in', async () => {
    const user = userEvent.setup();
    renderCheckIn();

    await user.click(await screen.findByRole('button', { name: 'Добавить отметку' }));

    expect(await screen.findByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
  });

  it('allows the open check-in form to collapse and reopen without losing the draft', async () => {
    const user = userEvent.setup();
    renderCheckIn(true);

    const heading = await screen.findByRole('heading', { name: 'Сон и настроение' });
    const details = heading.closest('details');
    const disclosure = heading.closest('summary');
    expect(details).toHaveAttribute('open');
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');

    await user.click(screen.getAllByRole('radio', { name: 'Хорошо' })[0]!);
    await user.click(disclosure!);

    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: 'Сохранить отметку' })).not.toBeVisible();

    await user.click(disclosure!);

    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('radio', { name: 'Хорошо' })[0]).toBeChecked();
  });

  it('keeps the check-in optional, supports partial data, and saves an observation', async () => {
    const user = userEvent.setup();
    renderCheckIn(true);

    expect(await screen.findByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
    expect(screen.getByText(/заполнение остаётся необязательным/)).toBeVisible();
    expect(screen.getByText(/не является медицинской оценкой/)).toBeVisible();

    await user.click(screen.getAllByRole('radio', { name: 'Хорошо' })[0]!);
    await user.click(screen.getByRole('button', { name: 'Сохранить отметку' }));

    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/check-ins/daily/2026-09-01',
        expect.objectContaining({
          method: 'PUT',
          body: {
            sleep_quality: 4,
            sleep_duration_minutes: null,
            mood: null,
            note: null,
          },
        }),
      ),
    );
    expect(await screen.findByRole('button', { name: 'Изменить' })).toBeVisible();
    expect(screen.queryByText('Личная заметка')).not.toBeInTheDocument();
  });

  it('edits and deletes an existing record without exposing its note in the summary', async () => {
    const user = userEvent.setup();
    currentRecord = baseRecord;
    renderCheckIn();

    expect(await screen.findByText('Заметка сохранена отдельно')).toBeVisible();
    expect(screen.queryByText('Личная заметка')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Изменить' }));
    const duration = screen.getByRole('textbox', { name: 'Сколько спали, часов' });
    expect(duration).toHaveValue('7');
    await user.clear(duration);
    await user.type(duration, '7,5');
    await user.click(screen.getAllByRole('radio', { name: 'Отлично' })[1]!);
    await user.click(screen.getByRole('button', { name: 'Сохранить отметку' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/check-ins/daily/2026-09-01',
        expect.objectContaining({
          method: 'PUT',
          body: expect.objectContaining({ sleep_duration_minutes: 450 }),
        }),
      ),
    );
    await waitFor(() => expect(feedbackMock.toast).toHaveBeenCalledWith('Отметка сохранена'));

    expect(await screen.findByText(/7,5 ч/)).toBeVisible();
    await user.click(await screen.findByRole('button', { name: 'Изменить' }));
    expect(screen.getByRole('textbox', { name: 'Сколько спали, часов' })).toHaveValue('7,5');
    await user.click(screen.getByRole('button', { name: 'Удалить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith('/api/v1/check-ins/daily/2026-09-01', {
        method: 'DELETE',
      }),
    );
    expect(await screen.findByRole('button', { name: 'Сохранить отметку' })).toBeVisible();
    expect(feedbackMock.confirm).toHaveBeenCalledTimes(1);
  });

  it('validates sleep hours without sending an invalid minute payload', async () => {
    const user = userEvent.setup();
    renderCheckIn(true);

    await screen.findByRole('heading', { name: 'Сон и настроение' });
    await user.click(screen.getAllByRole('radio', { name: 'Хорошо' })[0]!);
    const duration = screen.getByRole('textbox', { name: 'Сколько спали, часов' });
    await user.type(duration, '25');

    expect(duration).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('от 1 минуты до 24 часов');
    expect(screen.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
    expect(apiMock).not.toHaveBeenCalledWith(
      '/api/v1/check-ins/daily/2026-09-01',
      expect.objectContaining({ method: 'PUT' }),
    );
  });
});
