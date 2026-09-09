import { expect, test, type Page } from '@playwright/test';

const rootUser = {
  id: 1,
  telegram_user_id: 1001,
  username: 'root_owner',
  first_name: 'Root',
  is_coach: false,
  is_admin: true,
  is_root: true,
  has_active_program: false,
  has_workout_history: false,
  onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
  profile: {
    full_name: 'Владелец продукта',
    goal: 'maintenance',
    level: 'intermediate',
    workouts_per_week: 3,
    timezone: 'Europe/Moscow',
    kbju: null,
  },
  trainer: null,
};

const searchRow = {
  id: 71,
  telegram_user_id: 710071,
  username: 'alexandra_support_case',
  display_name: 'Александра Константинопольская-Северная',
  is_active: true,
  is_trainer: true,
  is_root: false,
  created_at: '2030-01-01T10:00:00Z',
  linked_providers: ['telegram', 'google'],
};

const jobs = [
  {
    job_id: 'notification:7142',
    kind: 'notification',
    user_id: 71,
    status: 'failed',
    created_at: '2030-01-04T10:00:00Z',
    scheduled_for: '2030-01-04T10:00:00Z',
    completed_at: null,
    attempt_count: 3,
    error_code: null,
    retry_allowed: false,
  },
  {
    job_id: 'export:71000000-0000-0000-0000-000000000071',
    kind: 'account_export',
    user_id: 71,
    status: 'error',
    created_at: '2030-01-04T09:00:00Z',
    scheduled_for: null,
    completed_at: '2030-01-04T09:01:00Z',
    attempt_count: null,
    error_code: 'generation_failed',
    retry_allowed: true,
  },
];

const audit = [
  {
    id: 901,
    action: 'root.account_blocked',
    actor_user_id: 1,
    target_user_id: 71,
    resource_type: 'user',
    resource_id: '71',
    reason: 'security_incident',
    created_at: '2030-01-05T10:00:00Z',
  },
];

const detail = {
  ...searchRow,
  identities: [
    {
      provider: 'google',
      identifier: 'a***@example.com',
      verified: true,
      last_login_at: '2030-01-05T09:00:00Z',
    },
  ],
  relationships: [
    {
      id: 404,
      account_role: 'trainer',
      counterparty_user_id: 88,
      counterparty_name: 'Клиент с длинным отображаемым именем',
      status: 'active',
      created_at: '2030-01-01T10:00:00Z',
      accepted_at: '2030-01-01T11:00:00Z',
      ended_at: null,
      ended_reason: null,
      can_end: true,
    },
  ],
  jobs,
  audit_history: audit,
};

async function mockAdminApi(page: Page, { root = true } = {}) {
  await page.addInitScript(() => {
    sessionStorage.setItem('fit_access_token', 'root-e2e-token');
  });
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: { app_env: 'dev', enable_dev_auth: true, telegram_bot_username: 'fit_bot' },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      return route.fulfill({ status: 401, json: { detail: 'No refresh cookie' } });
    }
    if (path.endsWith('/me')) {
      return route.fulfill({ json: { ...rootUser, is_root: root, is_admin: root } });
    }
    if (path.endsWith('/admin/users') && request.method() === 'GET') {
      return route.fulfill({ json: url.searchParams.get('q') ? [searchRow] : [] });
    }
    if (path.endsWith('/admin/users/71') && request.method() === 'GET') {
      return route.fulfill({ json: detail });
    }
    if (path.endsWith('/admin/jobs')) return route.fulfill({ json: jobs });
    if (path.endsWith('/admin/audit')) return route.fulfill({ json: audit });
    if (path.endsWith('/admin/funnel')) {
      return route.fulfill({
        json: {
          period_days: 30,
          cohort_since: '2030-01-01T00:00:00Z',
          analytics_provider_status: 'not_connected',
          coverage_note:
            'Только агрегаты подтверждённых данных аккаунта; anonymous landing, login и demo events не хранятся на сервере.',
          stages: [
            { key: 'registered', account_count: 120, cohort_rate_percent: 100 },
            { key: 'profile_ready', account_count: 91, cohort_rate_percent: 75.8 },
            { key: 'program_activated', account_count: 63, cohort_rate_percent: 52.5 },
            { key: 'core_value_reached', account_count: 48, cohort_rate_percent: 40 },
          ],
        },
      });
    }
    if (path.includes('/admin/') && ['PATCH', 'POST'].includes(request.method())) {
      return route.fulfill({ json: detail });
    }
    return route.fulfill({ status: 404, json: { detail: 'Not mocked' } });
  });
}

async function setTheme(page: Page, theme: 'light' | 'dark') {
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
}

async function openAccount(page: Page) {
  const search = page.getByLabel('Безопасный идентификатор');
  await search.fill('@alexandra_support_case');
  const submit = page.getByRole('button', { name: 'Найти' });
  await expect(submit).toBeEnabled();
  await search.press('Enter');
  const result = page.getByRole('button', {
    name: /Александра Константинопольская-Северная/,
  });
  await result.focus();
  await result.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Александра Константинопольская-Северная' }),
  ).toBeVisible();
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    ),
  ).toBe(true);
}

