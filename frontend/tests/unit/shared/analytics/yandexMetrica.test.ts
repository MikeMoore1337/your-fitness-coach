import { describe, expect, it } from 'vitest';
import {
  createYandexMetricaProvider,
  isYandexMetricaProductionHost,
  safeYandexReferrer,
  safeYandexUrl,
} from '../../../../src/shared/analytics/yandexMetrica';

describe('Yandex Metrica privacy boundary', () => {
  it('allows delivery only on the canonical production hostnames', () => {
    expect(isYandexMetricaProductionHost('your-fitness-coach.ru')).toBe(true);
    expect(isYandexMetricaProductionHost('APP.YOUR-FITNESS-COACH.RU.')).toBe(true);
    expect(isYandexMetricaProductionHost('localhost')).toBe(false);
    expect(isYandexMetricaProductionHost('preview.your-fitness-coach.ru')).toBe(false);
  });

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
    provider.send({ ...base, name: 'calculator_started' });
    provider.send({ ...base, name: 'calculator_result' });
    provider.send({ ...base, name: 'workout_completed' });

    expect(commands).toEqual([
      ['reachGoal', 'registration_completed'],
      ['reachGoal', 'calculator_started'],
      ['reachGoal', 'calculator_result'],
      ['params', { yfc_event: 'workout_completed', yfc_surface: 'desktop_web' }],
    ]);
    expect(JSON.stringify(commands)).not.toContain('private');
  });
});
