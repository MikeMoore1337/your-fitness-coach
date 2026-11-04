import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow, installTelegramHarness } from './fixtures/mobile-tma';
import type { ApiSchemas } from '../../src/shared/api/types';

type Row = ApiSchemas['HistoryImportRow'];
type Preview = ApiSchemas['HistoryImportPreview'];
type Choice = 'keep' | 'skip';
const IMPORT = '/api/v1/workout-history-imports';
const output = resolve('../.artifacts/tasks/833/evidence/after');
const capture = process.env.YFC_833_CAPTURE === 'true';

const candidate = (exercise_id: number, title: string) => ({
  exercise_id,
  title,
  metric_type: 'strength',
  unsupported_side: false,
});
const bench = candidate(11, 'Жим штанги лёжа');
const rower = candidate(12, 'Тяга верхнего блока');
const squat = candidate(13, 'Приседания');
const hack = candidate(14, 'Гакк-приседания');
const unresolved = {
  code: 'exercise_unresolved',
  field: 'exercise_name',
  message: 'Выберите упражнение из каталога',
};

function makeRow(
  line: number,
  ref: string,
  exercise: string,
  name: string,
  options: Partial<Row> = {},
): Row {
  return {
    line,
    source: {
      workout_ref: ref,
      completed_at: '2025-10-12T18:30:00+03:00',
      timezone: 'Europe/Moscow',
      workout_title: ref === 'w4' ? 'Ноги и корпус' : 'Верх тела',
      status: 'completed',
      exercise_ref: exercise,
      exercise_name: name,
      set_number: '1',
      set_status: 'completed',
      set_kind: 'working',
      reps: '8',
      weight: '60',
      weight_unit: 'kg',
      rir: '2',
      rpe: '',
      side: '',
    },
    completed_at_utc: '2025-10-12T15:30:00',
    completed_on: '2025-10-12',
    set_number: 1,
    reps: 8,
    weight_kg: '60.00',
    issues: [],
    blocking_issues: [],
    exercise_id: 11,
    match_mode: 'auto',
    match_status: 'matched',
    resolved_title: bench.title,
    candidates: [bench],
    excluded: false,
    ...options,
  };
}

function fixtureRows(): Row[] {
  const unsupported = {
    code: 'unsupported_side',
    field: 'side',
    message: 'Раздельные стороны пока не поддерживаются',
  };
  const rpe = {
    code: 'unsupported_rpe',
    field: 'rpe',
    message: 'RPE пока нельзя перенести без потери смысла',
  };
  const invalid = {
    code: 'invalid_completed_at',
    field: 'completed_at',
    message: 'Дата завершения не распознана',
  };
  const side = makeRow(6, 'w2', 'e4', 'Тяга одной рукой', {
    exercise_id: 11,
    issues: [unsupported],
    blocking_issues: [unsupported],
  });
  side.source = { ...side.source, side: 'left', weight: '12', reps: '10' };
  const effort = makeRow(7, 'w2', 'e5', 'Приседания', {
    exercise_id: 13,
    resolved_title: squat.title,
    issues: [rpe],
    blocking_issues: [rpe],
  });
  effort.source = { ...effort.source, rpe: '8' };
  const badDate = makeRow(8, 'w3', 'e6', 'Жим', {
    completed_at_utc: null,
    completed_on: null,
    issues: [invalid],
    blocking_issues: [invalid],
  });
  badDate.source = { ...badDate.source, completed_at: 'неизвестно' };
  return [
    makeRow(3, 'w1', 'e1', 'Жим штанги лёжа'),
    makeRow(4, 'w1', 'e2', 'Тяга на тренажёре', {
      exercise_id: null,
      match_mode: null,
      match_status: 'unknown',
      resolved_title: null,
      candidates: [],
      blocking_issues: [unresolved],
    }),
    makeRow(5, 'w1', 'e3', 'Присед', {
      exercise_id: null,
      match_mode: null,
      match_status: 'ambiguous',
      resolved_title: null,
      candidates: [squat, hack],
      blocking_issues: [unresolved],
    }),
    side,
    effort,
    badDate,
    makeRow(9, 'w4', 'e7', 'Приседания', {
      exercise_id: 13,
      resolved_title: squat.title,
      candidates: [squat],
    }),
  ];
}

