import { createHash, createHmac } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium, expect, test as base } from '@playwright/test';
import { installTelegramHarness } from '../e2e/fixtures/mobile-tma';

const test = base.extend({
  context: async ({ context }, runWithContext, info) => {
    // Synthetic clients use separate loopback addresses without disabling rate limits.
    const hash = createHash('sha256').update(`${info.project.name}/${info.testId}`).digest();
    await context.setExtraHTTPHeaders({
      'X-Forwarded-For': `127.${hash[0]}.${hash[1]}.${hash[2]}`,
    });
    await runWithContext(context);
  },
});

// WebKit service workers intercept requests before Playwright can hold the response.
const testWithoutServiceWorker = test.extend({ serviceWorkers: 'block' });

for (const theme of ['light', 'dark'] as const) {
  test(`real demo remains usable at actual Chromium zoom 200% (${theme})`, async ({
    browserName,
    baseURL,
  }, info) => {
    test.skip(browserName !== 'chromium', 'Browser zoom uses a Chromium extension');
    test.setTimeout(90_000);
    const extension = info.outputPath('demo-zoom-extension');
    await mkdir(extension, { recursive: true });
    await writeFile(
      resolve(extension, 'manifest.json'),
      JSON.stringify({
        manifest_version: 3,
        name: 'YFC demo zoom test',
        version: '1.0',
        permissions: ['tabs'],
        background: { service_worker: 'background.js' },
      }),
    );
    await writeFile(
      resolve(extension, 'background.js'),
      'chrome.runtime.onInstalled.addListener(() => {});',
    );
    const context = await chromium.launchPersistentContext('', {
      channel: 'chromium',
      headless: true,
      viewport: { width: 1024, height: 768 },
      ignoreDefaultArgs: ['--disable-extensions'],
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
    });
    try {
      const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent('serviceworker'));
      const page = context.pages()[0] ?? (await context.newPage());
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      for (const scenario of ['self_training', 'trainer'] as const) {
        const section = scenario === 'trainer' ? 'trainer' : 'today';
        await page.goto(
          new URL(`/demo?cabinet=1&scenario=${scenario}&section=${section}`, baseURL!).toString(),
        );
        await expect(page.getByText('Демо-режим · данные не сохраняются')).toBeVisible();
        const zoom = await worker.evaluate<number>(
          `(async () => { const [tab] = await chrome.tabs.query({active: true, currentWindow: true}); await chrome.tabs.setZoom(tab.id, 2); return chrome.tabs.getZoom(tab.id); })()`,
        );
        expect(zoom).toBe(2);
        await expect
          .poll(() =>
            page.evaluate(
              () =>
                document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
            ),
          )
          .toBe(true);
        if (scenario === 'trainer') {
          await expect(page.getByTestId('quick-add-trigger')).toHaveCount(0);
          const clients = page
            .getByRole('navigation', { name: 'Основная навигация' })
            .getByRole('link', { name: 'Клиенты', exact: true });
          await clients.click();
          await expect(clients).toHaveAttribute('aria-current', 'page');
          await page
            .getByRole('navigation', { name: 'Режим работы' })
            .getByRole('link', { name: 'Для себя' })
            .click();
        }
        const trigger = page.getByTestId('quick-add-trigger');
        await trigger.click();
        await expect(page.getByTestId('quick-add-sheet')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(trigger).toBeFocused();
      }
    } finally {
      await context.close();
    }
  });
}

testWithoutServiceWorker(
  'real demo Quick Add saves entered food only in its session',
  async ({ page, browser }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/demo?cabinet=1&scenario=self_training&section=today');
    await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
    await page.getByTestId('quick-add-trigger').click();
    await page
      .getByTestId('quick-add-sheet')
      .getByRole('link', { name: /Добавить еду/ })
      .click();
    const calories = page.getByRole('dialog').getByRole('spinbutton', { name: 'Калории' });
    await calories.fill('420');
    const keys = await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key.startsWith('fit_food_draft_')),
    );
    expect(keys).toEqual([]);
    const responsePromise = page.waitForResponse((response) => {
      const request = response.request();
      return (
        request.method() === 'POST' &&
        request.postDataJSON()?.path === '/api/v1/nutrition/diary/entries'
      );
    });
    await page.getByRole('button', { name: 'Сохранить Quick Add' }).click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const savedEntry = await response.json();
    expect(Number(savedEntry.nutrition.energy_kcal)).toBe(420);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Питание', level: 1 })).toBeVisible();
    const readDiary = (target: typeof page) =>
      target.evaluate(async (diaryDate) => {
        const token = JSON.parse(
          sessionStorage.getItem('fit_demo_sessions_v1') || '{}',
        ).self_training;
        const result = await fetch('/api/v1/demo/sessions/current/transport', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Demo-Session': token },
          body: JSON.stringify({
            path: `/api/v1/nutrition/diary?diary_date=${encodeURIComponent(diaryDate)}`,
            method: 'GET',
          }),
        });
        if (!result.ok) throw new Error(`Demo diary returned ${result.status}`);
        return result.json();
      }, savedEntry.diary_date);
    const diary = await readDiary(page);
    expect(
      diary.meals
        .flatMap((meal: { entries: Array<{ nutrition: { energy_kcal: number } }> }) => meal.entries)
        .some(
          (entry: { nutrition: { energy_kcal: number } }) =>
            Number(entry.nutrition.energy_kcal) === 420,
        ),
    ).toBe(true);
    const otherContext = await browser.newContext({
      serviceWorkers: 'block',
      baseURL: new URL(page.url()).origin,
    });
    const otherPage = await otherContext.newPage();
    await otherPage.goto('/demo?cabinet=1&scenario=self_training&section=nutrition');
    await expect(otherPage.getByRole('heading', { name: 'Питание', level: 1 })).toBeVisible();
    const otherDiary = await readDiary(otherPage);
    expect(otherDiary.meals.flatMap((meal: { entries: unknown[] }) => meal.entries)).toEqual([]);
    await otherContext.close();
  },
);

