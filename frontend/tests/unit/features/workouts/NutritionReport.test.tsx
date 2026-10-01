import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NutritionPeriodReport } from '../../../../src/features/workouts/NutritionReport';
import type { NutritionReport } from '../../../../src/shared/api/types';
import { NavigationProvider } from '../../../../src/shared/navigation/router';

function metric(average: number, minimum: number, maximum: number) {
  return { average, minimum, maximum, sample_days: 3 };
}

function comparison(actual: number, target: number) {
  return {
    average_actual: actual,
    average_target: target,
    average_deviation: actual - target,
    evaluated_days: 3,
  };
}

function makeReport(): NutritionReport {
  const days: NutritionReport['daily'] = [
    {
      diary_date: '2026-08-17',
      status: 'complete',
      is_current_day: false,
      calories: 2050,
      protein_g: 145,
      fat_g: 68,
      carbs_g: 210,
      target_calories: 2100,
      target_protein_g: 140,
      target_fat_g: 70,
      target_carbs_g: 220,
      calorie_deviation: -50,
      protein_deviation_g: 5,
      fat_deviation_g: -2,
      carbs_deviation_g: -10,
      within_calorie_tolerance: true,
      meets_protein_target: true,
      target_changed: false,
    },
    {
      diary_date: '2026-08-18',
      status: 'missing',
      is_current_day: false,
      target_calories: 2100,
      target_protein_g: 140,
      target_fat_g: 70,
      target_carbs_g: 220,
      target_changed: false,
    },
    {
      diary_date: '2026-08-19',
      status: 'complete',
      is_current_day: false,
      calories: 1900,
      protein_g: 132,
      fat_g: 62,
      carbs_g: 190,
      target_calories: 1950,
      target_protein_g: 135,
      target_fat_g: 65,
      target_carbs_g: 200,
      calorie_deviation: -50,
      protein_deviation_g: -3,
      fat_deviation_g: -3,
      carbs_deviation_g: -10,
      within_calorie_tolerance: true,
      meets_protein_target: false,
      target_changed: true,
    },
    {
      diary_date: '2026-08-20',
      status: 'incomplete',
      is_current_day: false,
      calories: 800,
      protein_g: 55,
      fat_g: 22,
      carbs_g: 90,
      target_calories: 1950,
      target_protein_g: 135,
      target_fat_g: 65,
      target_carbs_g: 200,
      target_changed: false,
    },
    {
      diary_date: '2026-08-21',
      status: 'fasted',
      is_current_day: false,
      calories: 0,
      protein_g: 0,
      fat_g: 0,
      carbs_g: 0,
      target_calories: 1950,
      target_protein_g: 135,
      target_fat_g: 65,
      target_carbs_g: 200,
      calorie_deviation: -1950,
      protein_deviation_g: -135,
      fat_deviation_g: -65,
      carbs_deviation_g: -200,
      within_calorie_tolerance: false,
      meets_protein_target: false,
      target_changed: false,
    },
    {
      diary_date: '2026-08-22',
      status: 'missing',
      is_current_day: false,
      target_calories: 1950,
      target_protein_g: 135,
      target_fat_g: 65,
      target_carbs_g: 200,
      target_changed: false,
    },
    {
      diary_date: '2026-08-23',
      status: 'missing',
      is_current_day: true,
      target_calories: 1950,
      target_protein_g: 135,
      target_fat_g: 65,
      target_carbs_g: 200,
      target_changed: false,
    },
  ];
  return {
    period: 'days_7',
    period_start: '2026-08-17',
    period_end: '2026-08-23',
    timezone: 'Europe/Moscow',
    summary: {
      logged_days: 3,
      eligible_days: 7,
      coverage_percent: 42.9,
      complete_days: 2,
      incomplete_days: 1,
      fasted_days: 1,
      missing_days: 3,
      current_day_status: 'missing',
      calories: metric(1316.7, 0, 2050),
      protein_g: metric(92.3, 0, 145),
      fat_g: metric(43.3, 0, 68),
      carbs_g: metric(133.3, 0, 210),
      calorie_comparison: comparison(1316.7, 2000),
      protein_comparison: comparison(92.3, 136.7),
      fat_comparison: comparison(43.3, 66.7),
      carbs_comparison: comparison(133.3, 206.7),
      days_within_calorie_tolerance: 2,
      calorie_tolerance_evaluated_days: 3,
      days_meeting_protein_target: 1,
      protein_target_evaluated_days: 3,
      exact_entry_count: 0,
      approximate_entry_count: 0,
      partial_entry_count: 0,
    },
    daily: days,
    target_changes: [
      {
        effective_from: '2026-08-19',
        source: 'adaptive',
        calories: 1950,
        protein_g: 135,
        fat_g: 65,
        carbs_g: 200,
      },
    ],
  };
}

