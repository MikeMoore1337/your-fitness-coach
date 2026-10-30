import { expect, test, type Locator, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  setNetworkOffline,
} from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ hasTouch: true, serviceWorkers: 'block' });

async function setup(page: Page, telegram = false, theme: 'dark' | 'light' = 'dark') {
  if (telegram)
    await installTelegramHarness(page, {
      platform: 'ios',
      colorScheme: theme,
      viewportHeight: 844,
      viewportStableHeight: 844,
      safeAreaInset: { top: 20, right: 0, bottom: 18, left: 0 },
      contentSafeAreaInset: { top: 32, right: 0, bottom: 14, left: 0 },
    });
  const platform = await installPlatformApi(page, {
    browserSession: !telegram,
    fixedDate: '2026-10-30',
  });
  let status = 'planned';
  let version = 0;
  let current: { id: number; body: string | null; tags: string[]; version: number } | null = null;
  let previous: Record<string, unknown> | null = {
    id: 17,
    workout_id: 41,
    workout_exercise_id: 100,
    version: 1,
    body: 'Легко, в следующий раз попробовать 105 кг',
    tags: ['easy', 'increase_weight'],
    completed_on: '2026-10-23',
    week_type: 'medium',
    load: {
      set_number: 3,
      actual_weight: 100,
      actual_reps: 10,
      duration_minutes: null,
      distance_km: null,
    },
  };
  const requests: Array<{ method: string; body: Record<string, unknown> }> = [];
  const applied = new Map<string, string>();
  const identity = {
    exercise_id: 11,
    source_template_exercise_id: 71,
    plan_revision_number: 1,
    week_number: 2,
    day_number: 3,
    source_cycle_week: 2,
    cycle_iteration: 1,
  };
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
    plan_revision_number: 1,
    source_cycle_week: 2,
    cycle_iteration: 1,
    started_at: status === 'in_progress' ? '2026-10-30T12:00:00' : null,
    completed_at: null,
    exercises: [
      {
        id: 101,
        exercise_id: 11,
        exercise_title: 'Жим штанги лёжа',
        source_template_exercise_id: 71,
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
  const noteResponse = () => ({
    workout_id: 42,
    workout_exercise_id: 101,
    ...identity,
    version,
    current_note: current,
    previous_note: previous,
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
    Object.assign(set, route.request().postDataJSON(), { version: set.version + 1 });
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
  await page.route('**/api/v1/workouts/42/set-history', (route) =>
    route.fulfill({
      json: {
        workout_id: 42,
        user_program_id: 1,
        program_revision_number: 1,
        sets: [1, 2, 3].map((number) => ({
          set_id: 200 + number,
          set_number: number,
          set_version: 1,
          workout_exercise_id: 101,
          exercise_id: 11,
          source_template_exercise_id: 71,
          previous_today: null,
          history_status: 'matched',
          previous_workout: {
            set_id: 1200 + number,
            set_number: number,
            set_version: 1,
            workout_id: 41,
            workout_exercise_id: 100,
            completed_at: '2026-10-23T12:00:00',
            performed_on: '2026-10-23',
            actual_weight: 100,
            actual_reps: 10,
          },
        })),
      },
    }),
  );
  await page.route('**/api/v1/workouts/42/exercise-notes/101', (route) => {
    const method = route.request().method();
    if (method === 'GET') return route.fulfill({ json: noteResponse() });
    const body = route.request().postDataJSON() as Record<string, unknown>;
    requests.push({ method, body });
    const mutation = String(body.mutation_id);
    if (applied.has(mutation)) return route.fulfill({ json: noteResponse() });
    if (body.expected_version !== version)
      return route.fulfill({
        status: 409,
        json: {
          detail: { code: 'exercise_note_version_conflict', current: { version, note: current } },
        },
      });
    version += 1;
    current =
      method === 'DELETE'
        ? null
        : { id: 99, body: body.body as string | null, tags: body.tags as string[], version };
    applied.set(mutation, JSON.stringify(body));
    return route.fulfill({ json: noteResponse() });
  });
  return {
    platform,
    sets,
    requests,
    clearPrevious() {
      previous = null;
    },
    remoteEdit(body: string) {
      version += 1;
      current = { id: 99, body, tags: ['hard'], version };
    },
    note() {
      return current;
    },
  };
}

async function enterWorkout(page: Page) {
  await page.goto('/app');
  await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
  await expect(page.locator('.active-workout')).toBeVisible();
}

async function completeFirst(page: Page) {
  const first = page.locator('[data-workout-set-id="201"]');
  await first.getByLabel(/^Вес,/).fill('100');
  await first.getByLabel(/^Повторы,/).fill('10');
  await first.getByRole('button', { name: /^Завершить:/ }).click();
  await expect(page.locator('[data-workout-set-id="202"]')).toHaveAttribute('aria-current', 'step');
  await expect(page.getByRole('timer', { name: 'Отдых' })).toBeVisible();
}

async function capture(page: Page, name: string) {
  if (process.env.YFC_CAPTURE_995_AFTER !== '1') return;
  const directory = resolve(process.cwd(), '..', '.artifacts', 'tasks', '995', 'evidence', 'after');
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: resolve(directory, `${name}.png`),
    animations: 'disabled',
    scale: 'css',
  });
}

async function expectTagsDistributed(note: Locator) {
  const geometry = await note.locator('.exercise-execution-note__tags').evaluate((element) => {
    const group = element.getBoundingClientRect();
    const buttons = Array.from(element.querySelectorAll('button')).map((button) => {
      const box = button.getBoundingClientRect();
      return {
        left: box.left,
        right: box.right,
        top: box.top,
        width: box.width,
        height: box.height,
        fits:
          button.scrollWidth <= button.clientWidth && button.scrollHeight <= button.clientHeight,
      };
    });
    return { left: group.left, right: group.right, buttons };
  });
  expect(geometry.buttons).toHaveLength(3);
  expect(Math.abs(geometry.buttons[0]!.left - geometry.left)).toBeLessThan(1);
  expect(Math.abs(geometry.buttons[2]!.right - geometry.right)).toBeLessThan(1);
  for (const button of geometry.buttons) {
    expect(Math.abs(button.width - geometry.buttons[0]!.width)).toBeLessThan(1);
    expect(Math.abs(button.top - geometry.buttons[0]!.top)).toBeLessThan(1);
    expect(button.height).toBeGreaterThanOrEqual(44);
    expect(button.fits).toBe(true);
  }
}

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 393, 430, 1440]) {
    test(`real React editor ${theme} ${width}`, async ({ page, browserName }) => {
      const height = width === 1440 ? 900 : width === 430 ? 932 : width === 393 ? 844 : 800;
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      const state = await setup(page);
      await enterWorkout(page);
      await completeFirst(page);
      const row = page.locator('[data-workout-set-id="202"]');
      const note = row.locator('.exercise-execution-note');
      await expect(note).toContainText('Легко, в следующий раз попробовать 105 кг');
      await expect(row.locator('.active-workout-set__history')).toContainText('100 кг × 10');
      await expect(row.locator('.active-workout-set__history')).toContainText(
        'Подход 1 · завершён',
      );
      await expect(page.getByText('Синхронизировано').first()).toBeVisible();
      await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        );
      });
      await expect(
        row.locator(
          '.active-workout-set__controls + .active-workout-set__prefill-actions--history',
        ),
      ).toHaveCount(1);
      const before = await row.evaluate((element) => {
        const top = element.getBoundingClientRect().top;
        return ['.active-workout-set__rir-row', '.active-workout-set__done'].map((selector) => {
          const rect = element.querySelector(selector)!.getBoundingClientRect();
          return [rect.top - top, rect.width, rect.height];
        });
      });
      const timer = page.getByRole('complementary', { name: 'Отдых между подходами' });
      const timerBefore = await timer.boundingBox();
      await note.evaluate((element) =>
        window.scrollTo({
          top: Math.max(0, element.getBoundingClientRect().bottom + scrollY - innerHeight + 110),
          behavior: 'instant',
        }),
      );
      await capture(page, `${browserName}-${theme}-${width}-collapsed`);
      await note.locator('summary').click();
      await note.locator('textarea').fill('100 кг легко, в следующий раз попробовать 105 кг.');
      await note.getByRole('button', { name: 'Легко', exact: true }).click();
      await note.getByRole('button', { name: 'Повысить вес' }).click();
      await note.locator('textarea').blur();
      await note.evaluate((element) =>
        window.scrollTo({
          top: element.getBoundingClientRect().top + scrollY - 125,
          behavior: 'instant',
        }),
      );
      const after = await row.evaluate((element) => {
        const top = element.getBoundingClientRect().top;
        return ['.active-workout-set__rir-row', '.active-workout-set__done'].map((selector) => {
          const rect = element.querySelector(selector)!.getBoundingClientRect();
          return [rect.top - top, rect.width, rect.height];
        });
      });
      expect(after).toEqual(before);
      const timerAfter = await timer.boundingBox();
      expect([timerAfter!.width, timerAfter!.height]).toEqual([
        timerBefore!.width,
        timerBefore!.height,
      ]);
      await expectNoHorizontalOverflow(page);
      await expectTagsDistributed(note);
      for (const button of await note.locator('button').all())
        expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await capture(page, `${browserName}-${theme}-${width}-editor`);
      if (width !== 1440) {
        await note.locator('textarea').focus();
        await page.setViewportSize({ width, height: 480 });
        await note.locator('textarea').scrollIntoViewIfNeeded();
        await expect(note.locator('textarea')).toBeInViewport();
        expect(
          await note.locator('textarea').evaluate((element) => {
            const box = element.getBoundingClientRect();
            const hit = document.elementFromPoint(
              box.left + box.width / 2,
              box.top + box.height / 2,
            );
            return box.top >= 0 && box.bottom <= innerHeight && hit === element;
          }),
        ).toBe(true);
        await expectNoHorizontalOverflow(page);
        await capture(page, `${browserName}-${theme}-${width}-keyboard-model`);
      }
      expect(state.sets[1]!.actual_weight).toBeNull();
      expect(state.sets[1]!.actual_reps).toBeNull();
      const done = row.locator('.active-workout-set__done');
      await done.evaluate((element) =>
        window.scrollTo({
          top: element.getBoundingClientRect().top + scrollY - 145,
          behavior: 'instant',
        }),
      );
      await expect(done).toBeVisible();
      expect(
        await done.evaluate((element) => {
          const box = element.getBoundingClientRect();
          const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
          return hit === element || element.contains(hit);
        }),
      ).toBe(true);
    });
  }
}

