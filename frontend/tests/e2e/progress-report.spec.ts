import { expect, test, type Page } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  assertCanonicalProgressReportInvariants,
  canonicalFacts,
  makeCanonicalProgressReportFixture,
  makeProgressReportFixture,
} from '../fixtures/progress-report';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type ReportState = Parameters<typeof makeProgressReportFixture>[0];

function extractPdfText(pdfPath: string): string {
  const repositoryRoot = resolve(process.cwd(), '..');
  const result = spawnSync(
    process.execPath,
    [
      resolve(repositoryRoot, 'scripts/run_python.mjs'),
      resolve(repositoryRoot, 'scripts/extract_pdf_text.py'),
      pdfPath,
    ],
    { cwd: repositoryRoot, encoding: 'utf8' },
  );
  expect(result.status, result.stderr || 'PDF text extractor failed').toBe(0);
  return result.stdout;
}

function compactPdfText(value: string): string {
  return value.replace(/\s+/g, '');
}

function browserDate(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  }).format(new Date(`${value}T12:00:00`));
}

function browserNumber(value: number): string {
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value);
}

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
  await expect(page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true })).toBeVisible();
  await expect(page.locator('.progress-report-document')).toContainText('Александр Константинович');
  await expect(page.getByRole('table', { name: 'Таблица замеров массы' })).toBeVisible();
  await expect(page.getByText('Тренер', { exact: true })).toBeVisible();
  await expect(page.getByText('Рекомендация:', { exact: true })).toBeVisible();
  const reportText = await page.locator('.progress-report-document').innerText();
  expect(reportText).not.toContain('active');
  expect(reportText).not.toContain('adherence-v1');
  expect(reportText).not.toContain('trainer');
  await expect(page.locator('.progress-report-confidence .data-confidence')).toHaveCount(3);
  await expect(
    page.locator('.progress-report-confidence__item .data-confidence__status'),
  ).toHaveText([
    'Тренировки — Данных достаточно для оценки',
    'Питание — Данных достаточно для оценки',
    'Замеры тела — Данных достаточно для оценки',
  ]);
  const wellbeingRows = page.locator(
    '[aria-label="Распределение: Качество сна"] li[data-wellbeing-value]',
  );
  await expect(wellbeingRows).toHaveCount(5);
  const wellbeingColors = [
    'rgb(212, 106, 110)',
    'rgb(227, 154, 69)',
    'rgb(158, 163, 161)',
    'rgb(178, 245, 32)',
    'rgb(74, 199, 104)',
  ];
  const wellbeingBarMetrics = await wellbeingRows.evaluateAll((rows) =>
    rows.map((row) => {
      const track = row.querySelector('.progress-report-wellbeing-metric__bar');
      const fill = row.querySelector('i');
      return {
        value: row.getAttribute('data-wellbeing-value'),
        trackWidth: track?.getBoundingClientRect().width ?? 0,
        fillWidth: fill?.getBoundingClientRect().width ?? 0,
        color: fill ? getComputedStyle(fill).backgroundColor : null,
      };
    }),
  );
  expect(wellbeingBarMetrics).toHaveLength(5);
  expect(wellbeingBarMetrics.map((item) => item.color)).toEqual([
    null,
    wellbeingColors[1],
    wellbeingColors[2],
    wellbeingColors[3],
    wellbeingColors[4],
  ]);
  expect(wellbeingBarMetrics[0]!.value).toBe('1');
  expect(wellbeingBarMetrics[0]!.fillWidth).toBe(0);
  expect(wellbeingBarMetrics[1]!.fillWidth / wellbeingBarMetrics[1]!.trackWidth).toBeGreaterThan(
    0.4,
  );
  expect(wellbeingBarMetrics[1]!.fillWidth / wellbeingBarMetrics[1]!.trackWidth).toBeLessThan(0.6);
  expect(wellbeingBarMetrics[3]!.fillWidth / wellbeingBarMetrics[3]!.trackWidth).toBeGreaterThan(
    0.95,
  );
  await expect(page.locator('.progress-report-document .progress-report-controls')).toHaveCount(1);
  await expect(page.locator('.progress-report-settings .progress-report-controls')).toBeVisible();
  await expect(
    page.locator(
      '.progress-report-overview + .progress-report-factual-summary + .progress-report-settings',
    ),
  ).toHaveCount(1);
  await expect(
    page.locator('.progress-report-document > .progress-report-section #report-training-title'),
  ).toHaveCount(1);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: testInfo.outputPath('desktop-1280-dark-preview.png'),
  });
  await page.screenshot({
    path: testInfo.outputPath('desktop-1280-dark-full.png'),
    fullPage: true,
  });
  const evidenceDirectory = process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR;
  if (evidenceDirectory && browserName === 'chromium') {
    await mkdir(evidenceDirectory, { recursive: true });
    await page.screenshot({ path: resolve(evidenceDirectory, 'desktop-1280-dark-after.png') });
    await page
      .locator('.progress-report-wellbeing-metric')
      .nth(0)
      .screenshot({
        path: resolve(evidenceDirectory, 'wellbeing-sleep-after.png'),
      });
    await page
      .locator('.progress-report-wellbeing-metric')
      .nth(1)
      .screenshot({
        path: resolve(evidenceDirectory, 'wellbeing-mood-after.png'),
      });
    await page.evaluate(() => {
      document.documentElement.dataset.colorScheme = 'light';
      document.documentElement.dataset.themePreference = 'light';
    });
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
    await page.screenshot({ path: resolve(evidenceDirectory, 'desktop-1280-light-after.png') });
    await page.evaluate(() => {
      localStorage.setItem('app-theme', 'dark');
      document.documentElement.dataset.colorScheme = 'dark';
      document.documentElement.dataset.themePreference = 'dark';
    });
    await page.reload();
  }

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

  await page.setViewportSize({ width: 1280, height: 900 });
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
  await expect(page.locator('.progress-report-print-footer')).toHaveCSS('position', 'static');
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
    const extracted = compactPdfText(extractPdfText(testInfo.outputPath('progress-report.pdf')));
    expect(extracted).toContain(compactPdfText('Качество сна'));
    expect(extracted).toContain(compactPdfText('Настроение'));
    expect(extracted).not.toContain(compactPdfText('Добавить отметку'));
    expect(extracted).not.toContain(compactPdfText('Печать / Сохранить как PDF'));
    if (evidenceDirectory) {
      await mkdir(evidenceDirectory, { recursive: true });
      await writeFile(resolve(evidenceDirectory, 'browser-progress-report.pdf'), pdf);
      if (browserName === 'chromium') {
        await page.addStyleTag({
          content: '.progress-report-page { filter: grayscale(1) !important; }',
        });
        const grayscalePdf = await page.pdf({
          path: testInfo.outputPath('grayscale-progress-report.pdf'),
          format: 'A4',
          printBackground: true,
          preferCSSPageSize: true,
        });
        await writeFile(
          resolve(evidenceDirectory, 'grayscale-browser-progress-report.pdf'),
          grayscalePdf,
        );
      }
    }
  }
});

