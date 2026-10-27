import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useQuickAddReturn } from '../../../src/app/useQuickAddReturn';

const location = vi.hoisted(() => ({
  path: '/app',
  search: '?section=today&wellbeing=1',
  navigate: vi.fn(),
}));
vi.mock('../../../src/shared/navigation/router', () => ({ useNavigation: () => location }));

let trigger: HTMLButtonElement;
let frames: FrameRequestCallback[];
const flushFrames = () => {
  for (let frame = 0; frame < 2; frame += 1) {
    const callbacks = frames.splice(0);
    callbacks.forEach((callback) => callback(frame));
  }
};

beforeEach(() => {
  location.path = '/app';
  location.search = '?section=today&wellbeing=1';
  location.navigate.mockClear();
  frames = [];
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => frames.push(callback));
  trigger = document.createElement('button');
  trigger.dataset.testid = 'quick-add-trigger';
  document.body.append(trigger);
});
afterEach(() => {
  cleanup();
  trigger.remove();
  delete document.documentElement.dataset.yfcKeyboard;
  vi.restoreAllMocks();
});

describe('quick form return focus', () => {
  it('waits for the destination route commit even when rendering outlasts two frames', () => {
    const { result, rerender } = renderHook(() => useQuickAddReturn('/app?section=today'));
    act(() => result.current());
    expect(location.navigate).toHaveBeenCalledWith('/app?section=today', true);
    act(flushFrames);
    expect(trigger).not.toHaveFocus();
    location.search = '?section=today';
    rerender();
    expect(trigger).toHaveFocus();
  });

  it('waits for a temporarily hidden mobile dock to become focusable', () => {
    trigger.style.visibility = 'hidden';
    const { result, rerender } = renderHook(() => useQuickAddReturn('/app?section=today'));
    act(() => result.current());
    location.search = '?section=today';
    rerender();
    act(flushFrames);
    expect(trigger).not.toHaveFocus();
    trigger.style.visibility = 'visible';
    act(flushFrames);
    expect(trigger).toHaveFocus();
  });

  it('disconnects pending keyboard restoration when the form owner unmounts', async () => {
    trigger.style.visibility = 'hidden';
    const { result, rerender, unmount } = renderHook(() => useQuickAddReturn('/app?section=today'));
    act(() => result.current());
    location.search = '?section=today';
    rerender();
    unmount();
    trigger.style.visibility = 'visible';
    document.documentElement.dataset.yfcKeyboard = 'hidden';
    await act(() => Promise.resolve());
    expect(trigger).not.toHaveFocus();
  });

  it('cancels pending focus if another route replaces the requested return', async () => {
    trigger.style.visibility = 'hidden';
    const { result, rerender } = renderHook(() => useQuickAddReturn('/app?section=today'));
    act(() => result.current());
    location.search = '?section=today';
    rerender();
    location.search = '?section=nutrition';
    rerender();
    trigger.style.visibility = 'visible';
    document.documentElement.dataset.yfcKeyboard = 'hidden';
    await act(() => Promise.resolve());
    expect(trigger).not.toHaveFocus();
  });
});
