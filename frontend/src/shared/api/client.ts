import { crossContextCoordinator, type CrossContextCoordinator } from '../browser/crossContextLock';
import { getApiRuntime } from '../runtime/runtime';

const ACCESS_TOKEN_KEY = 'fit_access_token';
const AUTH_CHANNEL_NAME = 'fit_auth_session';
const AUTH_STORAGE_EVENT_KEY = 'fit_auth_session_event_v1';
const AUTH_GENERATION_KEY = 'fit_auth_session_generation_v1';
const AUTH_REFRESH_LOCK_NAME = 'fit-auth-refresh';
export const AUTH_LOGOUT_EVENT = 'fit:auth-logout';
const AUTH_TOKEN_RECEIVED_EVENT = 'fit:auth-token-received';

type AuthChannelMessage = { type: 'access-token'; token: string } | { type: 'logout' };

const authChannel =
  typeof window !== 'undefined' && typeof window.BroadcastChannel === 'function'
    ? new window.BroadcastChannel(AUTH_CHANNEL_NAME)
    : null;

function receiveAuthMessage(message: AuthChannelMessage): void {
  if (message.type === 'access-token' && typeof message.token === 'string') {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, message.token);
    window.dispatchEvent(new Event(AUTH_TOKEN_RECEIVED_EVENT));
  } else if (message.type === 'logout') {
    sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  }
}

authChannel?.addEventListener('message', (event: MessageEvent<AuthChannelMessage>) => {
  if (!event.data || typeof event.data !== 'object' || !('type' in event.data)) return;
  receiveAuthMessage(event.data);
});

window.addEventListener('storage', (event) => {
  if (event.key !== AUTH_STORAGE_EVENT_KEY || authChannel || !event.newValue) return;
  try {
    const envelope = JSON.parse(event.newValue) as { message?: AuthChannelMessage };
    if (envelope.message?.type === 'logout' || envelope.message?.type === 'access-token') {
      receiveAuthMessage(envelope.message);
    }
  } catch {
    // Ignore malformed cross-tab messages.
  }
});

function broadcastAuthMessage(message: AuthChannelMessage): void {
  if (authChannel) {
    authChannel.postMessage(message);
    return;
  }
  try {
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    localStorage.setItem(AUTH_STORAGE_EVENT_KEY, JSON.stringify({ id, message }));
    localStorage.removeItem(AUTH_STORAGE_EVENT_KEY);
  } catch {
    // Session state remains usable in the current restrictive WebView.
  }
}

function authGeneration(): string | null {
  try {
    return localStorage.getItem(AUTH_GENERATION_KEY);
  } catch {
    return null;
  }
}

function advanceAuthGeneration(): void {
  try {
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    localStorage.setItem(AUTH_GENERATION_KEY, id);
  } catch {
    // BroadcastChannel remains the primary transport when shared storage is unavailable.
  }
}

async function waitForWinnerToken(tokenBeforeLock: string | null): Promise<boolean> {
  if (getAccessToken() !== tokenBeforeLock) return Boolean(getAccessToken());
  return new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timeout);
      window.removeEventListener(AUTH_TOKEN_RECEIVED_EVENT, onToken);
      resolve(Boolean(getAccessToken() && getAccessToken() !== tokenBeforeLock));
    };
    const onToken = () => finish();
    const timeout = window.setTimeout(finish, 250);
    window.addEventListener(AUTH_TOKEN_RECEIVED_EVENT, onToken, { once: true });
  });
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

function migrateLegacyToken(): void {
  const legacy = localStorage.getItem(ACCESS_TOKEN_KEY);
  if (legacy && !sessionStorage.getItem(ACCESS_TOKEN_KEY)) {
    sessionStorage.setItem(ACCESS_TOKEN_KEY, legacy);
  }
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem('fit_refresh_token');
  localStorage.removeItem(AUTH_STORAGE_EVENT_KEY);
}

migrateLegacyToken();

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  advanceAuthGeneration();
  broadcastAuthMessage({ type: 'access-token', token });
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  advanceAuthGeneration();
  window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
  broadcastAuthMessage({ type: 'logout' });
}

async function responseError(response: Response): Promise<ApiError> {
  const text = await response.text();
  let body: unknown = text;
  let message = text || `Ошибка ${response.status}`;
  try {
    body = JSON.parse(text);
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string') message = detail;
      if (Array.isArray(detail)) {
        message = detail
          .map((item) =>
            item && typeof item === 'object' && 'msg' in item ? String(item.msg) : String(item),
          )
          .join(' ');
      }
    }
  } catch {
    // Non-JSON error bodies remain readable.
  }
  return new ApiError(message.slice(0, 500), response.status, body);
}

let refreshPromise: Promise<boolean> | null = null;

