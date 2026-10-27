import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { TrainingAnalytics } from '../../../../src/shared/api/types';
import { MuscleWorkloadList } from '../../../../src/features/workouts/MuscleWorkload';

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
  return { muscle_group_workload: muscleGroupWorkload } as TrainingAnalytics;
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