function installApi(report = makeReport()) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input);
    if (path.includes('/nutrition-report')) {
      const period = new URL(path, 'http://test.local').searchParams.get('period');
      return new Response(JSON.stringify({ ...report, period: period ?? report.period }), {
        status: 200,
      });
    }
    return new Response(JSON.stringify({ detail: 'Unexpected request' }), { status: 500 });
  });
}

function renderReport(clientId?: number) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <NavigationProvider>
      <QueryClientProvider client={queryClient}>
        <NutritionPeriodReport clientId={clientId} />
      </QueryClientProvider>
    </NavigationProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/app?section=progress');
});

describe('NutritionPeriodReport', () => {
  it('shows truthful coverage, historical targets, chart and accessible day alternative', async () => {
    window.history.replaceState(null, '', '/app?section=progress&nutrition_period=days_7');
    installApi();
    renderReport();

    expect(await screen.findByText('Заполнено 3 из 7 дней')).toBeVisible();
    expect(
      screen.getByText('Средние значения рассчитаны только по заполненным дням.'),
    ).toBeVisible();
    expect(screen.getByRole('img', { name: /Калории по дням за период/ })).toBeVisible();
    expect(screen.getByText(/Точки — фактические значения/)).toBeVisible();
    expect(screen.getByText('Принятая адаптация')).toBeVisible();
    expect(screen.getAllByText('Новая цель').length).toBeGreaterThan(0);
    expect(screen.getByText('2 из 3')).toBeVisible();
    expect(screen.getByText('1 из 3')).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Открыть дневник за 23 авг. 2026 г.' }),
    ).toHaveAttribute('href', expect.stringContaining('return_to='));
    expect(screen.getByText(/не оценивает качество рациона/)).toBeVisible();
  });

  it('requests presets and applies a validated custom period while preserving it in the URL', async () => {
    installApi();
    renderReport();
    await screen.findByText('Заполнено 3 из 7 дней');

    fireEvent.click(screen.getByRole('tab', { name: 'Этот месяц' }));
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/workouts/progress/nutrition-report?period=current_month',
        expect.anything(),
      ),
    );

    fireEvent.click(screen.getByRole('tab', { name: 'Свой период' }));
    fireEvent.change(screen.getByLabelText('Начало периода'), {
      target: { value: '2026-08-01' },
    });
    fireEvent.change(screen.getByLabelText('Конец периода'), {
      target: { value: '2026-08-20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Показать период' }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/workouts/progress/nutrition-report?period=custom&date_from=2026-08-01&date_to=2026-08-20',
        expect.anything(),
      );
      expect(window.location.search).toContain('nutrition_period=custom');
      expect(window.location.search).toContain('nutrition_from=2026-08-01');
    });
  });

  it('keeps no-data distinct from zero and offers one real next step', async () => {
    const report = makeReport();
    report.summary.logged_days = 0;
    report.summary.complete_days = 0;
    report.summary.fasted_days = 0;
    report.summary.coverage_percent = 0;
    report.daily = report.daily.map((point) => ({
      diary_date: point.diary_date,
      status: 'missing',
      is_current_day: point.is_current_day,
      target_changed: false,
    }));
    report.target_changes = [];
    installApi(report);
    renderReport();

    expect(await screen.findByText('Нет заполненных дней за период')).toBeVisible();
    expect(screen.queryByText('0 ккал')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Открыть дневник питания' })).toHaveAttribute(
      'href',
      '/app?section=nutrition',
    );
  });

  it('uses the managed-client endpoint without linking into the trainer diary', async () => {
    installApi();
    renderReport(73);

    expect(await screen.findByText('Заполнено 3 из 7 дней')).toBeVisible();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/coach/clients/73/nutrition-report?period=days_30',
      expect.anything(),
    );
    expect(screen.queryByRole('link', { name: /Открыть дневник/ })).not.toBeInTheDocument();
  });
});
