import { afterEach, describe, expect, it } from 'vitest';
import {
  authRecoveryMessage,
  oauthStartHref,
  providerLabel,
  safeOAuthProvider,
} from '../../../../src/shared/auth/oauthRecovery';

describe('oauthRecovery', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/login');
  });

  it('builds a provider retry link with only an allowlisted next path', () => {
    expect(oauthStartHref('GOOGLE', '/coach')).toBe(
      '/api/v1/auth/oauth/google/start?next=%2Fcoach',
    );
    expect(oauthStartHref('google', 'https://evil.example')).toBe(
      '/api/v1/auth/oauth/google/start',
    );
    expect(oauthStartHref('google', '/app?trainer_intent=1')).toBe(
      '/api/v1/auth/oauth/google/start?next=%2Fapp%3Ftrainer_intent%3D1',
    );
    expect(oauthStartHref('unknown', '/app')).toBeNull();
  });

  it('normalizes provider query data and maps link errors without raw details', () => {
    expect(safeOAuthProvider(' VK ')).toBe('vk');
    expect(safeOAuthProvider('provider-secret')).toBeNull();
    expect(providerLabel('vk')).toBe('VK ID');
    expect(authRecoveryMessage('oauth_link_conflict', 'vk')).toBe(
      'Этот способ входа уже привязан к другому аккаунту.',
    );
    expect(authRecoveryMessage('provider-secret', 'google')).toBeNull();
  });
});
