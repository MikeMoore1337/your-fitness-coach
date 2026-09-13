import { describe, expect, it } from 'vitest';
import {
  createYandexMetricaProvider,
  safeYandexReferrer,
  safeYandexUrl,
} from '../../../../src/shared/analytics/yandexMetrica';

describe('Yandex Metrica privacy boundary', () => {
  it('removes query and hash values from route and referrer URLs', () => {
    expect(safeYandexUrl('/app?token=private#profile')).toBe('http://localhost:3000/app');
    expect(safeYandexReferrer('https://example.com/article?email=private#comment')).toBe(
      'https://example.com/article',
    );
    expect(safeYandexReferrer('https://user:password@example.com/private')).toBeUndefined();
  });

  it('maps growth actions to goal ids and sends no event payload values', () => {
    const commands: unknown[][] = [];
    const provider = createYandexMetricaProvider(
      (method, ...args) => commands.push([method, ...args]),
      'production',
    );
    const base = {
      surface: 'desktop_web' as const,
      schema_version: 2 as const,
      environment: 'production' as const,
      occurred_at: '2026-09-13T10:00:00.000Z',
    };

    provider.send({ ...base, name: 'registration_completed' });
    provider.send({ ...base, name: 'workout_completed' });

    expect(commands).toEqual([
      ['reachGoal', 'registration_completed'],
      ['params', { yfc_event: 'workout_completed', yfc_surface: 'desktop_web' }],
    ]);
    expect(JSON.stringify(commands)).not.toContain('private');
  });
});
