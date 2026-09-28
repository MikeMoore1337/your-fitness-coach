import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Workout } from '../../../../src/shared/api/types';
import { ProgressionGuidance } from '../../../../src/features/workouts/ProgressionGuidance';

type Guidance = NonNullable<Workout['exercises'][number]['progression_guidance']>;
type Proposal = NonNullable<Guidance['proposal']>;

afterEach(cleanup);

function guidance(overrides: Partial<Guidance> = {}): Guidance {
  return {
    ruleset_version: 'progression-guidance-v2',
    outcome: 'consider_progressing',
    message: 'Можно рассмотреть небольшое увеличение веса',
    detail:
      'Верхняя граница повторений стабильно достигнута. Доступный шаг оборудования учтён; решение остаётся за вами.',
    suggested_increment: 2.5,
    suggested_weight: 42.5,
    load_unit: 'kg',
    evidence: {
      target_reps_min: 8,
      target_reps_max: 10,
      prescribed_sets: 3,
      comparable_session_count: 2,
      required_session_count: 2,
      working_set_count: 6,
      rir_recorded_set_count: 6,
      reason_keys: ['top_range_repeated', 'full_rir_coverage'],
      sessions: [
        {
          workout_id: 31,
          scheduled_date: '2026-08-17',
          working_set_count: 3,
          load: 40,
          load_unit: 'kg',
          reps_min: 10,
          reps_max: 10,
          rir_recorded_set_count: 3,
          rir_values: ['1', '2', '2'],
          reached_failure: false,
          completion_feedback: 'as_expected',
        },
      ],
    },
    ...overrides,
  };
}

function proposal(
  rule_kind: Proposal['rule_kind'],
  rule_snapshot: Proposal['rule_snapshot'],
  extra: Partial<Proposal> = {},
): Proposal {
  return {
    proposal_id: 'a'.repeat(64),
    rule_id: 'b'.repeat(64),
    rule_kind,
    rule_snapshot,
    target_program_id: 1,
    target_revision_number: 2,
    target_exercise_id: 4,
    target_workout_id: 5,
    current_weight: 40,
    proposed_weight: null,
    proposed_action: 'hold',
    target_set_updates: [],
    source_evidence_ids: ['workout:31/set:20'],
    comparable_session_count: 2,
    reason_codes: ['top_range_repeated'],
    eligibility_status: 'review',
    requires_confirmation: true,
    ...extra,
  };
}

describe('ProgressionGuidance', () => {
  it('shows factual evidence and applies an exact configured step only once', () => {
    const onApply = vi.fn();
    render(
      <ProgressionGuidance
        exerciseKey={101}
        guidance={guidance()}
        onApply={onApply}
        onDismiss={() => undefined}
      />,
    );

    expect(screen.getByText('Можно рассмотреть небольшое увеличение веса')).toBeVisible();
    fireEvent.click(screen.getByText('Почему?'));
    expect(screen.getByText('Цель: 3 × 8–10')).toBeVisible();
    expect(screen.getByText(/40 кг · 10 повторов/)).toBeVisible();
    expect(screen.getByText(/тренировка: нормально/)).toBeVisible();

    const apply = screen.getByRole('button', { name: 'Применить 42,5 кг' });
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('keeps insufficient data plain and dismissible without an apply action', () => {
    const onDismiss = vi.fn();
    render(
      <ProgressionGuidance
        exerciseKey={102}
        guidance={guidance({
          outcome: 'review',
          message: 'Данных недостаточно — сначала закрепите текущий диапазон повторений',
          suggested_increment: null,
          suggested_weight: null,
          evidence: {
            ...guidance().evidence,
            comparable_session_count: 0,
            working_set_count: 0,
            rir_recorded_set_count: 0,
            sessions: [],
          },
        })}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.queryByRole('button', { name: /Применить/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Оставить текущую нагрузку' }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('explains the stored rule and prefers the proposal load', () => {
    const onApply = vi.fn();
    render(
      <ProgressionGuidance
        exerciseKey={103}
        guidance={guidance({
          suggested_weight: 42.5,
          proposal: proposal(
            'double_progression',
            {
              kind: 'double_progression',
              scope: 'program',
              rep_target: { kind: 'range', min_reps: 8, max_reps: 10 },
              increment_value: 5,
              increment_unit: 'kg',
            },
            {
              proposed_weight: 45,
              proposed_action: 'set_load',
              eligibility_status: 'eligible',
              target_set_updates: [
                {
                  set_id: 21,
                  set_number: 1,
                  planned_role: 'working',
                  current_weight: null,
                  set_version: 1,
                  relative_to_top: null,
                  proposed_weight: 45,
                },
              ],
            },
          ),
        })}
        onApply={onApply}
        onDismiss={() => undefined}
      />,
    );

    expect(
      screen.getByText(/Двойная прогрессия · диапазон 8–10 повторений · шаг 5 кг/),
    ).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Применить 45 кг' }));
    expect(onApply).toHaveBeenCalledOnce();
  });

  it.each([
    {
      kind: 'rir_rpe' as const,
      rule: {
        kind: 'rir_rpe',
        scope: 'exercise',
        effort_target: { kind: 'rir', value: 2 },
      },
      extra: {},
      expected: 'цель RIR 2 · уровень упражнения',
    },
    {
      kind: 'rir_rpe' as const,
      rule: {
        kind: 'rir_rpe',
        scope: 'block',
        block_number: 2,
        week_start: 3,
        week_end: 4,
        effort_target: { kind: 'rpe', value: 7 },
      },
      extra: {},
      expected: 'цель RPE 7 · блок 2 · недели 3–4',
    },
    {
      kind: 'percentage_training_max' as const,
      rule: {
        kind: 'percentage_training_max',
        scope: 'program',
        load_target: { kind: 'percent_training_max', value: 80 },
      },
      extra: {},
      expected: '80% от тренировочного максимума · уровень программы',
    },
    {
      kind: 'linear_load' as const,
      rule: {
        kind: 'linear_load',
        scope: 'program',
        increment_value: 2.5,
        increment_unit: 'kg',
        reset_on_failure: true,
      },
      extra: {},
      expected: 'сброс при отказе без заданной величины',
    },
    {
      kind: 'amrap_success_failure' as const,
      rule: {
        kind: 'amrap_success_failure',
        scope: 'program',
        rep_target: { kind: 'amrap', cap_reps: 12 },
        amrap_min_reps: 8,
        amrap_failure_action: 'reduce_load',
        increment_value: 2.5,
        increment_unit: 'kg',
      },
      extra: {},
      expected:
        'AMRAP, не более 12 повторений · шаг 2,5 кг · успех от 8 повторений · при невыполнении: снизить на 2,5 кг',
    },
    {
      kind: 'deload' as const,
      rule: { kind: 'deload', scope: 'block', block_number: 3 },
      extra: { deload_volume_percent: 60, deload_intensity_percent: 80 },
      expected: 'объём 60% · интенсивность 80% · блок 3',
    },
  ])('shows exact $kind rule targets', ({ kind, rule, extra, expected }) => {
    render(
      <ProgressionGuidance
        exerciseKey={104}
        guidance={guidance({ proposal: proposal(kind, rule, extra) })}
        onDismiss={() => undefined}
      />,
    );

    expect(screen.getByText(new RegExp(expected))).toBeVisible();
  });
});
