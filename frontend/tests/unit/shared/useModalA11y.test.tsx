import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useDocumentScrollLock, useModalA11y } from '../../../src/shared/ui/useModalA11y';

function Lock({ open }: { open: boolean }) {
  useDocumentScrollLock(open);
  return null;
}

function Modal({ name, onClose }: { name: string; onClose: () => void }) {
  const ref = useModalA11y<HTMLDivElement>(true, onClose);
  return (
    <div ref={ref} role="dialog" aria-label={name} tabIndex={-1}>
      <button>{name}</button>
    </div>
  );
}

function ParentModal() {
  const ref = useModalA11y<HTMLDivElement>(true, () => undefined, '[data-initial]');
  return (
    <div ref={ref} role="dialog" aria-label="Родительское окно" tabIndex={-1}>
      <button data-initial>Первое действие</button>
      <button>Открыть подтверждение</button>
    </div>
  );
}

describe('useDocumentScrollLock', () => {
  afterEach(() => {
    cleanup();
    document.documentElement.removeAttribute('style');
    document.body.removeAttribute('style');
    vi.restoreAllMocks();
  });

  it('locks the document for nested overlays and restores exact scroll position last', () => {
    Object.defineProperty(window, 'scrollX', { configurable: true, value: 12 });
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 240 });
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    document.body.style.overflow = 'auto';

    const view = render(
      <>
        <Lock open />
        <Lock open />
      </>,
    );

    expect(document.documentElement.style.overflow).toBe('hidden');
    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-240px');

    view.rerender(<Lock open />);
    expect(document.body.style.position).toBe('fixed');
    expect(scrollTo).not.toHaveBeenCalled();

    view.rerender(<Lock open={false} />);
    expect(document.documentElement.style.overflow).toBe('');
    expect(document.body.style.overflow).toBe('auto');
    expect(document.body.style.position).toBe('');
    expect(scrollTo).toHaveBeenCalledWith({ left: 12, top: 240, behavior: 'instant' });
  });

  it('sends Escape only to the top dialog and keeps its parent locked', () => {
    const parentClose = vi.fn();
    const childClose = vi.fn();
    const view = render(<Modal name="Редактор" onClose={parentClose} />);
    const parentTrigger = screen.getByRole('button', { name: 'Редактор' });
    parentTrigger.focus();
    const restoreFocus = vi.spyOn(parentTrigger, 'focus');
    view.rerender(
      <>
        <Modal name="Редактор" onClose={parentClose} />
        <Modal name="Поиск" onClose={childClose} />
      </>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(childClose).toHaveBeenCalledOnce();
    expect(parentClose).not.toHaveBeenCalled();
    view.rerender(<Modal name="Редактор" onClose={parentClose} />);
    expect(restoreFocus).toHaveBeenCalledWith({ preventScroll: true });
    expect(screen.getByRole('button', { name: 'Редактор' })).toHaveFocus();
    expect(document.body.style.position).toBe('fixed');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(parentClose).toHaveBeenCalledOnce();
  });

  it('does not let a delayed parent frame steal focus from a nested dialog', () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const view = render(<ParentModal />);
    screen.getByRole('button', { name: 'Открыть подтверждение' }).focus();
    view.rerender(
      <>
        <ParentModal />
        <Modal name="Подтверждение" onClose={() => undefined} />
      </>,
    );
    const child = screen.getByRole('button', { name: 'Подтверждение' });
    child.focus();

    frames[0]!(0);

    expect(child).toHaveFocus();
  });

  it('moves focus to the preferred control when a dialog first opens', () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const view = render(<button>Внешнее действие</button>);
    screen.getByRole('button', { name: 'Внешнее действие' }).focus();
    view.rerender(
      <>
        <button>Внешнее действие</button>
        <ParentModal />
      </>,
    );

    frames[0]!(0);

    expect(screen.getByRole('button', { name: 'Первое действие' })).toHaveFocus();
  });

  it('keeps the restored trigger when the initial parent frame runs late', () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const view = render(<ParentModal />);
    const trigger = screen.getByRole('button', { name: 'Открыть подтверждение' });
    trigger.focus();
    view.rerender(
      <>
        <ParentModal />
        <Modal name="Подтверждение" onClose={() => undefined} />
      </>,
    );
    screen.getByRole('button', { name: 'Подтверждение' }).focus();
    view.rerender(<ParentModal />);
    expect(trigger).toHaveFocus();

    frames[0]!(0);

    expect(trigger).toHaveFocus();
  });
});
