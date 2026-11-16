import { expect, test } from '@playwright/test';

test('FatSecret catalog, recurring template and history remain consistent across users', async ({
  page,
}) => {
  test.skip(!process.env.PW_REAL_IMPORT_BASE, 'requires isolated local import backend');
  test.setTimeout(120_000);
  const base = process.env.PW_REAL_IMPORT_BASE!;
  expect(['127.0.0.1', 'localhost']).toContain(new URL(base).hostname);
  const config = await page.request.get(`${base}/api/v1/public/config`);
  expect(config.ok()).toBeTruthy();
  expect(await config.json()).toMatchObject({ app_env: 'dev', enable_dev_auth: true });
  const id = 990_900_000 + (Date.now() % 1_000_000) * 2;
  const tokens: string[] = [];
  for (const telegram_user_id of [id, id + 1]) {
    const login = await page.request.post(`${base}/api/v1/auth/dev-login`, {
      data: { telegram_user_id },
    });
    expect(login.ok()).toBeTruthy();
    const token = (await login.json()).access_token as string;
    tokens.push(token);
    const payload = token.split('.')[1];
    if (!payload) throw new Error('Missing test token payload');
    const issuedAt = JSON.parse(Buffer.from(payload, 'base64url').toString()).iat as number;
    // shortcut: tolerates up to five seconds of backward test-host clock drift; use a stable clock for larger jumps.
    await expect
      .poll(
        async () => {
          const health = await page.request.get(`${base}/health/live`);
          return Math.floor(Date.parse(health.headers().date ?? '') / 1000) - issuedAt;
        },
        { timeout: 30_000 },
      )
      .toBeGreaterThanOrEqual(5);
    const profile = await page.request.patch(`${base}/api/v1/me/profile`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { goal: 'maintenance' },
    });
    expect(profile.ok()).toBeTruthy();
  }
  const [ownerToken, otherToken] = tokens;
  if (!ownerToken || !otherToken) throw new Error('Missing test session');
  const headers = (token: string) => ({ Authorization: `Bearer ${token}` });
  const product = `QA888 synthetic ${id}`;
  const nutrient = ['65', '3', '0', '5', '0', '0', '4', '1', '0', '0'];
  const rows = [
    [
      '# Food Diary Report - Detailed Report',
      'Среда, февраля 28, 2024',
      'Четверг, февраля 29, 2024',
    ],
    ['# Period Summary'],
    ['Сводка', 'Кал ( ккал)', 'Жир( г)', 'Углев( г)', 'Белк( г)'],
    ['Всего', '65', '3', '5', '4'],
    ['# Report Details'],
    [
      'Метка',
      'Кал ( ккал)',
      'Жир( г)',
      'Н/жир( г)',
      'Углев( г)',
      'Клетч( г)',
      'Сахар( г)',
      'Белк( г)',
      'Натри( мг)',
      'Холес( мг)',
      'Калий( мг)',
    ],
    ['Среда, февраля 28, 2024', ...nutrient],
    ['Завтрак', ...nutrient],
    [product, ...nutrient],
    ['100 г'],
    ['Итого за день', ...nutrient],
    ['Четверг, февраля 29, 2024', ...nutrient],
    ['Завтрак', ...nutrient],
    [product, ...nutrient],
    ['100 г'],
    ['Всего', ...nutrient],
  ];
  const csv = Buffer.from(rows.map((row) => row.map((v) => `"${v}"`).join(',')).join('\r\n'));
  await page.addInitScript(
    (value) => sessionStorage.setItem('fit_access_token', value),
    ownerToken,
  );
  await page.goto(`${base}/app?section=nutrition`);
  await page.getByRole('button', { name: /Импорт питания/ }).click();
  await page
    .locator('#nutrition-import-file')
    .setInputFiles({ name: 'synthetic.csv', mimeType: 'text/csv', buffer: csv });
  const upload = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === '/api/v1/nutrition/imports' &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Проверить файл' }).click();
  const uploaded = await upload;
  expect(uploaded.status()).toBe(201);
  const draft = await uploaded.json();
  expect(draft.rows).toHaveLength(2);
  const reviewRows = async () => {
    for (let index = 0; index < 2; index++) {
      await page.getByRole('button', { name: 'Разобрать' }).nth(index).click();
      await page.locator(`#kind-${index}`).selectOption('standard_food');
      await page.locator(`#basis-${index}`).selectOption('per_100_g');
      for (const [field, value] of [
        ['energy', '65'],
        ['protein', '4'],
        ['fat', '3'],
        ['carbs', '5'],
      ] as const)
        await page.locator(`#${field}-${index}`).fill(value);
      await page.getByRole('checkbox', { name: /Я проверил/ }).check();
      await page.getByRole('button', { name: 'Проверить продукт' }).click();
      await expect(page.locator(`#kind-${index}`)).toHaveCount(0);
    }
  };
  await reviewRows();
  await page.getByRole('button', { name: 'Продолжить' }).click();
  const catalogResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/catalog/confirm') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Подтвердить импорт' }).click();
  const catalog = await (await catalogResponse).json();
  expect(catalog.rows).toHaveLength(2);
  expect(new Set(catalog.rows.map((row: { food_id: number }) => row.food_id)).size).toBe(1);
  await expect(page.getByRole('heading', { name: 'Результат импорта' })).toBeVisible();
  const search = await page.request.get(
    `${base}/api/v1/nutrition/foods/search?q=${encodeURIComponent(product)}`,
    { headers: headers(otherToken) },
  );
  expect(search.ok()).toBeTruthy();
  expect(JSON.stringify(await search.json())).toContain(product);
  await page.getByRole('button', { name: 'Посмотреть предложения' }).click();
  await expect(page.getByText('2 из 2 дней')).toBeVisible();
  await page.getByRole('button', { name: 'Проверить состав' }).click();
  await page.getByLabel('Название шаблона').fill('QA888 шаблон');
  await page.locator('#recurring-amount-0').fill('120');
  await page.getByRole('button', { name: 'Сравнить КБЖУ' }).click();
  await page.getByRole('checkbox', { name: /Я проверил данные/ }).check();
  const templateResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/recurring-meals/confirm') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Сохранить шаблон' }).click();
  const templateResult = await (await templateResponse).json();
  await expect(page.getByRole('heading', { name: 'Шаблон сохранён' })).toBeVisible();
  const templateId = templateResult.template.id as number;
  expect(templateResult.existing).toBe(false);
  expect(Number(templateResult.template.items[0].amount)).toBe(120);
  expect(
    (
      await page.request.get(`${base}/api/v1/nutrition/templates/${templateId}`, {
        headers: headers(otherToken),
      })
    ).status(),
  ).toBe(404);
  const diary = async (token: string, date: string) => {
    const response = await page.request.get(`${base}/api/v1/nutrition/diary?diary_date=${date}`, {
      headers: headers(token),
    });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const entries = (day: { meals: { entries: unknown[] }[] }) =>
    day.meals.flatMap((meal) => meal.entries);
  expect(entries(await diary(ownerToken, '2024-02-29'))).toHaveLength(0);
  await page.getByRole('button', { name: 'К предложениям' }).click();
  await page.getByRole('button', { name: 'Не сохранять сейчас' }).click();
  await page.getByRole('button', { name: 'Перенести историю питания' }).click();
  const historyToggle = page.getByLabel(/Перенести историю питания/);
  await expect(historyToggle).not.toBeChecked();
  await historyToggle.check();
  await page.getByLabel('С даты').selectOption('2024-02-29');
  await page.getByRole('button', { name: 'Проверить изменения' }).click();
  await page.getByLabel(/Подтверждаю перенос/).check();
  await page.getByRole('button', { name: 'Перенести историю', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'История перенесена' })).toBeVisible();
  const firstDay = await diary(ownerToken, '2024-02-28');
  const importedDay = await diary(ownerToken, '2024-02-29');
  expect(entries(firstDay)).toHaveLength(0);
  const imported = entries(importedDay) as {
    food_name: string;
    nutrition_source: string;
    nutrition: { energy_kcal: string };
  }[];
  expect(imported).toHaveLength(1);
  expect(imported[0]!.food_name).toBe(product);
  expect(imported[0]!.nutrition_source).toBe('fatsecret');
  expect(Number(imported[0]!.nutrition.energy_kcal)).toBe(65);
  expect(importedDay.status).toBe('incomplete');
  expect(importedDay.status_is_explicit).toBe(false);
  const report = await page.request.get(
    `${base}/api/v1/workouts/progress/nutrition-report?period=custom&date_from=2024-02-28&date_to=2024-02-29`,
    { headers: headers(ownerToken) },
  );
  expect(report.ok()).toBeTruthy();
  const reportData = await report.json();
  expect(
    reportData.daily.find((day: { diary_date: string }) => day.diary_date === '2024-02-29'),
  ).toMatchObject({ status: 'incomplete', calories: 65 });
  expect(reportData.summary.logged_days).toBe(0);
  expect(entries(await diary(otherToken, '2024-02-29'))).toHaveLength(0);
  expect(
    (
      await page.request.get(`${base}/api/v1/nutrition/imports/${draft.id}`, {
        headers: headers(otherToken),
      })
    ).status(),
  ).toBe(404);
  await page.getByRole('button', { name: 'Открыть дневник' }).click();
  await page.getByRole('button', { name: /Импорт питания/ }).click();
  await page
    .locator('#nutrition-import-file')
    .setInputFiles({ name: 'synthetic.csv', mimeType: 'text/csv', buffer: csv });
  await page.getByRole('button', { name: 'Проверить файл' }).click();
  await expect(page.getByText('Предпросмотр: 2 строк')).toBeVisible();
  await reviewRows();
  await page.getByRole('button', { name: 'Продолжить' }).click();
  await page.getByRole('button', { name: 'Подтвердить импорт' }).click();
  await expect(page.getByRole('heading', { name: 'Результат импорта' })).toBeVisible();
  await expect(page.getByText('Добавлено: 0', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Посмотреть предложения' }).click();
  await page.getByRole('button', { name: 'Проверить состав' }).click();
  await page.locator('#recurring-amount-0').fill('120');
  await page.getByRole('button', { name: 'Сравнить КБЖУ' }).click();
  await page.getByRole('checkbox', { name: /Я проверил данные/ }).check();
  await page.getByRole('button', { name: 'Сохранить шаблон' }).click();
  await expect(page.getByRole('heading', { name: 'Такой шаблон уже сохранён' })).toBeVisible();
  const templates = await page.request.get(`${base}/api/v1/nutrition/templates`, {
    headers: headers(ownerToken),
  });
  expect(templates.ok()).toBeTruthy();
  expect((await templates.json()).items).toHaveLength(1);
  expect(entries(await diary(ownerToken, '2024-02-29'))).toHaveLength(1);
  await page.getByRole('button', { name: 'К предложениям' }).click();
  await page.getByRole('button', { name: 'Не сохранять сейчас' }).click();
  await page.getByRole('button', { name: 'Перенести историю питания' }).click();
  await page.getByLabel(/Перенести историю питания/).check();
  await page.getByLabel('С даты').selectOption('2024-02-29');
  await page.getByRole('button', { name: 'Проверить изменения' }).click();
  await page.getByLabel(/Подтверждаю перенос/).check();
  await page.getByRole('button', { name: 'Перенести историю', exact: true }).click();
  await expect(page.getByText(/Добавлено: 0/)).toBeVisible();
  expect(entries(await diary(ownerToken, '2024-02-29'))).toHaveLength(1);
  const sourcePreview = await page.request.get(
    `${base}/api/v1/nutrition/imports/${draft.id}/history`,
    {
      headers: headers(ownerToken),
    },
  );
  expect(sourcePreview.ok()).toBeTruthy();
  expect((await sourcePreview.json()).rows.map((row: { source: unknown }) => row.source)).toEqual(
    draft.rows.map((row: { source: unknown }) => row.source),
  );
  const repeatedSearch = await page.request.get(
    `${base}/api/v1/nutrition/foods/search?q=${encodeURIComponent(product)}`,
    { headers: headers(otherToken) },
  );
  expect(repeatedSearch.ok()).toBeTruthy();
  const products = (await repeatedSearch.json()).items.filter(
    (item: { name: string }) => item.name === product,
  );
  expect(products).toHaveLength(1);
  expect(products[0].id).toBe(catalog.rows[0].food_id);
  await page.goto(`${base}/app?section=nutrition&date=2024-02-29`);
  await expect(page.getByRole('button', { name: /четверг, 29 февраля/i })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.getByRole('button', { name: 'Завтрак', exact: true }).click();
  await expect(page.getByText(product)).toBeVisible();
});