test('report stays readable across the requested mobile viewport matrix', async ({
  page,
  browserName,
}, testInfo) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportApi(page);

  for (const width of [320, 360, 393, 430]) {
    for (const colorScheme of ['light', 'dark'] as const) {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
      await page.goto('/app/report?period=days_30');
      await page.evaluate((theme) => localStorage.setItem('app-theme', theme), colorScheme);
      await page.reload();

      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', colorScheme);
      await expect(
        page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true }),
      ).toBeVisible();
      await expect(page.locator('.progress-report-confidence')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Печать / Сохранить как PDF' })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await page.screenshot({
        path: testInfo.outputPath(`mobile-report-${width}-${colorScheme}.png`),
        fullPage: true,
      });
      if (
        process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR &&
        browserName === 'chromium' &&
        width === 360
      ) {
        await mkdir(process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR, { recursive: true });
        await page.screenshot({
          path: resolve(
            process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR,
            `mobile-360-${colorScheme}-after.png`,
          ),
          fullPage: true,
        });
      }
    }
  }
});

test('browser print PDF contains the canonical facts and privacy boundaries', async ({
  page,
  browserName,
}, testInfo) => {
  await installPlatformApi(page, { browserSession: true });
  await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname.endsWith('/download-link')) {
      await route.fulfill({
        json: {
          url: `${url.origin}/api/v1/workouts/progress/report/file/signed-canonical`,
          filename: 'progress-report-2026-07-26_2026-08-24.pdf',
          expires_at: '2026-08-29T19:05:00Z',
        },
      });
      return;
    }
    const report = makeCanonicalProgressReportFixture();
    assertCanonicalProgressReportInvariants(report);
    await route.fulfill({ json: report });
  });

  const period = canonicalFacts.period;
  await page.goto(
    `/app/report?period=${period.period}&date_from=${period.start}&date_to=${period.end}`,
  );
  await expect(page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true })).toBeVisible();
  const uiText = (await page.locator('.progress-report-document').innerText()).replace(
    /\u00a0/g,
    ' ',
  );
  expect(uiText).not.toContain('Скрытая заметка еженедельной отметки');
  expect(uiText).toContain('1 завершено из 2');
  expect(uiText).toContain('400 кг');
  expect(uiText).toContain('2 100 ккал');
  expect(uiText).toContain('155 г');
  expect(uiText).toContain('68 г');
  expect(uiText).toContain('230 г');
  expect(uiText).toContain('79 кг');
  expect(uiText).toContain('89 см');
  await expect(
    page.getByText('Сравнение недоступно: за выбранный период записана одна сессия.'),
  ).toBeVisible();
  await expect(
    page.locator('.progress-report-exercises').getByText('Первая сессия', { exact: true }),
  ).toHaveCount(0);
  for (const exercise of canonicalFacts.training.exercises) {
    expect(uiText).toContain(exercise.exercise_title);
    expect(uiText).toContain(browserDate(exercise.first_performed_on));
    expect(uiText).toContain(`${browserNumber(exercise.external_load_volume_kg)} кг`);
  }
  if (browserName !== 'chromium') return;
  await page.emulateMedia({ media: 'print' });
  const pdfPath = testInfo.outputPath('canonical-browser-progress-report.pdf');
  const pdf = await page.pdf({
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
  });
  expect(pdf.subarray(0, 4).toString()).toBe('%PDF');

  const extracted = compactPdfText(extractPdfText(pdfPath));
  const expected = [
    canonicalFacts.subject.name,
    `Период:${browserDate(period.start)} — ${browserDate(period.end)}`,
    `Тренировки${canonicalFacts.training.completed_workouts}завершеноиз${canonicalFacts.training.planned_workouts}`,
    `${canonicalFacts.training.external_load_volume_kg}кг`,
    `Ручноекардио${canonicalFacts.cardio.completed_sessions}завершено·${canonicalFacts.cardio.duration_minutes}мин`,
    `${browserNumber(canonicalFacts.nutrition.calories_average)}ккал`,
    `${browserNumber(canonicalFacts.nutrition.protein_g_average)}г`,
    `${browserNumber(canonicalFacts.nutrition.fat_g_average)}г`,
    `${browserNumber(canonicalFacts.nutrition.carbs_g_average)}г`,
  ];
  for (const fact of expected) {
    expect(extracted).toContain(compactPdfText(fact));
  }
  for (const trend of canonicalFacts.body) {
    const unit = trend.unit === 'kg' ? 'кг' : 'см';
    expect(extracted).toContain(`${trend.latest_value}${unit}`);
    expect(extracted).toContain(compactPdfText(browserDate(trend.latest_measured_on)));
  }
  for (const exercise of canonicalFacts.training.exercises) {
    expect(extracted).toContain(compactPdfText(exercise.exercise_title));
    expect(extracted).toContain(
      compactPdfText(`${browserNumber(exercise.external_load_volume_kg)} кг`),
    );
  }
  const evidenceDirectory = process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR;
  if (evidenceDirectory) {
    await mkdir(evidenceDirectory, { recursive: true });
    await page.screenshot({
      path: resolve(evidenceDirectory, 'canonical-one-record-after.png'),
      fullPage: true,
    });
  }
  for (const privateValue of canonicalFacts.privacy) {
    expect(extracted).not.toContain(compactPdfText(privateValue));
  }

  if (evidenceDirectory) {
    await writeFile(resolve(evidenceDirectory, 'canonical-browser-progress-report.pdf'), pdf);
  }
});

