import { expect, test, type Page } from '@playwright/test';
import { makeProgressReportFixture } from '../fixtures/progress-report';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type ReportState = Parameters<typeof makeProgressReportFixture>[0];

async function installReportApi(page: Page, state: ReportState = 'full') {
  await page.route(
    /\/api\/v1\/(?:workouts\/progress\/report|coach\/clients\/\d+\/progress-report)/,
    async (route) => {
      const report = makeProgressReportFixture(state);
      const url = new URL(route.request().url());
      if (route.request().method() === 'POST' && url.pathname.endsWith('/download-link')) {
        await route.fulfill({
          json: {
            url: `${url.origin}/api/v1/workouts/progress/report/file/signed-e2e`,
            filename: 'progress-report-2026-07-26_2026-08-24.pdf',
            expires_at: '2026-08-29T19:05:00Z',
          },
        });
        return;
      }
      report.period = (url.searchParams.get('period') ?? report.period) as typeof report.period;
      if (report.period === 'custom') {
        report.period_start = url.searchParams.get('date_from') ?? report.period_start;
        report.period_end = url.searchParams.get('date_to') ?? report.period_end;
      }
      if (url.pathname.includes('/coach/clients/')) report.subject.role = 'client';
      await route.fulfill({ json: report });
    },
  );
}

test('keeps custom date fields aligned while validation is visible', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportApi(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app/report?period=days_30');

  await page.getByRole('tab', { name: 'Свой период' }).click();
  const dateFrom = page.locator('#report-date-from');
  const dateTo = page.locator('#report-date-to');
  await expect(dateFrom).toBeVisible();
  await expect(dateTo).toBeVisible();
  await expect(page.getByText('Укажите обе даты.', { exact: true })).toBeVisible();

  const [fromBox, toBox] = await Promise.all([dateFrom.boundingBox(), dateTo.boundingBox()]);
  expect(fromBox).not.toBeNull();
  expect(toBox).not.toBeNull();
  expect(Math.abs(fromBox!.y - toBox!.y)).toBeLessThanOrEqual(1);
  expect(Math.abs(fromBox!.height - toBox!.height)).toBeLessThanOrEqual(1);
});

test('hides trainer handoff section when the client has no assigned trainer', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportApi(page);
  await page.goto('/app/report?period=days_30');

  await expect(page.getByRole('heading', { name: 'Факты за период' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Отправить отчёт текущему тренеру' })).toHaveCount(
    0,
  );
  await expect(page.getByText('Нет доступного текущего тренера', { exact: true })).toHaveCount(0);
});

test('full report keeps a mobile-first preview and print layout', async ({
  page,
  browserName,
}, testInfo) => {
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await installPlatformApi(page, { browserSession: true });
  await installReportApi(page);

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app/report?period=days_30');
  await expect(page.getByRole('heading', { name: /Александр Константинович/ })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Таблица замеров массы' })).toBeVisible();
  await expect(page.getByText('Тренер', { exact: true })).toBeVisible();
  await expect(page.getByText('Рекомендация:', { exact: true })).toBeVisible();
  const reportText = await page.locator('.progress-report-document').innerText();
  expect(reportText).not.toContain('active');
  expect(reportText).not.toContain('adherence-v1');
  expect(reportText).not.toContain('trainer');
  await expect(page.locator('.progress-report-confidence .data-confidence')).toHaveCount(3);
  await expect(
    page.locator(
      '.progress-report-document > .progress-report-overview + .progress-report-confidence + .progress-report-controls',
    ),
  ).toHaveCount(1);
  await expect(
    page.locator(
      '.progress-report-document > .progress-report-controls ~ .progress-report-section #report-training-title',
    ),
  ).toHaveCount(1);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: testInfo.outputPath('desktop-1280-dark-preview.png'),
  });
  await page.screenshot({
    path: testInfo.outputPath('desktop-1280-dark-full.png'),
    fullPage: true,
  });

  await page.setViewportSize({ width: 360, height: 800 });
  await expectNoHorizontalOverflow(page);
  const printButton = page.getByRole('button', { name: 'Печать / Сохранить как PDF' });
  await expect(printButton).toBeVisible();
  expect((await printButton.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  await expect(page.locator('.progress-report-macros-heading')).toHaveCSS('white-space', 'nowrap');
  await page.screenshot({
    path: testInfo.outputPath('mobile-web-360-dark-preview.png'),
  });
  await page.screenshot({
    path: testInfo.outputPath('mobile-web-360-dark-full.png'),
    fullPage: true,
  });
  await page.locator('.progress-report-macros-heading').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-67/mobile-web-360-nutrition-targets.png',
  });

  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.report-screen-only').first()).toBeHidden();
  await expect(page.locator('.progress-report-print-header')).toHaveCount(4);
  await expect(page.locator('.progress-report-print-header').first()).toBeVisible();
  await expect(page.locator('.progress-report-print-header').first()).toHaveCSS(
    'position',
    'static',
  );
  await expect(page.locator('.progress-report-print-header').first()).toHaveCSS(
    'align-items',
    'center',
  );
  await expect(page.locator('.progress-report-print-footer')).toHaveCSS(
    'border-top-style',
    'solid',
  );
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await page
    .locator('.data-viz-chart')
    .first()
    .screenshot({
      path: testInfo.outputPath('print-grayscale-chart-and-table.png'),
    });
  if (browserName === 'chromium') {
    const pdf = await page.pdf({
      path: testInfo.outputPath('progress-report.pdf'),
      format: 'A4',
      printBackground: true,
      preferCSSPageSize: true,
    });
    expect(pdf.subarray(0, 4).toString()).toBe('%PDF');
    expect(pdf.length).toBeGreaterThan(10_000);
  }
});

