import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  it('показывает рекомендации каждой стороны отдельно без общего повышения', () => {
    const left = guidance({ suggested_weight: 20.5, message: 'Можно рассмотреть увеличение' });
    const right = guidance({
      outcome: 'hold',
      suggested_weight: null,
      message: 'Пока оставьте текущую нагрузку',
      detail: 'Отмечен отказ.',
    });
    const onApply = vi.fn();
    render(
      <ProgressionGuidance
        exerciseKey={832}
        guidance={guidance({
          suggested_weight: null,
          side_guidance: { execution_mode: 'per_side', left, right },
        })}
        onApply={onApply}
        onDismiss={() => undefined}
      />,
    );
    expect(screen.getByText('Левая сторона')).toBeVisible();
    expect(screen.getByText(/Можно рассмотреть увеличение · 20,5 кг/)).toBeVisible();
    expect(screen.getByText('Правая сторона')).toBeVisible();
    expect(screen.getByText('Отмечен отказ.')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Применить/ })).not.toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });

  it('применяет проверенное предложение для обеих сторон одним действием', () => {
    const left = guidance({ suggested_weight: 20.5 });
    const right = guidance({ suggested_weight: 18.5 });
    const onApply = vi.fn();
    render(
      <ProgressionGuidance
        exerciseKey={833}
        guidance={guidance({
          suggested_weight: null,
          side_guidance: { execution_mode: 'per_side', left, right },
          proposal: proposal(
            'double_progression',
            {},
            {
              proposed_action: 'set_load',
              eligibility_status: 'eligible',
              side_execution_mode: 'per_side',
              proposed_side_weights: { left: 20.5, right: 18.5 },
            },
          ),
        })}
        onApply={onApply}
        onDismiss={() => undefined}
      />,
    );
    const apply = screen.getByRole('button', { name: 'Применить: левая 20,5 кг, правая 18,5 кг' });
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledOnce();
  });
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
    fireEvent.click(screen.getByText('Почему такой вес?'));
    expect(screen.getByText('Цель: 3 × 8–10')).toBeVisible();
    expect(screen.getByText(/40 кг · 10 повторов/)).toBeVisible();
    const history = screen.getByRole('list', { name: 'Последние тренировки' });
    expect(within(history).getByRole('listitem')).toHaveTextContent(/10 повторов\s+3 раб\. подх\./);
    expect(screen.getByText(/тренировка: нормально/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Подробнее о прогрессии' })).toHaveAttribute(
      'href',
      '/knowledge/training/progressive-overload',
    );

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

  it('shows the selected week type, comparable facts and actual proposal evidence', () => {
    render(
      <ProgressionGuidance
        exerciseKey={102}
        guidance={guidance({
          ruleset_version: 'progression-guidance-v3',
          evidence: { ...guidance().evidence, week_type: 'heavy' },
          proposal: proposal(
            'double_progression',
            {},
            {
              proposed_weight: 42.5,
              reason_codes: ['top_range_repeated'],
              source_evidence_ids: ['workout:31/set:20'],
            },
          ),
        })}
        onApply={() => undefined}
        onDismiss={() => undefined}
      />,
    );

    expect(screen.getByText('Следующая нагрузка · Тяжёлая неделя')).toBeVisible();
    expect(screen.getByText('Можно рассмотреть увеличение до 42,5 кг')).toBeVisible();
    expect(screen.getByText('Прошлая сопоставимая: 40 кг × 10 · 17 августа')).toBeVisible();
    fireEvent.click(screen.getByText('Почему такой вес?'));
    expect(screen.getByText('Источники: workout:31/set:20')).toBeVisible();
    expect(screen.getByText('Причины: top_range_repeated')).toBeVisible();
    expect(screen.getByText('Версия правила: progression-guidance-v3')).toBeVisible();
  });

  it('explains missing same-type history without a proposed load', () => {
    render(
      <ProgressionGuidance
        exerciseKey={103}
        guidance={guidance({
          ruleset_version: 'progression-guidance-v3',
          outcome: 'review',
          suggested_weight: null,
          evidence: {
            ...guidance().evidence,
            week_type: 'light',
            comparable_session_count: 0,
            sessions: [],
            reason_keys: ['insufficient_same_type_history'],
          },
          proposal: proposal(
            'double_progression',
            {},
            {
              reason_codes: ['insufficient_same_type_history'],
              source_evidence_ids: [],
            },
          ),
        })}
        onApply={() => undefined}
        onDismiss={() => undefined}
      />,
    );

    expect(screen.getByText('Следующая нагрузка · Лёгкая неделя')).toBeVisible();
    expect(screen.getByText('Сопоставимых тренировок пока нет.')).toBeVisible();
    expect(screen.getByText(/нужны полные сопоставимые тренировки лёгкого типа/)).toBeVisible();
    expect(screen.queryByRole('button', { name: /Применить/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Почему такой вес?'));
    expect(screen.queryByText(/Источники:/)).not.toBeInTheDocument();
    expect(screen.getByText('Причины: insufficient_same_type_history')).toBeVisible();
  });

  it('describes incomplete comparable facts without fabricating a weight', () => {
    const original = guidance();
    render(
      <ProgressionGuidance
        exerciseKey={103}
        guidance={guidance({
          ruleset_version: 'progression-guidance-v3',
          outcome: 'review',
          suggested_weight: null,
          evidence: {
            ...original.evidence,
            week_type: 'heavy',
            reason_keys: ['incomplete_session_facts'],
            sessions: [{ ...original.evidence.sessions[0]!, load: null }],
          },
        })}
        onApply={() => undefined}
        onDismiss={() => undefined}
      />,
    );
    expect(
      screen.getByText(/Прошлая сопоставимая: .*нагрузка неполная · 10 повторов/),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: /Применить/ })).not.toBeInTheDocument();
  });

  it('allows another explicit attempt after an asynchronous conflict', async () => {
    let rejectAttempt: (reason: Error) => void = () => undefined;
    const onApply = vi
      .fn()
      .mockImplementationOnce(() => new Promise((_resolve, reject) => (rejectAttempt = reject)))
      .mockResolvedValueOnce(undefined);
    render(
      <ProgressionGuidance
        exerciseKey={104}
        guidance={guidance()}
        onApply={onApply}
        onDismiss={() => undefined}
      />,
    );

    const apply = screen.getByRole('button', { name: 'Применить 42,5 кг' });
    fireEvent.click(apply);
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledTimes(1);
    rejectAttempt(new Error('409'));
    await waitFor(() => {
      fireEvent.click(apply);
      expect(onApply).toHaveBeenCalledTimes(2);
    });
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
