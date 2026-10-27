import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useScreenWakeLock } from '../../../../src/features/workouts/useScreenWakeLock';

const originalWakeLockDescriptor = Object.getOwnPropertyDescriptor(navigator, 'wakeLock');
const originalVisibilityDescriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState');

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (originalWakeLockDescriptor) {
    Object.defineProperty(navigator, 'wakeLock', originalWakeLockDescriptor);
  } else {
    Reflect.deleteProperty(navigator, 'wakeLock');
  }
  if (originalVisibilityDescriptor) {
    Object.defineProperty(document, 'visibilityState', originalVisibilityDescriptor);
  } else {
    Reflect.deleteProperty(document, 'visibilityState');
  }
});

describe('useScreenWakeLock', () => {
  it('requests only for a visible workout and reacquires after returning to the foreground', async () => {
    let visibility: Document['visibilityState'] = 'visible';
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibility,
    });
    const first = {
      released: false,
      release: vi.fn(async () => {
        first.released = true;
      }),
      addEventListener: vi.fn(),
    };
    const second = {
      released: false,
      release: vi.fn(async () => {
        second.released = true;
      }),
      addEventListener: vi.fn(),
    };
    const request = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: { request },
    });

    const hook = renderHook(({ enabled }) => useScreenWakeLock(enabled), {
      initialProps: { enabled: true },
    });
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));

    visibility = 'hidden';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitFor(() => expect(first.release).toHaveBeenCalledOnce());

    visibility = 'visible';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    hook.rerender({ enabled: false });
    await waitFor(() => expect(second.release).toHaveBeenCalledOnce());
    hook.unmount();
  });

  it('degrades silently when the browser denies the lock', async () => {
    const request = vi.fn().mockRejectedValue(new Error('NotAllowedError'));
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: { request },
    });

    const hook = renderHook(() => useScreenWakeLock(true));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    hook.unmount();
  });

  it('does nothing when the browser does not expose Screen Wake Lock', () => {
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: undefined,
    });

    const hook = renderHook(() => useScreenWakeLock(true));
    hook.unmount();
  });

  it('retries a stale request after the tab returns before the first request settles', async () => {
    let visibility: Document['visibilityState'] = 'visible';
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibility,
    });
    const first = {
      released: false,
      release: vi.fn(async () => {
        first.released = true;
      }),
      addEventListener: vi.fn(),
    };
    const second = {
      released: false,
      release: vi.fn(async () => {
        second.released = true;
      }),
      addEventListener: vi.fn(),
    };
    let resolveFirst!: (sentinel: typeof first) => void;
    const firstRequest = new Promise<typeof first>((resolve) => {
      resolveFirst = resolve;
    });
    const request = vi.fn().mockReturnValueOnce(firstRequest).mockResolvedValueOnce(second);
    Object.defineProperty(navigator, 'wakeLock', {
      configurable: true,
      value: { request },
    });

    const hook = renderHook(() => useScreenWakeLock(true));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));

    visibility = 'hidden';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    visibility = 'visible';
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(request).toHaveBeenCalledTimes(1);

    act(() => resolveFirst(first));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(first.release).toHaveBeenCalledOnce();
    hook.unmount();
  });
});
