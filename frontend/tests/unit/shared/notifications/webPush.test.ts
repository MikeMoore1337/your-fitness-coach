import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, getAccessToken } from '../../../../src/shared/api/client';
import { revokeWebPushSubscription } from '../../../../src/shared/notifications/webPush';

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
    Reflect.deleteProperty(navigator, 'serviceWorker');
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uses the captured account token even when logout clears it during lookup', async () => {
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
  });
});
