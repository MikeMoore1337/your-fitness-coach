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

it('shows facts and selects an unknown day in the month calendar', () => {
  render(<ActivityHeatmap data={data} />);
  expect(screen.getByText(/История неполная/)).toBeInTheDocument();
  expect(screen.getByText(/рабочие подходы — 4/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /январь/ }));
  fireEvent.click(screen.getByRole('button', { name: /^1 января 2026/ }));
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

it('resets the chosen day and expanded month across year changes and excludes future dates', () => {
  const view = render(<ActivityHeatmap data={data} year={2026} />);
  fireEvent.click(screen.getByRole('button', { name: /январь/ }));
  fireEvent.click(screen.getByRole('button', { name: /^1 января 2026/ }));
  view.rerender(
    <ActivityHeatmap
      year={2024}
      data={{ ...data, days: [{ date: '2024-12-31', completed_workouts: 2, working_sets: 6 }] }}
    />,
  );
  expect(screen.queryByRole('region', { name: /Выбор дня/ })).not.toBeInTheDocument();
  expect(screen.getByText(/рабочие подходы — 6/)).toBeInTheDocument();
  view.rerender(
    <ActivityHeatmap
      year={2026}
      data={{
        ...data,
        days: [
          ...data.days,
          { date: '2026-01-03', is_future: true, completed_workouts: null, working_sets: null },
        ],
      }}
    />,
  );
  expect(screen.getByText(/рабочие подходы — 4/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /январь/ }));
  expect(screen.getByRole('button', { name: /^3 января 2026/ })).toBeDisabled();
});