testWithoutServiceWorker(
  'real trainer demo navigation avoids unavailable program operations',
  async ({ page }) => {
    const forbidden: string[] = [];
    const transportPaths: string[] = [];
    page.on('response', (response) => {
      if (new URL(response.url()).pathname !== '/api/v1/demo/sessions/current/transport') return;
      const path = response.request().postDataJSON()?.path ?? 'unknown';
      transportPaths.push(path);
      if (response.status() === 403) forbidden.push(path);
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/demo?cabinet=1&scenario=trainer&section=trainer');
    const dock = page.getByRole('navigation', { name: 'Основная навигация' });
    await dock.getByRole('link', { name: 'Программы', exact: true }).click();
    const programs = page.locator('details').filter({
      has: page.getByRole('heading', { name: 'Программы клиентов', exact: true }),
    });
    await programs.locator('summary').click();
    await expect(
      page.getByText('Изменение этапов программы доступно после входа в рабочий кабинет.').first(),
    ).toBeVisible();
    await page.waitForLoadState('networkidle');
    expect(transportPaths.some((path) => path.startsWith('/api/v1/programs/assigned/'))).toBe(
      false,
    );
    expect(forbidden).toEqual([]);
  },
);

testWithoutServiceWorker('real trainer demo follows the connected route', async ({ page }) => {
  const forbidden: string[] = [];
  page.on('response', (response) => {
    if (
      response.status() === 403 &&
      new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport'
    ) {
      forbidden.push(response.request().postDataJSON()?.path ?? 'unknown');
    }
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/demo?cabinet=1&scenario=trainer&section=trainer');
  await expect(page.getByRole('heading', { name: 'Следующий шаг по клиентам' })).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('link', { name: 'Назначить программу', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Иван', level: 2 })).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('link', { name: 'Последние события', exact: true }).click();
  await page
    .getByLabel('Данные клиента')
    .getByRole('link', { name: 'Прогресс', exact: true })
    .click();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page
    .getByRole('listitem')
    .filter({ hasText: 'Алексей' })
    .getByRole('link', { name: 'Открыть задачи', exact: true })
    .click();
  await expect(page.locator('#coach-tasks-title')).toBeVisible();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await expect(page.getByText('Основной сценарий завершён')).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(forbidden).toEqual([]);
});

testWithoutServiceWorker(
  'demo explains unavailable wellbeing and cardio without protected mutations',
  async ({ page }) => {
    const forbidden: string[] = [];
    page.on('response', (response) => {
      if (
        response.status() === 403 &&
        new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport'
      ) {
        forbidden.push(response.request().postDataJSON()?.path ?? 'unknown');
      }
    });
    await page.goto('/demo?cabinet=1&scenario=self_training&section=today');
    await page.getByTestId('quick-add-trigger').click();
    await page
      .getByTestId('quick-add-sheet')
      .getByRole('link', { name: /Отметить самочувствие/ })
      .click();
    const wellbeingNotice = page.getByText(
      'Отметка самочувствия доступна после входа. В демо ответы не отправляются.',
    );
    await expect(wellbeingNotice).toBeVisible();
    await expect(wellbeingNotice).toBeInViewport();
    await expect(wellbeingNotice).toBeFocused();
    await page.getByTestId('quick-add-trigger').click();
    await page
      .getByTestId('quick-add-sheet')
      .getByRole('link', { name: /Добавить кардио/ })
      .click();
    const cardioNotice = page.getByText('Добавление кардио доступно после входа.');
    await expect(cardioNotice).toBeVisible();
    await expect(cardioNotice).toBeInViewport();
    await expect(cardioNotice).toBeFocused();
    await page.waitForLoadState('networkidle');
    expect(forbidden).toEqual([]);
  },
);

testWithoutServiceWorker(
  'real demo transport opens a workout and resolves nutrition goals',
  async ({ page }) => {
    await page.goto('/demo?cabinet=1&scenario=self_training&section=today');
    await expect(page.getByRole('heading', { name: /^Сегодня ·/ })).toBeVisible();
    await expect(page.getByText('Не удалось проверить порядок тренировок')).toHaveCount(0);
    const historyResponse = page.waitForResponse((response) => {
      const request = response.request();
      return (
        request.method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport' &&
        request.postDataJSON()?.path === '/api/v1/workouts/50001/set-history'
      );
    });
    await page.getByRole('button', { name: 'Начать тренировку' }).click();
    expect((await historyResponse).status()).toBe(200);
    await expect(
      page.getByRole('heading', { name: 'Верх тела · уверенный старт', level: 2 }),
    ).toBeVisible();
    await page.getByLabel('Вес, Жим гантелей лёжа с контролируемой паузой, подход 3').fill('19');
    await page
      .getByRole('spinbutton', {
        name: 'Повторы, Жим гантелей лёжа с контролируемой паузой, подход 3',
      })
      .fill('8');
    const restResponse = page.waitForResponse((response) => {
      const request = response.request();
      return (
        request.method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport' &&
        request.postDataJSON()?.path === '/api/v1/workouts/50001/rest-sessions'
      );
    });
    await page.getByRole('button', { name: /Завершить:.*подход 3/ }).click();
    await expect(page.locator('.active-workout-rest')).toBeVisible();
    const startedRest = await restResponse;
    expect(startedRest.status()).toBe(200);
    expect((await startedRest.json()).status).toBe('running');
    await expect(page.getByText('Ошибка сохранения', { exact: true })).toHaveCount(0);
    const actionResponse = page.waitForResponse((response) => {
      const request = response.request();
      return (
        request.method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport' &&
        /^\/api\/v1\/workouts\/rest-sessions\/\d+\/actions$/.test(request.postDataJSON()?.path)
      );
    });
    await page.getByRole('button', { name: '+30 сек' }).click();
    const extendedRest = await actionResponse;
    expect(extendedRest.status()).toBe(200);
    expect((await extendedRest.json()).adjusted_seconds).toBe(120);
    const stopResponse = page.waitForResponse((response) => {
      const request = response.request();
      return (
        request.method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/demo/sessions/current/transport' &&
        /^\/api\/v1\/workouts\/rest-sessions\/\d+\/actions$/.test(request.postDataJSON()?.path) &&
        request.postDataJSON()?.body?.action === 'complete'
      );
    });
    await page.getByRole('button', { name: 'Стоп: завершить отдых' }).click();
    const stoppedRest = await stopResponse;
    expect(stoppedRest.status()).toBe(200);
    expect((await stoppedRest.json()).status).toBe('completed');
    await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();
    await page.reload();
    await expect(page.getByText('3 из 3 подходов отмечено')).toBeVisible();
    await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
    await expect(page.getByText('Все подходы отмечены — можно завершать.')).toBeVisible();

    await page.goto('/demo?cabinet=1&scenario=nutrition&section=nutrition');
    await expect(page.getByRole('heading', { name: 'Питание', level: 1 })).toBeVisible();
    await expect(page.getByText('Базовая цель', { exact: true })).toBeVisible();
    await expect(page.getByText('Не удалось узнать источник цели.')).toHaveCount(0);
  },
);

function syntheticTelegramInitData(userId: number): string {
  const fields = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    user: JSON.stringify({ id: userId, first_name: 'Synthetic' }),
  };
  const message = Object.entries(fields)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
  const secret = createHmac('sha256', 'WebAppData').update('test-token').digest();
  const hash = createHmac('sha256', secret).update(message).digest('hex');
  return new URLSearchParams({ ...fields, hash }).toString();
}

for (const surface of [
  'pwa',
  'pwa-expiry',
  'pwa-expiry-same-unknown',
  'pwa-expiry-switch',
  'pwa-expiry-switch-unknown',
  'pwa-expiry-logout',
  'pwa-legacy-expiry',
  'pwa-close-inflight',
  'telegram',
] as const) {
  const legacyCase = surface === 'pwa-legacy-expiry';
  const closeCase = surface === 'pwa-close-inflight';
  const expiryCase = surface.startsWith('pwa-expiry') || legacyCase;
  const switchCase = surface.startsWith('pwa-expiry-switch');
  const expected =
    switchCase || surface === 'pwa-expiry-logout'
      ? 'clears the saved set across tabs'
      : 'automatically replays a saved set once';
  const scenarioTest = closeCase ? testWithoutServiceWorker : test;
  const title = `PostgreSQL offline ${surface} reload ${expected}`;
  scenarioTest(title, async ({ page, request }, info) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 393, height: 844 });
    const telegramUserId = Date.now() * 10 + info.workerIndex;
    const initData = syntheticTelegramInitData(telegramUserId);
    const login = await page.request.post('/api/v1/auth/dev-login', {
      data: {
        telegram_user_id: telegramUserId,
        full_name: 'Синтетическая проверка',
      },
    });
    expect(login.status()).toBe(200);
    const token = (await login.json()).access_token as string;
    let headers = { Authorization: `Bearer ${token}` };
    const catalog = await page.request.get('/api/v1/programs/exercises', { headers });
    expect(catalog.status()).toBe(200);
    const exercise = (await catalog.json()).find(
      (item: { metric_type: string }) => item.metric_type === 'strength',
    );
    expect(exercise).toBeTruthy();
    const created = await page.request.post('/api/v1/programs/templates', {
      headers,
      data: {
        title: 'Синтетическая тренировка',
        goal: 'strength',
        level: 'beginner',
        assign_after_create: false,
        days: [
          {
            title: 'День',
            exercises: [
              {
                exercise_id: exercise.id,
                prescribed_sets: 1,
                prescribed_reps: '8',
                rest_seconds: 90,
              },
            ],
          },
        ],
      },
    });
    expect(created.status()).toBe(200);
    const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());
    const weekday = (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
    const assigned = await page.request.post(
      `/api/v1/programs/templates/${(await created.json()).template.id}/assign-to-me`,
      {
        headers,
        data: { start_date: date, duration_weeks: 1, schedule_weekdays: [weekday] },
      },
    );
    expect(assigned.status()).toBe(200);
    const before = await page.request.get('/api/v1/workouts/today', { headers });
    expect(before.status()).toBe(200);
    const workoutId = (await before.json()).id as number;
    await page.addInitScript(
      ({ value, expiry }) => {
        if (!expiry || sessionStorage.getItem('audit_skip_initial_token') !== '1')
          sessionStorage.setItem('fit_access_token', value);
      },
      { value: token, expiry: expiryCase },
    );
    if (surface === 'telegram') await installTelegramHarness(page, { initData });
    await page.goto('/app?section=today');
    if (surface !== 'telegram' && !closeCase) {
      await page.waitForFunction(() => navigator.serviceWorker.ready.then(() => true));
      if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))))
        await page.reload();
      await expect
        .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? ''))
        .toContain('/sw.js');
    }
    const other = await page.context().newPage();
    await other.addInitScript(
      ({ value, expiry }) => {
        if (!expiry || sessionStorage.getItem('audit_skip_initial_token') !== '1')
          sessionStorage.setItem('fit_access_token', value);
      },
      { value: token, expiry: expiryCase },
    );
    if (surface === 'telegram') await installTelegramHarness(other, { initData });
    await other.goto('/app?section=profile');
    await expect(other.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
    const starting = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `/api/v1/workouts/${workoutId}/start`,
    );
    await page.getByRole('button', { name: 'Начать тренировку', exact: true }).first().click();
    const started = await starting;
    expect(started.status()).toBe(200);
    const original = (await started.json()).exercises[0].sets[0];
    const setId = original.id as number;
    await page.context().setOffline(true);
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      window.dispatchEvent(new Event('offline'));
    });
    await page
      .getByLabel(/^Вес, .* подход 1$/)
      .first()
      .fill('42.5');
    await page
      .getByLabel(/^Повторы, .* подход 1$/)
      .first()
      .fill('8');
    await page.getByRole('button', { name: '2 — ещё примерно 2 повтора' }).first().click();
    await page
      .getByRole('button', { name: /^Завершить: .*подход 1$/ })
      .first()
      .click();
    await expect(page.locator('.active-workout-sync')).toContainText(
      'Изменения сохранены на этом устройстве',
    );
    await expect
      .poll(() =>
        page.evaluate(() =>
          Object.keys(localStorage).some((key) => {
            if (!key.startsWith('fit_active_workout_queue_v4_user_')) return false;
            const stored = JSON.parse(localStorage.getItem(key) ?? 'null') as {
              queue?: { values?: { is_completed?: boolean } }[];
            } | null;
            return stored?.queue?.some((item) => item.values?.is_completed === true) ?? false;
          }),
        ),
      )
      .toBe(true);
    const offlineServer = await request.get('/api/v1/workouts/today', { headers });
    expect((await offlineServer.json()).exercises[0].sets[0]).toMatchObject({
      id: setId,
      is_completed: false,
      version: original.version,
    });
    if (closeCase) {
      const pending = await page.evaluate(() => {
        const key = Object.keys(localStorage).find((name) =>
          name.startsWith('fit_active_workout_queue_v4_user_'),
        );
        return key ? { key, value: localStorage.getItem(key) } : null;
      });
      expect(pending?.value).toBeTruthy();
      const queued = JSON.parse(pending!.value!).queue as { mutation_id: string }[];
      expect(queued).toHaveLength(1);
      await other.close();
      let releaseResponse!: () => void;
      const responseGate = new Promise<void>((resolve) => {
        releaseResponse = resolve;
      });
      let sentBody: { mutation_id: string } | undefined;
      let responseStatus = 0;
      await page.route('**/api/v1/workouts/sets/**', async (route) => {
        if (route.request().method() !== 'PATCH') return route.continue();
        sentBody = route.request().postDataJSON();
        const response = await route.fetch();
        responseStatus = response.status();
        await responseGate;
        await route.fulfill({ response }).catch(() => undefined);
      });
      const context = page.context();
      await context.setOffline(false);
      await page.evaluate(() => {
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
        window.dispatchEvent(new Event('online'));
      });
      await expect.poll(() => responseStatus).toBe(200);
      expect(sentBody?.mutation_id).toBe(queued[0]!.mutation_id);
      await page.close();
      releaseResponse();
      const resumed = await context.newPage();
      await resumed.goto('/app?section=today');
      await expect(
        resumed.getByRole('button', { name: 'Продолжить тренировку', exact: true }),
      ).toBeVisible();
      await expect
        .poll(() =>
          resumed.evaluate((key) => {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw).queue.length : 0;
          }, pending!.key),
        )
        .toBe(0);
      const resumedToken = await resumed.evaluate(() => sessionStorage.getItem('fit_access_token'));
      expect(resumedToken).toBeTruthy();
      const resumedHeaders = { Authorization: `Bearer ${resumedToken}` };
      await expect
        .poll(async () => {
          const response = await request.get('/api/v1/workouts/today', {
            headers: resumedHeaders,
          });
          return (await response.json()).exercises?.[0]?.sets?.[0]?.is_completed;
        })
        .toBe(true);
      const saved = (
        await (await request.get('/api/v1/workouts/today', { headers: resumedHeaders })).json()
      ).exercises[0].sets[0];
      expect(saved).toMatchObject({
        id: setId,
        actual_reps: 8,
        is_completed: true,
        version: original.version + 1,
      });
      const retry = await request.patch(`/api/v1/workouts/sets/${setId}`, {
        headers: resumedHeaders,
        data: sentBody,
      });
      expect(retry.status()).toBe(200);
      expect((await retry.json()).version).toBe(saved.version);
      return;
    }
    if (surface === 'pwa') {
      const navigation = await page.reload({ waitUntil: 'domcontentloaded' });
      expect(navigation?.status()).toBe(200);
      await expect(page.locator('#root')).not.toBeEmpty();
      expect((await other.reload({ waitUntil: 'domcontentloaded' }))?.status()).toBe(200);
      await expect(other.getByRole('heading', { name: 'Профиль и настройки' })).toBeVisible();
      await expect(
        other
          .getByRole('status')
          .filter({ hasText: /Изменения|Нет сети/ })
          .first(),
      ).toBeVisible();
    }
    const replayBodies: { mutation_id: string; is_completed: boolean }[] = [];
    page.context().on('request', (request) => {
      if (
        request.method() !== 'PATCH' ||
        new URL(request.url()).pathname !== `/api/v1/workouts/sets/${setId}`
      )
        return;
      const body = request.postDataJSON();
      if (body.is_completed === true) replayBodies.push(body);
    });
    if (surface === 'telegram' || expiryCase) {
      await page.evaluate(() => {
        sessionStorage.setItem('audit_force_offline', '1');
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      });
      if (surface === 'telegram')
        await page.evaluate(() => sessionStorage.removeItem('fit_authenticated_user_id'));
      await other.evaluate(() =>
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false }),
      );
      await page.addInitScript(() => {
        if (sessionStorage.getItem('audit_force_offline') === '1')
          Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      });
    }
    await page.context().setOffline(false);
    if (expiryCase) {
      const pending = await page.evaluate(() => {
        const key = Object.keys(localStorage).find((name) =>
          name.startsWith('fit_active_workout_queue_v4_user_'),
        );
        return key ? { key, value: localStorage.getItem(key) } : null;
      });
      expect(pending?.value).toBeTruthy();
      expect(JSON.parse(pending!.value!).queue).toHaveLength(1);
      await page.evaluate(() => sessionStorage.setItem('audit_skip_initial_token', '1'));
      await other.evaluate(() => sessionStorage.setItem('audit_skip_initial_token', '1'));
      const observer = await request.post('/api/v1/auth/dev-login', {
        data: { telegram_user_id: telegramUserId, full_name: 'Синтетическая проверка' },
      });
      expect(observer.status()).toBe(200);
      const revoked = await page.request.post('/api/v1/auth/logout', { headers, data: {} });
      expect(revoked.status()).toBe(200);
      headers = { Authorization: `Bearer ${(await observer.json()).access_token as string}` };
      if (legacyCase) {
        await other.evaluate(() => {
          for (const key of Object.keys(localStorage)) {
            if (key.startsWith('fit_active_workout_v1_')) localStorage.removeItem(key);
          }
          sessionStorage.removeItem('fit_access_token');
          const channel = new BroadcastChannel('fit_auth_session');
          channel.postMessage({ type: 'logout' });
          channel.close();
        });
        await expect
          .poll(() => page.evaluate(() => sessionStorage.getItem('fit_access_token')))
          .toBeNull();
      }
      await page.reload();
      await expect(page).toHaveURL(/\/login/);
      await expect
        .poll(() => other.evaluate(() => sessionStorage.getItem('fit_access_token')))
        .toBeNull();
      expect(await page.evaluate((key) => localStorage.getItem(key), pending!.key)).toBe(
        pending!.value,
      );
      expect(
        (await (await request.get('/api/v1/workouts/today', { headers })).json()).exercises[0]
          .sets[0].is_completed,
      ).toBe(false);
      await page.reload();
      await expect(page).toHaveURL(/\/login/);
      expect(await page.evaluate((key) => localStorage.getItem(key), pending!.key)).toBe(
        pending!.value,
      );
      if (surface.endsWith('-unknown')) {
        await page.evaluate(() => {
          sessionStorage.removeItem('fit_authenticated_user_id');
          localStorage.removeItem('fit_last_authenticated_user_id_v1');
        });
      }
      await page.evaluate(
        (userId) => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            if (input === '/api/v1/auth/dev-login' && init?.method === 'POST') {
              return originalFetch(input, {
                ...init,
                body: JSON.stringify({
                  telegram_user_id: userId,
                  full_name: 'Синтетическая проверка',
                }),
              });
            }
            return originalFetch(input, init);
          };
        },
        switchCase ? telegramUserId + 1_000_000 : telegramUserId,
      );
      const authenticating = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' &&
          new URL(response.url()).pathname === '/api/v1/auth/dev-login',
      );
      await page.getByRole('button', { name: 'Клиент', exact: true }).click();
      expect((await authenticating).status()).toBe(200);
      await expect(page).toHaveURL(/\/app/);
      if (switchCase) {
        await expect
          .poll(() => page.evaluate((key) => localStorage.getItem(key), pending!.key))
          .toBeNull();
        const newToken = await page.evaluate(() => sessionStorage.getItem('fit_access_token'));
        expect(newToken).toBeTruthy();
        await expect
          .poll(() => other.evaluate(() => sessionStorage.getItem('fit_access_token')))
          .toBe(newToken);
        const newProfile = await page.request.get('/api/v1/me', {
          headers: { Authorization: `Bearer ${newToken}` },
        });
        expect((await newProfile.json()).telegram_user_id).toBe(telegramUserId + 1_000_000);
        const unchanged = (await (await request.get('/api/v1/workouts/today', { headers })).json())
          .exercises[0].sets[0];
        expect(unchanged).toMatchObject({
          id: setId,
          is_completed: false,
          version: original.version,
        });
        expect(replayBodies).toHaveLength(0);
        return;
      }
      await expect(
        page.getByRole('status').filter({ hasText: 'Изменения тренировки сохранены' }),
      ).toBeVisible();
      expect(await page.evaluate((key) => localStorage.getItem(key), pending!.key)).toBe(
        pending!.value,
      );
      if (surface === 'pwa-expiry-logout') {
        const profile = page.getByRole('button', { name: 'Открыть профиль и настройки' });
        await profile.focus();
        await page.keyboard.press('Enter');
        await page.getByRole('dialog').getByRole('button', { name: 'Выйти из аккаунта' }).click();
        await expect(page).toHaveURL(/\/login/);
        await expect
          .poll(() => other.evaluate(() => sessionStorage.getItem('fit_access_token')))
          .toBeNull();
        expect(await page.evaluate((key) => localStorage.getItem(key), pending!.key)).toBeNull();
        expect(replayBodies).toHaveLength(0);
        return;
      }
    }
    if (surface === 'telegram') {
      const authenticating = page.waitForResponse(
        (response) =>
          response.request().method() === 'POST' &&
          new URL(response.url()).pathname === '/api/v1/auth/telegram/init',
      );
      await page.reload();
      expect((await authenticating).status()).toBe(200);
      await expect(
        page
          .getByRole('status')
          .filter({ hasText: /Изменения|Нет сети/ })
          .first(),
      ).toBeVisible();
      expect(
        (await (await request.get('/api/v1/workouts/today', { headers })).json()).exercises[0]
          .sets[0].is_completed,
      ).toBe(false);
    }
    await page.evaluate(() => {
      sessionStorage.removeItem('audit_force_offline');
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
      window.dispatchEvent(new Event('online'));
    });
    if (surface === 'telegram' || expiryCase) {
      await other.evaluate(() => {
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
        window.dispatchEvent(new Event('online'));
      });
    }
    await expect.poll(() => replayBodies.length).toBeGreaterThan(0);
    await expect
      .poll(async () => {
        const current = await page.request.get('/api/v1/workouts/today', { headers });
        return (await current.json()).exercises?.[0]?.sets?.[0]?.is_completed;
      })
      .toBe(true);
    const saved = (await (await page.request.get('/api/v1/workouts/today', { headers })).json())
      .exercises[0].sets[0];
    expect(saved).toMatchObject({
      id: setId,
      actual_reps: 8,
      rir: '2',
      is_completed: true,
      version: original.version + 1,
    });
    expect(Number(saved.actual_weight)).toBe(42.5);
    const retry = await page.request.patch(`/api/v1/workouts/sets/${setId}`, {
      headers,
      data: replayBodies[0],
    });
    expect(retry.status()).toBe(200);
    expect((await retry.json()).version).toBe(saved.version);
    expect(new Set(replayBodies.map((body) => body.mutation_id)).size).toBe(1);
    await page.reload();
    await expect(page.getByRole('region', { name: 'День' })).toContainText(
      '1 из 1 подходов отмечено',
    );
    await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
    const finishing = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `/api/v1/workouts/${workoutId}/finish`,
    );
    await page.getByRole('button', { name: 'Завершить тренировку', exact: true }).click();
    expect((await finishing).status()).toBe(200);
    const summary = await page.request.get('/api/v1/workouts/history/summary', { headers });
    expect(await summary.json()).toMatchObject({
      workouts_completed: 1,
      completed_sets: 1,
      volume_kg: 340,
    });
  });
}