function makePreview(rows = fixtureRows()): Preview {
  return {
    id: '833-test-draft',
    version: 1,
    status: 'pending',
    provider: 'yfc-neutral-csv',
    schema_version: 1,
    parser_version: '1.0',
    expires_at: '2027-11-01T15:30:00Z',
    rows,
    duplicate_choices: {},
    preview_signature: 'a'.repeat(64),
    duplicates: rows.some((row) => row.source.workout_ref === 'w4')
      ? [
          {
            workout_ref: 'w4',
            source_sets: [[13, 1, 8, '60.00', 'working', '2']],
            choice: null,
            candidates: [
              {
                kind: 'possible',
                workout_id: 73,
                title: 'Ноги и корпус',
                completed_at_utc: '2025-10-12T15:00:00',
                sets: [[13, 1, 7, '60.00', 'working', '2']],
              },
            ],
          },
        ]
      : [],
  };
}

async function installImportApi(page: Page) {
  let current = makePreview();
  let mode: 'normal' | 'lost' | 'stale' = 'normal';
  let opened: 'pending' | 'confirmed' | 'expired' = 'pending';
  let list: 'empty' | 'pending' = 'empty';
  let releaseUpload: (() => void) | undefined;
  let confirmCalls = 0;
  await page.route('**/api/v1/workout-history-imports**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (path === IMPORT && method === 'GET')
      return route.fulfill({
        json:
          list === 'empty'
            ? []
            : [
                {
                  id: current.id,
                  version: current.version,
                  status: 'pending',
                  created_at: '2026-10-31T12:00:00Z',
                  expires_at: '2027-11-01T15:30:00Z',
                },
              ],
      });
    if (path === IMPORT && method === 'POST') {
      await new Promise<void>((resolveUpload) => {
        releaseUpload = resolveUpload;
      });
      return route.fulfill({ status: 201, json: current });
    }
    if (path.endsWith('/catalog')) return route.fulfill({ json: [rower, bench, squat] });
    if (path.endsWith('/resolve')) {
      const body = request.postDataJSON() as {
        exercise_choices: Record<string, number>;
        excluded_lines: number[];
        duplicate_choices: Record<string, Choice>;
      };
      const available = [bench, rower, squat, hack];
      const rows = structuredClone(current.rows ?? []);
      for (const [line, id] of Object.entries(body.exercise_choices)) {
        const selected = rows.find((row) => row.line === Number(line));
        const match = available.find((item) => item.exercise_id === id);
        if (selected && match)
          for (const row of rows)
            if (
              row.source.workout_ref === selected.source.workout_ref &&
              row.source.exercise_ref === selected.source.exercise_ref
            ) {
              row.exercise_id = id;
              row.resolved_title = match.title;
              row.match_mode = 'manual';
              row.match_status = 'matched';
              row.blocking_issues = row.blocking_issues.filter(
                (issue) => issue.code !== 'exercise_unresolved',
              );
            }
      }
      for (const row of rows) row.excluded = body.excluded_lines.includes(row.line);
      const duplicates = (current.duplicates ?? [])
        .map((item) => ({ ...item, choice: body.duplicate_choices[item.workout_ref] ?? null }))
        .filter((item) => body.duplicate_choices[item.workout_ref] !== 'skip');
      current = {
        ...current,
        rows,
        version: current.version + 1,
        duplicate_choices: body.duplicate_choices,
        duplicates,
        preview_signature: 'b'.repeat(64),
      };
      return route.fulfill({ json: current });
    }
    if (path.endsWith('/confirm')) {
      confirmCalls += 1;
      if (mode === 'stale')
        return route.fulfill({
          status: 409,
          json: { detail: { code: 'preview_changed', message: 'История изменилась' } },
        });
      opened = 'confirmed';
      if (mode === 'lost') return route.abort('connectionreset');
      return route.fulfill({
        json: {
          id: current.id,
          version: current.version,
          status: 'confirmed',
          result: { workout_ids: [1], workout_count: 1, set_count: 3 },
        },
      });
    }
    if (path.endsWith('/833-test-draft') && method === 'GET') {
      if (opened === 'expired')
        return route.fulfill({
          status: 410,
          json: { detail: { code: 'draft_unavailable', message: 'Черновик больше недоступен' } },
        });
      if (opened === 'confirmed')
        return route.fulfill({
          json: {
            id: current.id,
            version: current.version,
            status: 'confirmed',
            result: { workout_ids: [1], workout_count: 1, set_count: 3 },
          },
        });
      return route.fulfill({ json: current });
    }
    if (method === 'DELETE') return route.fulfill({ status: 204, body: '' });
    return route.fulfill({ status: 404, json: { detail: 'Не найдено' } });
  });
  return {
    release: () => releaseUpload?.(),
    uploadWaiting: () => Boolean(releaseUpload),
    setMode: (value: typeof mode) => {
      mode = value;
    },
    setOpened: (value: typeof opened) => {
      opened = value;
    },
    setList: (value: typeof list) => {
      list = value;
    },
    setCurrent: (value: Preview) => {
      current = value;
    },
    confirmCalls: () => confirmCalls,
  };
}

