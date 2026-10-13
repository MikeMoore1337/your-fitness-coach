import type { Page } from '@playwright/test';
import { expect, test } from './fixtures/mobile-tma';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  setNetworkOffline,
} from './fixtures/mobile-tma';
import { makeProgressReportFixture } from '../fixtures/progress-report';
import { installPlatformApi } from './fixtures/platform-api';

type DailyState = 'empty' | 'partial' | 'filled' | 'error';

type DailyPayload = {
  sleep_quality: number | null;
  sleep_duration_minutes: number | null;
  mood: number | null;
  note: string | null;
};

type DailyRecord = DailyPayload & {
  id: number;
  user_id: number;
  local_date: string;
  timezone_at_entry: string;
  source: 'manual';
  created_at: string;
  updated_at: string;
};

function todayInMoscow(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
}

function shiftDate(localDate: string, days: number): string {
  const date = new Date(`${localDate}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function recordFor(localDate: string, state: Exclude<DailyState, 'error'>): DailyRecord | null {
  if (state === 'empty') return null;
  const partial = state === 'partial';
  return {
    id: 82,
    user_id: 7,
    local_date: localDate,
    timezone_at_entry: 'Europe/Moscow',
    sleep_quality: 4,
    sleep_duration_minutes: partial ? null : 420,
    mood: partial ? null : 5,
    note: partial ? null : 'Личная заметка остаётся только в экспорте.',
    source: 'manual',
    created_at: `${localDate}T08:00:00`,
    updated_at: `${localDate}T08:00:00`,
  };
}

async function installDailyWellbeingApi(page: Page, initialState: DailyState) {
  let state = initialState;
  let record = initialState === 'error' ? null : recordFor(todayInMoscow(), initialState);

  await page.route(/\/api\/v1\/check-ins\/daily(?:\/[^?]+)?(?:\?.*)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathDate = url.pathname.split('/').at(-1);
    const localDate = url.searchParams.get('local_date') ?? pathDate ?? todayInMoscow();

    if (request.method() === 'GET') {
      if (state === 'error') {
        return route.fulfill({ status: 503, json: { detail: 'Временная ошибка сервера' } });
      }
      return route.fulfill({
        json: {
          local_date: localDate,
          today: todayInMoscow(),
          timezone: 'Europe/Moscow',
          record: record ? { ...record, local_date: localDate } : null,
        },
      });
    }

    if (request.method() === 'PUT') {
      const payload = request.postDataJSON() as DailyPayload;
      record = {
        id: record?.id ?? 82,
        user_id: 7,
        local_date: localDate,
        timezone_at_entry: 'Europe/Moscow',
        source: 'manual',
        ...payload,
        created_at: `${localDate}T08:00:00`,
        updated_at: `${localDate}T09:00:00`,
      };
      state = 'filled';
      return route.fulfill({ json: record });
    }

    if (request.method() === 'DELETE') {
      record = null;
      state = 'empty';
      return route.fulfill({ status: 204, body: '' });
    }

    return route.fulfill({ status: 405, json: { detail: 'Method not allowed' } });
  });

  return {
    setState(next: DailyState) {
      state = next;
      record = next === 'error' ? null : recordFor(todayInMoscow(), next);
    },
  };
}

async function installReportApi(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, async (route) => {
    await route.fulfill({ json: makeProgressReportFixture('full') });
  });
}

function wellbeingUrl(localDate: string): string {
  return `/app?section=today&wellbeing=1&wellbeing_date=${localDate}`;
}

test('daily wellbeing covers empty, partial, filled, offline and error states on mock TMA', async ({
  tmaPage,
  tma,
}) => {
  const localDate = todayInMoscow();
  await installPlatformApi(tmaPage, { browserSession: true });
  const dailyApi = await installDailyWellbeingApi(tmaPage, 'empty');
  await tmaPage.setViewportSize({ width: 390, height: 844 });

  await tmaPage.goto(wellbeingUrl(localDate));
  await expect(tmaPage.getByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
  const wellbeingDisclosure = tmaPage.locator('details.daily-wellbeing-card > summary');
  const bottomNav = tmaPage.locator('#appBottomNav');
  await expect(wellbeingDisclosure).toHaveAttribute('aria-expanded', 'true');
  await expect(bottomNav).toBeHidden();
  await expect(wellbeingDisclosure).toBeFocused();
  await expect(tmaPage.locator('form.daily-wellbeing__form')).not.toBeFocused();
  await expect(tmaPage.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
  await expect(tmaPage.getByText(/заполнение остаётся необязательным/)).toBeVisible();
  const quickExit = tmaPage.getByRole('button', { name: 'Вернуться' });
  await expect(quickExit).toBeVisible();
  const firstSleepOption = tmaPage.getByRole('radio', { name: 'Очень плохо' });
  await firstSleepOption.focus();
  await expect(firstSleepOption).toBeFocused();
  await firstSleepOption.check();
  await quickExit.click();
  const discardDialog = tmaPage.getByRole('dialog', { name: 'Выйти без сохранения?' });
  await expect(discardDialog).toBeVisible();
  await discardDialog.getByRole('button', { name: 'Отмена' }).click();
  await expect(firstSleepOption).toBeChecked();
  await quickExit.click();
  await discardDialog.getByRole('button', { name: 'Выйти' }).click();
  await expect(tmaPage).toHaveURL(/\/app\?section=today$/);
  await expect(tmaPage.locator('form.daily-wellbeing__form')).toHaveCount(0);
  await expect(tmaPage.locator('[data-testid="quick-add-trigger"]')).toBeFocused();
  await tmaPage.goto(wellbeingUrl(localDate));
  await expect(tmaPage.getByRole('button', { name: 'Вернуться' })).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await expectTouchTargets(
    tmaPage.locator('.daily-wellbeing__option, .daily-wellbeing__actions .ui-button'),
  );
  await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-light-empty-390x844.png',
    fullPage: true,
  });

  await wellbeingDisclosure.focus();
  await expect(wellbeingDisclosure).toBeFocused();
  await wellbeingDisclosure.press('Enter');
  await expect(wellbeingDisclosure).toHaveAttribute('aria-expanded', 'false');
  await expect(bottomNav).toBeVisible();
  await expect(tmaPage.getByRole('button', { name: 'Сохранить отметку' })).not.toBeVisible();
  await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-light-collapsed-390x844.png',
    fullPage: true,
  });
  await wellbeingDisclosure.press('Enter');
  await expect(wellbeingDisclosure).toHaveAttribute('aria-expanded', 'true');
  await expect(bottomNav).toBeHidden();

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 430, height: 932 },
  ]) {
    await tmaPage.setViewportSize(viewport);
    await expectNoHorizontalOverflow(tmaPage);
    await expectTouchTargets(tmaPage.locator('.daily-wellbeing__option'));
  }
  await tmaPage.setViewportSize({ width: 390, height: 844 });

  dailyApi.setState('partial');
  await tmaPage.goto(wellbeingUrl(localDate));
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(tmaPage.getByRole('radio', { name: 'Хорошо' }).first()).toBeChecked();
  await expect(bottomNav).toBeHidden();
  await expect(tmaPage.getByText('Выберите хотя бы один показатель')).not.toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-dark-partial-390x844.png',
    fullPage: true,
  });

  await wellbeingDisclosure.focus();
  await wellbeingDisclosure.press('Enter');
  await expect(wellbeingDisclosure).toHaveAttribute('aria-expanded', 'false');
  await expect(bottomNav).toBeVisible();
  await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-dark-collapsed-390x844.png',
    fullPage: true,
  });
  await wellbeingDisclosure.press('Enter');
  await expect(wellbeingDisclosure).toHaveAttribute('aria-expanded', 'true');
  await expect(bottomNav).toBeHidden();

  await tmaPage.getByRole('radio', { name: 'Отлично' }).last().click();
  await tmaPage.getByRole('spinbutton').fill('420');
  await tmaPage.locator('.daily-wellbeing__note summary').click();
  await tmaPage.getByLabel('Заметка для себя').fill('Личная заметка остаётся только в экспорте.');
  await tmaPage.getByRole('button', { name: 'Сохранить отметку' }).click();
  await expect(tmaPage.getByRole('button', { name: 'Изменить' })).toBeVisible();
  await expect(tmaPage.getByText('Заметка сохранена отдельно')).toBeVisible();
  await expect(bottomNav).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-dark-filled-390x844.png',
    fullPage: true,
  });

  await tmaPage.getByRole('button', { name: 'Изменить' }).click();
  await setNetworkOffline(tmaPage, true);
  await expect(tmaPage.getByText(/Поля остаются на экране/)).toBeVisible();
  await expect(tmaPage.getByRole('button', { name: 'Сохранить отметку' })).toBeDisabled();
  await setNetworkOffline(tmaPage, false);

  dailyApi.setState('error');
  await tma.setTheme('light');
  await tmaPage.goto(wellbeingUrl(shiftDate(localDate, -1)));
  await expect(tmaPage.getByText('Не удалось загрузить данные', { exact: true })).toBeVisible();
  await expect(tmaPage.getByRole('button', { name: 'Повторить' })).toBeVisible();
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-light-error-390x844.png',
    fullPage: true,
  });
});

test('progress report shows daily coverage and keeps light/dark desktop layouts stable', async ({
  page,
}) => {
  await installPlatformApi(page, { browserSession: true });
  await installReportApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto('/app/report?period=days_30');
  await expect(page.getByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
  await expect(page.getByText('6 из 30 дней')).toBeVisible();
  await expect(page.getByText('В конце периода выше')).toBeVisible();
  await expect(
    page.getByText(/заметки не включены в агрегаты, PDF и доступ тренера/),
  ).toBeVisible();
  await page.getByText('Дни с фактическими отметками').click();
  await expect(page.getByRole('table', { name: 'Записанные дни сна и настроения' })).toHaveCount(1);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-82/desktop-light-report-1440x900.png',
    fullPage: true,
  });

  await page.evaluate(() => localStorage.setItem('app-theme', 'dark'));
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(page.getByRole('heading', { name: 'Сон и настроение' })).toBeVisible();
  await page.getByText('Дни с фактическими отметками').click();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({
    path: '../.artifacts/screenshots/task-82/desktop-dark-report-1440x900.png',
    fullPage: true,
  });
});