const historyImports = [
  {
    label: 'hevy',
    provider: 'hevy',
    csv: 'title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,set_type,weight_lbs,reps,distance_miles,duration_seconds,rpe\nSynthetic,"22 Dec 2025, 08:00","22 Dec 2025, 08:37",,barbell bench press,,,0,normal,100,8,0,0,\n',
  },
  {
    label: 'strong-legacy',
    provider: 'strong',
    csv: 'Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE\n2025-12-22 08:00:00,Synthetic,37m,barbell bench press,1,100,8,0,0,,,\n',
  },
  {
    label: 'strong-6.2',
    provider: 'strong',
    csv: 'Workout #;Date;Workout Name;Duration (sec);Exercise Name;Set Order;Weight (kg);Reps;RPE;Distance (meters);Seconds;Notes;Workout Notes\n21;2025-12-22 08:00:00;Synthetic;2220;barbell bench press;1;45.3599;8;;0;0;;\n',
  },
  {
    label: 'fitnotes-android',
    provider: 'fitnotes',
    csv: 'Date,Exercise,Category,Weight,Weight Unit,Reps,Distance,Distance Unit,Time,Comment\n2025-12-22,barbell bench press,Chest,100,lbs,8,,,,\n',
  },
  {
    label: 'fitnotes-ios',
    provider: 'fitnotes',
    csv: 'Date,Exercise,Category,Weight (kg),Weight (lbs),Reps,Distance,Distance Unit,Time,Notes,Kind\n2025-12-22,barbell bench press,Chest,,100,8,,,,,wr\n',
  },
] as const;

