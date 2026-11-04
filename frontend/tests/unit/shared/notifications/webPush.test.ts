import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getAccessToken } from '../../../../src/shared/api/client';
import {
  getExistingWebPushSubscription,
  revokeWebPushSubscription,
} from '../../../../src/shared/notifications/webPush';

vi.mock('../../../../src/shared/api/client', () => ({
  api: vi.fn().mockResolvedValue(undefined),
  getAccessToken: vi.fn(),
}));

describe('web push runtime lifecycle', () => {
  beforeEach(() => {
    vi.mocked(getAccessToken).mockReturnValue('old-account-token');
    vi.stubGlobal('Notification', { permission: 'granted' });
    vi.stubGlobal('PushManager', class PushManager {});
  });

  afterEach(() => {
    Reflect.deleteProperty(navigator, 'permissions');
    Reflect.deleteProperty(navigator, 'serviceWorker');
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('avoids looking up a subscription when push permission has not been granted', async () => {
    vi.stubGlobal('Notification', { permission: 'default' });
    const query = vi.fn().mockResolvedValue({ state: 'prompt' });
    const getRegistration = vi.fn();
    Object.defineProperty(navigator, 'permissions', { configurable: true, value: { query } });
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { getRegistration },
    });

    await expect(getExistingWebPushSubscription()).resolves.toBeNull();
    expect(query).toHaveBeenCalledWith({ name: 'push', userVisibleOnly: true });
    expect(getRegistration).not.toHaveBeenCalled();
  });

  it.each(['granted', 'denied', 'unavailable'])(
    'looks up the existing subscription when push permission is %s',
    async (state) => {
      vi.stubGlobal('Notification', { permission: 'default' });
      const query =
        state === 'unavailable'
          ? vi.fn().mockRejectedValue(new TypeError('unsupported'))
          : vi.fn().mockResolvedValue({ state });
      const subscription = { endpoint: 'https://example.test/push' };
      const getSubscription = vi.fn().mockResolvedValue(subscription);
      Object.defineProperty(navigator, 'permissions', { configurable: true, value: { query } });
      Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: { getRegistration: vi.fn().mockResolvedValue({ pushManager: { getSubscription } }) },
      });

      await expect(getExistingWebPushSubscription()).resolves.toBe(subscription);
      expect(getSubscription).toHaveBeenCalledOnce();
    },
  );

  it('checks the subscription if notification permission changes during the push query', async () => {
    const notification = { permission: 'default' };
    vi.stubGlobal('Notification', notification);
    const query = vi.fn(async () => {
      notification.permission = 'granted';
      return { state: 'prompt' };
    });
    const subscription = { endpoint: 'https://example.test/push' };
    const getSubscription = vi.fn().mockResolvedValue(subscription);
    Object.defineProperty(navigator, 'permissions', { configurable: true, value: { query } });
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { getRegistration: vi.fn().mockResolvedValue({ pushManager: { getSubscription } }) },
    });

    await expect(getExistingWebPushSubscription()).resolves.toBe(subscription);
    expect(getSubscription).toHaveBeenCalledOnce();
  });

  it.each([
    ['granted', null],
    ['default', 'granted'],
    ['default', 'denied'],
  ])(
    'revokes an existing subscription with notification permission %s',
    async (notification, push) => {
      vi.stubGlobal('Notification', { permission: notification });
      if (push) {
        Object.defineProperty(navigator, 'permissions', {
          configurable: true,
          value: { query: vi.fn().mockResolvedValue({ state: push }) },
        });
      }
      const unsubscribe = vi.fn().mockResolvedValue(true);
      const subscription = {
        endpoint: 'https://fcm.googleapis.com/fcm/send/test',
        toJSON: () => ({
          endpoint: 'https://fcm.googleapis.com/fcm/send/test',
          keys: { p256dh: 'test-p256dh', auth: 'test-auth' },
        }),
        unsubscribe,
      } as unknown as PushSubscription;
      const serviceWorker = {
        getRegistration: vi.fn(async () => {
          vi.mocked(getAccessToken).mockReturnValue(null);
          return { pushManager: { getSubscription: vi.fn().mockResolvedValue(subscription) } };
        }),
      };
      Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: serviceWorker,
      });

      await revokeWebPushSubscription();

      expect(api).toHaveBeenCalledWith(
        '/api/v1/notifications/web-push/subscription',
        expect.objectContaining({
          method: 'DELETE',
          headers: { Authorization: 'Bearer old-account-token' },
        }),
      );
      expect(unsubscribe).toHaveBeenCalledOnce();
    },
  );
});
