import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PwaProvider, usePwa } from '../../../src/shared/pwa/PwaProvider';
import { PWA_INSTALL_STATE_KEY, PWA_SAFE_UPDATE_EVENT } from '../../../src/shared/pwa/pwaRuntime';

function Probe() {
  const pwa = usePwa();
  return (
    <>
      <output data-testid="install-visible">{String(pwa.shouldShowInstallPrompt)}</output>
      <output data-testid="update-blocked">{String(pwa.updateBlockedByWorkout)}</output>
    </>
  );
}

const originalNavigatorProperties = new Map<PropertyKey, PropertyDescriptor | undefined>();

function overrideNavigatorProperty(property: PropertyKey, value: unknown): void {
  if (!originalNavigatorProperties.has(property)) {
    originalNavigatorProperties.set(property, Object.getOwnPropertyDescriptor(navigator, property));
  }
  Object.defineProperty(navigator, property, { configurable: true, value });
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  delete window.Telegram;
  for (const [property, descriptor] of originalNavigatorProperties) {
    if (descriptor) Object.defineProperty(navigator, property, descriptor);
    else delete (navigator as unknown as Record<PropertyKey, unknown>)[property];
  }
  originalNavigatorProperties.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe('PwaProvider', () => {
  it('captures the browser install option but does not expose it before product value', async () => {
    render(
      <PwaProvider>
        <Probe />
      </PwaProvider>,
    );

    const prompt = {
      prompt: vi.fn().mockResolvedValue(undefined),
      userChoice: Promise.resolve({ outcome: 'accepted' as const, platform: 'web' }),
    };
    const event = new Event('beforeinstallprompt');
    Object.defineProperty(event, 'prompt', { value: prompt.prompt });
    Object.defineProperty(event, 'userChoice', { value: prompt.userChoice });
    window.dispatchEvent(event);

    await waitFor(() => expect(screen.getByTestId('install-visible')).toHaveTextContent('false'));

    localStorage.setItem(
      PWA_INSTALL_STATE_KEY,
      JSON.stringify({ appOpenCount: 2, qualified: true, dismissedUntil: 0 }),
    );
    cleanup();
    render(
      <PwaProvider>
        <Probe />
      </PwaProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('install-visible')).toHaveTextContent('false'));
    window.dispatchEvent(event);
    await waitFor(() => expect(screen.getByTestId('install-visible')).toHaveTextContent('true'));
  });

  it('does not offer Safari install instructions inside an iOS Telegram Mini App', async () => {
    localStorage.setItem(
      PWA_INSTALL_STATE_KEY,
      JSON.stringify({ appOpenCount: 2, qualified: true, dismissedUntil: 0 }),
    );
    overrideNavigatorProperty('userAgent', 'Mozilla/5.0 (iPhone)');
    overrideNavigatorProperty('platform', 'iPhone');
    overrideNavigatorProperty('maxTouchPoints', 0);
    window.Telegram = { WebApp: { initData: 'signed-init-data' } };

    render(
      <PwaProvider>
        <Probe />
      </PwaProvider>,
    );

    expect(screen.getByTestId('install-visible')).toHaveTextContent('false');
    expect(screen.queryByText('Быстрый возврат к тренировке')).not.toBeInTheDocument();
  });

  it('blocks a waiting update while active workout data exists and applies it after safe completion', async () => {
    const postMessage = vi.fn();
    const waiting = { postMessage };
    const registration = {
      waiting,
      installing: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      update: vi.fn().mockResolvedValue(undefined),
    };
    overrideNavigatorProperty('serviceWorker', {
      controller: {},
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      register: vi.fn().mockResolvedValue(registration),
    });
    localStorage.setItem(
      'fit_active_workout_v1_user_7_workout_42',
      JSON.stringify({ workout_snapshot: { status: 'in_progress' }, queue: [] }),
    );

    render(
      <PwaProvider>
        <Probe />
      </PwaProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('update-blocked')).toHaveTextContent('true');
      expect(screen.getByRole('button', { name: 'После тренировки' })).toBeDisabled();
    });
    expect(postMessage).not.toHaveBeenCalled();

    localStorage.removeItem('fit_active_workout_v1_user_7_workout_42');
    window.dispatchEvent(new Event(PWA_SAFE_UPDATE_EVENT));
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith({ type: 'YFC_PWA_SKIP_WAITING' }));
  });
});
