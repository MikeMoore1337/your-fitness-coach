import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ActivityHeatmap } from '../../src/features/workouts/ActivityHeatmap';

const data = {
  timezone: 'Europe/Moscow',
  history_complete: false,
  undated_workouts: 1,
  days: [
    { date: '2026-01-01', completed_workouts: null, working_sets: null },
    { date: '2026-01-02', completed_workouts: 1, working_sets: 4 },
  ],
};

afterEach(cleanup);

it.each(['year', 'months'] as const)('shows facts and unknown days in %s view', (variant) => {
  render(<ActivityHeatmap data={data} variant={variant} />);
  expect(screen.getByText(/История неполная/)).toBeInTheDocument();
  expect(screen.getByText(/рабочие подходы — 4/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Выберите день'), { target: { value: '2026-01-01' } });
  expect(screen.getByText(/тренировки — Нет данных/)).toBeInTheDocument();
  expect(screen.getByRole('table')).toHaveTextContent('Нет данных');
});

it('shows an empty state', () => {
  render(<ActivityHeatmap data={{ ...data, days: [] }} />);
  expect(screen.getByText('Данных об активности пока нет.')).toBeInTheDocument();
});

it('distinguishes a known empty history from unknown days', () => {
  render(
    <ActivityHeatmap
      data={{
        ...data,
        history_complete: true,
        undated_workouts: 0,
        days: [{ date: '2026-01-01', completed_workouts: 0, working_sets: 0 }],
      }}
    />,
  );
  expect(screen.getByText('За этот период нет завершённых тренировок.')).toBeInTheDocument();
});

it('requests the selected calendar year', () => {
  const onYearChange = vi.fn();
  render(<ActivityHeatmap data={data} year={2026} onYearChange={onYearChange} />);
  expect(screen.getByRole('heading', { name: 'Активность за 2026 год' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Год'), { target: { value: '2024' } });
  expect(onYearChange).toHaveBeenCalledWith(2024);
});
