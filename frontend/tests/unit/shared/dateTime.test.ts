import { describe, expect, it } from 'vitest';
import { formatTimeZoneLabel } from '../../../src/shared/dateTime';

describe('formatTimeZoneLabel', () => {
  it('presents the profile timezone in Russian without exposing the IANA identifier', () => {
    expect(formatTimeZoneLabel('Europe/Moscow')).toMatch(/Москв/);
    expect(formatTimeZoneLabel('Europe/Moscow')).not.toContain('Europe/');
    expect(formatTimeZoneLabel('Asia/Tokyo')).toMatch(/Япони/);
  });

  it('keeps an unsupported timezone readable without claiming a different timezone', () => {
    expect(formatTimeZoneLabel('unknown/zone')).toBe('Часовой пояс профиля');
  });
});
