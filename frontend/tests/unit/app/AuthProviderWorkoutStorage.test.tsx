import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../../../src/app/AuthProvider';
import { clearAccessToken, setAccessToken } from '../../../src/shared/api/client';
import type { Workout } from '../../../src/shared/api/types';
import {
  activeWorkoutQueueKey,
  enqueueWorkoutMutation,
  loadActiveWorkoutQueue,
  loadCurrentActiveWorkoutSnapshot,
  saveActiveWorkoutQueue,
  saveActiveWorkoutSnapshot,
} from '../../../src/features/workouts/activeWorkoutQueue';

const activeWorkout: Workout = {
  id: 42,
  scheduled_date: '2030-01-10',
  title: 'Тренировка A',
  status: 'in_progress',
  day_number: 1,
  week_number: 1,
  started_at: '2030-01-10T10:00:00',
  exercises: [
    {
      id: 101,
      exercise_id: 11,
      exercise_title: 'Жим штанги лежа',
      metric_type: 'strength',
      sort_order: 1,
      prescribed_sets: 1,
      prescribed_reps: '8-10',
      rest_seconds: 90,
      has_guide: false,
      sets: [{ id: 201, set_number: 1, is_completed: false, version: 1 }],
    },
  ],
};

function Harness() {
  const { user, logout, devLogin, reloadUser } = useAuth();
  return (
    <div>
      <span data-testid="user-id">{user?.id ?? 'none'}</span>
      <button onClick={() => void logout()}>Выйти</button>
      <button onClick={() => void reloadUser()}>Обновить профиль</button>
      <button
        onClick={() =>
          void devLogin({
            telegram_user_id: 800,
            is_coach: false,
            is_admin: false,
          })
        }
      >
        Сменить аккаунт
      </button>
    </div>
  );
}