async function snap(page: Page, info: TestInfo, theme: string, width: number, name: string) {
  await expectNoHorizontalOverflow(page);
  if (!capture) return;
  await mkdir(output, { recursive: true });
  if (['01-entry', '02-upload', '04-preview', '10-confirm'].includes(name)) {
    await page.screenshot({
      path: resolve(output, `${info.project.name}-${theme}-${width}-${name}-context.png`),
      fullPage: true,
      animations: 'disabled',
    });
  }
  const navigation = page.locator('#appBottomNav');
  await navigation.evaluateAll((elements) =>
    elements.forEach((element) => {
      (element as HTMLElement).style.visibility = 'hidden';
    }),
  );
  try {
    await page.locator('.workout-history-card').screenshot({
      path: resolve(output, `${info.project.name}-${theme}-${width}-${name}.png`),
      animations: 'disabled',
    });
  } finally {
    await navigation.evaluateAll((elements) =>
      elements.forEach((element) => {
        (element as HTMLElement).style.visibility = '';
      }),
    );
  }
}

const sizes = [
  { width: 320, height: 800 },
  { width: 360, height: 800 },
  { width: 393, height: 844 },
  { width: 430, height: 932 },
  { width: 1440, height: 900 },
];
for (const theme of ['dark', 'light'] as const)
  for (const viewport of sizes) {
    test(`real history import flow ${theme} ${viewport.width}`, async ({ page }, info) => {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-10-09',
        progressState: 'populated',
      });
      const server = await installImportApi(page);
      await page.goto('/app?section=progress&progress_view=history');
      const entry = page.getByRole('button', { name: 'Импортировать историю' });
      await expect(entry).toBeVisible();
      await snap(page, info, theme, viewport.width, '01-entry');
      await entry.click();
      await expect(page.getByRole('button', { name: 'Выбрать файл' })).toBeVisible();
      await snap(page, info, theme, viewport.width, '02-upload');
      await page.getByLabel('Выбрать CSV-файл').setInputFiles({
        name: 'history.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('synthetic fixture'),
      });
      await expect(page.getByText('Проверяем файл…')).toBeVisible();
      await expect.poll(server.uploadWaiting).toBe(true);
      await snap(page, info, theme, viewport.width, '03-loading');
      server.release();
      await expect(page.getByText('Нужно проверить записи')).toBeVisible();
      await snap(page, info, theme, viewport.width, '04-preview');
      expect(server.confirmCalls()).toBe(0);
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('Упражнение не найдено')).toBeVisible();
      await expect(page.getByRole('radio', { name: rower.title })).toBeVisible();
      await snap(page, info, theme, viewport.width, '05-unknown');
      await page.getByRole('radio', { name: rower.title }).check();
      await page.getByRole('button', { name: 'Сохранить выбор' }).click();
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('Выберите упражнение', { exact: true }).first()).toBeVisible();
      await snap(page, info, theme, viewport.width, '06-ambiguous');
      await page.getByLabel('Упражнение в YFC').selectOption(String(squat.exercise_id));
      await page.getByRole('button', { name: 'Сохранить выбор' }).click();
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('Эти данные пока не поддерживаются')).toBeVisible();
      await snap(page, info, theme, viewport.width, '07-side');
      await page.getByRole('button', { name: 'Исключить строку', exact: true }).click();
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('RPE: 8')).toBeVisible();
      await snap(page, info, theme, viewport.width, '08-rpe');
      await page.getByRole('button', { name: 'Исключить строку', exact: true }).click();
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('Строка 8 · требует проверки')).toBeVisible();
      await snap(page, info, theme, viewport.width, '09-conflicts');
      await page.getByRole('button', { name: 'Подтвердить исключение' }).click();
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await page.getByRole('button', { name: 'Исключить тренировку' }).click();
      await page.getByRole('button', { name: 'Продолжить' }).click();
      await expect(page.getByText(/Не войдут:/)).toBeVisible();
      await expect(page.locator('.history-import__row')).toHaveCount(1);
      await snap(page, info, theme, viewport.width, '10-confirm');
      expect(server.confirmCalls()).toBe(0);
      server.setMode('lost');
      await page.getByRole('button', { name: 'Сохранить историю' }).click();
      await expect(page.getByText('Проверьте состояние импорта')).toBeVisible();
      await snap(page, info, theme, viewport.width, '11-unknown-result');
      await page.getByRole('button', { name: 'Обновить статус' }).click();
      await expect(page.getByText('История дополнена')).toBeVisible();
      await snap(page, info, theme, viewport.width, '12-success');
      expect(server.confirmCalls()).toBe(1);
      server.setList('pending');
      server.setOpened('pending');
      server.setCurrent(makePreview([makeRow(3, 'w1', 'e1', 'Жим штанги лёжа')]));
      await page.getByRole('button', { name: 'Готово' }).click();
      await entry.click();
      await expect(page.getByText('Черновик импорта', { exact: true })).toBeVisible();
      await snap(page, info, theme, viewport.width, '13-resume');
      await page.getByRole('button', { name: 'Продолжить проверку' }).click();
      await page.getByRole('button', { name: 'Продолжить' }).click();
      server.setMode('stale');
      await page.getByRole('button', { name: 'Сохранить историю' }).click();
      await expect(page.getByText('Нужен актуальный просмотр')).toBeVisible();
      await snap(page, info, theme, viewport.width, '14-stale');
      server.setOpened('expired');
      await page.getByRole('button', { name: 'Обновить предпросмотр' }).click();
      await expect(page.getByText('Черновик удалён')).toBeVisible();
      await snap(page, info, theme, viewport.width, '15-expired');
    });
  }

