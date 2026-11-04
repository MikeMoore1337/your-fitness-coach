import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { QuickAddSheet } from '../../../src/app/QuickAddSheet';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
