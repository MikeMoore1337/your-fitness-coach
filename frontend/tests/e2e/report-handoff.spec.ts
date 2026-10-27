import { expect, test, type Page } from '@playwright/test';
import { join } from 'node:path';
import { makeProgressReportFixture } from '../fixtures/progress-report';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const evidenceDir =
  process.env.TASK_83_EVIDENCE_DIR ??
  join(process.cwd(), '../.artifacts/tasks/83/evidence/report-handoff-visual-qa');

const trainer = {
  id: 44,
  telegram_user_id: null,
  username: 'trainer',
  full_name: 'Ирина Тренерова',
  can_open_chat: false,
  chat_url: null,
  chat_unavailable_reason: 'Уведомления остаются внутри приложения',
};

function currentUser() {
  return {
    id: 7,
    telegram_user_id: 7007,
    username: 'mobile_user',
    first_name: 'Анна',
    last_name: 'Петрова',
    photo_url: null,
    custom_avatar: null,
    is_coach: false,
    is_admin: false,
    has_active_program: true,
    has_workout_history: true,
    auth_providers: ['telegram'],
    onboarding: { status: 'complete', required_fields: [], missing_fields: [] },
    profile: {
      full_name: 'Анна Петрова',
      timezone: 'Europe/Moscow',
      goal: 'maintenance',
      level: 'beginner',
      height_cm: 168,
      weight_kg: 67,
      workouts_per_week: 3,
      cardio_trainings_per_week: 1,
      kbju: null,
    },
    trainer,
  };
}

function handoff(status: 'delivered' | 'pending' | 'failed' = 'delivered', attempt = 1) {
  return {
    id: 91,
    trainer,
    period: 'days_30',
    period_start: '2026-07-26',
    period_end: '2026-08-24',
    timezone: 'Europe/Moscow',
    report_contract_version: 'progress-report-v1',
    included_section_ids: ['overview', 'training', 'cardio', 'body', 'nutrition'],
    created_at: '2026-08-24T09:30:00+03:00',
    delivery_status: status,
    delivery_attempt: attempt,
    live: true,
  };
}

async function installReportHandoffApi(page: Page) {
  const report = makeProgressReportFixture();
  let handoffs: ReturnType<typeof handoff>[] = [];
  await page.route(/\/api\/v1\/me$/, async (route) => {
    await route.fulfill({ json: currentUser() });
  });
  await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?.*)?$/, async (route) => {
    await route.fulfill({ json: report });
  });
  await page.route(/\/api\/v1\/report-handoffs(?:\/91(?:\/retry)?)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith('/retry')) {
      const retried = handoff('delivered', 2);
      handoffs = [retried, ...handoffs.filter((item) => item.id !== retried.id)];
      await route.fulfill({ status: 200, json: retried });
      return;
    }
    if (request.method() === 'POST') {
      const created = handoff();
      handoffs = [created, ...handoffs.filter((item) => item.id !== created.id)];
      await route.fulfill({ status: 201, json: created });
      return;
    }
    if (url.pathname.endsWith('/91')) {
      await route.fulfill({
        status: 200,
        json: {
          handoff: handoffs[0] ?? handoff(),
          report,
          data_changed_since_send: false,
        },
      });
      return;
    }
    await route.fulfill({ status: 200, json: handoffs });
  });
}

async function installHandoffNotificationApi(page: Page) {
  await page.route(/\/api\/v1\/notifications$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: [
        {
          id: 91,
          category: 'report_handoff',
          event_kind: 'transactional',
          title: 'Новый отчёт от клиента',
          body: 'Клиент отправил вам отчёт за выбранный период.',
          created_at: '2026-08-24T09:30:00+03:00',
          scheduled_for: '2026-08-24T09:30:00+03:00',
          delivery_status: 'sent',
          sent_at: '2026-08-24T09:30:00+03:00',
          read_at: null,
          action_url:
            '/app?section=progress&report_handoff_id=91&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
        },
      ],
    });
  });
  await page.route(/\/api\/v1\/notifications\/91\/open$/, async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        destination:
          '/app?section=progress&report_handoff_id=91&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
        stale: false,
        message: null,
      },
    });
  });
}

test('handoff preview and delivery status remain clear on desktop and mobile', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportHandoffApi(page);
  await page.emulateMedia({ colorScheme: 'light' });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app/report?period=days_30');

  await expect(
    page.getByRole('heading', { name: 'Отправить отчёт текущему тренеру' }),
  ).toBeVisible();
  await expect(page.getByText('Ирина Тренерова', { exact: true })).toBeVisible();
  await expect(page.getByText('Живые данные', { exact: true })).toBeVisible();
  await expect(page.getByText(/Дневник питания: 80% покрытия/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Отправить отчёт тренеру' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: join(evidenceDir, 'desktop-1280-light-preview.png'),
    fullPage: true,
  });

  await page.getByRole('button', { name: 'Отправить отчёт тренеру' }).click();
  await expect(page.locator('.progress-report-handoff__status')).toContainText(
    'Доставлено в центр уведомлений',
  );
  await expect(page.getByRole('button', { name: 'Отправить обновлённую версию' })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark' });
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: join(evidenceDir, 'mobile-390-dark-delivered.png'),
    fullPage: true,
  });
});

test('notification handoff deep link opens the live report and returns to the center', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportHandoffApi(page);
  await page.goto(
    '/app?section=progress&report_handoff_id=91&return_to=%2Fapp%3Fsection%3Dprofile%23profile-notifications',
  );

  await expect(page).toHaveURL(/\/app\/report\?handoff_id=91/);
  await expect(page.getByText('Отчёт отправлен тренеру', { exact: false })).toBeVisible();
  await expect(page.getByText(/живые данные/, { exact: false })).toBeVisible();
  await expect(page.getByRole('link', { name: /Назад/ })).toHaveAttribute(
    'href',
    '/app?section=profile#profile-notifications',
  );
});

test('notification center opens the handoff and preserves its focus return', async ({ page }) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportHandoffApi(page);
  await installHandoffNotificationApi(page);
  await page.goto('/app?section=profile#profile-notifications');

  const notifications = page.locator('#profile-notifications');
  await expect(notifications).toBeVisible();
  await expect(notifications).toHaveAttribute('open', '');
  const center = notifications.locator('details.notification-center');
  await center.locator('summary').click();
  await notifications.getByRole('button', { name: 'Открыть: Новый отчёт от клиента' }).click();

  await expect(page).toHaveURL(/\/app\/report\?handoff_id=91/);
  await expect(page.getByRole('link', { name: /Назад/ })).toHaveAttribute(
    'href',
    '/app?section=profile#profile-notifications',
  );
});