function renderProvider(
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  }),
) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Harness />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe('AuthProvider active workout cleanup', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    setAccessToken('initial-token');
  });

  afterEach(() => {
    cleanup();
    clearAccessToken();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('очищает локальную тренировку при logout', async () => {
    const queueKey = activeWorkoutQueueKey(7, 42);
    localStorage.setItem(queueKey, '{"private":"draft"}');
    localStorage.setItem('fit_food_draft_7_2030-01-10_breakfast', '{"private":"food"}');
    localStorage.setItem('fit_measurement_draft_user_7', '{"private":"measurement"}');
    localStorage.setItem('fit_profile_draft_7', '{"private":"profile"}');
    localStorage.setItem('fit_workout_set_201', '{"private":"legacy"}');
    localStorage.setItem('app-theme', 'dark');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/me')) return new Response('{"id":7}', { status: 200 });
      if (path.endsWith('/auth/logout')) return new Response(null, { status: 204 });
      return new Response('{"detail":"unexpected"}', { status: 500 });
    });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));

    await userEvent.click(screen.getByRole('button', { name: 'Выйти' }));

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('none'));
    expect(localStorage.getItem(queueKey)).toBeNull();
    expect(localStorage.getItem('fit_food_draft_7_2030-01-10_breakfast')).toBeNull();
    expect(localStorage.getItem('fit_measurement_draft_user_7')).toBeNull();
    expect(localStorage.getItem('fit_profile_draft_7')).toBeNull();
    expect(localStorage.getItem('fit_workout_set_201')).toBeNull();
    expect(localStorage.getItem('app-theme')).toBe('dark');
  });

  it('очищает данные прежнего аккаунта перед account switch', async () => {
    const queueKey = activeWorkoutQueueKey(7, 42);
    localStorage.setItem(queueKey, '{"private":"draft"}');
    localStorage.setItem('fit_nutrition_draft_v2_user_7', '{"private":"nutrition"}');
    localStorage.setItem('fit_program_days_user_7', '{"private":"program"}');
    localStorage.setItem('fit_notification_draft_7', '{"private":"notification"}');
    localStorage.setItem('app-theme', 'light');
    let meCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/dev-login')) {
        return new Response('{"access_token":"switched-token"}', { status: 200 });
      }
      if (path.endsWith('/me')) {
        meCalls += 1;
        return new Response(JSON.stringify({ id: meCalls === 1 ? 7 : 8 }), { status: 200 });
      }
      return new Response('{"detail":"unexpected"}', { status: 500 });
    });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));

    await userEvent.click(screen.getByRole('button', { name: 'Сменить аккаунт' }));

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('8'));
    expect(localStorage.getItem(queueKey)).toBeNull();
    expect(localStorage.getItem('fit_nutrition_draft_v2_user_7')).toBeNull();
    expect(localStorage.getItem('fit_program_days_user_7')).toBeNull();
    expect(localStorage.getItem('fit_notification_draft_7')).toBeNull();
    expect(localStorage.getItem('app-theme')).toBe('light');
  });

  it('очищает кэш тренировки при смене пользователя во время обновления сессии', async () => {
    let meCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/me')) {
        meCalls += 1;
        return new Response(JSON.stringify({ id: meCalls === 1 ? 7 : 8 }), { status: 200 });
      }
      return new Response('{}', { status: 200 });
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderProvider(queryClient);
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    queryClient.setQueryData(['workout', 'today'], activeWorkout);

    await userEvent.click(screen.getByRole('button', { name: 'Обновить профиль' }));

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('8'));
    expect(queryClient.getQueryData(['workout', 'today'])).toBeUndefined();
  });

  it('восстанавливает offline-shell после refresh только для подтверждённой auth-сессии', async () => {
    saveActiveWorkoutSnapshot(7, activeWorkout);
    const firstFetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/me')) return new Response('{"id":7}', { status: 200 });
      return new Response('{"detail":"unexpected"}', { status: 500 });
    });
    const first = renderProvider();
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    first.unmount();
    firstFetch.mockRestore();

    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);
  });

  it('сохраняет offline-очередь при повторном подтверждении того же Telegram-аккаунта', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    saveActiveWorkoutSnapshot(7, activeWorkout);
    const queued = enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    saveActiveWorkoutQueue(queued);
    let validatedToken: string | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/telegram/init'))
        return new Response('{"access_token":"new-token"}', { status: 200 });
      if (path.endsWith('/me')) {
        validatedToken = (init?.headers as Record<string, string>).Authorization;
        return new Response('{"id":7}', { status: 200 });
      }
      return new Response('{}', { status: 200 });
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(validatedToken).toBe('Bearer new-token');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(queued.queue);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);
  });

  it('сохраняет очередь только проверенного аккаунта, если вкладка потеряла его ID', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    saveActiveWorkoutSnapshot(7, activeWorkout);
    const queued = enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    saveActiveWorkoutQueue(queued);
    saveActiveWorkoutSnapshot(8, { ...activeWorkout, id: 43 });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/telegram/init'))
        return new Response('{"access_token":"new-token"}', { status: 200 });
      if (path.endsWith('/me')) return new Response('{"id":7}', { status: 200 });
      return new Response('{}', { status: 200 });
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(queued.queue);
    expect(loadCurrentActiveWorkoutSnapshot(8)).toBeUndefined();
  });

  it('не сохраняет очередь без подтверждения предыдущего токена', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    saveActiveWorkoutSnapshot(7, activeWorkout);
    saveActiveWorkoutQueue(
      enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
        setId: 201,
        serverVersion: 1,
        values: { actual_reps: 8, actual_weight: 40, is_completed: true },
      }),
    );
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/telegram/init'))
        return new Response('{"access_token":"new-token"}', { status: 200 });
      if (path.endsWith('/me')) {
        const authorization = (init?.headers as Record<string, string>).Authorization;
        return new Response(authorization === 'Bearer initial-token' ? '{}' : '{"id":7}', {
          status: authorization === 'Bearer initial-token' ? 401 : 200,
        });
      }
      return new Response('{}', { status: 200 });
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
  });

  it('сохраняет подтверждённую offline-сессию при сетевой ошибке Telegram-входа', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    saveActiveWorkoutSnapshot(7, activeWorkout);
    const queued = enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
      setId: 201,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    saveActiveWorkoutQueue(queued);
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/public/config')) return new Response('{}', { status: 200 });
      throw new TypeError('Failed to fetch');
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(queued.queue);
  });

  it('очищает локальную тренировку, если Telegram подтвердил другой аккаунт', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    saveActiveWorkoutSnapshot(7, activeWorkout);
    saveActiveWorkoutQueue(
      enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
        setId: 201,
        serverVersion: 1,
        values: { actual_reps: 8, actual_weight: 40, is_completed: true },
      }),
    );
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/telegram/init'))
        return new Response('{"access_token":"new-token"}', { status: 200 });
      if (path.endsWith('/me')) return new Response('{"id":8}', { status: 200 });
      return new Response('{}', { status: 200 });
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('8'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual([]);
    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
  });

  it('очищает локальную тренировку при отклонённой Telegram-сессии', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    saveActiveWorkoutSnapshot(7, activeWorkout);
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).endsWith('/public/config')) return new Response('{}', { status: 200 });
      return new Response('{}', { status: 401 });
    });

    renderProvider();

    await waitFor(() => expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined());
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
  });

  it('не открывает private snapshot без access token', async () => {
    clearAccessToken();
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    saveActiveWorkoutSnapshot(7, activeWorkout);
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('none'));
  });
});
