import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearAllDemoSessions,
  DemoApiError,
  loadDemoSession,
  startDemoSession,
} from '../../../../src/features/demo/demoApi';

const snapshot = {
  capability: 'demo',
  scenario: 'self_training',
  fixture_version: 'demo-curated-v2',
  revision: 1,
  expires_at: '2026-08-24T12:30:00Z',
  state: {
    kind: 'self_training',
    screen: 'today',
    workout_title: 'Верх тела',
    workout_subtitle: 'Сегодня',
    completed_sets: 2,
    total_sets: 3,
    exercises: [],
    duration_minutes: 0,
    total_volume_kg: 0,
    progress_change_percent: 0,
  },
} as const;

describe('demoApi', () => {
  beforeEach(() => {
    clearAllDemoSessions();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('discards every demo credential before the auth handoff', async () => {
    const fetchMock = vi
      .spyOn(window, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...snapshot, session_token: 'D'.repeat(43) }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...snapshot, session_token: 'E'.repeat(43) }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    await startDemoSession('self_training');
    clearAllDemoSessions();
    expect(sessionStorage.getItem('fit_demo_sessions_v1')).toBeNull();

    await loadDemoSession('self_training');
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/demo/sessions');
  });

  it('creates an isolated credential-free session and keeps only its demo token', async () => {
    const fetchMock = vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...snapshot, session_token: 'A'.repeat(43) }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(startDemoSession('self_training')).resolves.toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/demo/sessions',
      expect.objectContaining({
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        body: JSON.stringify({ scenario: 'self_training' }),
      }),
    );
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(options.headers).not.toHaveProperty('Authorization');
    expect(sessionStorage.getItem('fit_demo_sessions_v1')).toContain('A'.repeat(43));
  });

  it('restores only the matching session through X-Demo-Session', async () => {
    sessionStorage.setItem(
      'fit_demo_sessions_v1',
      JSON.stringify({ self_training: 'B'.repeat(43) }),
    );
    const fetchMock = vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await loadDemoSession('self_training');

    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(options.credentials).toBe('omit');
    expect(options.headers).toEqual({ 'X-Demo-Session': 'B'.repeat(43) });
  });

  it('drops an expired token without silently mixing it into a new session', async () => {
    sessionStorage.setItem(
      'fit_demo_sessions_v1',
      JSON.stringify({ self_training: 'C'.repeat(43) }),
    );
    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Демо-сессия истекла. Начните новый сценарий.' }), {
        status: 410,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(loadDemoSession('self_training')).rejects.toEqual(
      new DemoApiError('Демо-сессия истекла. Начните новый сценарий.', 410),
    );
    expect(sessionStorage.getItem('fit_demo_sessions_v1')).not.toContain('C'.repeat(43));
  });
});
