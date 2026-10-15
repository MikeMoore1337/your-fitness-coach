import { writeFile } from 'node:fs/promises';
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
  let lastPayload: DailyPayload | null = null;

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
      lastPayload = payload;
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
    getLastPayload() {
      return lastPayload;
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
  const firstSleepOption = tmaPage.getByRole('radio', { name: 'Очень плохо' });
  await firstSleepOption.focus();
  await expect(firstSleepOption).toBeFocused();
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
  await tma.setTheme('light');
  await tmaPage.goto(wellbeingUrl(localDate));
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'light');
  await expect(tmaPage.getByRole('radio', { name: 'Хорошо' }).first()).toBeChecked();
  await expect(
    tmaPage
      .locator('.daily-wellbeing__option')
      .filter({ has: tmaPage.locator('input:checked') })
      .first(),
  ).toHaveCSS('border-bottom-color', 'rgb(178, 245, 32)');
  await expectNoHorizontalOverflow(tmaPage);
  await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-light-partial-390x844.png',
    fullPage: true,
  });

  await tmaPage.goto(wellbeingUrl(localDate));
  await tma.setTheme('dark');
  await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(tmaPage.getByRole('radio', { name: 'Хорошо' }).first()).toBeChecked();
  await expect(bottomNav).toBeHidden();
  await expect(tmaPage.getByText('Выберите хотя бы один показатель')).not.toBeVisible();
  await expect(
    tmaPage
      .locator('.daily-wellbeing__option')
      .filter({ has: tmaPage.locator('input:checked') })
      .first(),
  ).toHaveCSS('border-bottom-color', 'rgb(178, 245, 32)');
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
  await tmaPage.getByLabel('Сколько спали, часов').fill('7,5');
  await tmaPage.locator('.daily-wellbeing__note summary').click();
  await tmaPage.getByLabel('Заметка для себя').fill('Личная заметка остаётся только в экспорте.');
  const actionRows = await tmaPage
    .locator('.daily-wellbeing__actions .ui-button')
    .evaluateAll((buttons) =>
      buttons.map((button) => Math.round(button.getBoundingClientRect().top)),
    );
  expect(new Set(actionRows).size).toBe(1);
  await tmaPage.screenshot({
    path: '../.artifacts/screenshots/task-82/mobile-dark-hours-form-390x844.png',
    fullPage: true,
  });
  await tmaPage.getByRole('button', { name: 'Сохранить отметку' }).click();
  await expect(tmaPage.getByRole('button', { name: 'Изменить' })).toBeVisible();
  expect(dailyApi.getLastPayload()).toMatchObject({ sleep_duration_minutes: 450 });
  await expect(tmaPage.getByText(/7,5 ч/)).toBeVisible();
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

test('final visual evidence keeps wellbeing actions on one row in both themes', async ({
  tmaPage,
  tma,
}, testInfo) => {
  const localDate = todayInMoscow();
  await installPlatformApi(tmaPage, { browserSession: true, fixedDate: localDate });
  const dailyApi = await installDailyWellbeingApi(tmaPage, 'partial');
  const measurements: Array<Record<string, unknown>> = [];
  await tmaPage.goto(wellbeingUrl(localDate));

  for (const theme of ['dark', 'light'] as const) {
    for (const width of [320, 360, 390, 430]) {
      await tmaPage.setViewportSize({ width, height: 844 });
      dailyApi.setState('partial');
      await tmaPage.goto(wellbeingUrl(localDate));
      await tma.setTheme(theme);
      await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', theme);

      const actions = tmaPage.locator('.daily-wellbeing__actions .ui-button');
      await expect(actions).toHaveCount(2);
      await expect(actions.first()).toHaveText('Сохранить отметку');
      await expect(actions.last()).toHaveText('Удалить');
      const styles = await actions.evaluateAll((elements) =>
        elements.map((element) => {
          const style = getComputedStyle(element);
          const bounds = element.getBoundingClientRect();
          return {
            backgroundColor: style.backgroundColor,
            borderColor: style.borderTopColor,
            color: style.color,
            bounds: {
              bottom: Math.round(bounds.bottom * 100) / 100,
              height: Math.round(bounds.height * 100) / 100,
              left: Math.round(bounds.left * 100) / 100,
              right: Math.round(bounds.right * 100) / 100,
              top: Math.round(bounds.top * 100) / 100,
            },
          };
        }),
      );
      expect(styles[0]!.backgroundColor).not.toBe(styles[1]!.backgroundColor);
      expect(styles[1]!.color).toBe('rgb(255, 255, 255)');
      expect(Math.abs(styles[0]!.bounds.top - styles[1]!.bounds.top)).toBeLessThanOrEqual(1);
      expect(styles[0]!.bounds.right).toBeLessThanOrEqual(styles[1]!.bounds.left + 1);
      expect(styles.every(({ bounds }) => bounds.left >= 0)).toBe(true);
      expect(styles.every(({ bounds }) => bounds.right <= width + 1)).toBe(true);

      const radioStyles = await tmaPage
        .locator('.daily-wellbeing__option input')
        .evaluateAll((elements) =>
          elements.map((element) => {
            const style = getComputedStyle(element);
            return {
              accentColor: style.accentColor,
              appearance: style.appearance,
              colorScheme: style.colorScheme,
              checked: (element as HTMLInputElement).checked,
            };
          }),
        );
      const checkedRadio = radioStyles.find((radio) => radio.checked);
      const uncheckedRadios = radioStyles.filter((radio) => !radio.checked);
      expect(checkedRadio).toBeTruthy();
      expect(uncheckedRadios.length).toBeGreaterThan(0);
      expect(radioStyles.every((radio) => radio.colorScheme === theme)).toBe(true);
      expect(['auto', 'radio']).toContain(checkedRadio!.appearance);
      expect(uncheckedRadios.every((radio) => ['auto', 'radio'].includes(radio.appearance))).toBe(
        true,
      );
      expect(checkedRadio!.accentColor).toBe('rgb(178, 245, 32)');
      expect(
        uncheckedRadios.every((radio) => radio.accentColor !== checkedRadio!.accentColor),
      ).toBe(true);

      const unchecked = tmaPage.locator('.daily-wellbeing__option input:not(:checked)').first();
      await unchecked.focus();
      await expect(unchecked).toBeFocused();
      await expect(unchecked.locator('..')).toHaveCSS('outline-style', 'solid');
      await tmaPage.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
      await expectNoHorizontalOverflow(tmaPage);
      measurements.push({ theme, width, actions: styles, radioStyles });
      await tmaPage.screenshot({
        fullPage: true,
        path: testInfo.outputPath(`wellbeing-actions-${width}-${theme}.png`),
      });
    }
  }

  const boundsEvidence = JSON.stringify(measurements, null, 2);
  await writeFile(testInfo.outputPath('wellbeing-action-bounds.json'), boundsEvidence);
  await testInfo.attach('wellbeing-action-bounds.json', {
    body: boundsEvidence,
    contentType: 'application/json',
  });
});

