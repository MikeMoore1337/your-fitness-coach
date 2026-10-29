import { expect, test } from '@playwright/test';

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

    const programTitle = `Импорт браузера ${scenario.name}`;
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
        data: { title: `CI import strength ${scenario.name}`, metric_type: 'strength' },
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
    const confirm = page.getByRole('button', { name: 'Подтвердить и сохранить шаблон' });
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
    await expect(page.getByText('Программа импортирована в личные шаблоны')).toBeVisible();

    await page.goto('/app?section=programs&view=manage&panel=library');
    await page.reload();
    await expect(page.getByText(programTitle, { exact: true })).toBeVisible();
  });
}

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
