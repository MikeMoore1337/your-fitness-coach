import { beforeEach, describe, expect, it } from 'vitest';
import {
  AUTHENTICATED_USER_ID_STORAGE_KEY,
  USER_SCOPED_PERSISTENT_STORAGE_REGISTRY,
  activeWorkoutPointerStorageKey,
  activeWorkoutQueueStorageKey,
  activeWorkoutRestStorageKey,
  clearSensitiveUserScopedStorage,
} from '../../../src/shared/userScopedStorage';

describe('user-scoped browser storage registry', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('cleans every current and legacy sensitive domain while preserving global preferences', () => {
    const sensitiveKeys = USER_SCOPED_PERSISTENT_STORAGE_REGISTRY.flatMap(({ prefixes }) =>
      prefixes.map((prefix) => `${prefix}fixture`),
    );
    for (const key of sensitiveKeys) localStorage.setItem(key, '{"private":true}');
    localStorage.setItem('fit_access_token', 'legacy-access-token');
    localStorage.setItem('fit_refresh_token', 'legacy-refresh-token');
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, '7');
    localStorage.setItem('app-theme', 'dark');
    localStorage.setItem('landing-theme', 'light');
    localStorage.setItem('fit_telegram_link_prompt_dismissed_7', 'true');

    clearSensitiveUserScopedStorage();
    clearSensitiveUserScopedStorage();

    for (const key of sensitiveKeys) expect(localStorage.getItem(key)).toBeNull();
    expect(localStorage.getItem('fit_access_token')).toBeNull();
    expect(localStorage.getItem('fit_refresh_token')).toBeNull();
    expect(sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem('app-theme')).toBe('dark');
    expect(localStorage.getItem('landing-theme')).toBe('light');
    expect(localStorage.getItem('fit_telegram_link_prompt_dismissed_7')).toBe('true');
  });

  it("retains only the verified user's scoped workout when explicitly requested", () => {
    const kept = [
      `${activeWorkoutQueueStorageKey(7, 42)}:v3`,
      activeWorkoutPointerStorageKey(7),
      activeWorkoutRestStorageKey(7, 42),
    ];
    const removed = [
      `${activeWorkoutQueueStorageKey(70, 42)}:v3`,
      activeWorkoutPointerStorageKey(8),
      'fit_workout_pending_201',
      'fit_profile_draft_7',
    ];
    for (const key of [...kept, ...removed]) localStorage.setItem(key, 'synthetic');

    clearSensitiveUserScopedStorage(7);

    for (const key of kept) expect(localStorage.getItem(key)).toBe('synthetic');
    for (const key of removed) expect(localStorage.getItem(key)).toBeNull();
  });

  it('retains only scoped workouts with pending mutations on session expiry', () => {
    const key7 = `${activeWorkoutQueueStorageKey(7, 42)}:v3`;
    const legacy7 = activeWorkoutQueueStorageKey(7, 42);
    const key8 = `${activeWorkoutQueueStorageKey(8, 43)}:v3`;
    const empty = `${activeWorkoutQueueStorageKey(7, 44)}:v3`;
    localStorage.setItem(
      key7,
      JSON.stringify({
        schema_version: 3,
        user_id: 7,
        workout_id: 42,
        queue: [{ mutation_id: 'synthetic' }],
      }),
    );
    localStorage.setItem(
      legacy7,
      JSON.stringify({ schema_version: 1, user_id: 7, workout_id: 42, queue: [] }),
    );
    localStorage.setItem(
      key8,
      JSON.stringify({
        schema_version: 3,
        user_id: 8,
        workout_id: 43,
        queue: [{ mutation_id: 'synthetic' }],
      }),
    );
    localStorage.setItem(
      empty,
      JSON.stringify({ schema_version: 3, user_id: 7, workout_id: 44, queue: [] }),
    );
    localStorage.setItem(activeWorkoutPointerStorageKey(7), '42');
    localStorage.setItem(activeWorkoutRestStorageKey(7, 42), 'private rest');
    localStorage.setItem('fit_food_draft_7', 'private food');
    sessionStorage.setItem(AUTHENTICATED_USER_ID_STORAGE_KEY, '7');

    clearSensitiveUserScopedStorage({ pendingOnly: true, userId: 7 });

    for (const key of [key7, legacy7, activeWorkoutPointerStorageKey(7)]) {
      expect(localStorage.getItem(key)).not.toBeNull();
    }
    for (const key of [key8, empty, activeWorkoutRestStorageKey(7, 42), 'fit_food_draft_7']) {
      expect(localStorage.getItem(key)).toBeNull();
    }
    expect(sessionStorage.getItem(AUTHENTICATED_USER_ID_STORAGE_KEY)).toBeNull();
  });
});
