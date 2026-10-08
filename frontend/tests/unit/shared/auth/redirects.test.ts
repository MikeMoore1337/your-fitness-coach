import { describe, expect, it } from 'vitest';
import {
  hasExplicitAppDestination,
  loginPathForNext,
  safeAuthNextPath,
} from '../../../../src/shared/auth/redirects';
import { isTrainerIntentLocation } from '../../../../src/shared/auth/trainerIntent';

describe('authenticated entry routing', () => {
  it('preserves allowlisted app, report and coach deep links through login', () => {
    expect(safeAuthNextPath('/app?section=nutrition')).toBe('/app?section=nutrition');
    expect(safeAuthNextPath('/app?trainer_intent=1')).toBe('/app?trainer_intent=1');
    expect(safeAuthNextPath('/app/report?period=days_30')).toBe('/app/report?period=days_30');
    expect(safeAuthNextPath('/coach?client_id=42')).toBe('/coach?client_id=42');
    expect(safeAuthNextPath(`/share/${'A'.repeat(43)}`)).toBe(`/share/${'A'.repeat(43)}`);
    expect(loginPathForNext('/coach?client_id=42')).toBe('/login?next=%2Fcoach%3Fclient_id%3D42');
  });

  it('rejects external auth destinations and distinguishes Telegram transport params', () => {
    expect(safeAuthNextPath('https://evil.example/steal')).toBe('/app');
    expect(safeAuthNextPath('//evil.example/steal')).toBe('/app');
    expect(hasExplicitAppDestination('', '')).toBe(false);
    expect(hasExplicitAppDestination('?tgWebAppPlatform=android')).toBe(false);
    expect(hasExplicitAppDestination('?tgWebAppPlatform=android&section=nutrition')).toBe(true);
    expect(hasExplicitAppDestination('', '#tgWebAppData=signed')).toBe(false);
    expect(hasExplicitAppDestination('', '#profile-fitness')).toBe(true);
    expect(isTrainerIntentLocation('/app', '?trainer_intent=1')).toBe(true);
    expect(isTrainerIntentLocation('/app', '?trainer_intent=1&tgWebAppPlatform=android')).toBe(
      true,
    );
    expect(isTrainerIntentLocation('/app', '?trainer_intent=1&next=https://evil.example')).toBe(
      false,
    );
    expect(isTrainerIntentLocation('/app', '?trainer_intent=1', '#details')).toBe(false);
  });
});
