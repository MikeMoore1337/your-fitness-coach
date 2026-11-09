import { withHydrationFence } from '../../shared/browser/hydrationFence';
import {
  HYDRATION_PENDING_SESSION_PREFIX,
  HYDRATION_PENDING_STORAGE_PREFIX,
} from '../../shared/userScopedStorage';

export type HydrationAddRequest = {
  volume: number;
  kind: string;
  source: 'quick_preset' | 'manual';
  date: string;
  key: string;
  uncertain: boolean;
  demoGeneration?: number;
};
export type PendingHydration = Record<string, HydrationAddRequest[]>;
export type HydrationPendingStore = {
  entries: PendingHydration;
  confirmed: string[];
  demoGeneration?: number;
};

export const HYDRATION_PENDING_EVENT = 'fit:hydration-pending';
const kinds = new Set(['water', 'tea', 'coffee', 'milk', 'juice', 'other']);

export async function demoHydrationScope(token: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  const hash = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
  return `demo_${hash}`;
}

export function pendingStorageKey(scope: string): string {
  return `${HYDRATION_PENDING_STORAGE_PREFIX}${scope}`;
}

function validateRequest(date: string, raw: unknown): HydrationAddRequest {
  if (!raw || typeof raw !== 'object') throw new Error('Некорректная сохранённая запись');
  const item = raw as HydrationAddRequest;
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    item.date !== date ||
    !Number.isInteger(item.volume) ||
    item.volume < 1 ||
    item.volume > 5000 ||
    !kinds.has(item.kind) ||
    !['quick_preset', 'manual'].includes(item.source) ||
    typeof item.key !== 'string' ||
    !item.key ||
    item.key.length > 128 ||
    typeof item.uncertain !== 'boolean' ||
    (item.demoGeneration !== undefined &&
      (!Number.isSafeInteger(item.demoGeneration) || item.demoGeneration < 0))
  )
    throw new Error('Некорректная сохранённая запись');
  return { ...item };
}

export function readPendingHydration(scope: string): HydrationPendingStore {
  const raw: unknown = JSON.parse(
    localStorage.getItem(pendingStorageKey(scope)) ?? '{"entries":{},"confirmed":[]}',
  );
  if (!raw || typeof raw !== 'object' || Array.isArray(raw))
    throw new Error('Некорректное хранилище');
  const store = raw as HydrationPendingStore;
  if (
    !store.entries ||
    typeof store.entries !== 'object' ||
    Array.isArray(store.entries) ||
    !Array.isArray(store.confirmed) ||
    store.confirmed.some((key) => typeof key !== 'string' || !key || key.length > 128) ||
    (store.demoGeneration !== undefined &&
      (!Number.isSafeInteger(store.demoGeneration) || store.demoGeneration < 0))
  )
    throw new Error('Некорректное хранилище');
  const pending: PendingHydration = {};
  for (const [date, items] of Object.entries(store.entries)) {
    if (!Array.isArray(items)) throw new Error('Некорректное хранилище');
    pending[date] = items.map((item) => validateRequest(date, item));
  }
  return { ...store, entries: pending };
}

export function writePendingHydration(scope: string, store: HydrationPendingStore): void {
  const key = pendingStorageKey(scope);
  for (const [date, items] of Object.entries(store.entries)) {
    if (!items.length) delete store.entries[date];
  }
  if (
    Object.values(store.entries).some((items) => items.length) ||
    store.confirmed.length ||
    store.demoGeneration !== undefined
  )
    localStorage.setItem(key, JSON.stringify(store));
  else localStorage.removeItem(key);
  window.dispatchEvent(new CustomEvent(HYDRATION_PENDING_EVENT, { detail: key }));
}

function migratePending(scope: string): HydrationPendingStore {
  const store = readPendingHydration(scope);
  if (!scope.startsWith('user_')) return store;
  const legacyKey = `${HYDRATION_PENDING_SESSION_PREFIX}${scope.slice(5)}`;
  const saved = sessionStorage.getItem(legacyKey);
  if (saved === null) return store;
  const legacy: unknown = JSON.parse(saved);
  if (!legacy || typeof legacy !== 'object' || Array.isArray(legacy))
    throw new Error('Некорректное хранилище');
  for (const [date, raw] of Object.entries(legacy)) {
    const item = { ...validateRequest(date, raw), uncertain: true };
    if (store.confirmed.includes(item.key)) continue;
    const items = (store.entries[date] ??= []);
    const same = items.find((entry) => entry.key === item.key);
    if (
      same &&
      (same.volume !== item.volume || same.kind !== item.kind || same.source !== item.source)
    )
      throw new Error('Конфликт сохранённых записей');
    if (!same) items.push(item);
  }
  writePendingHydration(scope, store);
  sessionStorage.removeItem(legacyKey);
  return store;
}

export function withPendingHydration<T>(
  scope: string,
  task: (store: HydrationPendingStore) => T,
): Promise<T> {
  return withHydrationFence(pendingStorageKey(scope), () => task(migratePending(scope)));
}
