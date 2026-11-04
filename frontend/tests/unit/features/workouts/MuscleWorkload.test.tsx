import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { TrainingAnalytics } from '../../../../src/shared/api/types';
import {
  MuscleWorkloadDistribution,
  MuscleWorkloadList,
} from '../../../../src/features/workouts/MuscleWorkload';

afterEach(cleanup);

function period(
  completedSetCount: number,
  completedSessionCount: number,
  frequencyPerWeek: number,
): TrainingAnalytics['muscle_group_workload'][number]['current'] {
  return {
    completed_set_count: completedSetCount,
    primary_completed_set_count: completedSetCount,
    secondary_completed_set_count: 0,
    completed_session_count: completedSessionCount,
    frequency_per_week: frequencyPerWeek,
  };
}

function analytics(
  muscleGroupWorkload: TrainingAnalytics['muscle_group_workload'],
): TrainingAnalytics {
  return {
    period_days: 7,
    completed_set_count: 7,
    completed_sets_without_muscle_metadata: 0,
    muscle_group_workload: muscleGroupWorkload,
  } as TrainingAnalytics;
}

describe('MuscleWorkloadList', () => {
  it('keeps group metrics and exercise drill-down inside keyboard disclosures', () => {
    const longName = 'Передняя дельта и стабилизаторы плечевого пояса';
    render(
      <MuscleWorkloadList
        analytics={analytics([
          {
            muscle_id: 'chest',
            muscle_name: 'Грудь',
            current: period(18, 6, 1.4),
            previous: period(12, 4, 0.93),
            completed_set_count_change: 6,
            frequency_per_week_change: 0.47,
            trend: 'increased',
            contributing_exercises: [
              {
                exercise_id: 11,
                exercise_title: 'Жим штанги лёжа',
                contribution_roles: ['primary'],
                completed_set_count: 18,
                performed_session_count: 6,
                history_truncated: false,
                sessions: [],
              },
            ],
          },
          {
            muscle_id: 'front-deltoid',
            muscle_name: longName,
            current: period(9, 3, 0.7),
            previous: null,
            completed_set_count_change: null,
            frequency_per_week_change: null,
            trend: 'no_comparable_data',
            contributing_exercises: [],
          },
        ])}
      />,
    );

    const workload = document.querySelector<HTMLElement>(
      '[aria-label="Нагрузка по мышечным группам"]',
    );
    expect(workload).not.toBeNull();
    const cards = workload!.querySelectorAll(':scope > details.progress-exercise');
    expect(cards).toHaveLength(2);
    expect(screen.getByText(longName)).toBeVisible();
    expect(screen.getByText('Нет сравнения')).toBeVisible();

    const firstCard = cards[0] as HTMLDetailsElement;
    const firstSummary = firstCard.querySelector('summary') as HTMLElement;
    expect(firstCard.querySelectorAll('button')).toHaveLength(0);
    fireEvent.click(firstSummary);
    expect(firstCard).toHaveAttribute('open');
    expect(within(firstCard).getByText('Текущий период')).toBeVisible();
    expect(
      within(firstCard.querySelector('.progress-workload__comparison') as HTMLElement).getByText(
        '18 подх. · 1,4 в неделю',
      ),
    ).toBeVisible();

    const exerciseSummary = within(firstCard).getByText(/Жим штанги лёжа/);
    fireEvent.click(exerciseSummary);
    expect(within(firstCard).getByText('Сессии не записаны.')).toBeVisible();
  });

  it('keeps the honest empty state when no groups are available', () => {
    render(<MuscleWorkloadList analytics={analytics([])} />);

    expect(screen.getByText('Распределение по мышцам пока не определено')).toBeVisible();
    expect(
      document.querySelector('[aria-label="Нагрузка по мышечным группам"]'),
    ).not.toBeInTheDocument();
  });
});

function group(
  overrides: Partial<TrainingAnalytics['muscle_group_workload'][number]> = {},
): TrainingAnalytics['muscle_group_workload'][number] {
  return {
    muscle_id: 'triceps',
    muscle_name: 'Трицепс',
    current: {
      completed_set_count: 5,
      primary_completed_set_count: 2,
      secondary_completed_set_count: 3,
      completed_session_count: 1,
      frequency_per_week: 1,
    },
    previous: null,
    completed_set_count_change: null,
    frequency_per_week_change: null,
    trend: 'no_comparable_data',
    contributing_exercises: [],
    ...overrides,
  };
}

