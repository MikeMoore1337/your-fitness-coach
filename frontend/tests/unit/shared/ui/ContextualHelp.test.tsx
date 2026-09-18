import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ContextualHelp } from '../../../../src/shared/ui/ContextualHelp';

describe('ContextualHelp', () => {
  afterEach(() => {
    cleanup();
    window.history.replaceState({}, '', '/');
    delete window.Telegram;
  });

  it('keeps the short explanation inline and exposes the public article deliberately', () => {
    render(
      <ContextualHelp articlePath="/knowledge/training/repetitions-in-reserve">
        <p>Короткое объяснение</p>
      </ContextualHelp>,
    );

    const summaryText = screen.getByText('Что это?');
    const summary = summaryText.closest('summary') as HTMLElement;
    const details = summary.closest('details') as HTMLDetailsElement;
    expect(summary).toBeInTheDocument();
    expect(details).not.toHaveAttribute('open');
    expect(summary?.querySelector('.disclosure-icon')).toBeInTheDocument();

    fireEvent.click(summary);
    expect(details).toHaveAttribute('open');
    expect(screen.getByText('Короткое объяснение')).toBeVisible();
    expect(screen.getByRole('link', { name: /подробнее на сайте/i })).toHaveAttribute(
      'href',
      '/knowledge/training/repetitions-in-reserve',
    );
    expect(screen.getByRole('link', { name: /подробнее на сайте/i })).toHaveAttribute(
      'target',
      '_blank',
    );
    expect(screen.getByRole('link', { name: /подробнее на сайте/i })).toHaveAttribute(
      'rel',
      'noopener noreferrer',
    );

    summary.focus();
    fireEvent.click(summary);
    expect(details).not.toHaveAttribute('open');
    expect(summary).toHaveFocus();
  });

  it('uses Telegram openLink without changing the current app state', () => {
    const openLink = vi.fn();
    window.history.replaceState({}, '', '/app?section=progress');
    window.Telegram = { WebApp: { initData: 'signed', openLink } };
    render(
      <ContextualHelp articlePath="/knowledge/progress/how-to-read-progress">
        <p>Короткое объяснение</p>
      </ContextualHelp>,
    );

    fireEvent.click(screen.getByText('Что это?'));
    const link = screen.getByRole('link', { name: /подробнее на сайте/i });
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    const dispatched = link.dispatchEvent(click);

    expect(dispatched).toBe(false);
    expect(openLink).toHaveBeenCalledWith(
      'http://localhost:3000/knowledge/progress/how-to-read-progress',
      { try_instant_view: false },
    );
    expect(window.location.href).toBe('http://localhost:3000/app?section=progress');
  });

  it('keeps the native external link fallback when Telegram openLink fails', () => {
    window.Telegram = {
      WebApp: {
        initData: 'signed',
        openLink: vi.fn(() => {
          throw new Error('unsupported');
        }),
      },
    };
    render(
      <ContextualHelp articlePath="/knowledge/training/repetitions-in-reserve">
        <p>Короткое объяснение</p>
      </ContextualHelp>,
    );

    fireEvent.click(screen.getByText('Что это?'));
    const link = screen.getByRole('link', { name: /подробнее на сайте/i });
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    const dispatched = link.dispatchEvent(click);

    expect(dispatched).toBe(true);
    expect(click.defaultPrevented).toBe(false);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
