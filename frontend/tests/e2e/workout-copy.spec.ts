import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

type ClipboardState = { mode: 'success' | 'denied'; text: string; writes: number };

const historyRows = [
  {
    id: 43,
    title: 'Ноги и корпус',
    scheduled_date: '2026-10-29',
    status: 'completed',
    completed_at: '2026-10-30T08:15:00',
    completed_sets: 2,
    volume_kg: 320,
    completion_note: 'ЛИЧНАЯ ЗАМЕТКА',
    completion_feedback: null,
    adaptations: [],
    rest_sessions: [],
    exercises: [
      {
        workout_exercise_id: 55,
        exercise_id: 11,
        title: 'Приседания',
        prescribed_sets: 2,
        prescribed_reps: '8',
        sort_order: 1,
      },
    ],
  },
  {
    id: 44,
    title: 'Кардио',
    scheduled_date: '2026-10-28',
    status: 'completed',
    completed_at: '2026-10-28T08:15:00',
    completed_sets: 1,
    volume_kg: 0,
    completion_note: null,
    completion_feedback: null,
    adaptations: [],
    rest_sessions: [],
    exercises: [
      {
        workout_exercise_id: 56,
        exercise_id: 12,
        title: 'Велотренажёр',
        prescribed_sets: 1,
        prescribed_reps: '',
        sort_order: 1,
      },
    ],
  },
];

const historyCopy = {
  title: 'Ноги и корпус',
  scheduled_date: '2026-10-29',
  completed_at: '2026-10-30T08:15:00',
  completion_note: 'ЛИЧНАЯ ЗАМЕТКА',
  id: 987654,
  exercises: [
    {
      exercise_title: 'Приседания',
      metric_type: 'strength',
      sort_order: 1,
      notes: 'ПРИВАТНЫЙ КОММЕНТАРИЙ',
      sets: [
        {
          set_number: 1,
          actual_weight: 20,
          actual_reps: 10,
          set_kind: 'warmup',
          is_completed: true,
        },
        {
          set_number: 2,
          actual_weight: 40,
          actual_reps: 8,
          set_kind: 'working',
          is_completed: true,
        },
      ],
    },
  ],
};

const expectedHistory = [
  'Ноги и корпус',
  '30.10.2026',
  '',
  'Приседания',
  'Разминка 1: 20 кг × 10 повторений',
  'Рабочий подход 2: 40 кг × 8 повторений',
].join('\n');

async function installClipboard(page: Page) {
  await page.addInitScript(() => {
    const state = { mode: 'success', text: '', writes: 0 };
    Object.defineProperty(window, '__workoutClipboard', { value: state });
    class TestClipboardItem {
      data: Record<string, Promise<Blob>>;
      constructor(data: Record<string, Promise<Blob>>) {
        this.data = data;
      }
    }
    Object.defineProperty(window, 'ClipboardItem', {
      configurable: true,
      value: TestClipboardItem,
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          state.writes += 1;
          if (state.mode === 'denied') throw new Error('denied');
          state.text = text;
        },
        write: async (items: TestClipboardItem[]) => {
          state.writes += 1;
          const data = items[0]?.data['text/plain'];
          if (!data) throw new Error('Clipboard text missing');
          const blob = await data;
          if (state.mode === 'denied') throw new Error('denied');
          state.text = await blob.text();
        },
      },
    });
  });
}

async function clipboardState(page: Page): Promise<ClipboardState> {
  return page.evaluate(
    () => (window as unknown as { __workoutClipboard: ClipboardState }).__workoutClipboard,
  );
}

async function setClipboardMode(page: Page, mode: ClipboardState['mode']) {
  await page.evaluate((value) => {
    (window as unknown as { __workoutClipboard: ClipboardState }).__workoutClipboard.mode = value;
  }, mode);
}

async function installHistory(page: Page) {
  await page.route(/\/api\/v1\/workouts\/history(?:\?.*)?$/, (route) =>
    route.fulfill({ json: historyRows }),
  );
  await page.route('**/api/v1/workouts/history/summary', (route) =>
    route.fulfill({ json: { workouts_completed: 2, completed_sets: 3, volume_kg: 320 } }),
  );
  await page.route('**/api/v1/workouts/43/copy', (route) => route.fulfill({ json: historyCopy }));
}

async function openHistory(page: Page) {
  await page.goto('/app?section=progress&progress_view=history');
  const tab = page
    .getByRole('navigation', { name: 'Разделы прогресса' })
    .getByRole('tab', { name: /^История/ });
  await expect(tab).toBeVisible();
  if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
  await expect(page.locator('#workout-history-43')).toBeVisible();
}