describe('MuscleWorkloadDistribution', () => {
  it('shows authoritative group totals, separate roles and missing comparison as text', () => {
    render(<MuscleWorkloadDistribution analytics={analytics([group()])} />);

    const choice = screen.getByRole('button', { name: /Трицепс/ });
    expect(choice).toHaveAttribute('aria-pressed', 'true');
    expect(choice).toHaveAttribute('data-yfc-choice', 'compact');
    expect(choice).toHaveTextContent('Всего 5');
    expect(choice).toHaveTextContent('Основное2');
    expect(choice).toHaveTextContent('Вспомогательное3');
    expect(choice).toHaveTextContent('1 тренировка · 1 / нед.');
    const detail = screen.getByRole('region', { name: 'Трицепс' });
    expect(detail.id).toBe(choice.getAttribute('aria-controls'));
    expect(within(detail).getByText('Нет данных для сравнения')).toBeVisible();
    expect(within(detail).getByText('Предыдущие 7 дней')).toBeVisible();
    expect(within(detail).getByText('Нет данных', { exact: true })).toBeVisible();
    expect(screen.getByText(/Значения групп не складываются/)).toBeVisible();
  });

  it('preserves selection by id across periods and falls back when that group disappears', () => {
    const first = group();
    const second = group({ muscle_id: 'chest', muscle_name: 'Грудные мышцы' });
    const { rerender } = render(
      <MuscleWorkloadDistribution analytics={analytics([first, second])} />,
    );
    const secondButton = screen.getByRole('button', { name: /Грудные мышцы/ });
    secondButton.focus();
    fireEvent.click(secondButton);
    expect(secondButton).toHaveFocus();
    expect(secondButton).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('region', { name: 'Грудные мышцы' })).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Трицепс' })).not.toBeInTheDocument();

    rerender(
      <MuscleWorkloadDistribution analytics={{ ...analytics([second, first]), period_days: 30 }} />,
    );
    expect(screen.getByRole('button', { name: /Грудные мышцы/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText('Текущие 30 дней')).toBeVisible();
    rerender(<MuscleWorkloadDistribution analytics={analytics([first])} />);
    expect(screen.getByRole('button', { name: /Трицепс/ })).toHaveAttribute('aria-pressed', 'true');
    expect(document.querySelectorAll('.muscle-distribution__detail')).toHaveLength(1);
  });

  it('keeps a current null distinct from a recorded zero and a zero delta', () => {
    const zero = group({
      current: period(0, 0, 0),
      previous: period(0, 0, 0),
      completed_set_count_change: 0,
      trend: 'unchanged',
    });
    const { rerender } = render(<MuscleWorkloadDistribution analytics={analytics([zero])} />);
    expect(screen.getByRole('button')).toHaveTextContent('Всего 0');
    expect(document.querySelectorAll('.muscle-distribution__track > i')).toHaveLength(0);
    expect(screen.getByText('Изменение: 0 подходов')).toBeVisible();
    rerender(
      <MuscleWorkloadDistribution
        analytics={analytics([group({ current: null, previous: period(3, 1, 1) })])}
      />,
    );
    expect(screen.getByRole('button')).toHaveTextContent('Нет данных');
    expect(screen.getByRole('button')).toHaveTextContent('Ранее: 3 подх.');
    expect(screen.getByRole('button')).not.toHaveTextContent('Всего 0');
    expect(screen.getByText('Нет данных за текущий период')).toBeVisible();
    expect(screen.getByText('Нет данных для сравнения')).toBeVisible();
  });

  it('distinguishes empty history from completed sets without muscle metadata', () => {
    const { rerender } = render(
      <MuscleWorkloadDistribution analytics={{ ...analytics([]), completed_set_count: 0 }} />,
    );
    expect(
      screen.getByRole('heading', { name: 'Нет записанных подходов', level: 4 }),
    ).toBeVisible();
    rerender(
      <MuscleWorkloadDistribution
        analytics={{ ...analytics([]), completed_sets_without_muscle_metadata: 7 }}
      />,
    );
    expect(
      screen.getByRole('heading', { name: 'Распределение пока недоступно', level: 4 }),
    ).toBeVisible();
    expect(screen.getByText('Неполные сведения о мышцах')).toBeVisible();
    expect(screen.getByText(/7 подходов без мышечных связей/)).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('preserves source roles, bounded history and the native session disclosure', () => {
    render(
      <MuscleWorkloadDistribution
        analytics={analytics([
          group({
            contributing_exercises: [
              {
                exercise_id: 11,
                exercise_title: 'Жим <script> лёжа',
                contribution_roles: ['primary', 'secondary'],
                completed_set_count: 5,
                performed_session_count: 1,
                history_truncated: true,
                sessions: [
                  {
                    workout_id: 4,
                    workout_exercise_id: 22,
                    performed_on: '2026-10-30',
                    completed_set_count: 5,
                    reps_recorded_sets: 0,
                    volume_recorded_sets: 0,
                    sets: [],
                  },
                ],
              },
            ],
          }),
        ])}
      />,
    );
    const source = document.querySelector<HTMLDetailsElement>('.muscle-distribution__source')!;
    expect(source).not.toHaveAttribute('open');
    expect(within(source).getByText('Основное участие · Вспомогательное участие')).toBeVisible();
    expect(within(source).getByText('Показана часть истории')).toBeVisible();
    fireEvent.click(within(source).getByText('Жим <script> лёжа'));
    expect(source).toHaveAttribute('open');
    expect(within(source).getByText(/30 окт.*5 подходов/)).toBeVisible();
    expect(document.querySelector('script')).toBeNull();
  });
});