async function requestAccessTokenRefresh(tokenBeforeRequest: string | null): Promise<boolean> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'same-origin',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    if (!response.ok) {
      const winnerToken = getAccessToken();
      if (winnerToken && winnerToken !== tokenBeforeRequest) return true;
      if (response.status === 401 || response.status === 403) clearAccessToken();
      return false;
    }
    const data = (await response.json()) as { access_token?: unknown };
    if (typeof data.access_token !== 'string' || !data.access_token) {
      const winnerToken = getAccessToken();
      if (winnerToken && winnerToken !== tokenBeforeRequest) return true;
      clearAccessToken();
      return false;
    }
    setAccessToken(data.access_token);
    return true;
  } catch {
    const winnerToken = getAccessToken();
    return Boolean(winnerToken && winnerToken !== tokenBeforeRequest);
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function coordinateAccessTokenRefresh(
  coordinator: CrossContextCoordinator = crossContextCoordinator,
): Promise<boolean> {
  const tokenBeforeLock = getAccessToken();
  const generationBeforeLock = authGeneration();
  try {
    return await coordinator.run(AUTH_REFRESH_LOCK_NAME, async () => {
      const tokenAfterLock = getAccessToken();
      if (tokenAfterLock && tokenAfterLock !== tokenBeforeLock) return true;
      if (authGeneration() !== generationBeforeLock) {
        return waitForWinnerToken(tokenBeforeLock);
      }
      return requestAccessTokenRefresh(tokenAfterLock);
    });
  } catch {
    return false;
  }
}

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      return await coordinateAccessTokenRefresh();
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export interface ApiOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  timeoutMs?: number;
  retryAuth?: boolean;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { body, timeoutMs = 15_000, retryAuth = true, headers, signal, ...init } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) abortFromCaller();
  else signal?.addEventListener('abort', abortFromCaller, { once: true });
  const token = getAccessToken();
  const formData = typeof FormData !== 'undefined' && body instanceof FormData;
  const runtime = getApiRuntime();
  try {
    if (runtime.kind === 'demo') {
      if (formData) {
        throw new ApiError('Загрузка файлов недоступна в демо-режиме.', 403);
      }
      const method = (init.method ?? 'GET').toUpperCase();
      const response = await fetch('/api/v1/demo/sessions/current/transport', {
        method: 'POST',
        credentials: 'omit',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-Demo-Session': runtime.sessionToken,
        },
        body: JSON.stringify({
          path,
          method,
          body: body === undefined ? null : typeof body === 'string' ? body : body,
        }),
      });
      if (!response.ok) throw await responseError(response);
      if (response.status === 204) return undefined as T;
      const text = await response.text();
      if (method !== 'GET' && method !== 'HEAD') void runtime.onMutation?.();
      return (text ? JSON.parse(text) : null) as T;
    }
    const response = await fetch(path, {
      ...init,
      credentials: 'same-origin',
      signal: controller.signal,
      headers: {
        ...(body !== undefined && !formData ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      ...(body !== undefined
        ? {
            body: formData ? body : typeof body === 'string' ? body : JSON.stringify(body),
          }
        : {}),
    });
    if (response.status === 401 && retryAuth && (await refreshAccessToken())) {
      return api<T>(path, { ...options, retryAuth: false });
    }
    if (!response.ok) throw await responseError(response);
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : null) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (signal?.aborted) throw error;
      throw new ApiError('Сервер не ответил вовремя. Попробуйте снова.', 0);
    }
    if (error instanceof TypeError) {
      throw new ApiError('Нет соединения с сервером. Проверьте интернет и попробуйте снова.', 0);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}

export interface ApiFile {
  blob: Blob;
  filename: string | null;
}

function responseFilename(response: Response): string | null {
  const disposition = response.headers.get('Content-Disposition');
  const match = disposition?.match(/filename="([^"\\/]+)"/i);
  return match?.[1] ?? null;
}

export async function apiFile(
  path: string,
  { retryAuth = true }: { retryAuth?: boolean } = {},
): Promise<ApiFile> {
  if (getApiRuntime().kind === 'demo') {
    throw new ApiError('Скачивание файлов недоступно в демо-режиме.', 403);
  }
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15_000);
  const token = getAccessToken();
  try {
    const response = await fetch(path, {
      credentials: 'same-origin',
      signal: controller.signal,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (response.status === 401 && retryAuth && (await refreshAccessToken())) {
      return apiFile(path, { retryAuth: false });
    }
    if (!response.ok) throw await responseError(response);
    return { blob: await response.blob(), filename: responseFilename(response) };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('Сервер не ответил вовремя. Попробуйте снова.', 0);
    }
    if (error instanceof TypeError) {
      throw new ApiError('Нет соединения с сервером. Проверьте интернет и попробуйте снова.', 0);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
