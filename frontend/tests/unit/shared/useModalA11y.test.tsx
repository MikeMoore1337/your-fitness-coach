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
    expect(scrollTo).toHaveBeenCalledWith(12, 240);
  });

  it('sends Escape only to the top dialog and keeps its parent locked', () => {
    const parentClose = vi.fn();
    const childClose = vi.fn();
    const view = render(<Modal name="Редактор" onClose={parentClose} />);
    screen.getByRole('button', { name: 'Редактор' }).focus();
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
    expect(screen.getByRole('button', { name: 'Редактор' })).toHaveFocus();
    expect(document.body.style.position).toBe('fixed');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(parentClose).toHaveBeenCalledOnce();
  });
});
