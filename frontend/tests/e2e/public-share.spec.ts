import { expect, test, type Page } from '@playwright/test';

const shareId = 'A'.repeat(43);

const programShare = {
  share_id: shareId,
  share_type: 'program',
  status: 'active',
  created_at: '2026-10-03T10:00:00Z',
  public_url: `http://127.0.0.1:4173/share/${shareId}`,
  preview_hash: 'a'.repeat(64),
  snapshot: {
    kind: 'program',
    title: 'Силовая программа · снимок',
    goal: 'strength',
    level: 'beginner',
    duration_weeks: 4,
    days: [
      {
        day_number: 1,
        title: 'Силовой день',
        exercises: [
          {
            exercise_title: 'Приседания',
            metric_type: 'strength',
            prescribed_sets: 3,
            prescribed_reps: '8',
            prescribed_duration_minutes: null,
            rest_seconds: 90,
            weekly_prescriptions: [],
          },
        ],
      },
    ],
  },
};

const authenticatedUser = {
  id: 17,
  telegram_user_id: 7017,
  username: 'browser_user',
  first_name: 'Браузер',
  is_coach: false,
  is_admin: false,
  has_active_program: false,
  has_workout_history: false,
  auth_providers: ['telegram'],
  profile: { full_name: 'Тестовый пользователь', timezone: 'Europe/Moscow', kbju: null },
  trainer: null,
};

async function installPublicShareApi(page: Page) {
  await page.route('**/api/v1/public/config', (route) =>
    route.fulfill({
      json: {
        app_env: 'test',
        enable_dev_auth: false,
        enable_web_auth: false,
        enable_email_auth: false,
        telegram_bot_username: '',
        oauth_providers: [],
      },
    }),
  );
  await page.route('**/api/v1/me', (route) => route.fulfill({ json: authenticatedUser }));
  await page.route('**/api/v1/me/acquisition', (route) => route.fulfill({ status: 204, body: '' }));
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({ json: { access_token: 'refreshed-token' } }),
  );
  await page.route(`**/api/v1/public/shares/${shareId}`, (route) =>
    route.fulfill({ json: programShare }),
  );
}

test('program share is visible as a preview and imports only after explicit confirmation', async ({
  page,
}) => {
  await page.addInitScript(() => sessionStorage.setItem('fit_access_token', 'browser-token'));
  let importCalls = 0;
  await installPublicShareApi(page);
  await page.route(`**/api/v1/shares/${shareId}/import`, async (route) => {
    importCalls += 1;
    await route.fulfill({
      json: {
        share_id: shareId,
        status: 'imported',
        template_id: 91,
        user_program_id: 92,
        workouts_created: 4,
      },
    });
  });

  await page.goto(`/share/${shareId}`);
  await expect(page.getByRole('heading', { name: 'Силовая программа · снимок' })).toBeVisible();
  await expect(page.getByText('Приседания', { exact: true })).toBeVisible();
  await expect(page.getByText(/immutable-снимок программы/)).toBeVisible();
  expect(importCalls).toBe(0);

  await page.getByRole('button', { name: 'Добавить программу' }).click();
  await expect(page.getByRole('dialog', { name: 'Добавить копию программы?' })).toBeVisible();
  expect(importCalls).toBe(0);

  await page
    .getByRole('dialog', { name: 'Добавить копию программы?' })
    .getByRole('button', { name: 'Добавить программу' })
    .click();
  await expect(
    page.getByText('Копия создана через стандартный процесс назначения программы.'),
  ).toBeVisible();
  expect(importCalls).toBe(1);
});

test('revoked or malformed public share remains a non-disclosing error state', async ({ page }) => {
  await page.route('**/api/v1/public/config', (route) =>
    route.fulfill({
      json: {
        app_env: 'test',
        enable_dev_auth: false,
        enable_web_auth: false,
        enable_email_auth: false,
        telegram_bot_username: '',
        oauth_providers: [],
      },
    }),
  );
  await page.route('**/api/v1/me', (route) =>
    route.fulfill({ status: 401, json: { detail: 'Требуется вход' } }),
  );
  await page.route('**/api/v1/me/acquisition', (route) => route.fulfill({ status: 204, body: '' }));
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({ status: 401, json: { detail: 'Сессия отсутствует' } }),
  );
  await page.route('**/api/v1/public/shares/*', (route) =>
    route.fulfill({ status: 404, json: { detail: 'Ссылка недоступна' } }),
  );
  await page.goto(`/share/${'B'.repeat(43)}`);
  await expect(page.getByText('Ссылка недоступна или больше не действует.')).toBeVisible();
  await expect(page.getByText('Силовая программа · снимок', { exact: true })).toHaveCount(0);
});