for (const [index, scenario] of historyImports.entries()) {
  test(`PostgreSQL browser workout history import: ${scenario.label}`, async ({ page }) => {
    const login = await page.request.post('/api/v1/auth/dev-login', {
      data: { telegram_user_id: Date.now() * 10 + index, full_name: 'Synthetic QA' },
    });
    expect(login.status()).toBe(200);
    const token = (await login.json()).access_token as string;
    const headers = { Authorization: `Bearer ${token}` };
    await page.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
    await page.goto('/app?section=progress&progress_view=history');
    await page.getByRole('button', { name: 'Импортировать историю' }).click();
    await page.getByLabel('Источник').selectOption(scenario.provider);
    if (scenario.provider === 'strong')
      await page.getByLabel('Единица веса в файле').selectOption('lb');
    const upload = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/workout-history-imports',
    );
    await page.getByLabel('Выбрать CSV-файл').setInputFiles({
      name: 'synthetic.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(
        scenario.csv +
          (scenario.label === 'fitnotes-android'
            ? '2025-12-22,barbell bench press,Chest,110,lbs,2,,,,\n'
            : scenario.label === 'fitnotes-ios'
              ? '2025-12-22,barbell bench press,Chest,,110,2,,,,,wr\n'
              : ''),
      ),
    });
    const uploaded = await upload;
    expect(uploaded.status()).toBe(201);
    const preview = await uploaded.json();
    expect(preview.rows[0].blocking_issues).toEqual([]);
    expect(preview.rows[0].weight_kg).toBe('45.36');
    if (scenario.label === 'strong-6.2')
      expect(preview.rows[0].provider_fields['Weight (kg)']).toBe('45.3599');
    if (scenario.provider === 'fitnotes') {
      expect(preview.rows[0].source.set_status).toBe('');
      expect(preview.rows).toHaveLength(2);
      const excluding = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith('/resolve'),
      );
      await page.getByRole('button', { name: `Исключить строку ${preview.rows[1].line}` }).click();
      const excluded = await excluding;
      expect(excluded.status()).toBe(200);
      expect((await excluded.json()).rows[1].excluded).toBe(true);
      const resolved = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith('/resolve'),
      );
      await page.getByLabel('Тип подхода, если знаете').first().selectOption('working');
      expect((await resolved).status()).toBe(200);
    }
    const before = await page.request.get('/api/v1/workouts/history/summary', { headers });
    expect((await before.json()).workouts_completed).toBe(0);
    await page.getByRole('button', { name: 'Продолжить' }).click();
    if (scenario.provider === 'fitnotes') {
      await expect(page.getByRole('button', { name: 'Сохранить историю' })).toBeDisabled();
      await page
        .getByRole('checkbox', { name: 'Подтверждаю, что выбранные подходы выполнены' })
        .check();
    }
    const confirming = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith('/confirm'),
    );
    await page.getByRole('button', { name: 'Сохранить историю' }).click();
    const confirmed = await confirming;
    expect(confirmed.status()).toBe(200);
    const result = await confirmed.json();
    expect(result.result).toMatchObject({ workout_count: 1, set_count: 1 });
    await expect(page.getByText('История дополнена')).toBeVisible();
    const retry = await page.request.post(new URL(confirmed.url()).pathname, {
      headers: { ...headers, 'Content-Type': 'application/json' },
      data: confirmed.request().postData(),
    });
    expect(retry.status()).toBe(200);
    expect((await retry.json()).result).toEqual(result.result);
    const summary = await page.request.get('/api/v1/workouts/history/summary', { headers });
    expect(await summary.json()).toMatchObject({
      workouts_completed: 1,
      completed_sets: 1,
      volume_kg: 362.88,
    });
    const analytics = await page.request.get(
      '/api/v1/workouts/progress/training-analytics?date_from=2025-12-22&date_to=2025-12-22',
      { headers },
    );
    expect(analytics.status()).toBe(200);
    expect(await analytics.json()).toMatchObject({
      completed_workout_count: 1,
      completed_set_count: 1,
      external_load_volume_kg: 362.88,
    });
    await page.getByRole('button', { name: 'Открыть историю' }).click();
    await expect(
      page.getByRole('article', {
        name: `Тренировка ${scenario.provider === 'fitnotes' ? 'FitNotes' : 'Synthetic'} в истории`,
      }),
    ).toBeVisible();
  });
}

test('migrated PostgreSQL serves a real browser nutrition transaction and idempotent retry', async ({
  page,
}) => {
  const apiRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/v1/'))
      apiRequests.push(`${request.method()} ${url.pathname}`);
  });

  await page.goto('/login');
  const devLogin = page.getByRole('region', { name: 'Локальный режим разработки' });
  await expect(devLogin).toBeVisible();
  await devLogin.getByRole('button', { name: 'Клиент', exact: true }).click();
  await page.getByRole('heading', { level: 1, name: /^Сегодня ·/ }).waitFor();
  await page.goto('/app?section=nutrition');
  await expect(page).toHaveURL(/\/app\?section=nutrition$/);
  await expect(page.getByRole('heading', { name: 'Питание', exact: true })).toBeVisible();

  await page.getByTestId('nutrition-add-product').click();
  await page.getByRole('dialog').getByRole('button', { name: 'Быстрый ввод' }).click();
  const itemName = `Migrated PostgreSQL browser item ${Date.now()}`;
  await page.getByRole('textbox', { name: 'Название или контекст (необязательно)' }).fill(itemName);
  await page.getByRole('spinbutton', { name: 'Калории' }).fill('321');

  const firstRequestPromise = page.waitForRequest(
    (request) =>
      request.method() === 'POST' &&
      new URL(request.url()).pathname === '/api/v1/nutrition/diary/entries',
  );
  const firstResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/nutrition/diary/entries',
  );
  await page.getByRole('button', { name: 'Сохранить Quick Add' }).click();
  const firstRequest = await firstRequestPromise;
  const firstResponse = await firstResponsePromise;
  expect(firstResponse.status()).toBe(201);
  const firstEntry = (await firstResponse.json()) as { id: number };
  await expect(page.getByText(itemName, { exact: true })).toBeVisible();

  const idempotencyKey = await firstRequest.headerValue('idempotency-key');
  const requestBody = firstRequest.postData();
  expect(idempotencyKey).toBeTruthy();
  expect(requestBody).toBeTruthy();
  const retry = await page.evaluate(
    async ({ body, key }) => {
      const token = sessionStorage.getItem('fit_access_token');
      if (!token) throw new Error('browser access token is missing');
      const response = await fetch('/api/v1/nutrition/diary/entries', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Idempotency-Key': key,
        },
        body,
      });
      return { status: response.status, payload: (await response.json()) as { id: number } };
    },
    { body: requestBody!, key: idempotencyKey! },
  );
  expect(retry.status).toBe(201);
  expect(retry.payload.id).toBe(firstEntry.id);

  await page.reload();
  await expect(page.getByText(itemName, { exact: true })).toHaveCount(1);
  expect(apiRequests).toContain('POST /api/v1/auth/dev-login');
  expect(apiRequests).toContain('GET /api/v1/me');
  expect(apiRequests).toContain('POST /api/v1/nutrition/diary/entries');
});

test('#952 real browser saves a dated goal on migrated PostgreSQL', async ({ page }) => {
  const userId = Date.now() * 10 + 952;
  const login = await page.request.post('/api/v1/auth/dev-login', {
    data: { telegram_user_id: userId, full_name: 'Синтетическая проверка питания' },
  });
  expect(login.status()).toBe(200);
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date());
  const base = { calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 180 };
  const created = await page.request.post('/api/v1/nutrition/targets/manual', {
    headers,
    data: base,
  });
  expect(created.status()).toBe(200);
  await page.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
  await page.goto(`/app?section=nutrition&date=${date}`);
  await page.getByRole('button', { name: 'Изменить на эту дату' }).click();
  await page.getByLabel('Тип дня').selectOption('recovery');
  await page.getByLabel('Калории, ккал').fill('2250');
  await page.getByLabel('Углеводы, г').fill('240');
  await page.getByRole('button', { name: 'Проверить изменения' }).click();
  await expect(page.getByRole('heading', { name: 'Цель на выбранную дату' })).toBeVisible();
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/nutrition/targets/dates',
  );
  await page.getByRole('button', { name: 'Применить к этой дате' }).click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByText('Изменено вручную')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Изменено вручную')).toBeVisible();
  const resolved = await page.request.get(
    `/api/v1/nutrition/targets/for-date?target_date=${date}`,
    { headers },
  );
  expect(await resolved.json()).toMatchObject({
    origin: 'date',
    day_type: 'recovery',
    target: { calories: 2250 },
  });
  const report = await page.request.get(
    `/api/v1/workouts/progress/nutrition-report?period=custom&date_from=${date}&date_to=${date}`,
    { headers },
  );
  expect((await report.json()).daily[0].target_calories).toBe(2250);
  const completed = await page.request.put('/api/v1/nutrition/diary/status', {
    headers,
    data: { diary_date: date, status: 'fasted' },
  });
  expect(completed.status()).toBe(200);
  const denied = await page.request.post('/api/v1/nutrition/targets/dates', {
    headers: { ...headers, 'Idempotency-Key': 'completed-date-952' },
    data: { ...base, effective_from: date },
  });
  expect(denied.status()).toBe(409);
});

