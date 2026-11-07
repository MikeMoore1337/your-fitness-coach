import { IDBFactory, IDBObjectStore } from 'fake-indexeddb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createCrossContextCoordinator } from '../../../../src/shared/browser/crossContextLock';
import { resetHydrationFences } from '../../../../src/shared/browser/hydrationFence';
import {
  clearSensitiveUserScopedStorage,
  HYDRATION_PENDING_SESSION_PREFIX,
} from '../../../../src/shared/userScopedStorage';
import {
  pendingStorageKey,
  withPendingHydration,
  writePendingHydration,
} from '../../../../src/features/nutrition/hydrationPending';

const date = '2026-09-01';
const request = {
  date,
  volume: 250,
  kind: 'water',
  source: 'quick_preset' as const,
  key: 'old-key',
  uncertain: true,
};

describe('shared hydration pending requests', () => {
  beforeEach(() => {
    vi.stubGlobal('indexedDB', new IDBFactory());
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(async () => {
    await resetHydrationFences(null);
    vi.unstubAllGlobals();
  });

  it('migrates an older pending request without losing a different request for the same date', async () => {
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [{ ...request, key: 'other-key' }];
      writePendingHydration('user_7', store);
    });
    sessionStorage.setItem(
      `${HYDRATION_PENDING_SESSION_PREFIX}7`,
      JSON.stringify({ [date]: request }),
    );
    const store = await withPendingHydration('user_7', (value) => value);
    expect(store.entries[date]?.map((item) => item.key)).toEqual(['other-key', 'old-key']);
    expect(sessionStorage.getItem(`${HYDRATION_PENDING_SESSION_PREFIX}7`)).toBeNull();
  });

  it('does not resurrect a legacy retry already confirmed in another tab', async () => {
    await withPendingHydration('user_7', (store) => {
      store.confirmed.push(request.key);
      writePendingHydration('user_7', store);
    });
    sessionStorage.setItem(
      `${HYDRATION_PENDING_SESSION_PREFIX}7`,
      JSON.stringify({ [date]: request }),
    );
    const store = await withPendingHydration('user_7', (value) => value);
    expect(store.entries[date]).toBeUndefined();
    expect(store.confirmed).toContain(request.key);
    expect(sessionStorage.getItem(`${HYDRATION_PENDING_SESSION_PREFIX}7`)).toBeNull();
  });

  it('refuses the operation when no shared lock is available', async () => {
    const task = vi.fn();
    const coordinator = createCrossContextCoordinator({
      storage: null,
      nativeLocks: null,
      requireSharedLock: true,
    });
    await expect(coordinator.run('synthetic', task)).rejects.toThrow();
    expect(task).not.toHaveBeenCalled();
  });

  it('does not prepare a hydration request without IndexedDB', async () => {
    vi.stubGlobal('indexedDB', undefined);
    const task = vi.fn();
    await expect(withPendingHydration('user_7', task)).rejects.toThrow();
    expect(task).not.toHaveBeenCalled();
  });

  it('waits for a stale storage snapshot before using the pending request', async () => {
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [request];
      writePendingHydration('user_7', store);
    });
    const original = Storage.prototype.getItem;
    let stale = true;
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (
      this: Storage,
      key,
    ) {
      if (key === pendingStorageKey('user_7') && stale) {
        stale = false;
        return null;
      }
      return original.call(this, key);
    });
    const task = vi.fn((store) => store.entries[date]?.[0]?.key);
    try {
      await expect(withPendingHydration('user_7', task)).resolves.toBe(request.key);
      expect(stale).toBe(false);
      expect(task).toHaveBeenCalledTimes(1);
    } finally {
      getItem.mockRestore();
    }
  });

  it('clears the coordination revision when the account data is removed', async () => {
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [request];
      writePendingHydration('user_7', store);
    });
    clearSensitiveUserScopedStorage();
    expect(localStorage.getItem(pendingStorageKey('user_7'))).toBeNull();
    const next = await withPendingHydration('user_7', (store) => store);
    expect(next.entries).toEqual({});
  });

  it('retains the current account revision during account cleanup', async () => {
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [request];
      writePendingHydration('user_7', store);
    });
    const key = pendingStorageKey('user_7');
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [{ ...request, key: 'newer-key' }];
      writePendingHydration('user_7', store);
    });
    await resetHydrationFences(key);
    const original = Storage.prototype.getItem;
    let stale = true;
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (
      this: Storage,
      name,
    ) {
      if (name === key && stale) {
        stale = false;
        return null;
      }
      return original.call(this, name);
    });
    try {
      const current = await withPendingHydration('user_7', (store) => store);
      expect(current.entries[date]?.[0]?.key).toBe('newer-key');
      expect(stale).toBe(false);
    } finally {
      getItem.mockRestore();
    }
  });

  it('does not restore removed account data from a stale tab after logout', async () => {
    await withPendingHydration('user_7', (store) => {
      store.entries[date] = [request];
      writePendingHydration('user_7', store);
    });
    const key = pendingStorageKey('user_7');
    const oldValue = localStorage.getItem(key);
    clearSensitiveUserScopedStorage();
    await resetHydrationFences(null);
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const open = indexedDB.open('fit_hydration_coordination_v1');
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    const keys = await new Promise<IDBValidKey[]>((resolve, reject) => {
      const transaction = database.transaction('revisions');
      const read = transaction.objectStore('revisions').getAllKeys();
      read.onsuccess = () => resolve(read.result);
      read.onerror = () => reject(read.error);
    });
    database.close();
    expect(keys).toEqual(['__epoch__']);
    const original = Storage.prototype.getItem;
    let staleReads = 2;
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (
      this: Storage,
      name,
    ) {
      if (name === key && staleReads > 0) {
        staleReads -= 1;
        return oldValue;
      }
      return original.call(this, name);
    });
    try {
      const current = await withPendingHydration('user_7', (store) => store);
      expect(current.entries).toEqual({});
      expect(staleReads).toBe(0);
    } finally {
      getItem.mockRestore();
    }
  });

  it('preserves only the selected account when clearing user data', async () => {
    for (const scope of ['user_7', 'user_8']) {
      await withPendingHydration(scope, (store) => {
        store.entries[date] = [{ ...request, key: scope }];
        writePendingHydration(scope, store);
      });
    }
    clearSensitiveUserScopedStorage(7);
    const kept = await withPendingHydration('user_7', (store) => store);
    const removed = await withPendingHydration('user_8', (store) => store);
    expect(kept.entries[date]?.[0]?.key).toBe('user_7');
    expect(removed.entries).toEqual({});
  });

  it('recovers a saved request if the coordination transaction aborts', async () => {
    await withPendingHydration('user_7', (store) => store);
    const put = vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementationOnce(() => {
      throw new DOMException('Storage failed', 'UnknownError');
    });
    try {
      await expect(
        withPendingHydration('user_7', (store) => {
          store.entries[date] = [request];
          writePendingHydration('user_7', store);
        }),
      ).rejects.toThrow();
    } finally {
      put.mockRestore();
    }
    const recovered = await withPendingHydration('user_7', (store) => store);
    expect(recovered.entries[date]?.[0]?.key).toBe(request.key);
  });

  it('recovers an interrupted write after cleanup retains the same account', async () => {
    await withPendingHydration('user_7', (store) => store);
    const put = vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementationOnce(() => {
      throw new DOMException('Storage failed', 'UnknownError');
    });
    try {
      await expect(
        withPendingHydration('user_7', (store) => {
          store.entries[date] = [request];
          writePendingHydration('user_7', store);
        }),
      ).rejects.toThrow();
    } finally {
      put.mockRestore();
    }
    await resetHydrationFences(pendingStorageKey('user_7'));
    const recovered = await withPendingHydration('user_7', (store) => store);
    expect(recovered.entries[date]?.[0]?.key).toBe(request.key);
  });
});
