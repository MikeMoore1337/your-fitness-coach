import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ProgressReportPage from '../../../src/pages/reports/ProgressReportPage';
import { NavigationProvider } from '../../../src/shared/navigation/router';
import { makeProgressReportFixture } from '../../fixtures/progress-report';

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NavigationProvider>
      <QueryClientProvider client={queryClient}>
        <ProgressReportPage />
      </QueryClientProvider>
    </NavigationProvider>,
  );
}

function installApi(report = makeProgressReportFixture()) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).includes('/download-link')) {
      return new Response(
        JSON.stringify({
          url: 'https://app.your-fitness-coach.ru/api/v1/workouts/progress/report/file/signed',
          filename: 'progress-report-2026-08-01_2026-08-20.pdf',
          expires_at: '2026-08-29T19:05:00Z',
        }),
        { status: 200 },
      );
    }
    return new Response(JSON.stringify(report), { status: 200 });
  });
}

function makeBodyOnlyReport(summaryLineCount: 0 | 1 | 2) {
  const report = makeProgressReportFixture('empty');
  const populated = makeProgressReportFixture('full');
  const bodyTrend = populated.body.trends[0];
  if (summaryLineCount >= 1) {
    report.body = { ...report.body, trends: bodyTrend ? [bodyTrend] : [] };
  }
  if (summaryLineCount >= 2) {
    report.training = { ...report.training, planned_workouts: 1, completed_workouts: 1 };
  }
  return report;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '/app/report?period=days_30');
  Object.defineProperty(window, 'Telegram', { configurable: true, value: undefined });
});

describe('ProgressReportPage', () => {
  it.each([0, 1, 2] as const)(
    'renders exactly the factual summary items for the %s-line state',
    async (summaryLineCount) => {
      installApi(makeBodyOnlyReport(summaryLineCount));
      renderPage();

      await screen.findByRole('heading', { name: /Александр Петров/ });
      const summary = document.querySelector('.progress-report-factual-summary');
      expect(summary).not.toBeNull();
      expect(summary?.querySelectorAll('dl > div')).toHaveLength(summaryLineCount);
      expect(summary?.textContent).not.toContain('custom:');
    },
  );

  it('shows factual report sections and invokes browser print outside TMA', async () => {
    installApi();
    const print = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    renderPage();

    expect(await screen.findByRole('heading', { name: /Александр Константинович/ })).toBeVisible();
    expect(screen.getByText('84')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Фактическая сводка' })).toBeVisible();
    expect(screen.getAllByText('Живот').length).toBeGreaterThan(0);
    expect(screen.getByText(/Живот: 84 см/)).toBeVisible();
    expect(screen.getByRole('table', { name: 'Таблица замеров массы' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
    expect(screen.getByText(/заметки не включены в агрегаты, PDF и доступ тренера/)).toBeVisible();
    expect(screen.getByText(/Пропущенный или неполный день/)).toBeVisible();
    expect(screen.getByText(/не медицинская оценка/)).toBeVisible();
    expect(screen.getByText('Тренер', { exact: true })).toBeVisible();
    expect(screen.getByText(/статус: активна/)).toBeVisible();
    expect(screen.getByText('Рекомендация:', { exact: true })).toBeVisible();
    expect(document.querySelector('.progress-report-document')?.textContent).not.toContain(
      'adherence-v1',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Печать / Сохранить как PDF' }));
    expect(print).toHaveBeenCalledTimes(1);
  });

  it('validates and persists a custom period and managed client subject', async () => {
    window.history.replaceState(null, '', '/app/report?period=days_30&client_id=73');
    installApi();
    renderPage();
    await screen.findByRole('heading', { name: /Александр Константинович/ });

    fireEvent.click(screen.getByRole('tab', { name: 'Свой период' }));
    fireEvent.change(screen.getByLabelText('Начало'), { target: { value: '2026-08-01' } });
    fireEvent.change(screen.getByLabelText('Окончание'), { target: { value: '2026-08-20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Показать период' }));

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/coach/clients/73/progress-report?period=custom&date_from=2026-08-01&date_to=2026-08-20',
        expect.anything(),
      );
      expect(window.location.search).toContain('client_id=73');
      expect(window.location.search).toContain('date_from=2026-08-01');
    });
  });

  it('hands a short-lived PDF file to native Telegram download', async () => {
    window.history.replaceState(
      null,
      '',
      '/app/report?period=custom&date_from=2026-08-01&date_to=2026-08-20&client_id=73',
    );
    const downloadFile = vi.fn(
      (_params: { url: string; file_name: string }, callback: (accepted: boolean) => void) =>
        callback(true),
    );
    Object.defineProperty(window, 'Telegram', {
      configurable: true,
      value: { WebApp: { initData: 'signed-test-data', downloadFile } },
    });
    installApi();
    const print = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    renderPage();
    await screen.findByRole('heading', { name: /Александр Константинович/ });

    fireEvent.click(screen.getByRole('button', { name: 'Скачать PDF' }));

    await waitFor(() =>
      expect(downloadFile).toHaveBeenCalledWith(
        {
          url: 'https://app.your-fitness-coach.ru/api/v1/workouts/progress/report/file/signed',
          file_name: 'progress-report-2026-08-01_2026-08-20.pdf',
        },
        expect.any(Function),
      ),
    );
    expect(screen.getByText('Telegram открыл сохранение PDF.')).toBeVisible();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/coach/clients/73/progress-report/download-link?period=custom&date_from=2026-08-01&date_to=2026-08-20',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(print).not.toHaveBeenCalled();
  });

  it('keeps an actionable signed PDF link when native Telegram download is unavailable', async () => {
    Object.defineProperty(window, 'Telegram', {
      configurable: true,
      value: { WebApp: { initData: 'signed-test-data' } },
    });
    installApi();
    renderPage();
    await screen.findByRole('heading', { name: /Александр Константинович/ });

    fireEvent.click(screen.getByRole('button', { name: 'Скачать PDF' }));

    expect(await screen.findByText('Откройте готовый PDF по ссылке.')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Скачать PDF' })).toHaveAttribute(
      'href',
      'https://app.your-fitness-coach.ru/api/v1/workouts/progress/report/file/signed',
    );
  });
});
