import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { glassProps } from '../../../../src/shared/ui/Glass';
import { GlassInteractions } from '../../../../src/shared/ui/GlassInteractions';
import { Button } from '../../../../src/shared/ui/common';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function tracking(matches = true) {
  const media = { matches, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => media),
  );
  const callbacks = new Map<number, FrameRequestCallback>();
  let sequence = 0;
  const raf = vi.fn((callback: FrameRequestCallback) => {
    callbacks.set(++sequence, callback);
    return sequence;
  });
  vi.stubGlobal('requestAnimationFrame', raf);
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn((id: number) => callbacks.delete(id)),
  );
  return {
    raf,
    media,
    flush: () => {
      const pending = [...callbacks.values()];
      callbacks.clear();
      pending.forEach((callback) => callback(16));
    },
    pending: () => callbacks.size,
  };
}

function move(element: HTMLElement, pointerType = 'mouse') {
  const event = new Event('pointermove', { bubbles: true });
  Object.defineProperties(event, {
    clientX: { value: 75 },
    clientY: { value: 20 },
    pointerType: { value: pointerType },
  });
  element.dispatchEvent(event);
}

it('coalesces pointer movement and cancels pending work on unmount', () => {
  const clock = tracking();
  const { unmount } = render(
    <>
      <GlassInteractions />
      <button {...glassProps('clear', true)}>Control</button>
    </>,
  );
  const button = screen.getByRole('button');
  vi.spyOn(button, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 0, 100, 40));
  for (let index = 0; index < 20; index++) move(button);
  expect(clock.raf).toHaveBeenCalledTimes(1);
  clock.flush();
  expect(button.style.getPropertyValue('--glass-x')).toBe('57.5%');
  expect(clock.pending()).toBe(0);
  move(button);
  unmount();
  expect(clock.pending()).toBe(0);
  expect(button.style.getPropertyValue('--glass-x')).toBe('');
});

it('does not track touch, disabled controls or reduced-motion interaction', () => {
  const clock = tracking();
  render(
    <>
      <GlassInteractions />
      <button {...glassProps('regular', true)}>Control</button>
    </>,
  );
  const button = screen.getByRole('button');
  move(button, 'touch');
  expect(clock.pending()).toBe(0);
  button.setAttribute('disabled', '');
  move(button);
  expect(clock.pending()).toBe(0);
  button.removeAttribute('disabled');
  clock.media.matches = false;
  move(button);
  expect(clock.pending()).toBe(0);
});

it('keeps native button semantics and forwards actions without a wrapper', () => {
  const click = vi.fn();
  const { rerender } = render(
    <Button glass="regular" onClick={click}>
      Сохранить
    </Button>,
  );
  const button = screen.getByRole('button', { name: 'Сохранить' });
  fireEvent.click(button);
  expect(click).toHaveBeenCalledOnce();
  expect(button).toHaveAttribute('data-glass-variant', 'regular');
  rerender(
    <Button glass="regular" disabled onClick={click}>
      Сохранить
    </Button>,
  );
  fireEvent.click(button);
  expect(click).toHaveBeenCalledOnce();
});
