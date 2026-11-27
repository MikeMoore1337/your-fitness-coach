import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AUTH_LOGOUT_EVENT,
  AUTH_SESSION_EXPIRED_EVENT,
  AUTH_TOKEN_RECEIVED_EVENT,
  api,
  apiFile,
  clearAccessToken,
  coordinateAccessTokenRefresh,
  expireAccessToken,
  getAccessToken,
  refreshAccessToken,
  setAccessToken,
  switchAuthenticatedAccount,
} from '../../../../src/shared/api/client';
import { createCrossContextCoordinator } from '../../../../src/shared/browser/crossContextLock';

describe('api client', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    vi.restoreAllMocks();
  });
  afterEach(() => clearAccessToken());

  it('stores access tokens only in sessionStorage', () => {
    setAccessToken('secret');
    expect(getAccessToken()).toBe('secret');
    expect(localStorage.getItem('fit_access_token')).toBeNull();
  });

  it('refreshes once after 401 and retries with the new token', async () => {
    setAccessToken('old');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"detail":"expired"}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{"access_token":"new"}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    await expect(api<{ ok: boolean }>('/api/v1/me')).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe('new');
  });

  it('discards a stale read and retries once after the same verified account signs in', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)))
      .mockResolvedValueOnce(new Response('{"version":"fresh"}', { status: 200 }));
    const request = api<{ version: string }>('/api/v1/workouts/session-rotation');
    setAccessToken('new-token', 7);
    finishRequest(new Response('{"version":"stale"}', { status: 200 }));

    await expect(request).resolves.toEqual({ version: 'fresh' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({
      Authorization: 'Bearer new-token',
    });
  });

  it('waits for the verified token when the same-user login marker arrives first', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)))
      .mockResolvedValueOnce(new Response('{"version":"fresh"}', { status: 200 }));
    const request = api<{ version: string }>('/api/v1/workouts/session-rotation');
    localStorage.setItem(
      'fit_auth_verified_login_v1',
      JSON.stringify({ id: 'pending', userId: 7 }),
    );
    finishRequest(new Response('{"version":"stale"}', { status: 200 }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalledOnce();
    setAccessToken('new-token', 7);
    window.dispatchEvent(new Event(AUTH_TOKEN_RECEIVED_EVENT));

    await expect(request).resolves.toEqual({ version: 'fresh' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toMatchObject({
      Authorization: 'Bearer new-token',
    });
  });

  it('does not retry if logout occurs while waiting for a verified token', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    localStorage.setItem(
      'fit_auth_verified_login_v1',
      JSON.stringify({ id: 'pending', userId: 7 }),
    );
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    clearAccessToken();

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('stops waiting when the caller cancels before the verified token arrives', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const controller = new AbortController();
    const rejected = expect(
      api('/api/v1/private', { signal: controller.signal }),
    ).rejects.toMatchObject({
      name: 'AbortError',
    });
    localStorage.setItem(
      'fit_auth_verified_login_v1',
      JSON.stringify({ id: 'pending', userId: 7 }),
    );
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not extend the original timeout while waiting for a token', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private', { timeoutMs: 40 })).rejects.toMatchObject({
      name: 'AbortError',
    });
    localStorage.setItem(
      'fit_auth_verified_login_v1',
      JSON.stringify({ id: 'pending', userId: 7 }),
    );
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not retry file downloads even after a verified same-account login', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(apiFile('/api/v1/account/export')).rejects.toMatchObject({
      name: 'AbortError',
    });
    setAccessToken('new-token', 7);
    finishRequest(new Response('stale', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each([
    ['another account', { method: 'GET' }, 8, false],
    ['mutation', { method: 'POST', body: { value: 1 } }, 7, false],
    ['explicit headers', { headers: { Authorization: 'Bearer explicit' } }, 7, false],
    ['caller cancelled', { method: 'GET' }, 7, true],
  ])('does not retry a stale request after %s', async (_case, options, nextUser, cancelled) => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const controller = new AbortController();
    const request = api('/api/v1/private', { ...options, signal: controller.signal });
    const rejected = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    setAccessToken('next-token', nextUser);
    if (cancelled) controller.abort();
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not retry a stale read after logout and a new login, even for the same account', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    clearAccessToken();
    setAccessToken('new-token', 7);
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not retry a stale read after expiry and a new login, even for the same account', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    expireAccessToken();
    setAccessToken('new-token', 7);
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('does not retry when a different account signed in before the original account returned', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    setAccessToken('other-account', 8);
    setAccessToken('same-account', 7);
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('fails closed when the previous account identity is not known', async () => {
    setAccessToken('old-token', 7);
    let finishRequest!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRequest = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    setAccessToken('new-token', 7);
    finishRequest(new Response('{"secret":"stale"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('limits recovery to one new read when the verified session changes again', async () => {
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    setAccessToken('first-token', 7);
    let finishFirst!: (response: Response) => void;
    let finishSecond!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishFirst = resolve)))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishSecond = resolve)));
    const rejected = expect(api('/api/v1/private')).rejects.toMatchObject({ name: 'AbortError' });
    setAccessToken('second-token', 7);
    finishFirst(new Response('{"secret":"first"}', { status: 200 }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    setAccessToken('third-token', 7);
    finishSecond(new Response('{"secret":"second"}', { status: 200 }));

    await rejected;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not restore a token when an in-flight refresh finishes after logout', async () => {
    setAccessToken('old');
    let finishRefresh!: (response: Response) => void;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finishRefresh = resolve;
        }),
    );
    const refreshing = refreshAccessToken();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    clearAccessToken();
    finishRefresh(new Response('{"access_token":"late"}', { status: 200 }));

    await expect(refreshing).resolves.toBe(false);
    expect(getAccessToken()).toBeNull();
  });

  it('does not retry a stale mutation under another account after a delayed refresh', async () => {
    setAccessToken('old-account');
    let finishRefresh!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"detail":"expired"}', { status: 401 }))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          }),
      )
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    const request = api('/api/v1/workouts/sets/201', { method: 'PATCH', body: { reps: 10 } });
    const result = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    switchAuthenticatedAccount(8);
    setAccessToken('new-account');
    finishRefresh(new Response('{"access_token":"late-old-account"}', { status: 200 }));

    await result;
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe('new-account');
  });

  it('does not retry a pending mutation after an explicit sign-in without a known previous ID', async () => {
    setAccessToken('old-account');
    let finishRefresh!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"detail":"expired"}', { status: 401 }))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          }),
      )
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    const request = api('/api/v1/workouts/sets/201', { method: 'PATCH', body: { reps: 10 } });
    const result = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    setAccessToken('new-account', 8);
    finishRefresh(new Response('{"access_token":"late-old-account"}', { status: 200 }));

    await result;
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe('new-account');
  });

  it('does not retry a pending file request after a verified sign-in', async () => {
    setAccessToken('old-account');
    let finishRefresh!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          }),
      )
      .mockResolvedValueOnce(new Response('private file', { status: 200 }));
    const request = apiFile('/api/v1/account/export');
    const result = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    setAccessToken('new-account', 8);
    finishRefresh(new Response('{"access_token":"late-old-account"}', { status: 200 }));

    await result;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('notices another tab verified a login before its token message arrives', async () => {
    setAccessToken('old-account');
    let finishRefresh!: (response: Response) => void;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finishRefresh = resolve;
          }),
      );
    const request = api('/api/v1/workouts/sets/201', { method: 'PATCH', body: { reps: 10 } });
    const result = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    localStorage.setItem('fit_auth_verified_login_v1', JSON.stringify({ id: 'login', userId: 8 }));
    finishRefresh(new Response('{"access_token":"late-old-account"}', { status: 200 }));

    await result;
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe('old-account');
  });

  it('clears the verified account marker on explicit logout', () => {
    setAccessToken('verified', 7);
    expect(localStorage.getItem('fit_auth_verified_login_v1')).not.toBeNull();
    clearAccessToken();
    expect(localStorage.getItem('fit_auth_verified_login_v1')).toBeNull();
  });

  it('marks a new explicit logout while keeping the legacy message type', () => {
    const post =
      typeof window.BroadcastChannel === 'function'
        ? vi.spyOn(window.BroadcastChannel.prototype, 'postMessage')
        : undefined;
    const store = vi.spyOn(Storage.prototype, 'setItem');
    clearAccessToken();
    const fallback = store.mock.calls.find(([key]) => key === 'fit_auth_session_event_v1');
    const message = post?.mock.calls[0]?.[0] ?? JSON.parse(fallback![1]).message;
    expect(message).toEqual({ type: 'logout', cause: 'explicit-logout' });
  });

  it('broadcasts verified sign-in using the existing access-token message type', () => {
    const post =
      typeof window.BroadcastChannel === 'function'
        ? vi.spyOn(window.BroadcastChannel.prototype, 'postMessage')
        : undefined;
    const store = vi.spyOn(Storage.prototype, 'setItem');
    setAccessToken('verified', 7);
    const fallback = store.mock.calls.find(([key]) => key === 'fit_auth_session_event_v1');
    const message = post?.mock.calls[0]?.[0] ?? JSON.parse(fallback![1]).message;
    const { id: loginId } = JSON.parse(localStorage.getItem('fit_auth_verified_login_v1')!);
    expect(message).toEqual({ type: 'access-token', token: 'verified', userId: 7, loginId });
  });

  it('discards an in-flight file response after logout', async () => {
    setAccessToken('old');
    let finishRequest!: (response: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finishRequest = resolve;
        }),
    );
    const result = expect(apiFile('/api/v1/me/exports/1/download')).rejects.toMatchObject({
      name: 'AbortError',
    });
    clearAccessToken();
    finishRequest(new Response('private export', { status: 200 }));
    await result;
  });

  it('discards an in-flight authenticated response after logout', async () => {
    setAccessToken('old');
    let finishRequest!: (response: Response) => void;
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finishRequest = resolve;
        }),
    );
    const request = api('/api/v1/me');
    const result = expect(request).rejects.toMatchObject({ name: 'AbortError' });
    clearAccessToken();
    finishRequest(new Response('{"id":7}', { status: 200 }));

    await result;
    expect(getAccessToken()).toBeNull();
  });

  it('keeps a safe Russian business detail, status, and raw conflict body', async () => {
    const body = {
      detail: { code: 'warmup_target_stale', message: 'Тренировка изменилась' },
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status: 409 }),
    );

    await expect(api('/api/v1/workouts/42')).rejects.toMatchObject({
      status: 409,
      message: 'Тренировка изменилась',
      body,
    });
  });

  it.each([500, 502, 503])('uses a Russian fallback for server status %s', async (status) => {
    const body = {
      detail: {
        message:
          'Traceback (most recent call last): File "/srv/app/main.py", line 7, secret=sk-test-secret',
      },
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status }),
    );

    await expect(api('/api/v1/workouts/42')).rejects.toMatchObject({
      status,
      message: 'Сервис временно недоступен. Попробуйте ещё раз.',
      body,
    });
  });

  it('does not expose HTML gateway responses', async () => {
    const body = '<html><body>secret=sk-test-secret</body></html>';
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(body, { status: 502 }));

    await expect(api('/api/v1/workouts/42')).rejects.toMatchObject({
      status: 502,
      message: 'Сервис временно недоступен. Попробуйте ещё раз.',
      body,
    });
  });

  it('does not flatten malformed validation arrays into user-facing text', async () => {
    const body = { detail: [{ msg: { leaked: 'internal-path' }, loc: ['body', 'weight'] }] };
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status: 422 }),
    );

    await expect(api('/api/v1/workouts/42')).rejects.toMatchObject({
      status: 422,
      message: 'Проверьте введённые данные.',
      body,
    });
  });

  it('preserves an expired 401 status and body while clearing the failed session', async () => {
    setAccessToken('expired-session');
    const expired = vi.fn();
    const logout = vi.fn();
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, expired);
    window.addEventListener(AUTH_LOGOUT_EVENT, logout);
    const body = { detail: 'expired' };
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'invalid refresh' }), { status: 401 }),
      );

    await expect(api('/api/v1/me')).rejects.toMatchObject({
      status: 401,
      message: 'Сессия недействительна или истекла. Войдите снова.',
      body,
    });
    expect(getAccessToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
    expect(logout).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, expired);
    window.removeEventListener(AUTH_LOGOUT_EVENT, logout);
  });

  it('preserves a 403 status and raw body without clearing the session', async () => {
    setAccessToken('active-session');
    const body = { detail: 'Forbidden' };
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status: 403 }),
    );

    await expect(api('/api/v1/workouts/42')).rejects.toMatchObject({
      status: 403,
      message: 'Недостаточно прав для выполнения этого действия.',
      body,
    });
    expect(getAccessToken()).toBe('active-session');
  });

  it('reuses a token refreshed by another tab while waiting for the browser lock', async () => {
    setAccessToken('old');
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const request = vi.fn(async (_name: string, callback: () => Promise<boolean>) => {
      setAccessToken('from-another-tab');
      return callback();
    });
    const originalLocks = navigator.locks;
    Object.defineProperty(navigator, 'locks', {
      configurable: true,
      value: { request },
    });

    try {
      await expect(refreshAccessToken()).resolves.toBe(true);
      expect(request).toHaveBeenCalledWith('fit-auth-refresh', expect.any(Function));
      expect(fetchMock).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe('from-another-tab');
    } finally {
      Object.defineProperty(navigator, 'locks', {
        configurable: true,
        value: originalLocks,
      });
    }
  });

  it('does not reuse a different account token after waiting for the refresh lock', async () => {
    setAccessToken('old-account');
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const request = vi.fn(async (_name: string, callback: () => Promise<boolean>) => {
      switchAuthenticatedAccount(8);
      setAccessToken('new-account');
      return callback();
    });
    const originalLocks = navigator.locks;
    Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } });
    try {
      await expect(refreshAccessToken()).resolves.toBe(false);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(getAccessToken()).toBe('new-account');
    } finally {
      Object.defineProperty(navigator, 'locks', { configurable: true, value: originalLocks });
    }
  });

  it('serializes two refresh contexts without Web Locks and reuses the winner token', async () => {
    setAccessToken('old');
    const originalLocks = navigator.locks;
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
    const firstContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'context-a',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const secondContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'context-b',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{"access_token":"winner"}', { status: 200 }));

    try {
      await expect(
        Promise.all([
          coordinateAccessTokenRefresh(firstContext),
          coordinateAccessTokenRefresh(secondContext),
        ]),
      ).resolves.toEqual([true, true]);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(getAccessToken()).toBe('winner');
    } finally {
      Object.defineProperty(navigator, 'locks', {
        configurable: true,
        value: originalLocks,
      });
    }
  });

  it('waits for delayed winner-token delivery after the fallback lock', async () => {
    setAccessToken('old');
    sessionStorage.setItem('fit_authenticated_user_id', '7');
    const holder = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'refresh-holder',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    const waitingContext = createCrossContextCoordinator({
      nativeLocks: null,
      ownerId: 'refresh-waiter',
      pollMs: 1,
      leaseMs: 1000,
      timeoutMs: 2000,
    });
    let releaseHolder!: () => void;
    const hold = new Promise<void>((resolve) => {
      releaseHolder = resolve;
    });
    let holderEntered!: () => void;
    const entered = new Promise<void>((resolve) => {
      holderEntered = resolve;
    });
    const holding = holder.run('fit-auth-refresh', async () => {
      holderEntered();
      await hold;
    });
    await entered;
    const waiting = coordinateAccessTokenRefresh(waitingContext);
    setAccessToken('winner');
    sessionStorage.setItem('fit_access_token', 'old');
    releaseHolder();
    window.setTimeout(() => {
      if (typeof window.BroadcastChannel === 'function') {
        const channel = new window.BroadcastChannel('fit_auth_session');
        channel.postMessage({
          type: 'access-token',
          token: 'winner',
          source: 'refresh',
          refreshUserId: 7,
        });
        channel.close();
      } else {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'fit_auth_session_event_v1',
            newValue: JSON.stringify({
              message: {
                type: 'access-token',
                token: 'winner',
                source: 'refresh',
                refreshUserId: 7,
              },
            }),
          }),
        );
      }
    }, 10);
    const fetchMock = vi.spyOn(globalThis, 'fetch');

    await expect(Promise.all([holding, waiting])).resolves.toEqual([undefined, true]);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe('winner');
  });

  it('turns a fetch failure into a readable offline error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'));

    await expect(api('/api/v1/me')).rejects.toMatchObject({
      status: 0,
      message: 'Нет соединения с сервером. Проверьте интернет и попробуйте снова.',
    });
  });

  it('turns an elapsed request timeout into a readable timeout error', async () => {
    vi.useFakeTimers();
    try {
      vi.spyOn(globalThis, 'fetch').mockImplementationOnce((_input, init) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Timed out', 'AbortError'));
          });
        });
      });

      const request = expect(api('/api/v1/me', { timeoutMs: 10 })).rejects.toMatchObject({
        status: 0,
        message: 'Сервер не ответил вовремя. Попробуйте снова.',
      });
      await vi.advanceTimersByTimeAsync(10);

      await request;
    } finally {
      vi.useRealTimers();
    }
  });

  it('sends FormData with auth without overriding the browser multipart boundary', async () => {
    setAccessToken('avatar-token');
    const form = new FormData();
    form.append('file', new Blob(['avatar'], { type: 'image/png' }), 'avatar.png');
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));

    await expect(
      api<{ ok: boolean }>('/api/v1/me/avatar', { method: 'PUT', body: form }),
    ).resolves.toEqual({ ok: true });

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.body).toBe(form);
    expect(init?.headers).toMatchObject({ Authorization: 'Bearer avatar-token' });
    expect(init?.headers).not.toHaveProperty('Content-Type');
  });

  it('forwards caller cancellation without presenting it as a timeout', async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, 'fetch').mockImplementationOnce((_input, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Cancelled', 'AbortError'));
        });
      });
    });

    const request = api('/api/v1/nutrition/foods/search?q=test', {
      signal: controller.signal,
    });
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: 'AbortError' });
  });
});