test('import confirmation works in simulated PWA and Telegram shells', async ({ browser }) => {
  for (const surface of ['pwa', 'telegram'] as const) {
    const context = await browser.newContext({
      viewport: { width: 393, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const page = await context.newPage();
    if (surface === 'telegram')
      await installTelegramHarness(page, { viewportHeight: 844, viewportStableHeight: 844 });
    else
      await page.addInitScript(() => {
        const original = window.matchMedia.bind(window);
        window.matchMedia = (query) => {
          const value = original(query);
          if (query === '(display-mode: standalone)')
            Object.defineProperty(value, 'matches', { value: true });
          return value;
        };
      });
    await installPlatformApi(page, { browserSession: true, progressState: 'populated' });
    const server = await installImportApi(page);
    server.setCurrent(makePreview([makeRow(3, 'w1', 'e1', 'Жим штанги лёжа')]));
    await page.goto('/app?section=progress&progress_view=history');
    await page.getByRole('button', { name: 'Импортировать историю' }).click();
    await expect(page.getByRole('button', { name: 'Выбрать файл' })).toBeVisible();
    await page.getByLabel('Выбрать CSV-файл').setInputFiles({
      name: 'history.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from('synthetic fixture'),
    });
    await expect.poll(server.uploadWaiting).toBe(true);
    server.release();
    await page.getByRole('button', { name: 'Продолжить' }).click();
    expect(server.confirmCalls()).toBe(0);
    await page.getByRole('button', { name: 'Сохранить историю' }).click();
    await expect(page.getByText('История дополнена')).toBeVisible();
    expect(server.confirmCalls()).toBe(1);
    await expectNoHorizontalOverflow(page);
    await context.close();
  }
});

test('long source names stay within a 320px viewport', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await installPlatformApi(page, { browserSession: true, progressState: 'populated' });
  const server = await installImportApi(page);
  const longRow = makeRow(3, 'w1', 'e1', 'Д'.repeat(128));
  longRow.source.workout_title = 'Т'.repeat(128);
  longRow.resolved_title = 'У'.repeat(128);
  server.setCurrent(makePreview([longRow]));
  await page.goto('/app?section=progress&progress_view=history');
  await page.getByRole('button', { name: 'Импортировать историю' }).click();
  await page.getByLabel('Выбрать CSV-файл').setInputFiles({
    name: 'history.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('synthetic fixture'),
  });
  await expect.poll(server.uploadWaiting).toBe(true);
  server.release();
  await expect(page.getByRole('button', { name: 'Продолжить' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  const overflow = await page.locator('.history-import').evaluate((panel) => {
    const right = panel.getBoundingClientRect().right;
    return [...panel.querySelectorAll('*')]
      .filter((element) => element.getBoundingClientRect().right > right + 1)
      .map((element) => element.tagName);
  });
  expect(overflow).toEqual([]);
});
