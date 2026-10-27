import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WebPushSettings } from '../../../../src/features/account/WebPushSettings';
import {
  getExistingWebPushSubscription,
  subscribeToWebPush,
  webPushPermission,
} from '../../../../src/shared/notifications/webPush';
import { isTelegramSurface } from '../../../../src/shared/pwa/pwaRuntime';
import { FeedbackProvider } from '../../../../src/shared/ui/FeedbackProvider';

vi.mock('../../../../src/shared/notifications/webPush', () => ({
  getExistingWebPushSubscription: vi.fn().mockResolvedValue(null),
  revokeWebPushSubscription: vi.fn().mockResolvedValue(undefined),
  subscribeToWebPush: vi.fn().mockResolvedValue({
    endpoint: 'https://fcm.googleapis.com/fcm/send/test',
    keys: { p256dh: 'test-p256dh', auth: 'test-auth' },
  }),
  supportsWebPush: vi.fn().mockReturnValue(true),
  webPushPermission: vi.fn().mockReturnValue('default'),
}));

vi.mock('../../../../src/shared/pwa/pwaRuntime', () => ({
  isIosInstallSurface: vi.fn().mockReturnValue(false),
  isPwaStandalone: vi.fn().mockReturnValue(false),
  isTelegramSurface: vi.fn().mockReturnValue(false),
}));

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <FeedbackProvider>
        <WebPushSettings />
      </FeedbackProvider>
    </QueryClientProvider>,
  );
}

describe('WebPushSettings', () => {
  beforeEach(() => {
    vi.mocked(isTelegramSurface).mockReturnValue(false);
    vi.mocked(webPushPermission).mockReturnValue('default');
    vi.mocked(getExistingWebPushSubscription).mockResolvedValue(null);
    vi.mocked(subscribeToWebPush).mockResolvedValue({
      endpoint: 'https://fcm.googleapis.com/fcm/send/test',
      keys: { p256dh: 'test-p256dh', auth: 'test-auth' },
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === '/api/v1/notifications/web-push/config') {
        return new Response(
          JSON.stringify({ enabled: true, application_server_key: 'test-public-key' }),
          { status: 200 },
        );
      }
      if (path === '/api/v1/notifications/web-push/status') {
        return new Response(JSON.stringify({ enabled: true, registered: false }), { status: 200 });
      }
      if (path === '/api/v1/notifications/web-push/subscription' && init?.method === 'POST') {
        return new Response(JSON.stringify({ status: 'registered' }), { status: 201 });
      }
      return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('показывает ценность и запрашивает permission только по явному действию', async () => {
    const requestPermission = vi.fn().mockResolvedValue('granted');
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: { permission: 'default', requestPermission },
    });
    renderSettings();

    expect(
      await screen.findByRole('heading', { name: 'Уведомления браузера' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/В push нет деталей тренировки или питания/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Включить уведомления браузера' }));

    await waitFor(() => expect(requestPermission).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/notifications/web-push/subscription',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
    const postCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(
        ([input, init]) =>
          String(input).endsWith('/web-push/subscription') && init?.method === 'POST',
      );
    expect(postCall?.[1]?.body).toContain('test-p256dh');
  });

  it('скрывает Web Push в Telegram Mini App', async () => {
    vi.mocked(isTelegramSurface).mockReturnValue(true);
    renderSettings();

    await waitFor(() => expect(screen.queryByText('Уведомления браузера')).not.toBeInTheDocument());
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('объясняет заблокированное разрешение без повторного prompt', async () => {
    vi.mocked(webPushPermission).mockReturnValue('denied');
    const requestPermission = vi.fn();
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: { permission: 'denied', requestPermission },
    });
    renderSettings();

    expect(await screen.findByText(/Разрешение заблокировано браузером/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Включить уведомления/ })).not.toBeInTheDocument();
    expect(requestPermission).not.toHaveBeenCalled();
  });
});
