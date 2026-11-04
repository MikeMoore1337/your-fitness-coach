import { expect, test, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  setNetworkOffline,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ hasTouch: true, serviceWorkers: 'block' });

const previous = {
  note: 'Жим ногами можно прибавить.',
  completed_on: '2026-10-23',
  day_number: 3,
  workout_title: 'Силовая база',
  is_latest_completion: true,
};

async function setupWorkout(
  page: Page,
  surface: 'web' | 'pwa' | 'telegram' = 'web',
  theme: 'dark' | 'light' = 'dark',
) {
  if (surface === 'telegram') {
    await installTelegramHarness(page, {
      platform: 'ios',
      colorScheme: theme,
      viewportHeight: 844,
      viewportStableHeight: 844,
      safeAreaInset: { top: 20, right: 0, bottom: 18, left: 0 },
      contentSafeAreaInset: { top: 32, right: 0, bottom: 14, left: 0 },
    });
  } else if (surface === 'pwa') {
    await page.addInitScript(() => {
      const original = window.matchMedia.bind(window);
      window.matchMedia = (query) => {
        const result = original(query);
        if (query === '(display-mode: standalone)') {
          Object.defineProperty(result, 'matches', { configurable: true, value: true });
        }
        return result;
      };
      Object.defineProperty(navigator, 'standalone', { configurable: true, value: true });
    });
  }
  const platform = await installPlatformApi(page, {
    browserSession: surface !== 'telegram',
    fixedDate: '2026-10-30',
  });
  let status = 'planned';
  let note: typeof previous | null = { ...previous };
  let noteStatus = 200;
  let sourceTemplateExerciseId: number | null = null;
  const noteMethods: string[] = [];
  const sets = [1, 2, 3].map((number) => ({
    id: 200 + number,
    set_number: number,
    actual_reps: null as number | null,
    actual_weight: null as number | null,
    rir: null as string | null,
    set_kind: 'working',
    reached_failure: null as boolean | null,
    is_completed: false,
    version: 1,
  }));
  const workout = () => ({
    id: 42,
    scheduled_date: '2026-10-30',
    scheduled_time: null,
    title: 'Силовая база',
    status,
    day_number: 3,
    week_number: 2,
    started_at: status === 'in_progress' ? '2026-10-30T12:00:00' : null,
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Жим штанги лёжа',
        source_template_exercise_id: sourceTemplateExerciseId,
        metric_type: 'strength',
        sort_order: 1,
        prescribed_sets: 3,
        prescribed_reps: '8–10',
        rest_seconds: 90,
        notes: null,
        has_guide: false,
        sets,
      },
    ],
  });
  await page.route('**/api/v1/workouts/today', (route) => route.fulfill({ json: workout() }));
  await page.route('**/api/v1/workouts/week', (route) => route.fulfill({ json: [workout()] }));
  await page.route('**/api/v1/workouts/42/start', (route) => {
    status = 'in_progress';
    return route.fulfill({ json: workout() });
  });
  await page.route('**/api/v1/workouts/sets/*', (route) => {
    const id = Number(new URL(route.request().url()).pathname.split('/').at(-1));
    const set = sets.find((item) => item.id === id)!;
    const body = route.request().postDataJSON();
    Object.assign(set, body, { version: set.version + 1 });
    return route.fulfill({ json: set });
  });
  await page.route('**/api/v1/workouts/42/rest-sessions', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    const body = route.request().postDataJSON();
    return route.fulfill({
      json: {
        id: 900,
        workout_id: 42,
        source_set_id: body.source_set_id,
        started_at: body.started_at,
        ended_at: null,
        planned_seconds: 90,
        adjusted_seconds: 90,
        measured_seconds: null,
        status: 'running',
        source: null,
        quality: 'normal',
        version: 1,
        start_mutation_id: body.mutation_id,
      },
    });
  });
  await page.route('**/api/v1/workouts/42/previous-completion-note', (route) => {
    noteMethods.push(route.request().method());
    return route.fulfill({
      status: noteStatus,
      json: noteStatus === 200 ? { previous_note: note } : { detail: 'Данные изменились' },
    });
  });
  return {
    platform,
    sets,
    noteMethods,
    setNote(value: typeof previous | null) {
      note = value;
    },
    setNoteStatus(value: number) {
      noteStatus = value;
    },
    setSourceTemplateExerciseId(value: number) {
      sourceTemplateExerciseId = value;
    },
  };
}

async function capture(page: Page, name: string) {
  if (process.env.YFC_CAPTURE_1195_AFTER !== '1') return;
  const dir = resolve(process.cwd(), '..', '.artifacts', 'tasks', '1195', 'evidence', 'after');
  await mkdir(dir, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: resolve(dir, `${name}.png`),
    animations: 'disabled',
    scale: 'css',
  });
}