testWithoutServiceWorker(
  '#952 Calendar and Coach OS resolve the same future goal without future diary access',
  async ({ page, browser }, info) => {
    test.setTimeout(90_000);
    const athleteId = Date.now() * 10 + info.workerIndex * 2;
    const athleteLogin = await page.request.post('/api/v1/auth/dev-login', {
      data: { telegram_user_id: athleteId, full_name: 'Тестовый спортсмен' },
    });
    const coachLogin = await page.request.post('/api/v1/auth/dev-login', {
      data: { telegram_user_id: athleteId + 1, full_name: 'Тестовый тренер', is_coach: true },
    });
    expect(athleteLogin.status()).toBe(200);
    expect(coachLogin.status()).toBe(200);
    const athleteToken = (await athleteLogin.json()).access_token as string;
    const coachToken = (await coachLogin.json()).access_token as string;
    const athleteHeaders = { Authorization: `Bearer ${athleteToken}` };
    const coachHeaders = { Authorization: `Bearer ${coachToken}` };
    const me = await page.request.get('/api/v1/me', { headers: athleteHeaders });
    expect(me.status()).toBe(200);
    const clientId = (await me.json()).id as number;
    const invite = await page.request.post('/api/v1/coach/invite-links', { headers: coachHeaders });
    expect(invite.status()).toBe(201);
    const code = (await invite.json()).code as string;
    const accepted = await page.request.post('/api/v1/me/coach-invites/link/confirm', {
      headers: athleteHeaders,
      data: { token: code },
    });
    expect(accepted.status()).toBe(204);
    const access = await page.request.get('/api/v1/me/trainer/nutrition-access', {
      headers: athleteHeaders,
    });
    expect(access.status()).toBe(200);
    const relationshipId = (await access.json()).relationship_id as number;

    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(
      new Date(),
    );
    const date = new Date(`${today}T12:00:00Z`);
    const todayWeekday = (date.getUTCDay() + 6) % 7;
    // On Sunday the week strip has no future day, so advance only the browser calendar to Monday.
    if (todayWeekday === 6) date.setUTCDate(date.getUTCDate() + 1);
    const calendarToday = date.toISOString().slice(0, 10);
    date.setUTCDate(date.getUTCDate() + 1);
    const future = date.toISOString().slice(0, 10);
    const futureWeekday = (date.getUTCDay() + 6) % 7;
    const exercises = await page.request.get('/api/v1/programs/exercises', {
      headers: athleteHeaders,
    });
    expect(exercises.status()).toBe(200);
    const exercise = (await exercises.json())[0];
    expect(exercise).toBeTruthy();
    const template = await page.request.post('/api/v1/programs/templates', {
      headers: athleteHeaders,
      data: {
        title: 'Тестовая программа',
        goal: 'strength',
        level: 'beginner',
        assign_after_create: false,
        week_cycle: { length_weeks: 1, repeat: true },
        days: [
          {
            title: 'Тестовый день',
            exercises: [
              {
                exercise_id: exercise.id,
                prescribed_sets: 2,
                prescribed_reps: '8',
                rest_seconds: 90,
              },
            ],
          },
        ],
      },
    });
    expect(template.status()).toBe(200);
    const assigned = await page.request.post(
      `/api/v1/programs/templates/${(await template.json()).template.id}/assign-to-me`,
      {
        headers: athleteHeaders,
        data: { start_date: today, duration_weeks: 8, schedule_weekdays: [todayWeekday] },
      },
    );
    expect(assigned.status()).toBe(200);
    const programId = (await assigned.json()).user_program_id as number;
    const target = { calories: 2200, protein_g: 150, fat_g: 70, carbs_g: 242 };
    const rule = await page.request.post('/api/v1/nutrition/targets/schedule', {
      headers: { ...athleteHeaders, 'Idempotency-Key': `qa952-future-${athleteId}` },
      data: {
        ...target,
        program_id: programId,
        revision_number: 1,
        effective_from: future,
        scope: 'recovery',
        day_type: 'recovery',
        week_type: null,
      },
    });
    expect(rule.status()).toBe(200);
    const forbidden = await page.request.get(`/api/v1/nutrition/diary?diary_date=${future}`, {
      headers: athleteHeaders,
    });
    expect(forbidden.status()).toBe(422);
    const forbiddenWrite = await page.request.post('/api/v1/nutrition/diary/entries', {
      headers: { ...athleteHeaders, 'Idempotency-Key': `qa952-future-write-${athleteId}` },
      data: {
        diary_date: future,
        meal_type: 'lunch',
        amount: '1',
        amount_unit: 'serving',
        quick_add: { name: 'Тест', energy_kcal: '500' },
      },
    });
    expect(forbiddenWrite.status()).toBe(422);
    const resolved = await page.request.get(
      `/api/v1/nutrition/targets/for-date?target_date=${future}`,
      { headers: athleteHeaders },
    );
    expect(resolved.status()).toBe(200);
    const canonical = await resolved.json();
    expect(canonical).toMatchObject({ date: future, origin: 'schedule', target });
    const trainerDay = await page.request.get(
      `/api/v1/coach-nutrition-proposals/clients/${clientId}/day?target_date=${future}`,
      { headers: coachHeaders },
    );
    expect(trainerDay.status()).toBe(200);
    const trainer = await trainerDay.json();
    expect(trainer).toMatchObject({
      target_id: canonical.target.id,
      program: { program_id: programId },
      binding: { revision_number: 1 },
      day: { plan_date: future },
    });
    expect(Number(trainer.day.targets.energy_kcal)).toBe(2200);
    expect(Number(trainer.day.targets.protein_g)).toBe(150);
    expect(Number(trainer.day.targets.fat_g)).toBe(70);
    expect(Number(trainer.day.targets.carbs_g)).toBe(242);

    const requests: string[] = [];
    page.on('request', (request) => requests.push(request.url()));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem('app-theme', sessionStorage.getItem('qa_theme') ?? 'light'),
    );
    await page.addInitScript(
      (token) => sessionStorage.setItem('fit_access_token', token),
      athleteToken,
    );
    if (todayWeekday === 6)
      await page.clock.setFixedTime(new Date(`${calendarToday}T12:00:00+03:00`));
    await page.goto('/app?section=today');
    const week = page.getByRole('navigation', { name: 'Эта неделя' });
    const futureButton = week.locator('button.week-strip__day').nth(futureWeekday);
    await futureButton.focus();
    await expect(futureButton).toBeFocused();
    await futureButton.press('Enter');
    await expect(futureButton).toHaveAttribute('aria-pressed', 'true');
    const summary = page.getByRole('region', { name: /Цель на/ });
    await expect(summary).toContainText('2200 ккал');
    for (const value of ['150 г', '70 г', '242 г', 'По программе'])
      await expect(summary).toContainText(value);
    await expect(summary).not.toContainText('Осталось');
    await expect(summary.getByRole('link', { name: /дневник/i })).toHaveCount(0);
    expect(requests.some((url) => url.includes(`/nutrition/diary?diary_date=${future}`))).toBe(
      false,
    );
    await page.screenshot({ path: info.outputPath('future-target-desktop-light.png') });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => sessionStorage.setItem('qa_theme', 'dark'));
    await page.reload();
    await week.locator('button.week-strip__day').nth(futureWeekday).click();
    await expect(summary).toContainText('2200 ккал');
    await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect(requests.some((url) => url.includes(`/nutrition/diary?diary_date=${future}`))).toBe(
      false,
    );
    await summary.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath('future-target-mobile-dark.png') });

    const coachContext = await browser.newContext({ serviceWorkers: 'block' });
    const coach = await coachContext.newPage();
    await coach.addInitScript(
      (token) => sessionStorage.setItem('fit_access_token', token),
      coachToken,
    );
    if (todayWeekday === 6)
      await coach.clock.setFixedTime(new Date(`${calendarToday}T12:00:00+03:00`));
    await coach.goto(`/coach?tab=clients&client_id=${clientId}`);
    const switchCoach = coach.getByRole('button', { name: 'Тренер', exact: true });
    if (await switchCoach.isVisible()) await switchCoach.click();
    await coach.locator('#coach-client-nutrition > summary').click();
    await coach.getByRole('button', { name: 'Открыть питание клиента' }).click();
    await expect(coach.locator('.coach-nutrition-assigned')).toContainText('2200 ккал');
    await expect(coach.locator('.coach-nutrition-assigned')).toContainText(
      new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' }).format(
        date,
      ),
    );
    const revoked = await page.request.put('/api/v1/me/trainer/nutrition-access', {
      headers: athleteHeaders,
      data: { relationship_id: relationshipId, nutrition_access: false },
    });
    expect(revoked.status()).toBe(200);
    const denied = await page.request.get(
      `/api/v1/coach-nutrition-proposals/clients/${clientId}/day?target_date=${future}`,
      { headers: coachHeaders },
    );
    expect(denied.status()).toBe(404);
    await coach.reload();
    await coach.locator('#coach-client-nutrition > summary').click();
    await coach.getByRole('button', { name: 'Открыть питание клиента' }).click();
    await expect(coach.getByText('Доступ к питанию закрыт')).toBeVisible();
    await expect(coach.locator('.coach-nutrition-assigned')).toHaveCount(0);
    await coachContext.close();
  },
);

const importColumns = [
  'program_title',
  'goal',
  'level',
  'day_number',
  'day_title',
  'exercise_name',
  'prescribed_sets',
  'prescribed_reps',
  'rest_seconds',
  'exercise_id',
  'exercise_slug',
  'metric_type',
  'prescribed_duration_minutes',
  'notes',
  'superset_group',
  'superset_order',
  'prescription',
  'block_number',
  'block_title',
  'block_is_deload',
  'coaching_rule',
];

const programImportViewports = [
  { name: 'desktop light', width: 1440, height: 900, theme: 'light' },
  { name: 'mobile dark', width: 390, height: 844, theme: 'dark' },
] as const;

function csvCell(value: string): string {
  return `"${value.replaceAll('"', '""')}"`;
}

