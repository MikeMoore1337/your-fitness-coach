import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import {
  DataConfidence,
  dataConfidenceBasis,
  type DataConfidenceSignal,
} from '../../../../src/shared/ui/DataConfidence';

function signal(
  status: DataConfidenceSignal['status'],
  counters: Record<string, number>,
  reasonKeys: string[] = status === 'sufficient' ? ['thresholds_met'] : ['too_few_points'],
): DataConfidenceSignal {
  return {
    status,
    counters,
    reason_keys: reasonKeys,
  };
}

afterEach(cleanup);

describe('DataConfidence', () => {
  it('prefixes a report status with its explicit section label', () => {
    render(
      <DataConfidence
        label="Тренировки"
        kind="training"
        signal={signal('sufficient', {
          working_set_count: 8,
          workout_session_count: 3,
        })}
      />,
    );

    expect(screen.getByText('Тренировки — Данных достаточно для оценки')).toBeInTheDocument();
  });

  it('keeps the plain-language status before a concrete nutrition basis and neutral next step', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DataConfidence
        kind="nutrition"
        signal={signal('limited', { logged_day_count: 4, eligible_day_count: 14 })}
        action={<a href="/app?section=nutrition">Дополнить дневник</a>}
      />,
    );

    expect(screen.getByText('Вывод пока предварительный')).toBeInTheDocument();
    expect(screen.getByText('За период дневник заполнен за 4 из 14 дней.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Дополнить дневник' })).toBeInTheDocument();
    expect(container.querySelector('.badge')).not.toBeInTheDocument();

    const disclosure = screen.getByText('Почему такой вывод').closest('details');
    await user.click(screen.getByText('Почему такой вывод'));
    expect(disclosure).toHaveAttribute('open');
    expect(screen.getByText(/Пропущенные и неполные дни не считаются нулём/)).toBeVisible();
  });

  it('renders stale as a distinct textual state without an outdated action', () => {
    render(
      <DataConfidence
        isStale
        kind="training"
        signal={signal('sufficient', {
          working_set_count: 8,
          workout_session_count: 3,
          required_working_set_count: 6,
          required_workout_session_count: 2,
        })}
        action={<a href="/app?section=today">Открыть тренировку</a>}
      />,
    );

    const region = screen.getByLabelText(/Достаточно ли данных: Показана сохранённая оценка/);
    expect(region).toHaveAttribute('data-confidence-state', 'stale');
    expect(screen.getByText('Показана сохранённая оценка')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Открыть тренировку' })).not.toBeInTheDocument();
  });

  it('formats deterministic bases for body, training and calibration metadata', () => {
    expect(
      dataConfidenceBasis(
        'weight',
        signal('limited', {
          point_count: 2,
          span_days: 9,
          required_point_count: 3,
          required_span_days: 14,
        }),
      ),
    ).toBe('Сейчас есть 2 замера за 9 дней; минимум — 3 замера за 14 дней.');
    expect(
      dataConfidenceBasis(
        'anthropometry',
        signal(
          'insufficient',
          {
            maximum_point_count: 0,
            maximum_span_days: 0,
            required_point_count_per_metric: 3,
            required_span_days_per_metric: 14,
          },
          ['no_anthropometry_measurements'],
        ),
      ),
    ).toBe(
      'Пока нет замеров окружностей; для оценки нужны повторные замеры одной и той же окружности.',
    );
    expect(
      dataConfidenceBasis(
        'training',
        signal('limited', {
          working_set_count: 4,
          workout_session_count: 1,
          required_working_set_count: 6,
          required_workout_session_count: 2,
        }),
      ),
    ).toBe('Учтено 4 рабочих подхода в 1 тренировке; минимум — 6 подходов в 2 тренировках.');
    expect(
      dataConfidenceBasis(
        'calibration',
        signal('insufficient', {
          logged_day_count: 4,
          eligible_day_count: 28,
          first_window_weight_point_count: 1,
          last_window_weight_point_count: 1,
        }),
      ),
    ).toBe(
      'Дневник заполнен за 4 из 28 завершённых дней. Замеров массы в начале и конце окна: 1 и 1.',
    );
  });

  it('does not combine anthropometry maxima that can belong to different metrics', () => {
    const sharedCounters = {
      measured_metric_count: 2,
      sufficient_metric_count: 0,
      maximum_point_count: 3,
      maximum_span_days: 30,
      required_point_count_per_metric: 3,
      required_span_days_per_metric: 14,
    };

    const shortSpan = dataConfidenceBasis(
      'anthropometry',
      signal('limited', sharedCounters, ['timespan_too_short']),
    );
    expect(shortSpan).toBe('Ни одна окружность с 3 замерами пока не охватывает период в 14 дней.');
    expect(shortSpan).not.toContain('3 замера за 30 дней');

    expect(
      dataConfidenceBasis(
        'anthropometry',
        signal('limited', { ...sharedCounters, maximum_point_count: 2 }, ['too_few_points']),
      ),
    ).toBe(
      'В самой заполненной окружности — 2 замера; для оценки одной окружности нужно минимум 3 замера.',
    );

    expect(
      dataConfidenceBasis(
        'anthropometry',
        signal('sufficient', { ...sharedCounters, sufficient_metric_count: 1 }, ['thresholds_met']),
      ),
    ).toBe('1 окружность достигла порога: 3 замера за период не короче 14 дней.');
  });
});
