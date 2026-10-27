import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  hasActiveWorkoutData,
  isIosInstallSurface,
  isPwaStandalone,
  PWA_INSTALL_STATE_KEY,
  readPwaInstallState,
  unregisterPwaServiceWorkers,
  writePwaInstallState,
} from '../../../src/shared/pwa/pwaRuntime';

const originalNavigatorProperties = new Map<PropertyKey, PropertyDescriptor | undefined>();
const originalWindowProperties = new Map<PropertyKey, PropertyDescriptor | undefined>();

function overrideProperty(
  target: object,
  property: PropertyKey,
  value: unknown,
  originals: Map<PropertyKey, PropertyDescriptor | undefined>,
): void {
  if (!originals.has(property))
    originals.set(property, Object.getOwnPropertyDescriptor(target, property));
  Object.defineProperty(target, property, { configurable: true, value });
}

function restoreProperties(
  target: object,
  originals: Map<PropertyKey, PropertyDescriptor | undefined>,
): void {
  for (const [property, descriptor] of originals) {
    if (descriptor) Object.defineProperty(target, property, descriptor);
    else delete (target as Record<PropertyKey, unknown>)[property];
  }
  originals.clear();
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

afterEach(() => {
  restoreProperties(navigator, originalNavigatorProperties);
  restoreProperties(window, originalWindowProperties);
  vi.unstubAllGlobals();
});

describe('PWA runtime state', () => {
  it('bounds and recovers install qualification state without retaining arbitrary fields', () => {
    localStorage.setItem(
      PWA_INSTALL_STATE_KEY,
      JSON.stringify({ appOpenCount: 999, qualified: true, dismissedUntil: -4, private: 'data' }),
    );

    expect(readPwaInstallState()).toEqual({
      appOpenCount: 10,
      qualified: true,
      dismissedUntil: 0,
    });

    expect(writePwaInstallState({ appOpenCount: 2, qualified: true, dismissedUntil: 123 })).toBe(
      true,
    );
    expect(JSON.parse(localStorage.getItem(PWA_INSTALL_STATE_KEY) || '{}')).toEqual({
      appOpenCount: 2,
      qualified: true,
      dismissedUntil: 123,
    });
  });

  it('recognizes standalone display mode and the iOS install surface without a fingerprint', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
    expect(isPwaStandalone()).toBe(true);

    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: false }));
    overrideProperty(navigator, 'standalone', true, originalNavigatorProperties);
    expect(isPwaStandalone()).toBe(true);

    overrideProperty(navigator, 'userAgent', 'Mozilla/5.0 (iPhone)', originalNavigatorProperties);
    overrideProperty(navigator, 'platform', 'iPhone', originalNavigatorProperties);
    overrideProperty(navigator, 'maxTouchPoints', 0, originalNavigatorProperties);
    expect(isIosInstallSurface()).toBe(true);
  });

  it('blocks an update only when canonical active-workout data is present or unreadable', () => {
    expect(hasActiveWorkoutData()).toBe(false);

    localStorage.setItem('fit_unrelated_private_draft_7', '{"private":true}');
    expect(hasActiveWorkoutData()).toBe(false);

    localStorage.setItem(
      'fit_active_workout_v1_user_7_workout_42',
      JSON.stringify({ workout_snapshot: { status: 'in_progress' }, queue: [] }),
    );
    expect(hasActiveWorkoutData()).toBe(true);

    localStorage.removeItem('fit_active_workout_v1_user_7_workout_42');
    localStorage.setItem('fit_active_workout_v1_user_7_workout_42', '{malformed');
    expect(hasActiveWorkoutData()).toBe(true);
  });

  it('unregisters only the YFC root worker and its bounded caches', async () => {
    const yfcUnregister = vi.fn().mockResolvedValue(true);
    const unrelatedUnregister = vi.fn().mockResolvedValue(true);
    const registrations = [
      {
        scope: `${window.location.origin}/`,
        active: { scriptURL: `${window.location.origin}/sw.js` },
        waiting: null,
        installing: null,
        unregister: yfcUnregister,
      },
      {
        scope: `${window.location.origin}/`,
        active: { scriptURL: `${window.location.origin}/other/sw.js` },
        waiting: null,
        installing: null,
        unregister: unrelatedUnregister,
      },
      {
        scope: `${window.location.origin}/other/`,
        active: { scriptURL: `${window.location.origin}/sw.js` },
        waiting: null,
        installing: null,
        unregister: unrelatedUnregister,
      },
    ];
    const getRegistrations = vi.fn().mockResolvedValue(registrations);
    overrideProperty(navigator, 'serviceWorker', { getRegistrations }, originalNavigatorProperties);

    const deleteCache = vi.fn().mockResolvedValue(true);
    overrideProperty(
      window,
      'caches',
      {
        keys: vi.fn().mockResolvedValue(['yfc-pwa-static-v1', 'other-cache']),
        delete: deleteCache,
      },
      originalWindowProperties,
    );

    await unregisterPwaServiceWorkers();

    expect(getRegistrations).toHaveBeenCalledOnce();
    expect(yfcUnregister).toHaveBeenCalledOnce();
    expect(unrelatedUnregister).not.toHaveBeenCalled();
    expect(deleteCache).toHaveBeenCalledWith('yfc-pwa-static-v1');
    expect(deleteCache).toHaveBeenCalledTimes(1);
  });
});
