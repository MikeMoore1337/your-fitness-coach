import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block', timezoneId: 'UTC' });

const PAST_TODAY_MESSAGE =
  'Для сегодняшней даты выберите будущее время сегодня в часовом поясе профиля.';

const surfaces = [
  { name: 'Web', pwa: false, telegram: false },
  { name: 'PWA', pwa: true, telegram: false },
  { name: 'TMA', pwa: false, telegram: true },
] as const;

for (const surface of surfaces) {
  test(`#871 personal reminder rejects a passed time on ${surface.name}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-10T07:30:00Z'));
    await page.setViewportSize({ width: 390, height: 844 });

    if (surface.pwa) {
      await page.addInitScript(() => {
        const nativeMatchMedia = window.matchMedia.bind(window);
        window.matchMedia = (query: string) => {
          const result = nativeMatchMedia(query);
          if (query.includes('display-mode: standalone')) {
            Object.defineProperty(result, 'matches', { configurable: true, value: true });
          }
          return result;
        };
      });
    }
    if (surface.telegram) {
      await installTelegramHarness(page, {
        colorScheme: 'light',
        viewportHeight: 760,
        viewportStableHeight: 844,
        safeAreaInset: { top: 24, right: 0, bottom: 20, left: 0 },
        contentSafeAreaInset: { top: 40, right: 0, bottom: 16, left: 0 },
      });
    }
    await installPlatformApi(page, {
      browserSession: true,
      fixedDate: '2026-10-10',
      notificationState: 'empty',
    });

    const writes: Array<Record<string, unknown>> = [];
    await page.route('**/api/v1/notifications', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const payload = route.request().postDataJSON() as Record<string, unknown>;
      writes.push(payload);
      return route.fulfill({
        status: 201,
        json: {
          id: 901,
          category: 'custom_reminder',
          event_kind: 'reminder',
          title: payload.title,
          body: payload.body,
          created_at: '2026-10-10T07:30:00',
          scheduled_for: payload.scheduled_for,
          status: 'queued',
          delivery_status: 'queued',
          sent_at: null,
          read_at: null,
          action_url: null,
        },
      });
    });

    await page.goto('/app?section=profile#profile-notifications');
    const personal = page.locator('.notification-personal');
    await personal.locator(':scope > summary').click();
    const title = personal.getByRole('textbox', { name: 'Заголовок', exact: true });
    const body = personal.getByRole('textbox', {
      name: 'Текст внутри приложения',
      exact: true,
    });
    const date = personal.locator('input[type="date"]');
    const create = personal.getByRole('button', { name: 'Создать напоминание', exact: true });

    await title.fill('Проверка варианта B');
    await body.fill('Не менять введённое время');
    await date.fill('2026-10-10');
    await create.click();

    await expect(page.getByText(PAST_TODAY_MESSAGE, { exact: true })).toBeVisible();
    await expect(title).toHaveValue('Проверка варианта B');
    await expect(body).toHaveValue('Не менять введённое время');
    await expect(date).toHaveValue('2026-10-10');
    expect(writes).toHaveLength(0);

    await date.fill('2026-10-11');
    await create.click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({ scheduled_for: '2026-10-11T09:00:00' });
  });
}
