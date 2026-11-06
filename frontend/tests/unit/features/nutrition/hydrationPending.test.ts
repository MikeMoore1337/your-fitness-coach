import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createCrossContextCoordinator } from '../../../../src/shared/browser/crossContextLock';
import { HYDRATION_PENDING_SESSION_PREFIX } from '../../../../src/shared/userScopedStorage';
import {
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
    localStorage.clear();
    sessionStorage.clear();
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
});