for (const state of ['partial', 'empty'] as const) {
  test(`${state} data stays factual and printable`, async ({ page }) => {
    await installPlatformApi(page, { browserSession: true });
    await installReportApi(page, state);
    await page.goto('/app/report?period=days_90');

    await expect(page.getByRole('heading', { name: 'Александр Петров' })).toBeVisible();
    await expect(page.getByText(/не медицинская оценка/)).toBeVisible();
    await expect(page.getByText(/не заполняет пропуски/)).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-67/desktop-${state}-preview.png`,
    });
    if (state === 'empty') {
      await expect(page.getByText('Нет замеров массы за период', { exact: true })).toBeVisible();
      await expect(page.getByText('Отсутствующие дни не интерполируются.')).toBeVisible();
      await expect(page.getByText('Активной программы на дату формирования нет.')).toBeVisible();
    }
  });
}

test('dark TMA hands an exact short-lived PDF to native download', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramHarness(page, { colorScheme: 'dark' });
  const tma = new TelegramHarness(page);
  await installPlatformApi(page);
  await installReportApi(page);

  await page.goto('/app/report?period=custom&date_from=2026-08-01&date_to=2026-08-20&client_id=73');
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.getByRole('heading', { name: /Александр Константинович/ })).toBeVisible();
  await page.getByRole('button', { name: 'Скачать PDF' }).click();
  await expect(page.getByText('Telegram открыл сохранение PDF.')).toBeVisible();
  await expect
    .poll(async () => (await tma.state()).downloads)
    .toEqual([
      {
        url: `${new URL(page.url()).origin}/api/v1/workouts/progress/report/file/signed-e2e`,
        fileName: 'progress-report-2026-07-26_2026-08-24.pdf',
      },
    ]);
  await expect(page).toHaveURL(/period=custom/);
  await expect(page).toHaveURL(/date_from=2026-08-01/);
  await expect(page).toHaveURL(/client_id=73/);
  await expectNoHorizontalOverflow(page);
  await page.locator('.data-viz-chart').first().scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-69b/tma-390x844-dark-chart.png',
  });
  await page.getByText('Telegram открыл сохранение PDF.').scrollIntoViewIfNeeded();
  await page.screenshot({
    path: '../.artifacts/screenshots/task-113A-round-4/tma-390-dark-pdf-download-preview.png',
  });
  await page.screenshot({
    path: '../.artifacts/screenshots/task-113A-round-4/tma-390-dark-pdf-download.png',
    fullPage: true,
  });
});
