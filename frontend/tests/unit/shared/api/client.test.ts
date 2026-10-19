import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  clearAccessToken,
  coordinateAccessTokenRefresh,
  getAccessToken,
  refreshAccessToken,
  setAccessToken,
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
    const body = { detail: 'expired' };
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(body), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'invalid refresh' }), { status: 401 }));

    await expect(api('/api/v1/me')).rejects.toMatchObject({
      status: 401,
      message: 'Сессия недействительна или истекла. Войдите снова.',
      body,
    });
    expect(getAccessToken()).toBeNull();
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
        channel.postMessage({ type: 'access-token', token: 'winner' });
        channel.close();
      } else {
        window.dispatchEvent(
          new StorageEvent('storage', {
            key: 'fit_auth_session_event_v1',
            newValue: JSON.stringify({
              message: { type: 'access-token', token: 'winner' },
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

      const request = api('/api/v1/me', { timeoutMs: 10 });
      await vi.advanceTimersByTimeAsync(10);

      await expect(request).rejects.toMatchObject({
        status: 0,
        message: 'Сервер не ответил вовремя. Попробуйте снова.',
      });
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
