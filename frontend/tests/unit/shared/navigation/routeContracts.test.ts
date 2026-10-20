import { describe, expect, it } from 'vitest';
import {
  coachTabFromSearch,
  demoReturnPathFromLogin,
  focusedContextReturn,
  progressReportReturn,
  safeTrainerReturnPath,
} from '../../../../src/shared/navigation/routeContracts';
import {
  hasNoDuplicateParams,
  positiveInteger,
  positiveIntegerParam,
} from '../../../../src/shared/navigation/routeParams';

const ORIGIN = 'https://app.example';

describe('navigation route contracts', () => {
  it('accepts only safe positive integer query values', () => {
    expect(positiveInteger('42')).toBe(42);
    expect(positiveInteger('0')).toBeNull();
    expect(positiveInteger('9007199254740992')).toBeNull();

    const params = new URLSearchParams('client_id=42&client_id=43');
    expect(positiveIntegerParam(params, 'client_id')).toBeNull();
    expect(hasNoDuplicateParams(params, ['client_id'])).toBe(false);
  });

  it('keeps trainer returns same-origin and allowlisted', () => {
    expect(safeTrainerReturnPath('/coach?tab=clients', ORIGIN)).toBe('/coach?tab=clients');
    expect(safeTrainerReturnPath('https://evil.example/coach?tab=clients', ORIGIN)).toBeNull();
    expect(safeTrainerReturnPath('/coach?tab=clients&tab=programs', ORIGIN)).toBeNull();
  });

  it('rejects ambiguous coach and demo route parameters', () => {
    expect(coachTabFromSearch('?client_id=42&client_id=43')).toBe('today');
    expect(demoReturnPathFromLogin('?from=demo&scenario=nutrition&scenario=trainer')).toBeNull();
  });

  it('does not return to a handoff with an unsafe identifier', () => {
    expect(
      progressReportReturn(
        '?handoff_id=9007199254740992&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
        ORIGIN,
      ),
    ).toBe('/app?section=progress');
  });

  it('rejects ambiguous internal return paths without opening an external target', () => {
    expect(
      focusedContextReturn(
        `?workout_id=43&return_to=${encodeURIComponent('/app?section=profile&section=profile#profile-notifications')}`,
        ORIGIN,
      ),
    ).toBe('/app?section=progress');
    expect(
      focusedContextReturn(
        `?workout_id=43&return_to=${encodeURIComponent('https://evil.example/steal')}`,
        ORIGIN,
      ),
    ).toBe('/app?section=progress');
  });
});