for (const scenario of programImportViewports) {
  test(`PostgreSQL browser import persists a private template at ${scenario.name}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: scenario.width, height: scenario.height });
    await page.addInitScript((theme) => localStorage.setItem('app-theme', theme), scenario.theme);

    await page.goto('/login');
    const devLogin = page.getByRole('region', { name: 'Локальный режим разработки' });
    await expect(devLogin).toBeVisible();
    await devLogin.getByRole('button', { name: 'Клиент', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: /^Сегодня ·/ })).toBeVisible();

    const suffix = Date.now();
    const programTitle = `Импорт браузера ${scenario.name} ${suffix}`;
    const row = [
      '',
      '',
      '',
      '1',
      'Силовая 1',
      `Упражнение для ручного сопоставления ${scenario.name}`,
      '3',
      '8-12',
      '90',
      '',
      '',
      'strength',
      '',
      '',
      '',
      '',
      '',
      '',
      '',
      '',
      '',
    ];
    const source = [
      '#yfc_template_version,1',
      importColumns.map(csvCell).join(','),
      row.map(csvCell).join(','),
    ].join('\n');

    await page.goto('/app?section=programs&view=manage&panel=create');
    await expect(page.getByRole('heading', { name: 'Импорт программы' })).toBeVisible();

    const accessToken = await page.evaluate(() => sessionStorage.getItem('fit_access_token'));
    if (!accessToken) throw new Error('browser access token is missing');
    const exerciseResponse = await page.request.post(
      new URL('/api/v1/programs/exercises', page.url()).toString(),
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        data: { title: `CI import strength ${scenario.name} ${suffix}`, metric_type: 'strength' },
      },
    );
    expect(exerciseResponse.status()).toBe(201);
    const strengthExercise = (await exerciseResponse.json()) as {
      id: number;
      title: string;
      metric_type: string;
    };

    const upload = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === '/api/v1/programs/imports',
    );
    await page.getByLabel('Загрузить документ программы').setInputFiles({
      name: `program-import-${scenario.name.replaceAll(' ', '-')}.csv`,
      mimeType: 'text/csv',
      buffer: Buffer.from(source),
    });
    expect((await upload).status()).toBe(201);
    await expect(
      page.getByRole('heading', { name: 'Проверьте план перед сохранением' }),
    ).toBeVisible();

    await page.getByLabel('Название программы').fill(programTitle);
    await page.getByLabel('Цель', { exact: true }).selectOption('maintenance');
    await page.getByLabel('Уровень', { exact: true }).selectOption('beginner');

    const exercisePicker = page.getByRole('combobox', { name: 'Упражнение для строки 3' });
    await exercisePicker.fill(strengthExercise.title);
    const exerciseOption = page.getByRole('option', { name: strengthExercise.title });
    await expect(exerciseOption).toBeVisible();
    await exerciseOption.click();
    await expect(exercisePicker).toHaveValue(strengthExercise.title);

    const resolved = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname.endsWith('/resolve'),
    );
    await page.getByRole('button', { name: 'Применить исправления' }).click();
    expect((await resolved).status()).toBe(200);
    const confirm = page.getByRole('button', { name: 'Сохранить шаблон' });
    await expect(confirm).toBeEnabled();

    if (scenario.width < 500) {
      const documentWidth = await page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      }));
      expect(documentWidth.content).toBeLessThanOrEqual(documentWidth.viewport);
    }

    const confirmation = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname.endsWith('/confirm'),
    );
    await confirm.click();
    const response = await confirmation;
    expect(response.status()).toBe(200);
    expect((await response.json()).template.title).toBe(programTitle);
    await expect(page.getByRole('heading', { name: 'Шаблон сохранён' })).toBeVisible();
    await page.getByRole('button', { name: 'Открыть в моих шаблонах' }).click();

    await page.reload();
    await expect(page.getByText(programTitle, { exact: true })).toBeVisible();
  });
}

test('#1381 real XLSX import saves and schedules the returned assignment in PostgreSQL', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 393, height: 844 });
  const login = await page.request.post('/api/v1/auth/dev-login', {
    data: { telegram_user_id: Date.now() * 10 + info.workerIndex, full_name: 'Проверка импорта' },
  });
  expect(login.status()).toBe(200);
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const file = await page.request.get('/api/v1/programs/imports/template.xlsx', { headers });
  expect(file.status()).toBe(200);
  const exercise = await page.request.post('/api/v1/programs/exercises', {
    headers,
    data: { title: `Синтетическое упражнение ${Date.now()}`, metric_type: 'strength' },
  });
  expect(exercise.status()).toBe(201);
  const exerciseTitle = (await exercise.json()).title as string;
  await page.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
  await page.goto('/app?section=programs&view=manage&panel=create');
  const uploading = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/programs/imports',
  );
  await page.getByLabel('Загрузить документ программы').setInputFiles({
    name: 'synthetic-program.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: await file.body(),
  });
  const upload = await uploading;
  expect(upload.status()).toBe(201);
  const preview = (await upload.json()) as {
    rows: { match_status: string; resolved_exercise_title: string | null }[];
  };
  expect(preview.rows).toHaveLength(1);
  await expect(
    page.getByRole('heading', { name: 'Проверьте план перед сохранением' }),
  ).toBeVisible();
  await page.getByLabel('Название программы').fill('Синтетическая программа 1381');
  let expectedExerciseTitle = preview.rows[0]?.resolved_exercise_title;
  if (preview.rows[0]?.match_status !== 'matched') {
    const picker = page.getByRole('combobox', { name: 'Упражнение для строки 3' });
    await picker.scrollIntoViewIfNeeded();
    await picker.fill(exerciseTitle);
    await page.getByRole('option', { name: exerciseTitle }).click({ timeout: 5000 });
    await page.getByLabel('Название программы').click();
    await picker.click();
    await picker.press('ArrowDown');
    await picker.press('Enter');
    await expect(picker).toHaveValue(exerciseTitle);
    expectedExerciseTitle = exerciseTitle;
  }
  expect(expectedExerciseTitle).toBeTruthy();
  const resolving = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname.endsWith('/resolve'),
  );
  await page.getByRole('button', { name: 'Применить исправления' }).click();
  expect((await resolving).status()).toBe(200);
  const openSchedule = page.getByRole('button', { name: 'Сохранить и назначить' });
  await expect(openSchedule).toBeEnabled();
  if (process.env.YFC_1381_EVIDENCE) {
    await openSchedule.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: info.outputPath('real-xlsx-preview.png'),
      animations: 'disabled',
    });
  }
  await openSchedule.click();
  const dialog = page.getByRole('dialog', { name: 'Синтетическая программа 1381' });
  await expect(dialog).toBeVisible();
  const panel = await dialog.locator('.assignment-modal').boundingBox();
  expect(panel).not.toBeNull();
  expect(panel!.y).toBeGreaterThanOrEqual(0);
  expect(panel!.y + panel!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  const start = dialog.getByLabel('Начать не раньше');
  const startDate = new Date(`${await start.inputValue()}T12:00:00Z`);
  startDate.setUTCDate(startDate.getUTCDate() + 7);
  await start.fill(startDate.toISOString().slice(0, 10));
  await expect(dialog).toContainText('программа будет запланирована');
  if (process.env.YFC_1381_EVIDENCE) {
    await page.screenshot({
      path: info.outputPath('real-xlsx-schedule.png'),
      animations: 'disabled',
    });
  }
  await page.keyboard.press('Tab');
  await expect(dialog.locator(':focus')).toHaveCount(1);
  const assignment = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname.endsWith('/assign-to-me'),
  );
  await dialog.getByRole('button', { name: 'Сохранить и назначить' }).click();
  const response = await assignment;
  expect(response.status()).toBe(200);
  const assigned = (await response.json()) as { user_program_id: number; status: string };
  expect(assigned.status).toBe('scheduled');
  await expect(page.getByRole('heading', { name: 'Программа запланирована' })).toBeVisible();
  const outcomeButtonHeights = await page
    .locator('.program-import-outcome button')
    .evaluateAll((buttons) => buttons.map((button) => button.getBoundingClientRect().height));
  expect(Math.min(...outcomeButtonHeights)).toBeGreaterThanOrEqual(44);
  if (process.env.YFC_1381_EVIDENCE) {
    await page.locator('.program-import-outcome').scrollIntoViewIfNeeded();
    await page.screenshot({
      path: info.outputPath('real-xlsx-scheduled.png'),
      animations: 'disabled',
    });
  }
  const templates = await page.request.get('/api/v1/programs/templates/mine', { headers });
  expect((await templates.json()) as object[]).toContainEqual(
    expect.objectContaining({
      title: 'Синтетическая программа 1381',
      assigned_program_id: assigned.user_program_id,
      assigned_program_status: 'scheduled',
    }),
  );
  await page.getByRole('button', { name: 'Открыть программу' }).click();
  await expect(page).toHaveURL(new RegExp(`assigned_program_id=${assigned.user_program_id}`));
  await expect(page.getByRole('article', { name: 'Жизненный цикл программы' })).toContainText(
    'Запланирована',
  );
  await expect(page.getByRole('heading', { name: expectedExerciseTitle! })).toBeVisible();
});

test('#1335 real PostgreSQL generator rechecks an explicit suggestion before confirmation', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  const login = await page.request.post('/api/v1/auth/dev-login', {
    data: { telegram_user_id: 13_350_001, full_name: 'Проверка подбора' },
  });
  expect(login.status()).toBe(200);
  const accessToken = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${accessToken}` };
  await page.addInitScript(
    (token) => sessionStorage.setItem('fit_access_token', token),
    accessToken,
  );
  const beforeResponse = await page.request.get('/api/v1/programs/templates/mine', { headers });
  expect(beforeResponse.status()).toBe(200);
  const beforeIds = (await beforeResponse.json()).map((item: { id: number }) => item.id);
  let browserConfirms = 0;
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      new URL(request.url()).pathname === '/api/v1/programs/generator/confirm'
    )
      browserConfirms++;
  });
  await page.goto('/app?section=programs&view=manage&start=generator');
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('radio', { name: /Рекомпозиция/ }).check();
  await dialog.getByRole('button', { name: 'Далее' }).click();
  await dialog.getByRole('radio', { name: /Начинаю или возвращаюсь/ }).check();
  await dialog.getByRole('button', { name: 'Далее' }).click();
  await dialog.locator('input[name="generator-frequency"][value="2"]').check();
  await dialog.getByRole('button', { name: 'Далее' }).click();
  await dialog.getByRole('radio', { name: /60 минут/ }).check();
  await dialog.getByRole('button', { name: 'Далее' }).click();
  await dialog.getByRole('radio', { name: /Дома/ }).check();
  await dialog.getByRole('checkbox', { name: 'Собственный вес' }).check();
  const firstPromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/programs/generator/preview',
  );
  await dialog.getByRole('button', { name: 'Показать программу' }).click();
  const first = await firstPromise;
  expect(first.status()).toBe(200);
  expect(first.request().postDataJSON()).toMatchObject({
    goal: 'recomposition',
    experience: 'beginner',
    days_per_week: 2,
    training_location: 'home',
    available_equipment_ids: ['bodyweight'],
  });
  const rejected = await first.json();
  expect(rejected.status).toBe('no_compatible');
  expect(rejected.draft_token).toBeNull();
  expect(rejected.suggestions.length).toBeGreaterThan(0);
  const suggestion = rejected.suggestions[0];
  const secondPromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/programs/generator/preview',
  );
  await dialog.getByRole('button', { name: 'Применить предложенное изменение' }).first().click();
  const second = await secondPromise;
  expect(second.status()).toBe(200);
  expect(second.request().postDataJSON()).toEqual(suggestion.inputs);
  const checked = await second.json();
  expect(checked.status).toBe('preview');
  expect(checked.program.goal).toBe(suggestion.inputs.goal);
  expect(checked.program.days_per_week).toBe(suggestion.inputs.days_per_week);
  const afterPreview = await page.request.get('/api/v1/programs/templates/mine', { headers });
  expect(afterPreview.status()).toBe(200);
  expect((await afterPreview.json()).map((item: { id: number }) => item.id)).toEqual(beforeIds);
  expect(browserConfirms).toBe(0);
  const confirmPromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/v1/programs/generator/confirm',
  );
  await dialog.getByRole('button', { name: 'Подтвердить программу' }).click();
  const confirmation = await confirmPromise;
  expect(confirmation.status()).toBe(200);
  const saved = await confirmation.json();
  expect(saved.idempotent).toBe(false);
  expect(saved.workouts_created).toBeGreaterThan(0);
  expect(browserConfirms).toBe(1);
  await expect(
    dialog.getByRole('heading', { name: saved.template.title, exact: true }),
  ).toBeVisible();
  const retry = await page.request.post('/api/v1/programs/generator/confirm', {
    headers,
    data: { draft_token: checked.draft_token },
  });
  expect(retry.status()).toBe(200);
  expect(await retry.json()).toMatchObject({
    idempotent: true,
    assigned_program_id: saved.assigned_program_id,
    workouts_created: 0,
  });
  const persisted = await page.request.get('/api/v1/programs/templates/mine', { headers });
  expect(persisted.status()).toBe(200);
  expect(
    (await persisted.json()).filter((item: { id: number }) => item.id === saved.template.id),
  ).toHaveLength(1);
});

