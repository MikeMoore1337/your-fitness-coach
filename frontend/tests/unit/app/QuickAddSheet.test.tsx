import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QuickAddSheet } from '../../../src/app/QuickAddSheet';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function pointer(target: Element, type: string, y: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX: 200, clientY: y, button: 0 });
  Object.defineProperties(event, { pointerId: { value: 1 }, isPrimary: { value: true } });
  fireEvent(target, event);
}

it('returns incomplete or interrupted drags and closes once after a valid drag', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  const onClose = vi.fn();
  const { container } = render(<QuickAddSheet actions={[]} onClose={onClose} open />);
  const panel = screen.getByRole('dialog');
  const grip = container.querySelector('.app-quick-add-panel__grip')!;
  Object.defineProperty(panel, 'offsetHeight', { value: 300 });
  pointer(grip, 'pointerdown', 100);
  pointer(grip, 'pointermove', 150);
  pointer(grip, 'pointerup', 150);
  expect(onClose).not.toHaveBeenCalled();
  expect(panel.style.transform).toBe('');
  pointer(grip, 'pointerdown', 100);
  pointer(grip, 'pointermove', 340);
  pointer(grip, 'pointercancel', 340);
  expect(onClose).not.toHaveBeenCalled();
  pointer(grip, 'pointerdown', 100);
  pointer(grip, 'pointermove', 340);
  fireEvent(window, new Event('resize'));
  pointer(grip, 'pointerup', 340);
  expect(onClose).not.toHaveBeenCalled();
  pointer(grip, 'pointerdown', 100);
  pointer(grip, 'pointermove', 340);
  pointer(grip, 'pointerup', 340);
  expect(onClose).toHaveBeenCalledOnce();
});

it.each(['another control', 'no active control'])(
  'restores quick-add focus without overriding %s',
  (focusState) => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });

    const content = (open: boolean) => (
      <div>
        <button className="app-quick-add-trigger">Добавить</button>
        <button>Другое меню</button>
        <QuickAddSheet actions={[]} onClose={() => undefined} open={open} />
      </div>
    );
    const view = render(content(false));
    const trigger = screen.getByRole('button', { name: 'Добавить' });
    trigger.focus();
    view.rerender(content(true));
    screen.getByRole('button', { name: 'Закрыть быстрые действия' }).focus();
    view.rerender(content(false));

    const other = screen.getByRole('button', { name: 'Другое меню' });
    if (focusState === 'another control') other.focus();
    else trigger.blur();
    frames.at(-1)?.(0);
    expect(focusState === 'another control' ? other : trigger).toHaveFocus();
  },
);
