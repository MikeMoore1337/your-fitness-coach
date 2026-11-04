import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionRotationToday } from '../../../../src/features/dashboard/SessionRotationToday';
import { SessionRotationSettings } from '../../../../src/features/programs/SessionRotationSettings';
import { ApiError } from '../../../../src/shared/api/client';
import type { ApiSchemas } from '../../../../src/shared/api/types';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

const apiMock = vi.hoisted(() => vi.fn());
const connection = vi.hoisted(() => ({ online: true }));

vi.mock('../../../../src/shared/api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../../src/shared/api/client')>(
    '../../../../src/shared/api/client',
  );
  return { ...actual, api: apiMock };
});
vi.mock('../../../../src/shared/ui/OnlineStatus', () => ({
  useOnlineStatus: () => connection.online,
}));
vi.mock('../../../../src/shared/navigation/router', () => ({
  AppLink: ({ to, children, ...props }: React.ComponentProps<'a'> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

const state: ApiSchemas['SessionRotationStateResponse'] = {
  mode: 'rotation',
  status: 'ready',
  program_id: 7,
  revision_number: 2,
  cursor: 'a'.repeat(64),
  duration_weeks: 8,
  can_extend: true,
  current: { day_number: 1, title: 'Грудь и трицепс', from_template: false },
  next: { day_number: 2, title: 'Спина и бицепс', from_template: false },
  days: [
    { day_number: 1, title: 'Грудь и трицепс', from_template: false },
    { day_number: 2, title: 'Спина и бицепс', from_template: false },
  ],
};

function renderWithProviders(child: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FeedbackProvider>{child}</FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('Session Rotation', () => {
  beforeEach(() => {
    apiMock.mockReset();
    connection.online = true;
  });
  afterEach(cleanup);

  it('requires a plan week and confirms a skip using the server cursor', async () => {
    apiMock.mockResolvedValue({ ...state, current: state.next, cursor: 'b'.repeat(64) });
    renderWithProviders(
      <SessionRotationToday
        state={state}
        refreshing={false}
        pendingLocalChanges={false}
        onResume={vi.fn()}
        onStarted={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Грудь и трицепс' })).toBeInTheDocument();
    expect(screen.getByText('Спина и бицепс')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Пропустить тренировку' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Неделя программы'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Пропустить тренировку' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Спина и бицепс');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Пропустить' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/workouts/session-rotation/skip',
        expect.objectContaining({
          method: 'POST',
          body: expect.objectContaining({
            expected_cursor: state.cursor,
            expected_day_number: 1,
            plan_week_number: 1,
          }),
        }),
      ),
    );
  });

  it('keeps an active workout accessible offline but blocks cancellation', () => {
    connection.online = false;
    const onResume = vi.fn();
    renderWithProviders(
      <SessionRotationToday
        state={{ ...state, status: 'in_progress', current: { ...state.current!, workout_id: 15 } }}
        refreshing={false}
        pendingLocalChanges={true}
        onResume={onResume}
        onStarted={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить тренировку' }));
    expect(onResume).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: 'Отменить тренировку' })).toBeDisabled();
    expect(screen.getByText(/Нет соединения/)).toBeInTheDocument();
  });

  it('does not ask for a week when the server identifies an unambiguous plan', () => {
    renderWithProviders(
      <SessionRotationToday
        state={{ ...state, default_plan_week: 1 }}
        refreshing={false}
        pendingLocalChanges={false}
        onResume={vi.fn()}
        onStarted={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText('Неделя программы')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Начать тренировку' })).toBeEnabled();
  });

  it('shows a version conflict and asks the user to check the refreshed queue', async () => {
    apiMock.mockRejectedValue(new ApiError('Конфликт', 409));
    renderWithProviders(
      <SessionRotationToday
        state={{ ...state, default_plan_week: 1 }}
        refreshing={false}
        pendingLocalChanges={false}
        onResume={vi.fn()}
        onStarted={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Начать тренировку' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Очередь или программа изменились. Данные обновлены; проверьте выбор ещё раз.',
    );
  });

  it('keeps the next day visible while asking for a sufficient extension', () => {
    renderWithProviders(
      <SessionRotationToday
        state={{ ...state, status: 'expired', min_extension_weeks: 12 }}
        refreshing={false}
        pendingLocalChanges={false}
        onResume={vi.fn()}
        onStarted={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Грудь и трицепс' })).toBeInTheDocument();
    expect(screen.getByText(/укажите не меньше 12 недель/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Общая длительность, недель'), {
      target: { value: '11' },
    });
    expect(screen.getByRole('button', { name: 'Продлить программу' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Общая длительность, недель'), {
      target: { value: '12' },
    });
    expect(screen.getByRole('button', { name: 'Продлить программу' })).toBeEnabled();
  });

  it('asks an athlete to agree an extension with the coach when required', () => {
    renderWithProviders(
      <SessionRotationToday
        state={{ ...state, status: 'expired', can_extend: false }}
        refreshing={false}
        pendingLocalChanges={false}
        onResume={vi.fn()}
        onStarted={vi.fn()}
      />,
    );
    expect(screen.getByText('Продление программы согласуйте с тренером.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Продлить программу' })).not.toBeInTheDocument();
  });

  it('previews settings before applying the explicitly selected first day', async () => {
    const settings = {
      program_id: 7,
      mode: 'calendar',
      revision_number: 1,
      days: state.days,
      future_reminders: 0,
    };
    apiMock.mockImplementation(async (path: string) => {
      if (path.endsWith('/preview'))
        return {
          ...settings,
          mode: 'rotation',
          first_day_number: 2,
          preview_token: 'b'.repeat(64),
        };
      if (path.endsWith('/apply')) return { ...settings, mode: 'rotation', revision_number: 2 };
      return settings;
    });
    renderWithProviders(<SessionRotationSettings programId={7} />);
    fireEvent.click(await screen.findByRole('tab', { name: 'По очереди' }));
    expect(screen.getByRole('button', { name: 'Проверить изменения' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('С какой тренировки начать?'), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }));
    expect(await screen.findByText(/Первой будет: Спина и бицепс/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить изменения' }));
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith(
        '/api/v1/programs/assigned/7/session-rotation/apply',
        expect.objectContaining({
          body: expect.objectContaining({ first_day_number: 2, preview_token: 'b'.repeat(64) }),
        }),
      ),
    );
  });
});
