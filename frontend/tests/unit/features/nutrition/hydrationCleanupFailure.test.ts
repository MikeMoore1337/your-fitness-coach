import { IDBFactory, IDBObjectStore } from 'fake-indexeddb';
import { expect, it, vi } from 'vitest';

it.each(['clear', 'put'] as const)(
  'does not restore stale pending data if cleanup %s fails in another context',
  async (method) => {
    vi.resetModules();
    vi.stubGlobal('indexedDB', new IDBFactory());
    localStorage.clear();
    const first = await import('../../../../src/features/nutrition/hydrationPending');
    const fence = await import('../../../../src/shared/browser/hydrationFence');
    const date = '2026-09-01';
    const key = first.pendingStorageKey('user_7');
    await first.withPendingHydration('user_7', (store) => {
      store.entries[date] = [
        {
          date,
          volume: 250,
          kind: 'water',
          source: 'quick_preset',
          key: 'old-key',
          uncertain: true,
        },
      ];
      first.writePendingHydration('user_7', store);
    });
    const oldValue = localStorage.getItem(key);
    localStorage.removeItem(key);
    const failure = vi.spyOn(IDBObjectStore.prototype, method).mockImplementationOnce(() => {
      throw new DOMException('Storage failed', 'UnknownError');
    });
    try {
      await expect(fence.resetHydrationFences(null)).rejects.toThrow();
    } finally {
      failure.mockRestore();
    }
    vi.resetModules();
    const other = await import('../../../../src/features/nutrition/hydrationPending');
    const original = Storage.prototype.getItem;
    let staleReads = 2;
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (
      this: Storage,
      name,
    ) {
      if (name === key && staleReads-- > 0) return oldValue;
      return original.call(this, name);
    });
    try {
      const current = await other.withPendingHydration('user_7', (store) => store);
      expect(current.entries).toEqual({});
    } finally {
      getItem.mockRestore();
      vi.unstubAllGlobals();
    }
  },
);