async function showNoteBelowTimer(page: Page) {
  await page.locator('.previous-workout-note').evaluate((element) => {
    window.scrollTo({
      top: element.getBoundingClientRect().top + scrollY - 130,
      behavior: 'instant',
    });
  });
  await expect(page.locator('.previous-workout-note')).toBeInViewport();
}

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430]) {
    test(`note stays readable on ${width}px ${theme}`, async ({ page, browserName }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.clock.install({ time: new Date('2026-10-30T12:00:00Z') });
      await page.clock.setFixedTime(new Date('2026-10-30T12:00:00Z'));
      const state = await setupWorkout(page);
      await page.goto('/app');
      const note = page.locator('.previous-workout-note');
      await expect(note).toContainText(previous.note);
      await expect(note).toContainText('День 3 «Силовая база» · 23 октября 2026');
      await expect(note.locator('summary')).toHaveAccessibleName(/Заметка с прошлого выполнения/);
      await expectNoHorizontalOverflow(page);
      if (width === 393) {
        const contrasts = await note.evaluate((element) => {
          const luminance = (color: string) => {
            const channels = color
              .match(/[\d.]+/g)!
              .slice(0, 3)
              .map(Number)
              .map((value) => {
                const channel = value / 255;
                return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
              });
            return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722;
          };
          const background = luminance(getComputedStyle(element).backgroundColor);
          return ['strong', 'small', 'p'].map((selector) => {
            const foreground = luminance(getComputedStyle(element.querySelector(selector)!).color);
            return (
              (Math.max(foreground, background) + 0.05) / (Math.min(foreground, background) + 0.05)
            );
          });
        });
        for (const contrast of contrasts) expect(contrast).toBeGreaterThanOrEqual(4.5);
      }
      await capture(page, `${browserName}-${theme}-${width}-planned`);
      await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
      await expect(page.locator('.active-workout .previous-workout-note')).toContainText(
        previous.note,
      );
      expect(state.sets.map((item) => [item.actual_weight, item.actual_reps])).toEqual([
        [null, null],
        [null, null],
        [null, null],
      ]);
      const first = page.locator('[data-workout-set-id="201"]');
      await first.getByLabel(/^Вес,/).fill('40');
      await first.getByLabel(/^Повторы,/).fill('8');
      await first.getByRole('button', { name: /^Завершить:/ }).click();
      await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
      await expect(page.locator('[data-workout-set-id="202"]')).toHaveAttribute(
        'aria-current',
        'step',
      );
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() =>
              requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
            ),
          ),
      );
      await showNoteBelowTimer(page);
      const timer = await page.locator('.active-workout-rest').boundingBox();
      const noteBox = await note.boundingBox();
      expect(timer).not.toBeNull();
      expect(noteBox).not.toBeNull();
      expect(noteBox!.y).toBeGreaterThanOrEqual(timer!.y + timer!.height - 1);
      await expectNoHorizontalOverflow(page);
      await capture(page, `${browserName}-${theme}-${width}-active`);
      const summary = note.locator('summary');
      await expect(summary).toHaveCSS('cursor', 'pointer');
      expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await summary.focus();
      await expect(summary).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(note).not.toHaveAttribute('open');
      if (width === 393) await capture(page, `${browserName}-${theme}-${width}-collapsed`);
      await page.keyboard.press('Enter');
      await expect(note).toHaveAttribute('open', '');
      expect(state.noteMethods.length).toBeGreaterThan(0);
      expect(state.noteMethods.every((method) => method === 'GET')).toBe(true);
      expect(state.platform.completionFeedback().note).toBeNull();
    });
  }
}

for (const theme of ['dark', 'light'] as const) {
  test(`older note and desktop layout ${theme}`, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const state = await setupWorkout(page);
    state.setNote({ ...previous, is_latest_completion: false });
    await page.goto('/app');
    const note = page.locator('.previous-workout-note');
    await expect(note).toContainText('Последняя сохранённая заметка');
    await expect(note).toContainText('23 октября 2026');
    await expectNoHorizontalOverflow(page);
    await capture(page, `${browserName}-${theme}-393-older`);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await capture(page, `${browserName}-${theme}-1440-older`);
    await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
    const first = page.locator('[data-workout-set-id="201"]');
    await first.getByLabel(/^Вес,/).fill('40');
    await first.getByLabel(/^Повторы,/).fill('8');
    await first.getByRole('button', { name: /^Завершить:/ }).click();
    await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
    await expect(page.locator('[data-workout-set-id="202"]')).toHaveAttribute(
      'aria-current',
      'step',
    );
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
        ),
    );
    await showNoteBelowTimer(page);
    await capture(page, `${browserName}-${theme}-1440-active-older`);
  });
}