async function screenshot(page: Page, info: TestInfo, name: string) {
  const directory = process.env.YFC_828_AFTER_DIR;
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: resolve(directory, `${info.project.name}-${name}.png`),
    animations: 'disabled',
  });
}

async function expectButtonGeometry(page: Page, buttonName: string) {
  const button = page.getByRole('button', { name: buttonName, exact: true });
  await button.scrollIntoViewIfNeeded();
  await expect(button).toBeVisible();
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await expectNoHorizontalOverflow(page);
}

async function expectDialogGeometry(page: Page) {
  const geometry = await page
    .getByRole('dialog', { name: 'Скопируйте текст вручную' })
    .evaluate((dialog) => {
      const backdrop = dialog.querySelector('.modal__backdrop')?.getBoundingClientRect();
      const panel = dialog.querySelector('.modal__panel')?.getBoundingClientRect();
      if (!backdrop || !panel) throw new Error('Dialog geometry missing');
      return {
        left: backdrop.left,
        top: backdrop.top,
        right: backdrop.right,
        bottom: backdrop.bottom,
        panelLeft: panel.left,
        panelRight: panel.right,
        panelTop: panel.top,
        panelBottom: panel.bottom,
        width: window.innerWidth,
        height: window.innerHeight,
      };
    });
  expect(geometry.left).toBeLessThanOrEqual(0);
  expect(geometry.top).toBeLessThanOrEqual(0);
  expect(geometry.right).toBeGreaterThanOrEqual(geometry.width);
  expect(geometry.bottom).toBeGreaterThanOrEqual(geometry.height);
  expect(geometry.panelLeft).toBeGreaterThanOrEqual(0);
  expect(geometry.panelRight).toBeLessThanOrEqual(geometry.width);
  expect(geometry.panelTop).toBeGreaterThanOrEqual(0);
  expect(geometry.panelBottom).toBeLessThanOrEqual(geometry.height);
}

for (const width of [320, 360, 393, 430, 1280]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`copy completed workouts ${width}px ${theme}`, async ({ page }, info) => {
      test.setTimeout(60_000);
      await page.setViewportSize({ width, height: width === 1280 ? 900 : 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installClipboard(page);
      await installPlatformApi(page, {
        browserSession: true,
        workoutStatus: 'completed',
        fixedDate: '2026-10-30',
      });
      await installHistory(page);
      await page.goto('/app?section=today');
      await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
      const completion = page.getByRole('button', { name: 'Скопировать тренировку', exact: true });
      await expectButtonGeometry(page, 'Скопировать тренировку');
      if (width === 393 || width === 1280)
        await screenshot(page, info, `completion-action-${width}-${theme}`);
      await completion.click();
      await expect(page.getByText('Тренировка скопирована')).toBeVisible();
      expect((await clipboardState(page)).text).toContain('Рабочий подход 1: 40 кг × 8 повторений');
      if (width === 393 || width === 1280)
        await screenshot(page, info, `completion-success-${width}-${theme}`);
      await page.getByRole('button', { name: 'Закрыть сообщение' }).click();

      await setClipboardMode(page, 'denied');
      await completion.click();
      const completionDialog = page.getByRole('dialog', { name: 'Скопируйте текст вручную' });
      await expect(completionDialog).toBeVisible();
      await expectDialogGeometry(page);
      const text = completionDialog.getByRole('textbox', { name: 'Текст тренировки' });
      await expect(text).toHaveValue(/Рабочий подход 1: 40 кг × 8 повторений/);
      if (width === 393 || width === 1280)
        await screenshot(page, info, `completion-fallback-${width}-${theme}`);
      await completionDialog.getByRole('button', { name: 'Выделить' }).click();
      expect(
        await text.evaluate((node: HTMLTextAreaElement) => [
          node.selectionStart,
          node.selectionEnd,
        ]),
      ).toEqual([0, (await text.inputValue()).length]);
      if (width === 393 || width === 1280)
        await screenshot(page, info, `completion-selection-${width}-${theme}`);
      await page.keyboard.press('Escape');
      await expect(completionDialog).not.toBeVisible();

      await openHistory(page);
      await expect(page.getByRole('button', { name: /^Скопировать тренировку:/ })).toHaveCount(2);
      const history = page.getByRole('button', {
        name: 'Скопировать тренировку: Ноги и корпус',
        exact: true,
      });
      await expectButtonGeometry(page, 'Скопировать тренировку: Ноги и корпус');
      if (width === 393 || width === 1280)
        await screenshot(page, info, `history-action-${width}-${theme}`);
      await setClipboardMode(page, 'success');
      await history.click();
      await expect(page.getByText('Тренировка скопирована')).toBeVisible();
      expect((await clipboardState(page)).text).toBe(expectedHistory);
      expect((await clipboardState(page)).text).not.toMatch(/ЛИЧНАЯ|ПРИВАТНЫЙ|987654/);
      if (width === 393 || width === 1280)
        await screenshot(page, info, `history-success-${width}-${theme}`);
      await page.getByRole('button', { name: 'Закрыть сообщение' }).click();
      await setClipboardMode(page, 'denied');
      await history.click();
      const historyDialog = page.getByRole('dialog', { name: 'Скопируйте текст вручную' });
      await expect(historyDialog).toBeVisible();
      await expectDialogGeometry(page);
      await expect(historyDialog.getByRole('textbox', { name: 'Текст тренировки' })).toHaveValue(
        expectedHistory,
      );
      if (width === 393 || width === 1280)
        await screenshot(page, info, `history-fallback-${width}-${theme}`);
      await historyDialog
        .locator('.modal__actions')
        .getByRole('button', { name: 'Закрыть' })
        .click();
      await expect(historyDialog).not.toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }
}

test('history starts clipboard write before its detail request finishes', async ({ page }) => {
  await installClipboard(page);
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'completed' });
  await installHistory(page);
  let release!: () => void;
  const barrier = new Promise<void>((resolvePromise) => {
    release = resolvePromise;
  });
  await page.route('**/api/v1/workouts/43/copy', async (route) => {
    await barrier;
    await route.fulfill({ json: historyCopy });
  });
  await openHistory(page);
  const button = page.getByRole('button', { name: 'Скопировать тренировку: Ноги и корпус' });
  await button.click();
  await expect.poll(async () => (await clipboardState(page)).writes).toBe(1);
  await expect(button).toBeDisabled();
  release();
  await expect(page.getByText('Тренировка скопирована')).toBeVisible();
  expect((await clipboardState(page)).text).toBe(expectedHistory);
});