test('final typography audit records computed roles for Progress, Today, Wellbeing and Quick Add', async ({
  tmaPage,
  tma,
}, testInfo) => {
  const localDate = todayInMoscow();
  await installPlatformApi(tmaPage, {
    browserSession: true,
    fixedDate: localDate,
    progressState: 'populated',
    measurementHistory: 'many',
    programHistory: 'many',
  });
  await installReportApi(tmaPage);
  const dailyApi = await installDailyWellbeingApi(tmaPage, 'partial');
  const measurements: Array<Record<string, unknown>> = [];
  await tmaPage.goto(wellbeingUrl(localDate));

  async function capture(
    theme: 'dark' | 'light',
    surface: string,
    token: string,
    selector: string,
  ) {
    const element = tmaPage.locator(selector).first();
    await expect(element).toBeVisible();
    const computed = await element.evaluate((node) => {
      const style = getComputedStyle(node);
      return {
        fontFamily: style.fontFamily,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
        lineHeight: style.lineHeight,
        text: node.textContent?.trim() ?? '',
      };
    });
    measurements.push({ surface, selector, theme, token, ...computed });
  }

  for (const theme of ['dark', 'light'] as const) {
    await tmaPage.setViewportSize({ width: 393, height: 844 });

    await tmaPage.goto('/app?section=progress');
    await tma.setTheme(theme);
    await expect(tmaPage.locator('html')).toHaveAttribute('data-color-scheme', theme);
    await capture(
      theme,
      'Progress / page title',
      '--font-display + mobile page scale + --line-height-tight',
      '.app-section--progress .progress-hero h1',
    );
    await capture(
      theme,
      'Progress / section selector',
      '--font-body + --font-size-body + --font-weight-medium',
      '.app-section--progress .progress-category-nav .ui-tab',
    );

    await tmaPage.goto('/app?section=today');
    await tma.setTheme(theme);
    await capture(
      theme,
      'Today / page title',
      '--font-display + existing Today hero scale',
      '.today-dashboard--design-v2 .today-dashboard__header h1',
    );
    await capture(
      theme,
      'Today / primary workout title',
      '--font-display + existing workout density scale',
      '.today-dashboard--design-v2 .today-workout-copy h2',
    );

    await tmaPage.getByRole('button', { name: 'Быстро добавить', exact: true }).click();
    await capture(
      theme,
      'Quick Add / sheet title',
      '--font-display + 1.25rem section density + --font-weight-medium + --line-height-tight',
      '.app-quick-add-panel__header h2',
    );
    await capture(
      theme,
      'Quick Add / action label',
      '--font-body + --font-size-body-lg + --font-weight-medium + --line-height-body',
      '.app-quick-add-action__copy strong',
    );
    await tmaPage.keyboard.press('Escape');

    dailyApi.setState('partial');
    await tmaPage.goto(wellbeingUrl(localDate));
    await tma.setTheme(theme);
    await capture(
      theme,
      'DailyWellbeing / field label',
      '--font-body + --font-size-body + --font-weight-medium + --line-height-tight',
      '.daily-wellbeing__form .ui-field__label',
    );
    await capture(
      theme,
      'DailyWellbeing / radio group legend',
      '--font-body + --font-weight-strong + --line-height-body',
      '.daily-wellbeing__options legend',
    );
    await capture(
      theme,
      'DailyWellbeing / primary action',
      '--font-body + --font-size-body-lg + --font-weight-strong + --line-height-body',
      '.daily-wellbeing__actions .ui-button',
    );
  }

  const typographyEvidence = JSON.stringify(measurements, null, 2);
  await writeFile(testInfo.outputPath('typography-computed.json'), typographyEvidence);
  await testInfo.attach('typography-computed.json', {
    body: typographyEvidence,
    contentType: 'application/json',
  });
});
