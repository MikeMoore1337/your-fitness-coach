import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useMotionPresence } from '../../../../src/shared/ui/useMotionPresence';

const options = {
  closingAnimationName: 'exit',
  openingAnimationName: 'enter',
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('useMotionPresence lifetime', () => {
  it('finishes the closing animation only after the existing fallback duration', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useMotionPresence(options));

    expect(result.current.phase).toBe('closed');
    act(() => result.current.show());
    expect(result.current.phase).toBe('opening');
    act(() => result.current.hide());
    expect(result.current.phase).toBe('closing');

    act(() => vi.advanceTimersByTime(259));
    expect(result.current.phase).toBe('closing');
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.phase).toBe('closed');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears the closing fallback and ignores late callbacks after unmount', () => {
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => useMotionPresence(options));
    act(() => result.current.show());
    act(() => result.current.hide());
    const { hide, show, onAnimationEnd } = result.current;
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(() => {
      hide();
      show();
      onAnimationEnd({ animationName: 'exit' } as never);
      vi.runAllTimers();
    }).not.toThrow();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('restores presence when reopened during an in-flight closing transition', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useMotionPresence(options));
    act(() => result.current.show());
    act(() => result.current.hide());
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    act(() => result.current.show());
    expect(result.current.phase).toBe('opening');
    expect(vi.getTimerCount()).toBe(0);
  });
});