for (const state of ['partial', 'empty'] as const) {
  test(`${state} data stays factual and printable`, async ({ page, browserName }, testInfo) => {
    await installPlatformApi(page, { browserSession: true });
    await installReportApi(page, state);
    await page.goto('/app/report?period=days_90');

    await expect(
      page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true }),
    ).toBeVisible();
    await expect(page.locator('.progress-report-subject')).toHaveText('Александр Петров');
    await expect(page.getByText(/не медицинская оценка/)).toBeVisible();
    await expect(page.getByText(/не заполняет пропуски/)).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await page.screenshot({
      path: `../.artifacts/screenshots/task-67/desktop-${state}-preview.png`,
    });
    if (state === 'empty') {
      await expect(page.getByText('Нет замеров массы за период', { exact: true })).toBeVisible();
      await expect(
        page.getByText('За выбранный период окружности не записаны.', { exact: true }),
      ).toBeVisible();
      await expect(page.locator('.progress-report-section--body table')).toHaveCount(0);
      await expect(page.getByText('Отсутствующие дни не интерполируются.')).toBeVisible();
      await expect(page.getByText('Активной программы на дату формирования нет.')).toBeVisible();
      const evidenceDirectory = process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR;
      if (evidenceDirectory) {
        await mkdir(evidenceDirectory, { recursive: true });
        await page.screenshot({
          path: resolve(evidenceDirectory, 'empty-circumference-after.png'),
          fullPage: true,
        });
      }
    }
    if (browserName === 'chromium') {
      await page.emulateMedia({ media: 'print' });
      const pdf = await page.pdf({
        path: testInfo.outputPath(`progress-report-${state}.pdf`),
        format: 'A4',
        printBackground: true,
        preferCSSPageSize: true,
      });
      expect(pdf.subarray(0, 4).toString()).toBe('%PDF');
      expect(pdf.length).toBeGreaterThan(10_000);
      const evidenceDirectory = process.env.YFC_PROGRESS_REPORT_BROWSER_PDF_EVIDENCE_DIR;
      if (evidenceDirectory) {
        await mkdir(evidenceDirectory, { recursive: true });
        await writeFile(resolve(evidenceDirectory, `browser-progress-report-${state}.pdf`), pdf);
      }
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
  await expect(page.getByRole('heading', { name: 'Отчёт о прогрессе', exact: true })).toBeVisible();
  await expect(page.locator('.progress-report-document')).toContainText('Александр Константинович');
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
