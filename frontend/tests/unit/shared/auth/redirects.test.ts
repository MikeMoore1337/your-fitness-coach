import { describe, expect, it } from 'vitest';
import {
  hasExplicitAppDestination,
  loginPathForNext,
  safeAuthNextPath,
} from '../../../../src/shared/auth/redirects';

describe('authenticated entry routing', () => {
  it('preserves allowlisted app, report and coach deep links through login', () => {
    expect(safeAuthNextPath('/app?section=nutrition')).toBe('/app?section=nutrition');
    expect(safeAuthNextPath('/app/report?period=days_30')).toBe('/app/report?period=days_30');
    expect(safeAuthNextPath('/coach?client_id=42')).toBe('/coach?client_id=42');
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
  });
});
