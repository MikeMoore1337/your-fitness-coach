import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  demoReturnPathFromLogin,
  focusedContextReturn,
  NavigationProvider,
} from '../../../../src/shared/navigation/router';

describe('NavigationProvider Telegram BackButton', () => {
  const callbacks = new Set<() => void>();
  const backButton = {
    show: vi.fn(),
    hide: vi.fn(),
    setText: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    onClick: vi.fn((callback: () => void) => callbacks.add(callback)),
    offClick: vi.fn((callback: () => void) => callbacks.delete(callback)),
  };

  beforeEach(() => {
    callbacks.clear();
    Object.values(backButton).forEach((mock) => mock.mockClear());
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    window.history.replaceState({}, '', '/app?workout_id=43&comment_id=7&workout_exercise_id=55');
    window.Telegram = { WebApp: { initData: 'signed', BackButton: backButton } };
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    delete window.Telegram;
    window.history.replaceState({}, '', '/');
  });

  it('показывает BackButton во вложенном feedback-контексте и возвращает в Прогресс', async () => {
    render(
      <NavigationProvider>
        <div>content</div>
      </NavigationProvider>,
    );

    expect(backButton.show).toHaveBeenCalledOnce();
    expect(callbacks.size).toBe(1);
    act(() => callbacks.values().next().value?.());

    await waitFor(() => expect(window.location.href).toMatch(/\/app\?section=progress$/));
    expect(backButton.hide).toHaveBeenCalled();
  });

  it('скрывает native BackButton на root active workout с видимым in-page back', () => {
    window.history.replaceState({}, '', '/app?section=today');

    render(
      <NavigationProvider>
        <button type="button">К сводке</button>
      </NavigationProvider>,
    );

    expect(screen.getByRole('button', { name: 'К сводке' })).toBeInTheDocument();
    expect(backButton.hide).toHaveBeenCalled();
    expect(backButton.show).not.toHaveBeenCalled();
    expect(callbacks.size).toBe(0);
  });

  it('возвращает из тренировки в точную ревизию программы и отклоняет внешний return_to', async () => {
    const returnTo = '/app?section=programs&program_history=77&program_revision=4';
    window.history.replaceState(
      {},
      '',
      `/app?section=progress&workout_id=943&program_history=77&program_revision=4&return_to=${encodeURIComponent(returnTo)}`,
    );

    render(
      <NavigationProvider>
        <div>content</div>
      </NavigationProvider>,
    );
    act(() => callbacks.values().next().value?.());

    await waitFor(() => expect(window.location.href).toContain(returnTo));
    expect(
      focusedContextReturn(
        `?workout_id=943&program_history=77&program_revision=4&return_to=${encodeURIComponent('https://example.com/steal')}`,
      ),
    ).toBe('/app?section=progress');
    expect(
      focusedContextReturn(
        `?section=programs&workout_id=43&return_to=${encodeURIComponent('/app?section=today')}`,
      ),
    ).toBe('/app?section=today');
    expect(focusedContextReturn('?section=programs&workout_id=43')).toBe('/app?section=programs');
  });

  it('возвращает из публичного demo на landing без запуска защищённого TMA auth', async () => {
    window.history.replaceState({}, '', '/demo?scenario=trainer');

    render(
      <NavigationProvider>
        <div>demo</div>
      </NavigationProvider>,
    );

    expect(backButton.show).toHaveBeenCalledOnce();
    act(() => callbacks.values().next().value?.());

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(window.location.pathname).not.toBe('/app');
  });

  it('возвращает из demo auth handoff в allowlisted scenario', async () => {
    window.history.replaceState({}, '', '/login?next=%2Fapp&from=demo&scenario=nutrition');

    render(
      <NavigationProvider>
        <div>login</div>
      </NavigationProvider>,
    );
    act(() => callbacks.values().next().value?.());

    await waitFor(() => expect(window.location.href).toMatch(/\/demo\?scenario=nutrition$/));
    expect(demoReturnPathFromLogin('?from=demo&scenario=trainer&cabinet=1&section=trainer')).toBe(
      '/demo?cabinet=1&scenario=trainer&section=trainer',
    );
    expect(demoReturnPathFromLogin('?from=demo&scenario=nutrition&cabinet=1&section=trainer')).toBe(
      '/demo?cabinet=1&scenario=nutrition&section=today',
    );
    expect(
      demoReturnPathFromLogin('?from=demo&scenario=self_training&cabinet=1&section=plan'),
    ).toBe('/demo?cabinet=1&scenario=self_training&section=plan');
    expect(
      demoReturnPathFromLogin('?from=demo&scenario=self_training&cabinet=1&section=profile'),
    ).toBe('/demo?cabinet=1&scenario=self_training&section=profile');
    expect(demoReturnPathFromLogin('?from=demo&scenario=https://evil.example')).toBeNull();
  });
});
