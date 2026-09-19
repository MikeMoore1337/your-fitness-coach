import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Client,
  CoachAssignedProgram,
  TrainerClientProgressSummary,
} from '../../../../src/shared/api/types';
import {
  activityLabel,
  clientDisplayName,
  coachWorkspaceStats,
  formatDaysAgo,
  filterCoachClients,
  russianQuantity,
} from '../../../../src/features/coach/coachWorkspace';

const clients = [
  { id: 1, full_name: 'Анна Петрова', username: 'anna', status: 'active' },
  { id: 2, full_name: 'Борис С очень длинной фамилией', username: 'boris', status: 'active' },
  { id: null, invite_id: 41, full_name: 'Ожидающий клиент', status: 'pending' },
] as Client[];

function summary(
  userId: number,
  lastWorkout: string | null,
  personalRecords = 0,
  measuredOn?: string,
): TrainerClientProgressSummary {
  return {
    user_id: userId,
    period_days: 30,
    period_start: '2030-01-03',
    period_end: '2030-02-01',
    training: {
      planned_workouts: 8,
      completed_workouts: 6,
      skipped_workouts: 1,
      frequency_per_week: 1.5,
      volume_kg: 12000,
      new_personal_records: personalRecords,
      last_completed_workout_on: lastWorkout,
      next_workout: null,
    },
    cardio: {
      completed_sessions: 0,
      planned_sessions: 0,
      frequency_per_week: 0,
      duration_minutes: 0,
      distance_km: null,
      zone_duration: [],
    },
    nutrition: {
      visible: true,
      logged_days: 14,
      complete_days: 12,
      incomplete_days: 2,
      fasted_days: 0,
      unlogged_days: 15,
      adherence_evaluated_days: 12,
      average_calories: 2000,
      target_calories: 2100,
      average_protein_g: 130,
      target_protein_g: 140,
      target_effective_on: '2030-01-01',
    },
    body: {
      latest_measurement: measuredOn ? { measured_on: measuredOn, weight_kg: 70 } : null,
      trends: [],
      priority: null,
      guidance: {
        comparison_basis: 'self',
        minimum_points_for_interpretation: 2,
        minimum_span_days_for_interpretation: 14,
        consistency_tips: [],
        circumference_limitations: [],
      },
    },
    adherence: {
      formula_version: 'v1',
      overall_percent: 75,
      included_components: ['workouts'],
      workouts: { status: 'available', percent: 75, achieved: 6, evaluated: 8, weight: 1 },
      cardio: { status: 'not_applicable', achieved: 0, evaluated: 0, weight: 0 },
      calories: { status: 'available', percent: 80, achieved: 8, evaluated: 10, weight: 1 },
      protein: { status: 'available', percent: 70, achieved: 7, evaluated: 10, weight: 1 },
    },
    data_sufficiency: {} as TrainerClientProgressSummary['data_sufficiency'],
    client_name: clients.find((client) => client.id === userId)?.full_name,
  };
}

describe('coach workspace summaries', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2030-02-01T12:00:00'));
  });
  afterEach(() => vi.useRealTimers());

  it('computes factual dashboard counts without a subjective score', () => {
    const summaries = [summary(1, '2030-01-31', 2, '2030-01-29'), summary(2, null)];

    expect(coachWorkspaceStats(clients, summaries)).toEqual({
      active: 2,
      pending: 1,
      recent: 1,
      attention: 1,
      personalRecords: 2,
      measurementUpdates: 1,
    });
    expect(activityLabel('2030-01-31')).toBe('Тренировался вчера');
    expect(activityLabel(null)).toBe('Тренировок ещё не было');
  });

  it('uses deterministic Russian plural forms for relative days', () => {
    expect([1, 2, 5, 11, 21, 22, 25, 31, 42].map((days) => formatDaysAgo(days))).toEqual([
      '1 день назад',
      '2 дня назад',
      '5 дней назад',
      '11 дней назад',
      '21 день назад',
      '22 дня назад',
      '25 дней назад',
      '31 день назад',
      '42 дня назад',
    ]);
    expect(russianQuantity(31, ['день', 'дня', 'дней'])).toBe('день');
    expect(activityLabel('2030-01-01')).toBe('Тренировался 31 день назад');
  });

  it('filters by activity, assignment and searchable identity', () => {
    const summaries = new Map([
      [1, summary(1, '2030-01-31')],
      [2, summary(2, '2030-01-15')],
    ]);
    const programs = [{ client_id: 1, is_active: true }] as CoachAssignedProgram[];
    const base = { clients, programs, summaries };

    expect(
      filterCoachClients({ ...base, filter: 'attention', search: '' }).map((client) => client.id),
    ).toEqual([2]);
    expect(
      filterCoachClients({ ...base, filter: 'without_program', search: '' }).map(
        (client) => client.id,
      ),
    ).toEqual([2]);
    expect(
      filterCoachClients({ ...base, filter: 'all', search: 'длинной' }).map((client) => client.id),
    ).toEqual([2]);
    expect(
      filterCoachClients({ ...base, filter: 'pending', search: '' }).map(
        (client) => client.invite_id,
      ),
    ).toEqual([41]);
  });

  it('does not promote a raw Telegram id to the primary client identity', () => {
    expect(
      clientDisplayName({
        id: 3,
        full_name: null,
        username: null,
        telegram_user_id: 99123,
        status: 'active',
      } as Client),
    ).toBe('Клиент');
    expect(
      clientDisplayName({
        id: null,
        invite_id: 42,
        full_name: null,
        username: null,
        status: 'pending',
      } as Client),
    ).toBe('Ожидающий клиент');
  });
});
