import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../../../src/app/AuthProvider';
import {
  AUTH_TOKEN_RECEIVED_EVENT,
  clearAccessToken,
  setAccessToken,
} from '../../../src/shared/api/client';
import type { Workout } from '../../../src/shared/api/types';
import {
  activeWorkoutQueueKey,
  enqueueWorkoutMutation,
  loadActiveWorkoutQueue,
  loadCurrentActiveWorkoutSnapshot,
  saveActiveWorkoutQueue,
  saveActiveWorkoutSnapshot,
} from '../../../src/features/workouts/activeWorkoutQueue';
import { lastAuthenticatedUserId } from '../../../src/shared/userScopedStorage';

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
  const { user, config, loading, logout, devLogin, emailLogin, reloadUser } = useAuth();
  return (
    <div>
      <span data-testid="user-id">{user?.id ?? 'none'}</span>
      <span data-testid="auth-loading">{loading ? 'loading' : 'ready'}</span>
      <span data-testid="auth-config">{config?.enable_dev_auth ? 'enabled' : 'missing'}</span>
      <button onClick={() => void logout()}>Выйти</button>
      <button
        onClick={() =>
          void reloadUser().finally(() => window.dispatchEvent(new Event('test:reload-complete')))
        }
      >
        Обновить профиль
      </button>
      <button onClick={() => void emailLogin('same@example.test', 'test-password').catch(() => {})}>
        Войти снова
      </button>
      <button
        onClick={() => void emailLogin('other@example.test', 'test-password').catch(() => {})}
      >
        Войти в другой аккаунт
      </button>
      <button
        onClick={() => void emailLogin('invalid@example.test', 'test-password').catch(() => {})}
      >
        Проверить отклонённый вход
      </button>
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

  function pendingWorkout(userId = 7, workout = activeWorkout) {
    saveActiveWorkoutSnapshot(userId, workout);
    const queued = enqueueWorkoutMutation(loadActiveWorkoutQueue(userId, workout.id), {
      setId: workout.exercises[0]!.sets[0]!.id,
      serverVersion: 1,
      values: { actual_reps: 8, actual_weight: 40, is_completed: true },
    });
    expect(saveActiveWorkoutQueue(queued)).toBe(true);
    return queued.queue;
  }

  function mockExpiredSession() {
    const verified: string[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/refresh')) return new Response('{}', { status: 401 });
      if (path.endsWith('/auth/logout')) return new Response(null, { status: 204 });
      if (path.endsWith('/auth/email/login')) {
        const body = JSON.parse(String(init?.body)) as { email: string };
        return new Response(
          JSON.stringify({
            access_token: body.email.startsWith('same')
              ? 'same-token'
              : body.email.startsWith('other')
                ? 'other-token'
                : 'invalid-token',
          }),
          { status: 200 },
        );
      }
      if (path.endsWith('/me')) {
        const authorization = (init?.headers as Record<string, string>).Authorization;
        if (authorization === 'Bearer invalid-token') verified.push(authorization);
        if (authorization === 'Bearer same-token' || authorization === 'Bearer other-token') {
          verified.push(authorization);
          return new Response(
            JSON.stringify({ id: authorization === 'Bearer same-token' ? 7 : 8 }),
            {
              status: 200,
            },
          );
        }
        return new Response('{}', { status: 401 });
      }
      return new Response('{}', { status: 200 });
    });
    return verified;
  }

  it('loads public login options if the session changes while configuration is in flight', async () => {
    let finishConfig!: (response: Response) => void;
    let configRequests = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) {
        configRequests += 1;
        if (configRequests === 1)
          return new Promise<Response>((resolve) => {
            finishConfig = resolve;
          });
        return new Response('{"enable_dev_auth":true}', { status: 200 });
      }
      if (path.endsWith('/me')) return new Response('{"id":7}', { status: 200 });
      return new Response('{}', { status: 200 });
    });
    renderProvider();
    await vi.waitFor(() => expect(configRequests).toBe(1));
    act(() => setAccessToken('new-token'));
    finishConfig(new Response('{"enable_dev_auth":true}', { status: 200 }));
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(screen.getByTestId('user-id')).toHaveTextContent('7');
    expect(screen.getByTestId('auth-config')).toHaveTextContent('enabled');
  });

  it('сохраняет неотправленный подход после истечения сессии, новой вкладки и входа в тот же аккаунт', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    const pending = pendingWorkout();
    localStorage.setItem('fit_food_draft_7_2030-01-10_breakfast', 'private food');
    const verified = mockExpiredSession();
    const first = renderProvider();

    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(sessionStorage.getItem('fit_access_token')).toBeNull();
    expect(lastAuthenticatedUserId()).toBe(7);
    expect(localStorage.getItem('fit_food_draft_7_2030-01-10_breakfast')).toBeNull();
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);

    first.unmount();
    sessionStorage.clear();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);

    await userEvent.click(screen.getByRole('button', { name: 'Войти снова' }));
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(verified).toContain('Bearer same-token');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);
  });

  it('удаляет сохранённую после истечения очередь при входе в другой подтверждённый аккаунт', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    pendingWorkout();
    mockExpiredSession();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'Войти в другой аккаунт' }));
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('8'));
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull();
    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
    expect(lastAuthenticatedUserId()).toBe(8);
  });

  it('без ID вкладки сохраняет очереди до проверки и оставляет только подтверждённый аккаунт', async () => {
    sessionStorage.removeItem('fit_authenticated_user_id');
    const pending = pendingWorkout();
    pendingWorkout(8, { ...activeWorkout, id: 43 });
    mockExpiredSession();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));

    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
    expect(loadActiveWorkoutQueue(8, 43).queue).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'Войти снова' }));
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
    expect(localStorage.getItem(activeWorkoutQueueKey(8, 43))).toBeNull();
    expect(loadCurrentActiveWorkoutSnapshot(8)).toBeUndefined();
  });

  it('очищает сохранённую после истечения очередь при явном выходе', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    pendingWorkout();
    mockExpiredSession();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(loadActiveWorkoutQueue(7, 42).queue).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await waitFor(() => expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull());
    expect(loadCurrentActiveWorkoutSnapshot(7)).toBeUndefined();
    expect(lastAuthenticatedUserId()).toBeUndefined();
  });

  it('не удаляет очередь и не открывает данные при неподтверждённом новом токене', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    const pending = pendingWorkout();
    const verified = mockExpiredSession();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));

    await userEvent.click(screen.getByRole('button', { name: 'Проверить отклонённый вход' }));
    await waitFor(() => expect(verified).toContain('Bearer invalid-token'));
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(sessionStorage.getItem('fit_access_token')).toBeNull();
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
  });

  it('подтверждает аккаунт после повторного входа в другой вкладке', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    const pending = pendingWorkout();
    const verified = mockExpiredSession();
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');

    await act(async () => {
      sessionStorage.setItem('fit_access_token', 'same-token');
      window.dispatchEvent(new Event(AUTH_TOKEN_RECEIVED_EVENT));
    });

    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    expect(verified).toContain('Bearer same-token');
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
  });

  it('не возобновляет сессию и не восстанавливает очередь после явного выхода при позднем 401', async () => {
    let meCalls = 0;
    let refreshCalls = 0;
    let finishMe!: (response: Response) => void;
    const delayedMe = new Promise<Response>((resolve) => {
      finishMe = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/logout')) return new Response(null, { status: 204 });
      if (path.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        return new Response('{"access_token":"late-token"}', { status: 200 });
      }
      if (path.endsWith('/me')) {
        meCalls += 1;
        return meCalls === 2 ? delayedMe : new Response('{"id":7}', { status: 200 });
      }
      return new Response('{}', { status: 200 });
    });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    pendingWorkout();
    const reloadDone = new Promise<void>((resolve) =>
      window.addEventListener('test:reload-complete', () => resolve(), { once: true }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Обновить профиль' }));
    await waitFor(() => expect(meCalls).toBe(2));
    await userEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull();

    await act(async () => {
      finishMe(new Response('{}', { status: 401 }));
      await reloadDone;
    });

    expect(refreshCalls).toBe(0);
    expect(sessionStorage.getItem('fit_access_token')).toBeNull();
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull();
  });

  it('не возвращает прежнего пользователя после смены аккаунта и позднего ответа профиля', async () => {
    let oldMeCalls = 0;
    let finishOldMe!: (response: Response) => void;
    const delayedMe = new Promise<Response>((resolve) => {
      finishOldMe = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/dev-login'))
        return new Response('{"access_token":"switched-token"}', { status: 200 });
      if (path.endsWith('/me')) {
        const authorization = (init?.headers as Record<string, string>).Authorization;
        if (authorization === 'Bearer switched-token')
          return new Response('{"id":8}', { status: 200 });
        oldMeCalls += 1;
        return oldMeCalls === 2 ? delayedMe : new Response('{"id":7}', { status: 200 });
      }
      return new Response('{}', { status: 200 });
    });
    renderProvider();
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('7'));
    pendingWorkout();
    const reloadDone = new Promise<void>((resolve) =>
      window.addEventListener('test:reload-complete', () => resolve(), { once: true }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Обновить профиль' }));
    await waitFor(() => expect(oldMeCalls).toBe(2));
    await userEvent.click(screen.getByRole('button', { name: 'Сменить аккаунт' }));
    await waitFor(() => expect(screen.getByTestId('user-id')).toHaveTextContent('8'));

    await act(async () => {
      finishOldMe(new Response('{"id":7}', { status: 200 }));
      await reloadDone;
    });

    expect(screen.getByTestId('user-id')).toHaveTextContent('8');
    expect(sessionStorage.getItem('fit_access_token')).toBe('switched-token');
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull();
  });

  it('не запускает повторный refresh после выхода во время начальной загрузки профиля', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    pendingWorkout();
    let finishMe!: (response: Response) => void;
    const delayedMe = new Promise<Response>((resolve) => {
      finishMe = resolve;
    });
    let meStarted = false;
    let refreshCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith('/public/config')) return new Response('{}', { status: 200 });
      if (path.endsWith('/auth/logout')) return new Response(null, { status: 204 });
      if (path.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        return new Response('{"access_token":"late-token"}', { status: 200 });
      }
      if (path.endsWith('/me')) {
        meStarted = true;
        return delayedMe;
      }
      return new Response('{}', { status: 200 });
    });
    renderProvider();
    await waitFor(() => expect(meStarted).toBe(true));
    await userEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await act(async () => {
      finishMe(new Response('{"id":7}', { status: 200 }));
    });

    await waitFor(() => expect(screen.getByTestId('auth-loading')).toHaveTextContent('ready'));
    expect(refreshCalls).toBe(0);
    expect(screen.getByTestId('user-id')).toHaveTextContent('none');
    expect(sessionStorage.getItem('fit_access_token')).toBeNull();
    expect(localStorage.getItem(activeWorkoutQueueKey(7, 42))).toBeNull();
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

  it('сохраняет очередь нового подтверждённого аккаунта при недействительном предыдущем токене', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'synthetic-init-data' } });
    saveActiveWorkoutSnapshot(7, activeWorkout);
    saveActiveWorkoutQueue(
      enqueueWorkoutMutation(loadActiveWorkoutQueue(7, 42), {
        setId: 201,
        serverVersion: 1,
        values: { actual_reps: 8, actual_weight: 40, is_completed: true },
      }),
    );
    const pending = loadActiveWorkoutQueue(7, 42).queue;
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
    expect(loadActiveWorkoutQueue(7, 42).queue).toEqual(pending);
    expect(loadCurrentActiveWorkoutSnapshot(7)?.id).toBe(42);
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
