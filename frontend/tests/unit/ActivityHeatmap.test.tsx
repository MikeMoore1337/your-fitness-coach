import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
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

beforeEach(() =>
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  ),
);
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('shows facts and selects an unknown day in the month calendar', () => {
  render(<ActivityHeatmap data={data} />);
  expect(screen.getByText(/История неполная/)).toBeInTheDocument();
  expect(screen.getByText(/рабочие подходы — 4/)).toBeInTheDocument();
  fireEvent.click(document.querySelector('.activity-heatmap__month-button')!);
  fireEvent.click(
    document.querySelector('.activity-heatmap__desktop button[data-date="2026-01-01"]')!,
  );
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
  fireEvent.click(document.querySelector('.activity-heatmap__month-button')!);
  fireEvent.click(
    document.querySelector('.activity-heatmap__desktop button[data-date="2026-01-01"]')!,
  );
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
  fireEvent.click(document.querySelector('.activity-heatmap__month-button')!);
  expect(
    document.querySelector('.activity-heatmap__desktop button[data-date="2026-01-03"]')!,
  ).toBeDisabled();
});

it('opens the account current month and resets past years to January', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-04-01T00:30:00Z'));
  const calendarData = (year: number) => ({
    ...data,
    timezone: 'America/Los_Angeles',
    days: Array.from({ length: 365 }, (_, i) => ({
      date: new Date(Date.UTC(year, 0, i + 1)).toISOString().slice(0, 10),
      completed_workouts: null,
      working_sets: null,
    })),
  });
  const view = render(<ActivityHeatmap year={2026} data={calendarData(2026)} />);
  expect(document.querySelector('.activity-heatmap__month-nav h3')).toHaveTextContent('март 2026');
  expect(document.querySelectorAll('.activity-heatmap__slide')).toHaveLength(12);
  expect(document.querySelectorAll('.activity-heatmap__slide:not([inert])')).toHaveLength(1);
  view.rerender(<ActivityHeatmap year={2025} data={calendarData(2025)} />);
  expect(document.querySelector('.activity-heatmap__month-nav h3')).toHaveTextContent(
    'январь 2025',
  );
});

it.each([true, false])('respects reduced motion %s for month buttons', (reduce) => {
  vi.stubGlobal('matchMedia', () => ({ matches: reduce }));
  render(
    <ActivityHeatmap
      data={{
        ...data,
        days: [...data.days, { date: '2026-02-01', completed_workouts: 0, working_sets: 0 }],
      }}
    />,
  );
  fireEvent.click(screen.getByLabelText('Следующий месяц'));
  expect(HTMLElement.prototype.scrollTo).toHaveBeenLastCalledWith(
    expect.objectContaining({ behavior: reduce ? 'instant' : 'smooth' }),
  );
});

it('keeps the account current year selectable across the UTC year boundary', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-12-31T12:30:00Z'));
  render(
    <ActivityHeatmap
      year={2027}
      onYearChange={vi.fn()}
      data={{
        timezone: 'Pacific/Kiritimati',
        history_complete: true,
        undated_workouts: 0,
        days: [{ date: '2027-01-01', completed_workouts: 0, working_sets: 0 }],
      }}
    />,
  );
  expect(screen.getByLabelText('Год')).toHaveValue('2027');
  expect(document.querySelector('.activity-heatmap__month-nav h3')).toHaveTextContent(
    'январь 2027',
  );
});
