import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  formatWeekRange,
  TRAINING_WEEK_LEGEND,
  WeekStrip,
} from '../../../../src/shared/ui/WeekStrip';

vi.mock('../../../../src/shared/navigation/router', () => ({
  AppLink: ({ to, children, ...props }: React.ComponentProps<'a'> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe('WeekStrip', () => {
  it('supports an exact rolling seven-day range for report contexts', () => {
    render(
      <WeekStrip
        anchorDate="2026-08-23"
        ariaLabel="Неделя отчёта"
        mode="overview"
        rangeStart="2026-08-17"
        title="Дни отчёта"
        today="2026-08-23"
      />,
    );

    expect(screen.getByText('17 — 23 авг.')).toBeVisible();
    expect(screen.getByLabelText(/понедельник, 17 августа/)).toBeVisible();
    expect(screen.getByLabelText(/воскресенье, 23 августа, сегодня/)).toBeVisible();
  });

  it('separates the selected diary date from today and navigates by week', () => {
    const onSelect = vi.fn();
    const onPrevious = vi.fn();
    render(
      <WeekStrip
        anchorDate="2026-08-20"
        ariaLabel="Неделя дневника"
        isDateDisabled={(date) => date > '2026-08-23'}
        mode="picker"
        navigation={{
          nextDisabled: true,
          onNext: vi.fn(),
          onPrevious,
        }}
        onSelect={onSelect}
        selectedDate="2026-08-20"
        title="Эта неделя"
        today="2026-08-23"
      />,
    );

    const week = screen.getByRole('navigation', { name: 'Неделя дневника' });
    const selected = within(week).getByRole('button', { name: /20 августа.*выбрано/i });
    const today = within(week).getByRole('button', { name: /23 августа.*сегодня/i });
    expect(selected).toHaveAttribute('aria-pressed', 'true');
    expect(selected).not.toHaveAttribute('aria-current');
    expect(today).toHaveAttribute('aria-current', 'date');
    expect(today).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Следующая неделя' })).toBeDisabled();

    fireEvent.click(today);
    fireEvent.click(screen.getByRole('button', { name: 'Предыдущая неделя' }));
    expect(onSelect).toHaveBeenCalledWith('2026-08-23');
    expect(onPrevious).toHaveBeenCalledOnce();
  });

  it('renders overview statuses and only exposes configured days as links', () => {
    const { container } = render(
      <WeekStrip
        anchorDate="2026-08-20"
        ariaLabel="Эта неделя"
        getDayMeta={(date) =>
          date === '2026-08-18'
            ? {
                link: {
                  label: 'Открыть тренировку Силовая база',
                  to: '/app?section=progress&workout_id=42',
                },
                activities: [{ key: 'strength', label: 'Силовая' }],
                status: { key: 'completed', label: 'Выполнено' },
              }
            : {}
        }
        mode="overview"
        legend={TRAINING_WEEK_LEGEND}
        title="Эта неделя"
        today="2026-08-20"
      />,
    );

    expect(screen.getByRole('region', { name: 'Эта неделя' })).toBeInTheDocument();
    const legendSummary = screen.getByText('Обозначения').closest('summary');
    const legend = container.querySelector<HTMLElement>('.week-strip__legend');
    expect(legend).not.toBeNull();
    expect(legendSummary?.closest('details')).not.toHaveAttribute('open');
    expect(legend!).not.toBeVisible();
    fireEvent.click(legendSummary!);
    expect(legendSummary?.closest('details')).toHaveAttribute('open');
    expect(screen.getByRole('list', { name: 'Обозначения недели' })).toBeVisible();
    expect(within(legend!).getByText('Силовая')).toBeVisible();
    expect(within(legend!).getByText('Кардио')).toBeVisible();
    expect(within(legend!).getByText('Отдых')).toBeVisible();
    expect(within(legend!).getByText('Выполнено')).toBeVisible();
    expect(container.querySelectorAll('.week-strip__pictogram')).not.toHaveLength(0);
    expect(
      container.querySelector('[data-pictogram="strength"] [data-icon="week-strength"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-pictogram="planned"] [data-icon="week-planned"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-pictogram="in-progress"] [data-icon="week-in-progress"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        '[data-icon="week-planned"] img[src="/assets/icons/action-week-planned-dark.png"]',
      ),
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        '[data-icon="week-in-progress"] img[src="/assets/icons/action-week-in-progress-dark.png"]',
      ),
    ).toBeInTheDocument();
    expect(
      container.querySelector(
        '[data-icon="week-skipped"] img[src="/assets/icons/action-week-skipped-dark.png"]',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Выполнено.*Открыть тренировку/i })).toHaveAttribute(
      'href',
      '/app?section=progress&workout_id=42',
    );
    expect(screen.getByRole('group', { name: /20 августа.*сегодня/i })).toHaveAttribute(
      'aria-current',
      'date',
    );
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('formats cross-month and cross-year ranges without losing context', () => {
    expect(formatWeekRange(['2026-08-31', '2026-09-06'])).toBe('31 авг. — 6 сент.');
    expect(formatWeekRange(['2026-12-28', '2027-01-03'])).toBe('28 дек. 2026 г. — 3 янв. 2027 г.');
  });
});
