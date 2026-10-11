import { expect, test } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

test.use({ serviceWorkers: 'block', timezoneId: 'UTC' });

for (const width of [320, 360, 393, 430]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`#871 personal reminder date ${width} ${theme}`, async ({
      page,
      browserName,
    }, testInfo) => {
      await page.clock.setFixedTime(new Date('2026-10-09T22:30:00Z'));
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((mode) => localStorage.setItem('app-theme', mode), theme);
      if (width === 393) {
        await installTelegramHarness(page, {
          colorScheme: theme,
          viewportHeight: 900,
          safeAreaInset: { top: 24, bottom: 34, left: 0, right: 0 },
        });
      }
      await installPlatformApi(page, { browserSession: width !== 393, fixedDate: '2026-10-10' });
      const writes: Record<string, unknown>[] = [];
      await page.route('**/api/v1/notifications', async (route) => {
        if (route.request().method() !== 'POST') return route.fallback();
        writes.push(route.request().postDataJSON() as Record<string, unknown>);
        if (writes.length === 1) {
          return route.fulfill({
            status: 503,
            json: { detail: 'Напоминание временно не сохранено' },
          });
        }
        return route.fulfill({ json: { id: 901, ...writes.at(-1) } });
      });
      await page.goto('/app?section=profile');
      await page.getByRole('link', { name: 'Уведомления', exact: true }).click();
      const personal = page.locator('.notification-personal');
      await personal.locator(':scope > summary').click();
      const date = personal.locator('input[type="date"]');
      const title = personal.getByRole('textbox', { name: 'Заголовок', exact: true });
      const body = personal.getByRole('textbox', { name: 'Текст внутри приложения', exact: true });
      const create = personal.getByRole('button', { name: 'Создать напоминание', exact: true });
      await expect(date).toHaveAttribute('min', '2026-10-10');
      await title.fill('Проверка даты');
      await body.fill('Мой текст напоминания');
      await date.fill('2026-10-09');
      await create.click();
      if (browserName === 'webkit') {
        await expect(
          page.getByText('Выберите сегодняшнюю или будущую дату.', { exact: true }),
        ).toBeVisible();
      } else {
        expect(await date.evaluate((node: HTMLInputElement) => node.validity.rangeUnderflow)).toBe(
          true,
        );
      }
      expect(writes).toHaveLength(0);
      await page.screenshot({ path: testInfo.outputPath('past-date-blocked.png') });

      await date.fill('');
      await create.click();
      expect(await date.evaluate((node: HTMLInputElement) => node.validity.valueMissing)).toBe(
        true,
      );
      expect(writes).toHaveLength(0);
      await date.fill('2026-10-11');
      await create.click();
      await expect(
        page.getByText('Напоминание временно не сохранено', { exact: true }),
      ).toBeVisible();
      await expect(title).toHaveValue('Проверка даты');
      await expect(body).toHaveValue('Мой текст напоминания');
      await expect(date).toHaveValue('2026-10-11');
      await create.click();
      await expect(page.getByText('Личное напоминание создано', { exact: true })).toBeVisible();
      expect(writes).toHaveLength(2);
      expect(writes[0]).toEqual(writes[1]);
      expect(writes[1]).toMatchObject({
        scheduled_for: '2026-10-11T09:00:00',
        title: 'Проверка даты',
      });

      await date.fill('2026-10-10');
      await create.click();
      await expect.poll(() => writes.length).toBe(3);
      expect(writes[2]).toMatchObject({ scheduled_for: '2026-10-10T09:00:00' });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width + 1,
      );
    });
  }
}
