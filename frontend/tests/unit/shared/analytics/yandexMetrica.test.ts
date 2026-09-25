import { describe, expect, it } from 'vitest';
import {
  createYandexMetricaProvider,
  isYandexMetricaProductionHost,
  safeYandexReferrer,
  safeYandexUrl,
} from '../../../../src/shared/analytics/yandexMetrica';
import type { ProductEventEnvelope } from '../../../../src/shared/analytics/productEvents';

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

  it('sends only the allowlisted navigation and next-action dimensions', () => {
    const commands: unknown[][] = [];
    const provider = createYandexMetricaProvider(
      (method, ...args) => commands.push([method, ...args]),
      'production',
    );
    const base = {
      surface: 'mobile_web' as const,
      schema_version: 2 as const,
      environment: 'production' as const,
      occurred_at: '2026-09-13T10:00:00.000Z',
    };

    provider.send({
      ...base,
      name: 'section_navigation_selected',
      from_section: 'today',
      to_section: 'programs',
      user_id: 'private-user-id',
      email: 'private@example.com',
    } as ProductEventEnvelope);
    provider.send({
      ...base,
      name: 'next_action_clicked',
      action_kind: 'ready_program',
      position: 'secondary',
      workout_name: 'private-workout',
      body_weight: 72,
    } as ProductEventEnvelope);

    expect(commands).toEqual([
      [
        'params',
        {
          yfc_event: 'section_navigation_selected',
          yfc_surface: 'mobile_web',
          yfc_from_section: 'today',
          yfc_to_section: 'programs',
        },
      ],
      [
        'params',
        {
          yfc_event: 'next_action_clicked',
          yfc_surface: 'mobile_web',
          yfc_action_kind: 'ready_program',
          yfc_position: 'secondary',
        },
      ],
    ]);
    expect(JSON.stringify(commands)).not.toMatch(/private|72/);
  });
});
