import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
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
  expect(screen.getByText('История неполная', { exact: true })).toBeInTheDocument();
  expect(screen.getByText(/рабочие подходы — 4/)).toBeInTheDocument();
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
  expect(screen.getByRole('heading', { name: 'Активность' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Год'), { target: { value: '2024' } });
  expect(onYearChange).toHaveBeenCalledWith(2024);
});

it('resets the chosen day across year changes and excludes future dates', () => {
  const view = render(<ActivityHeatmap data={data} year={2026} />);
  fireEvent.click(
    document.querySelector('.activity-heatmap__desktop button[data-date="2026-01-01"]')!,
  );
  view.rerender(
    <ActivityHeatmap
      year={2024}
      data={{ ...data, days: [{ date: '2024-12-31', completed_workouts: 2, working_sets: 6 }] }}
    />,
  );
  expect(
    document.querySelector('.activity-heatmap__desktop button[data-date="2024-12-31"]'),
  ).toHaveAttribute('aria-pressed', 'true');
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

it.each([
  [2023, 365, 53],
  [2024, 366, 53],
  [2012, 366, 54],
])('keeps every date in %i with %i days and %i calendar columns', (year, count, weeks) => {
  const days = Array.from({ length: count }, (_, i) => ({
    date: new Date(Date.UTC(year, 0, i + 1)).toISOString().slice(0, 10),
    completed_workouts: 0,
    working_sets: 0,
  }));
  render(<ActivityHeatmap year={year} data={{ ...data, days }} />);
  const grid = screen.getByRole('grid');
  expect(grid).toHaveAttribute('aria-colcount', String(weeks + 1));
  expect(grid.querySelectorAll('button[data-date]')).toHaveLength(count);
  expect(grid.querySelector(`button[data-date="${year}-01-01"]`)).toBeInTheDocument();
  expect(grid.querySelector(`button[data-date="${year}-12-31"]`)).toBeInTheDocument();
  expect(grid.querySelectorAll('button[tabindex="0"]')).toHaveLength(1);
});
it('navigates the year grid by weeks, selects with one tab stop and shows factual hover text', () => {
  const days = Array.from({ length: 366 }, (_, i) => ({
    date: new Date(Date.UTC(2024, 0, i + 1)).toISOString().slice(0, 10),
    completed_workouts: i === 0 ? 1 : null,
    working_sets: i === 0 ? 4 : null,
  }));
  render(<ActivityHeatmap year={2024} data={{ ...data, days }} />);
  const grid = screen.getByRole('grid');
  const first = grid.querySelector<HTMLButtonElement>('button[data-date="2024-01-01"]')!;
  fireEvent.mouseEnter(first.parentElement!);
  expect(screen.getByRole('tooltip')).toHaveTextContent('рабочие подходы — 4');
  fireEvent.click(first);
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  expect(first).toHaveAttribute('aria-pressed', 'true');
  fireEvent.keyDown(first, { key: 'ArrowRight' });
  expect(grid.querySelector('button[data-date="2024-01-08"]')).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
  expect(grid.querySelector('button[data-date="2024-01-09"]')).toHaveFocus();
  fireEvent.keyDown(document.activeElement!, { key: 'End', ctrlKey: true });
  expect(grid.querySelector('button[data-date="2024-12-31"]')).toHaveFocus();
  expect(grid.querySelectorAll('button[tabindex="0"]')).toHaveLength(1);
  fireEvent.keyDown(document.activeElement!, { key: 'Home', ctrlKey: true });
  expect(first).toHaveFocus();
});

it('keeps known facts visible when only one activity value is unknown', () => {
  render(
    <ActivityHeatmap
      data={{
        ...data,
        days: [{ date: '2026-01-02', completed_workouts: 1, working_sets: null }],
      }}
    />,
  );
  const details = screen.getByLabelText('Данные выбранного дня');
  expect(within(details).getByText('1')).toBeInTheDocument();
  expect(within(details).getByText('Нет данных')).toBeInTheDocument();
  expect(details).toHaveAttribute('aria-live', 'polite');
});

it('explains fully unknown days and preserves confirmed zero', () => {
  const view = render(
    <ActivityHeatmap
      data={{
        ...data,
        days: [{ date: '2026-01-01', completed_workouts: null, working_sets: null }],
      }}
    />,
  );
  expect(screen.getByLabelText('Данные выбранного дня')).toHaveTextContent(
    'Нет достоверных данных за этот день.',
  );
  view.rerender(
    <ActivityHeatmap
      data={{ ...data, days: [{ date: '2026-01-01', completed_workouts: 0, working_sets: 0 }] }}
    />,
  );
  expect(within(screen.getByLabelText('Данные выбранного дня')).getAllByText('0')).toHaveLength(2);
});
