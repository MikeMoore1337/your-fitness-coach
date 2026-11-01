import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { installIssue834ImportApi } from './fixtures/issue-834-import';

const evidenceDir = resolve('../.artifacts/runtime/tests/playwright/redesign-visual-834');
const viewports = [
  { width: 320, height: 800 },
  { width: 393, height: 844 },
  { width: 1440, height: 900 },
] as const;

async function screenshot834(
  page: Page,
  info: TestInfo,
  theme: 'dark' | 'light',
  width: number,
  state: string,
) {
  await expectNoHorizontalOverflow(page);
  await mkdir(evidenceDir, { recursive: true });
  const name = [info.project.name, theme, width, state].join('-') + '.png';
  await page.screenshot({
    path: resolve(evidenceDir, name),
    fullPage: true,
    animations: 'disabled',
    caret: 'hide',
  });
}

for (const theme of ['dark', 'light'] as const) {
  for (const viewport of viewports) {
    test('#834 provider UI ' + theme + ' ' + viewport.width, async ({ page }, info) => {
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.clock.setFixedTime(new Date('2026-10-09T12:00:00+03:00'));
      await page.addInitScript((name) => localStorage.setItem('app-theme', name), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-10-09',
        progressState: 'populated',
      });
      const mock = await installIssue834ImportApi(page, 'fitnotes');
      await page.goto('/app?section=progress&progress_view=history');
      await page.getByRole('button', { name: 'Импортировать историю' }).click();
      await expect(page.getByLabel('Источник')).toBeVisible();
      await page.getByLabel('Источник').selectOption('strong');
      await expect(page.getByLabel('Единица веса в файле')).toBeVisible();
      await page.getByLabel('Единица веса в файле').selectOption('lb');
      await screenshot834(page, info, theme, viewport.width, '01-strong-upload');
      await page.getByLabel('Источник').selectOption('fitnotes');
      await expect(page.getByLabel('Единица веса в файле')).toHaveCount(0);
      await screenshot834(page, info, theme, viewport.width, '02-fitnotes-upload');
      await page.getByLabel('Выбрать CSV-файл').setInputFiles({
        name: 'synthetic-fitnotes.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('Date,Exercise\n2025-10-12,Example', 'utf8'),
      });
      await expect(page.getByText(/В FitNotes нет времени и типа подхода/)).toBeVisible();
      await expect(page.getByText('Время не указано')).toBeVisible();
      await expect(page.getByLabel('Тип подхода, если знаете')).toHaveValue('');
      expect(mock.uploads()).toBe(1);
      await screenshot834(page, info, theme, viewport.width, '03-fitnotes-preview');
      await page.getByLabel('Тип подхода, если знаете').selectOption('working');
      await expect(page.getByLabel('Тип подхода, если знаете')).toHaveValue('working');
      expect(mock.resolves()).toBe(1);
      await screenshot834(page, info, theme, viewport.width, '04-fitnotes-kind-review');
      await page.getByRole('button', { name: 'Продолжить' }).click();
      await expect(page.getByText(/После подтверждения данные появятся в истории/)).toBeVisible();
      await screenshot834(page, info, theme, viewport.width, '05-fitnotes-confirm');
      expect(mock.confirmations()).toBe(0);
      await page.getByRole('button', { name: 'Сохранить историю' }).click();
      await expect(page.getByText('История дополнена')).toBeVisible();
      expect(mock.confirmations()).toBe(1);
      await screenshot834(page, info, theme, viewport.width, '06-fitnotes-success');
      expect(errors).toEqual([]);
    });

    test('#834 Hevy unsupported ' + theme + ' ' + viewport.width, async ({ page }, info) => {
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.clock.setFixedTime(new Date('2026-10-09T12:00:00+03:00'));
      await page.addInitScript((name) => localStorage.setItem('app-theme', name), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-10-09',
        progressState: 'populated',
      });
      const mock = await installIssue834ImportApi(page, 'hevy');
      await page.goto('/app?section=progress&progress_view=history');
      await page.getByRole('button', { name: 'Импортировать историю' }).click();
      await page.getByLabel('Источник').selectOption('hevy');
      await page.getByLabel('Выбрать CSV-файл').setInputFiles({
        name: 'synthetic-hevy.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from('title,start_time\nExample,2025-10-12', 'utf8'),
      });
      await expect(page.getByText('Нужно проверить записи')).toBeVisible();
      await screenshot834(page, info, theme, viewport.width, '07-hevy-preview');
      await page.getByRole('button', { name: 'Проверить записи' }).click();
      await expect(page.getByText('Эти данные пока не поддерживаются')).toBeVisible();
      await expect(page.getByText('Длительность в секундах: 75')).toBeVisible();
      await expect(page.getByText('RPE: 8')).toBeVisible();
      expect(mock.confirmations()).toBe(0);
      await screenshot834(page, info, theme, viewport.width, '08-hevy-unsupported');
      expect(errors).toEqual([]);
    });
  }
}