testWithoutServiceWorker(
  'PostgreSQL nutrition preview matches confirmation and refreshed report',
  async ({ page }, info) => {
    info.setTimeout(60_000);
    await page.setViewportSize({ width: 320, height: 720 });
    const userId = Date.now() * 10 + info.workerIndex;
    const login = await page.request.post('/api/v1/auth/dev-login', {
      data: { telegram_user_id: userId, full_name: 'Синтетическая проверка питания' },
    });
    expect(login.status()).toBe(200);
    const token = (await login.json()).access_token as string;
    const headers = { Authorization: `Bearer ${token}` };
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(
      new Date(),
    );
    const target = await page.request.post('/api/v1/nutrition/targets/manual', {
      headers,
      data: { calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 190 },
    });
    expect(target.status()).toBe(200);
    const food = await page.request.post('/api/v1/nutrition/foods', {
      headers,
      data: {
        name: 'Тестовый продукт для проверки',
        energy_kcal_per_100g: '120',
        protein_g_per_100g: '12',
        fat_g_per_100g: '4',
        carbs_g_per_100g: '8',
        fiber_g_per_100g: null,
      },
    });
    expect(food.status()).toBe(201);
    const foodId = (await food.json()).id as number;
    for (const item of [
      { name: 'Тестовая овсяная каша', energy: '150', protein: '5', fat: '3', carbs: '25' },
      { name: 'Тестовое яблоко', energy: '52', protein: '0.3', fat: '0.2', carbs: '14' },
    ]) {
      const created = await page.request.post('/api/v1/nutrition/foods', {
        headers,
        data: {
          name: item.name,
          energy_kcal_per_100g: item.energy,
          protein_g_per_100g: item.protein,
          fat_g_per_100g: item.fat,
          carbs_g_per_100g: item.carbs,
          fiber_g_per_100g: null,
        },
      });
      expect(created.status()).toBe(201);
      const favorite = await page.request.put(
        `/api/v1/nutrition/foods/${(await created.json()).id}/favorite`,
        { headers },
      );
      expect(favorite.status()).toBe(200);
    }
    const entry = await page.request.post('/api/v1/nutrition/diary/entries', {
      headers,
      data: {
        food_id: foodId,
        diary_date: today,
        meal_type: 'breakfast',
        amount: '100',
        amount_unit: 'g',
      },
    });
    expect(entry.status()).toBe(201);
    await page.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
    await page.goto('/app?section=progress&progress_view=nutrition&progress_period=days_7');
    const report = page.locator('#nutrition-period-report');
    await expect(report.getByRole('heading', { name: 'Отчёт по питанию' })).toBeVisible();
    const dayLink = report.locator(`a[href*="date=${today}"]`).first();
    await expect(dayLink).toBeVisible();
    await dayLink.click();
    await expect(page.getByRole('link', { name: 'К отчёту по питанию' })).toBeVisible();
    const suggestions = page.getByRole('region', { name: 'Варианты из вашей еды' });
    await suggestions.getByRole('button', { name: 'Варианты из вашей еды' }).click();
    await expect(
      suggestions.getByText('Тестовый продукт для проверки', { exact: true }),
    ).toBeVisible();
    await expect(suggestions.locator('.nutrition-suggestion-card:visible')).toHaveCount(2);
    const showAll = suggestions.getByRole('button', {
      name: /Показать все 3 варианта|Свернуть/,
    });
    const secondReview = suggestions
      .locator('.nutrition-suggestion-card:visible')
      .nth(1)
      .getByRole('button', { name: 'Проверить вариант' });
    const checkGap = async () => {
      const previous = await secondReview.boundingBox();
      const toggle = await showAll.boundingBox();
      expect(previous).not.toBeNull();
      expect(toggle).not.toBeNull();
      expect(toggle!.y - previous!.y - previous!.height).toBeGreaterThanOrEqual(11);
    };
    await checkGap();
    await showAll.click();
    await expect(suggestions.locator('.nutrition-suggestion-card:visible')).toHaveCount(3);
    await checkGap();
    const thirdReview = suggestions
      .locator('.nutrition-suggestion-card:visible')
      .nth(2)
      .getByRole('button', { name: 'Проверить вариант' });
    await thirdReview.click();
    await expect(suggestions.locator('.nutrition-suggestion-review')).toBeVisible();
    await suggestions.getByRole('button', { name: 'Вернуться к вариантам' }).click();
    await suggestions.getByRole('button', { name: 'Показать все 3 варианта' }).click();
    await suggestions.getByRole('button', { name: 'Свернуть' }).click();
    const targetCard = suggestions
      .locator('.nutrition-suggestion-card')
      .filter({ hasText: 'Тестовый продукт для проверки' });
    let commitCount = 0;
    let commitBody: Record<string, unknown> | undefined;
    let commitKey = '';
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/v1/nutrition/diary/suggestions/commit') {
        commitCount += 1;
        commitBody = request.postDataJSON() as Record<string, unknown>;
        commitKey = request.headers()['idempotency-key'] ?? '';
      }
    });
    await targetCard.getByRole('button', { name: 'Проверить вариант' }).click();
    const review = suggestions.locator('.nutrition-suggestion-review');
    const nextPreview = page.waitForResponse((response) => {
      if (new URL(response.url()).pathname !== '/api/v1/nutrition/diary/suggestions/preview')
        return false;
      const payload = response.request().postDataJSON() as { items: { amount: string }[] };
      return payload.items[0]?.amount === '150';
    });
    await review.getByLabel('Количество').fill('150');
    const previewResponse = await nextPreview;
    expect(previewResponse.status()).toBe(200);
    const preview = await previewResponse.json();
    expect(Number(preview.before.energy_kcal)).toBe(120);
    expect(Number(preview.addition.energy_kcal)).toBe(180);
    expect(Number(preview.after.energy_kcal)).toBe(300);
    expect(preview.after.fiber_g).toBeNull();
    await expect(review.getByRole('row', { name: /Ккал/ })).toContainText('300');
    await expect(review.getByText(/Прогноз дня после добавления:/)).toContainText('300 ккал');
    for (const name of ['Показатель', 'Было', 'Вариант', 'Станет']) {
      const lines = await review.getByRole('columnheader', { name }).evaluate((header) => {
        const range = document.createRange();
        range.selectNodeContents(header);
        return range.getClientRects().length;
      });
      expect(lines, name).toBe(1);
    }
    await review.getByText('Предпочтения и ограничения', { exact: true }).click();
    const limitPreview = page.waitForResponse((response) => {
      if (new URL(response.url()).pathname !== '/api/v1/nutrition/diary/suggestions/preview')
        return false;
      return response.request().postDataJSON().constraints?.max_fat_g === '8';
    });
    await review.getByLabel('Жиры, г').fill('8');
    expect((await (await limitPreview).json()).constraint_status).toBe('violated');
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeDisabled();
    await review.getByLabel('Жиры, г').fill('10');
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled();

    const excludedInput = review.getByLabel('Найти исключаемый продукт');
    expect((await excludedInput.boundingBox())!.width).toBeGreaterThanOrEqual(120);
    await excludedInput.fill('Тестовый');
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeDisabled();
    await expect(
      page.locator('datalist option[value="Тестовый продукт для проверки"]'),
    ).toHaveCount(1);
    await excludedInput.fill('Тестовый продукт для проверки');
    await review.getByRole('button', { name: 'Добавить исключаемый продукт' }).click();
    await expect(review.getByText('Выбранный вариант содержит исключённый продукт.')).toBeVisible();
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeDisabled();
    await review
      .getByRole('button', { name: 'Убрать Тестовый продукт для проверки из исключений' })
      .click();

    const preferredInput = review.getByLabel('Найти предпочитаемый продукт');
    await preferredInput.fill('Тестовый');
    await expect(
      page.locator('datalist option[value="Тестовый продукт для проверки"]'),
    ).toHaveCount(1);
    await preferredInput.fill('Тестовый продукт для проверки');
    await review.getByRole('button', { name: 'Добавить предпочитаемый продукт' }).click();
    await expect(
      review.getByText('В варианте есть указанный предпочитаемый продукт.'),
    ).toBeVisible();
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled();
    const preferredAdd = review.getByRole('button', { name: 'Добавить предпочитаемый продукт' });
    const excludedAdd = review.getByRole('button', { name: 'Добавить исключаемый продукт' });
    await preferredAdd.hover();
    const background = (button: Element) => getComputedStyle(button).backgroundColor;
    expect(await preferredAdd.evaluate(background)).toBe(await excludedAdd.evaluate(background));
    const removePreferred = review.getByRole('button', {
      name: 'Убрать Тестовый продукт для проверки из предпочтений',
    });
    const buttonSize = await removePreferred.evaluate((button) => ({
      width: button.clientWidth,
      scrollWidth: button.scrollWidth,
      height: button.getBoundingClientRect().height,
    }));
    expect(buttonSize.scrollWidth).toBeLessThanOrEqual(buttonSize.width);
    expect(buttonSize.height).toBeLessThanOrEqual(56);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      320,
    );
    const confirmButton = review.getByRole('button', { name: 'Добавить выбранное' });
    await confirmButton.scrollIntoViewIfNeeded();
    const actionVisibility = await confirmButton.evaluate((button) => {
      const rect = button.getBoundingClientRect();
      const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      return { height: rect.height, receivesPointer: hit != null && button.contains(hit) };
    });
    expect(actionVisibility.height).toBeGreaterThanOrEqual(44);
    expect(actionVisibility.receivesPointer).toBe(true);
    expect(commitCount).toBe(0);
    const confirmed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/nutrition/diary/suggestions/commit',
    );
    await review.getByRole('button', { name: 'Добавить выбранное' }).click();
    expect((await confirmed).status()).toBe(201);
    await expect(targetCard.getByRole('button', { name: 'Проверить вариант' })).toBeVisible();
    expect(commitCount).toBe(1);
    expect(commitKey).toBeTruthy();
    expect(commitBody?.constraints).toEqual({
      max_fat_g: '10',
      preferred_food_ids: [foodId],
      excluded_food_ids: [],
    });
    const retry = await page.request.post('/api/v1/nutrition/diary/suggestions/commit', {
      headers: { ...headers, 'Idempotency-Key': commitKey },
      data: commitBody,
    });
    expect(retry.status()).toBe(201);
    expect((await retry.json()).replayed).toBe(true);
    const diary = await page.request.get(`/api/v1/nutrition/diary?diary_date=${today}`, {
      headers,
    });
    const diaryData = await diary.json();
    expect(Number(diaryData.totals.energy_kcal)).toBe(300);
    expect(diaryData.totals.fiber_g).toBeNull();
    const updatedReport = await page.request.get(
      '/api/v1/workouts/progress/nutrition-report?period=days_7',
      { headers },
    );
    const reportData = await updatedReport.json();
    const todayPoint = reportData.daily.find(
      (item: { diary_date: string }) => item.diary_date === today,
    );
    expect(todayPoint.calories).toBe(300);
    expect(todayPoint.fiber_g).toBeNull();
    expect(reportData.summary.calories.sample_days).toBe(0);

    await targetCard.getByRole('button', { name: 'Проверить вариант' }).click();
    await review.getByText('Предпочтения и ограничения', { exact: true }).click();
    await expect(review.getByLabel('Жиры, г')).toHaveValue('');
    await expect(review.getByRole('button', { name: /Убрать .* из предпочтений/ })).toHaveCount(0);
    await review.getByRole('button', { name: 'Вернуться к вариантам' }).click();

    const planner = page.getByTestId('meal-planner');
    await planner.locator('summary').click();
    const planSuggestions = planner.getByRole('region', { name: 'Варианты для плана' });
    const targetPlanCard = planSuggestions
      .locator('.nutrition-suggestion-card')
      .filter({ hasText: 'Тестовый продукт для проверки' });
    await expect(targetPlanCard).toBeVisible();
    await expect(planSuggestions.locator('.nutrition-suggestion-card:visible')).toHaveCount(3);
    await targetPlanCard.getByRole('button', { name: 'Проверить вариант' }).click();
    const planReview = planSuggestions.locator('.nutrition-suggestion-review');
    const planPreviewResponse = page.waitForResponse((response) => {
      if (new URL(response.url()).pathname !== '/api/v1/nutrition/plans/suggestions/preview')
        return false;
      const payload = response.request().postDataJSON() as { items: { amount: string }[] };
      return payload.items[0]?.amount === '50';
    });
    await planReview.getByLabel('Количество').fill('50');
    const planPreview = await (await planPreviewResponse).json();
    expect(Number(planPreview.before.energy_kcal)).toBe(0);
    expect(Number(planPreview.after.energy_kcal)).toBe(60);
    expect(Number(planPreview.diary.energy_kcal)).toBe(300);
    expect(Number(planPreview.projected_after.energy_kcal)).toBe(360);
    await expect(planReview.getByText(/Записано в дневнике:/)).toContainText('300 ккал');
    await expect(planReview.getByText(/Прогноз дня после добавления:/)).toContainText('360 ккал');
    await planReview.getByText('Предпочтения и ограничения', { exact: true }).click();
    await planReview.getByLabel('Ккал', { exact: true }).fill('350');
    await expect(
      planReview.getByText('После добавления будет превышен заданный предел калорий.'),
    ).toBeVisible();
    await expect(planReview.getByRole('button', { name: 'Добавить в план' })).toBeDisabled();
    await planReview.getByLabel('Ккал', { exact: true }).fill('360');
    await expect(planReview.getByRole('button', { name: 'Добавить в план' })).toBeEnabled();
    const planExcluded = planReview.getByLabel('Найти исключаемый продукт');
    await planExcluded.fill('Тестовый');
    await expect(
      page.locator('datalist option[value="Тестовый продукт для проверки"]'),
    ).toHaveCount(1);
    await planExcluded.fill('Тестовый продукт для проверки');
    await planReview.getByRole('button', { name: 'Добавить исключаемый продукт' }).click();
    await expect(
      planReview.getByText('Выбранный вариант содержит исключённый продукт.'),
    ).toBeVisible();
    await expect(planReview.getByRole('button', { name: 'Добавить в план' })).toBeDisabled();
    await planReview
      .getByRole('button', { name: 'Убрать Тестовый продукт для проверки из исключений' })
      .click();
    await expect(planReview.getByRole('button', { name: 'Добавить в план' })).toBeEnabled();
    const planConfirmation = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/v1/nutrition/plans/fill',
    );
    await planReview.getByRole('button', { name: 'Добавить в план' }).click();
    expect((await planConfirmation).status()).toBe(201);
    const planDay = await page.request.get(`/api/v1/nutrition/plans/day?plan_date=${today}`, {
      headers,
    });
    expect(Number((await planDay.json()).planned.energy_kcal)).toBe(60);
    const unchangedDiary = await page.request.get(`/api/v1/nutrition/diary?diary_date=${today}`, {
      headers,
    });
    expect(Number((await unchangedDiary.json()).totals.energy_kcal)).toBe(300);
    await page.getByRole('link', { name: 'К отчёту по питанию' }).click();
    await expect(
      page.locator('#nutrition-period-report').getByRole('heading', { name: 'Отчёт по питанию' }),
    ).toBeVisible();
    await report.getByText('Дни периода: 7').click();
    const todayRow = report
      .locator('tr')
      .filter({ has: page.locator(`time[datetime="${today}"]`) });
    await expect(todayRow.getByText('300 ккал', { exact: true })).toBeVisible();
    await expect(todayRow.getByText('Клетчатка: — г')).toBeVisible();
    await report.locator(`a[href*="date=${today}"]`).first().click();
    await suggestions.getByRole('button', { name: 'Варианты из вашей еды' }).click();
    await targetCard.getByRole('button', { name: 'Проверить вариант' }).click();
    await expect(review.getByRole('button', { name: 'Добавить выбранное' })).toBeEnabled();
    const changedTarget = await page.request.post('/api/v1/nutrition/targets/manual', {
      headers,
      data: { calories: 2200, protein_g: 150, fat_g: 80, carbs_g: 220 },
    });
    expect(changedTarget.status()).toBe(200);
    const staleConfirmation = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/nutrition/diary/suggestions/commit',
    );
    await review.getByRole('button', { name: 'Добавить выбранное' }).click();
    expect((await staleConfirmation).status()).toBe(409);
    await expect(suggestions.getByText(/Данные изменились/)).toBeVisible();
    const emptyLogin = await page.request.post('/api/v1/auth/dev-login', {
      data: { telegram_user_id: userId + 1, full_name: 'Синтетический пустой дневник' },
    });
    expect(emptyLogin.status()).toBe(200);
    const emptyToken = (await emptyLogin.json()).access_token as string;
    const emptyPage = await page.context().newPage();
    await emptyPage.setViewportSize({ width: 320, height: 720 });
    await emptyPage.addInitScript(
      (value) => sessionStorage.setItem('fit_access_token', value),
      emptyToken,
    );
    await emptyPage.goto(`/app?section=nutrition&date=${today}`);
    const emptySuggestions = emptyPage.getByRole('region', { name: 'Варианты из вашей еды' });
    await emptySuggestions.getByRole('button', { name: 'Варианты из вашей еды' }).click();
    await expect(emptySuggestions.getByText('Нет цели КБЖУ на эту дату')).toBeVisible();
    const emptyTarget = await emptyPage.request.post('/api/v1/nutrition/targets/manual', {
      headers: { Authorization: `Bearer ${emptyToken}` },
      data: { calories: 2000, protein_g: 150, fat_g: 70, carbs_g: 190 },
    });
    expect(emptyTarget.status()).toBe(200);
    await emptyPage.reload();
    await emptySuggestions.getByRole('button', { name: 'Варианты из вашей еды' }).click();
    await expect(emptySuggestions.getByText('Пока нет готовых вариантов')).toBeVisible();
    await emptyPage.close();
  },
);
