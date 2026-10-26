import { describe, expect, it } from 'vitest';
import {
  canSendRootConsent,
  HERMES_OWNER_ORIGIN,
  readHermesPairingNonce,
} from '../../../../src/pages/admin/HermesRootConsentPage';

const nonce = 'c'.repeat(64);
const origin = 'https://app.your-fitness-coach.ru';

describe('Hermes Root consent bridge', () => {
  it('accepts exactly one fragment challenge with 256-bit random nonce', () => {
    expect(readHermesPairingNonce('#nonce=' + nonce)).toBe(nonce);
    expect(readHermesPairingNonce('#nonce=' + 'x'.repeat(64))).toBe(null);
    expect(readHermesPairingNonce('#nonce=' + nonce + '&redirect=https://evil')).toBe(null);
    expect(readHermesPairingNonce('#nonce=' + 'a'.repeat(12))).toBe(null);
    expect(readHermesPairingNonce('#token=secret')).toBe(null);
  });
  it('permits only a live authorized YFC Root in the specific owner popup origin', () => {
    expect(HERMES_OWNER_ORIGIN).toBe('https://hermes.mikemoore.top');
    expect(canSendRootConsent(true, '#nonce=' + nonce, true, origin)).toBe(true);
    expect(canSendRootConsent(false, '#nonce=' + nonce, true, origin)).toBe(false);
    expect(canSendRootConsent(true, '#nonce=' + nonce, false, origin)).toBe(false);
    expect(canSendRootConsent(true, '#nonce=' + nonce, true, 'http://localhost:3000')).toBe(false);
    expect(canSendRootConsent(true, '#nonce=' + nonce, true, 'https://evil.example')).toBe(false);
    expect(canSendRootConsent(true, '#nonce=' + '0'.repeat(12), true, origin)).toBe(false);
  });
});
