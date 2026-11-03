import { createHmac } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { installTelegramHarness } from '../e2e/fixtures/mobile-tma';

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

for (const surface of ['pwa', 'telegram'] as const) {
  test(`PostgreSQL offline ${surface} reload automatically replays a saved set once`, async ({
    page,
    request,
  }, info) => {
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
    const headers = { Authorization: `Bearer ${token}` };
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
    await page.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
    if (surface === 'telegram') await installTelegramHarness(page, { initData });
    await page.goto('/app?section=today');
    if (surface === 'pwa') {
      await page.waitForFunction(() => navigator.serviceWorker.ready.then(() => true));
      if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))))
        await page.reload();
      await expect
        .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? ''))
        .toContain('/sw.js');
    }
    const other = await page.context().newPage();
    await other.addInitScript((value) => sessionStorage.setItem('fit_access_token', value), token);
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
    const offlineServer = await request.get('/api/v1/workouts/today', { headers });
    expect((await offlineServer.json()).exercises[0].sets[0]).toMatchObject({
      id: setId,
      is_completed: false,
      version: original.version,
    });
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
    if (surface === 'telegram') {
      await page.evaluate(() => {
        sessionStorage.setItem('audit_force_offline', '1');
        sessionStorage.removeItem('fit_authenticated_user_id');
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      });
      await other.evaluate(() =>
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false }),
      );
      await page.addInitScript(() => {
        if (sessionStorage.getItem('audit_force_offline') === '1')
          Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      });
    }
    await page.context().setOffline(false);
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
    if (surface === 'telegram') {
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

  await page.getByRole('button', { name: /Быстрый ввод/ }).click();
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