for (const theme of ['dark', 'light'] as const)
  test(`offline queue, conflict and edit ${theme}`, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const state = await setup(page);
    await enterWorkout(page);
    const note = page.locator('[data-workout-set-id="201"] .exercise-execution-note');
    await expect(note).toContainText('Легко, в следующий раз');
    await note.locator('summary').click();
    await note.locator('textarea').fill('Мой вариант');
    await note.getByRole('button', { name: 'Тяжело' }).click();
    state.platform.setOffline(true);
    await setNetworkOffline(page, true);
    await note.getByRole('button', { name: 'Сохранить' }).click();
    await expect(note).toContainText('сохранена на устройстве');
    await note.evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 125,
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-offline`);
    expect(state.requests).toHaveLength(0);
    state.remoteEdit('Версия другого устройства');
    state.platform.setOffline(false);
    await setNetworkOffline(page, false);
    await expect(note).toContainText('Заметка изменилась на другом устройстве');
    expect(state.note()?.body).toBe('Версия другого устройства');
    await page.getByRole('button', { name: /К сводке/ }).click();
    const recovery = page.locator('.exercise-execution-note__recovery').first();
    await expect(recovery).toContainText('Неотправленная заметка');
    await recovery.locator('summary').click();
    await expect(recovery).toContainText('Мой вариант');
    await capture(page, `${browserName}-${theme}-393-recovery`);
    await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
    await note.locator('summary').click();
    await expect(note.getByText(/Заметка изменилась на другом устройстве/)).toBeVisible();
    await note.getByRole('button', { name: 'Посмотреть сохранённую версию' }).click();
    await expect(note).toContainText('На сервере: Версия другого устройства');
    await note.evaluate((element) =>
      window.scrollTo({
        top: Math.max(0, element.getBoundingClientRect().bottom + scrollY - innerHeight + 110),
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-conflict`);
    await note.getByRole('button', { name: 'Сохранить мой вариант' }).click();
    await expect.poll(() => state.note()?.body).toBe('Мой вариант');
    expect(state.note()?.tags).toEqual(['hard']);
    expect(state.sets[0]!.actual_weight).toBeNull();
    expect(state.sets[0]!.actual_reps).toBeNull();
    expect(state.platform.completionFeedback().note).toBeNull();
    expect(state.requests.map((request) => request.body.expected_version)).toEqual([0, 1]);
    await expect(note.getByRole('button', { name: 'Удалить', exact: true })).toBeVisible();
    await note.evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 125,
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-edit-delete`);
    await note.getByRole('button', { name: 'Удалить', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
    await expect.poll(() => state.note()).toBeNull();
  });

for (const theme of ['dark', 'light'] as const) {
  test(`empty, long text and TMA keyboard ${theme}`, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const state = await setup(page, true, theme);
    state.clearPrevious();
    await enterWorkout(page);
    const note = page.locator('[data-workout-set-id="201"] .exercise-execution-note');
    await expect(note).toContainText('Подходящих заметок пока нет');
    await note.locator('summary').click();
    await note.evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 100,
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-empty-tma`);
    await note.locator('textarea').fill('Оченьдлинноеслово'.repeat(25));
    await expectNoHorizontalOverflow(page);
    await capture(page, `${browserName}-${theme}-393-long-tma`);
    await note.locator('textarea').focus();
    await page.setViewportSize({ width: 393, height: 480 });
    await note.locator('textarea').scrollIntoViewIfNeeded();
    await expect(note.locator('textarea')).toBeFocused();
    await expectNoHorizontalOverflow(page);
    await capture(page, `${browserName}-${theme}-393-tma-keyboard-model`);
  });

  test(`note remains editable after the last set ${theme}`, async ({ page, browserName }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const state = await setup(page);
    await enterWorkout(page);
    await completeFirst(page);
    for (const id of [202, 203]) {
      const row = page.locator(`[data-workout-set-id="${id}"]`);
      await expect(row).toHaveAttribute('aria-current', 'step');
      await row.getByLabel(/^Вес,/).fill('100');
      await row.getByLabel(/^Повторы,/).fill('10');
      await row.getByRole('button', { name: /^Завершить:/ }).click();
    }
    const exercise = page.locator('.active-workout-exercise').first();
    const toggle = exercise.locator('.active-workout-exercise__toggle');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.click();
    const note = exercise.locator('.exercise-execution-note');
    await expect(note).toContainText('Легко, в следующий раз');
    await note.locator('summary').click();
    await note.locator('textarea').fill('После последнего подхода');
    await note.getByRole('button', { name: 'Сохранить' }).click();
    await expect.poll(() => state.note()?.body).toBe('После последнего подхода');
    await note.evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 125,
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-completed-exercise`);
    await expectNoHorizontalOverflow(page);
  });

  test(`history keeps exercise notes separate from workout feedback ${theme}`, async ({
    page,
    browserName,
  }) => {
    await page.setViewportSize({ width: 393, height: 844 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-30' });
    let historyNote = {
      id: 99,
      workout_id: 41,
      workout_exercise_id: 100,
      exercise_id: 11,
      exercise_title: 'Жим штанги лёжа',
      body: 'Личное наблюдение',
      tags: ['easy'],
      version: 1,
    };
    await page.route('**/api/v1/workouts/history?*', (route) =>
      route.fulfill({
        json: [
          {
            id: 41,
            title: 'Силовая база',
            scheduled_date: '2026-10-23',
            status: 'completed',
            completed_sets: 3,
            volume_kg: 3000,
            completion_note: 'Общая заметка тренировки',
            completion_feedback: null,
            exercises: [],
            adaptations: [],
          },
        ],
      }),
    );
    await page.route('**/api/v1/workouts/history/summary', (route) =>
      route.fulfill({
        json: {
          workouts_completed: 1,
          completed_sets: 3,
          volume_kg: 3000,
        },
      }),
    );
    await page.route('**/api/v1/workouts/41/exercise-notes', (route) =>
      route.fulfill({ json: [historyNote] }),
    );
    await page.route('**/api/v1/workouts/exercise-notes/history/99', (route) => {
      if (route.request().method() === 'GET')
        return route.fulfill({ json: { version: historyNote.version, current_note: historyNote } });
      const body = route.request().postDataJSON();
      if (body.expected_version !== historyNote.version)
        return route.fulfill({
          status: 409,
          json: { detail: { code: 'exercise_note_version_conflict' } },
        });
      historyNote = {
        ...historyNote,
        body: body.body,
        tags: body.tags,
        version: historyNote.version + 1,
      };
      return route.fulfill({ json: { version: historyNote.version, current_note: historyNote } });
    });
    await page.goto('/app?section=progress&progress_view=history');
    await expect(page.getByText('Общая заметка тренировки')).toBeVisible();
    await page.getByText('Заметки к упражнениям').click();
    await page.getByText('Жим штанги лёжа').click();
    const editor = page.locator('.exercise-execution-note').filter({ hasText: 'Жим штанги лёжа' });
    await expect(editor.getByLabel('Заметка к этому выполнению')).toHaveValue('Личное наблюдение');
    await expectTagsDistributed(editor);
    await editor.getByLabel('Заметка к этому выполнению').fill('Поправленная запись');
    await editor.evaluate((element) =>
      window.scrollTo({
        top: element.getBoundingClientRect().top + scrollY - 120,
        behavior: 'instant',
      }),
    );
    await capture(page, `${browserName}-${theme}-393-history-edit`);
    await editor.getByRole('button', { name: 'Сохранить' }).click();
    await expect.poll(() => historyNote.body).toBe('Поправленная запись');
    await expect(page.getByText('Общая заметка тренировки')).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
}