test('history load errors do not claim success or show incomplete text', async ({ page }) => {
  await installClipboard(page);
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'completed' });
  await installHistory(page);
  await page.route('**/api/v1/workouts/43/copy', (route) =>
    route.fulfill({ status: 503, json: { detail: 'unavailable' } }),
  );
  await openHistory(page);
  await page.getByRole('button', { name: 'Скопировать тренировку: Ноги и корпус' }).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить тренировку');
  await expect(page.getByRole('dialog', { name: 'Скопируйте текст вручную' })).toHaveCount(0);
  await expect(page.getByText('Тренировка скопирована')).toHaveCount(0);
});

for (const surface of ['pwa', 'tma'] as const) {
  test(`${surface} offers the manual fallback`, async ({ page }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await installClipboard(page);
    if (surface === 'pwa') {
      await page.addInitScript(() =>
        Object.defineProperty(navigator, 'standalone', { configurable: true, value: true }),
      );
    } else {
      await installTelegramHarness(page, {
        platform: 'ios',
        viewportHeight: 844,
        viewportStableHeight: 844,
      });
    }
    await installPlatformApi(page, {
      browserSession: surface === 'pwa',
      workoutStatus: 'completed',
    });
    await page.goto('/app');
    await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
    const button = page.getByRole('button', { name: 'Скопировать тренировку', exact: true });
    await button.click();
    await expect(page.getByText('Тренировка скопирована')).toBeVisible();
    expect((await clipboardState(page)).text).toContain('Приседания');
    await page.getByRole('button', { name: 'Закрыть сообщение' }).click();
    if (surface === 'pwa') {
      await page.evaluate(() =>
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined }),
      );
    } else {
      await setClipboardMode(page, 'denied');
    }
    await button.click();
    const dialog = page.getByRole('dialog', { name: 'Скопируйте текст вручную' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('textbox', { name: 'Текст тренировки' })).toHaveValue(
      /Приседания/,
    );
    if (surface === 'tma') {
      const telegram = new TelegramHarness(page);
      await expect.poll(async () => (await telegram.state()).backButton.visible).toBe(true);
      await telegram.clickBack();
    } else {
      await dialog.locator('.modal__actions').getByRole('button', { name: 'Закрыть' }).click();
    }
    await expect(dialog).not.toBeVisible();
  });
}