test('completion note and set history remain independent', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  const state = await setupWorkout(page);
  state.setNote({ ...previous, note: 'В заметке: 999 кг × 99' });
  state.setSourceTemplateExerciseId(71);
  await page.route('**/api/v1/workouts/42/set-history', (route) =>
    route.fulfill({
      json: {
        workout_id: 42,
        user_program_id: 1,
        program_revision_number: 1,
        sets: [
          {
            set_id: 201,
            set_number: 1,
            set_version: 1,
            workout_exercise_id: 101,
            exercise_id: 11,
            source_template_exercise_id: 71,
            previous_today: null,
            history_status: 'matched',
            previous_workout: {
              set_id: 1201,
              set_number: 1,
              set_version: 1,
              workout_id: 41,
              workout_exercise_id: 100,
              completed_at: '2026-10-23T12:00:00',
              performed_on: '2026-10-23',
              actual_weight: 42.5,
              actual_reps: 8,
            },
          },
        ],
      },
    }),
  );
  await page.goto('/app');
  await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
  const note = page.locator('.active-workout .previous-workout-note');
  const set = page.locator('[data-workout-set-id="201"]');
  await expect(note).toContainText('В заметке: 999 кг × 99');
  await expect(set.locator('.active-workout-set__history')).toContainText('42.5 кг × 8');
  await expect(set.getByLabel(/^Вес,/)).toHaveValue('');
  await expect(set.getByLabel(/^Повторы,/)).toHaveValue('');
  await set.getByRole('button', { name: 'Подставить из прошлой тренировки' }).click();
  await expect(set.getByLabel(/^Вес,/)).toHaveValue('42.5');
  await expect(set.getByLabel(/^Повторы,/)).toHaveValue('8');
  await expect(note).toContainText('В заметке: 999 кг × 99');
});

test('long notes wrap at 320px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const state = await setupWorkout(page);
  state.setNote({ ...previous, note: 'Оченьдлинноеслово'.repeat(25) });
  await page.goto('/app');
  await expect(page.locator('.previous-workout-note p')).toContainText('Оченьдлинноеслово');
  await expectNoHorizontalOverflow(page);
});

test('offline, reconnect, deleted note and 409 do not show stale history', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  const state = await setupWorkout(page);
  await page.goto('/app');
  await expect(page.getByText(previous.note)).toBeVisible();
  state.platform.setOffline(true);
  await setNetworkOffline(page, true);
  await expect(page.getByText(previous.note)).toHaveCount(0);
  state.setNote({ ...previous, note: 'Изменённая заметка', is_latest_completion: false });
  state.platform.setOffline(false);
  await setNetworkOffline(page, false);
  await expect(page.getByText('Изменённая заметка')).toBeVisible();
  await expect(page.getByText('Последняя сохранённая заметка')).toBeVisible();
  await expect(page.getByText(previous.note)).toHaveCount(0);
  state.setNoteStatus(409);
  await page.reload();
  await expect(page.getByText('Начать тренировку', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.previous-workout-note')).toHaveCount(0);
  state.setNoteStatus(200);
  state.setNote(null);
  await page.reload();
  await expect(page.getByText('Начать тренировку', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.previous-workout-note')).toHaveCount(0);
  expect(state.noteMethods.every((method) => method === 'GET')).toBe(true);
});

for (const surface of ['pwa', 'telegram'] as const) {
  for (const theme of ['dark', 'light'] as const) {
    test(`note works on ${surface} ${theme} with safe areas and keyboard`, async ({
      page,
      browserName,
    }) => {
      await page.setViewportSize({ width: 393, height: 844 });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await setupWorkout(page, surface, theme);
      await page.goto('/app');
      await expect(page.locator('.previous-workout-note')).toContainText(previous.note);
      if (surface === 'telegram') {
        const safeArea = await page.evaluate(() => ({
          top: document.documentElement.style.getPropertyValue('--yfc-tg-safe-top'),
          bottom: document.documentElement.style.getPropertyValue('--yfc-tg-safe-bottom'),
        }));
        expect(safeArea).toEqual({ top: '20px', bottom: '18px' });
      }
      await capture(page, `${browserName}-${theme}-393-${surface}-planned`);
      await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
      const note = page.locator('.active-workout .previous-workout-note');
      await expect(note).toContainText(previous.note);
      await note.locator('summary').focus();
      await page.keyboard.press('Enter');
      await expect(note).not.toHaveAttribute('open');
      await page.keyboard.press('Enter');
      await expect(note).toHaveAttribute('open', '');
      const weight = page.locator('[data-workout-set-id="201"]').getByLabel(/^Вес,/);
      await weight.focus();
      await page.setViewportSize({ width: 393, height: 500 });
      await expect(weight).toBeFocused();
      await weight.scrollIntoViewIfNeeded();
      await expect(weight).toBeInViewport();
      await expectNoHorizontalOverflow(page);
      await capture(page, `${browserName}-${theme}-393-${surface}-keyboard`);
    });
  }
}