test('root workspace keeps one desktop scan path and semantic operation boundaries', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setTheme(page, 'light');
  await mockAdminApi(page);
  await page.goto('/admin');
  await openAccount(page);

  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect(page.getByText('a***@example.com')).toBeVisible();
  await expect(page.getByText(/создание других администраторов здесь недоступны/)).toBeVisible();
  await expect(page.getByText('Удалить аккаунт')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /imperson/i })).toHaveCount(0);
  await expect(page.getByText('Заявки тренеров')).toHaveCount(0);
  await expect(page.getByText('Шаблоны программ')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /повтор.*уведом/i })).toHaveCount(0);

  const searchBox = await page.locator('.admin-search').boundingBox();
  const detailBox = await page.locator('.admin-detail').boundingBox();
  expect(searchBox).not.toBeNull();
  expect(detailBox).not.toBeNull();
  expect(searchBox!.x + searchBox!.width).toBeLessThan(detailBox!.x);
  await expectNoHorizontalOverflow(page);

  await page.screenshot({
    path: '../.artifacts/screenshots/task-71/1440-light-account-detail.png',
    fullPage: true,
  });
});

test('tablet dark state keeps job status readable and retry bounded to exports', async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await setTheme(page, 'dark');
  await mockAdminApi(page);
  await page.goto('/admin');
  await page.getByRole('button', { name: 'Задачи' }).click();

  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.getByText('Notification retry отключён')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Повторить экспорт' })).toBeVisible();
  await expect(page.getByRole('button', { name: /повтор.*уведом/i })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-71/768-dark-jobs.png',
    fullPage: true,
  });
});

test('mobile destructive confirmation names the subject and preserves touch geometry', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setTheme(page, 'dark');
  await mockAdminApi(page);
  await page.goto('/admin');
  await openAccount(page);
  await page
    .getByRole('button', { name: 'Заблокировать Александра Константинопольская-Северная' })
    .click();

  const dialog = page.getByRole('dialog', {
    name: 'Заблокировать Александра Константинопольская-Северная',
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Причина: Запрос поддержки/)).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Отмена' })).toBeFocused();
  const actionBoxes = await dialog.getByRole('button').evaluateAll((buttons) =>
    buttons.map((button) => {
      const box = button.getBoundingClientRect();
      return { width: box.width, height: box.height };
    }),
  );
  expect(actionBoxes.every((box) => box.width >= 44 && box.height >= 44)).toBe(true);
  await expect(dialog.locator('.modal__panel')).toHaveCSS('background-color', 'rgb(25, 25, 25)');
  await expect(dialog.locator('.modal__panel')).toHaveCSS('opacity', '1');
  const [cancelBox, confirmBox] = await Promise.all([
    dialog.getByRole('button', { name: 'Отмена' }).boundingBox(),
    dialog.getByRole('button', { name: 'Подтвердить блокировку' }).boundingBox(),
  ]);
  expect(cancelBox).not.toBeNull();
  expect(confirmBox).not.toBeNull();
  expect(cancelBox!.x + cancelBox!.width).toBeLessThanOrEqual(confirmBox!.x);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-71/390-dark-destructive-confirm.png',
  });
});

test('non-root web account receives a controlled permission state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setTheme(page, 'light');
  await mockAdminApi(page, { root: false });
  await page.goto('/admin');

  await expect(page.getByRole('heading', { name: 'Root-доступ не подтверждён' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Вернуться в личный режим' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-71/390-light-permission-denied.png',
    fullPage: true,
  });
});

for (const viewport of [
  { width: 360, height: 800 },
  { width: 430, height: 932 },
]) {
  test(`workspace remains usable at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await setTheme(page, viewport.width === 360 ? 'light' : 'dark');
    await mockAdminApi(page);
    await page.goto('/admin');
    if (viewport.width === 430) {
      await openAccount(page);
    } else {
      await expect(page.getByText('Введите идентификатор')).toBeVisible();
      await expect(page.getByLabel('Безопасный идентификатор')).toBeVisible();
    }
    await expectNoHorizontalOverflow(page);
    const navButtons = await page
      .getByRole('navigation', { name: 'Разделы Root workspace' })
      .getByRole('button')
      .evaluateAll((buttons) =>
        buttons.map((button) => {
          const box = button.getBoundingClientRect();
          return { width: box.width, height: box.height };
        }),
      );
    expect(navButtons.every((box) => box.width >= 44 && box.height >= 44)).toBe(true);
  });
}

test('Telegram Mini App has no admin entry and redirects the direct route', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    Object.assign(window, {
      Telegram: {
        WebApp: {
          initData: 'query_id=tma-root-boundary',
          colorScheme: 'dark',
          themeParams: { bg_color: '#0b0d0c', secondary_bg_color: '#171a18' },
          ready() {},
          expand() {},
          onEvent() {},
          offEvent() {},
          setHeaderColor() {},
          setBackgroundColor() {},
          BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        },
      },
    });
  });
  await mockAdminApi(page);
  await page.goto('/admin?tgWebAppPlatform=android&tgWebAppData=tma-root-boundary');

  await expect(page).toHaveURL(/\/app$/);
  await expect(
    page.getByRole('heading', { name: 'Операции поддержки и безопасности' }),
  ).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Войти и продолжить' })).toBeVisible();
});
