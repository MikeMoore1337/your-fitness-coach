import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { attachUiAuditReport, collectUiAudit, type UiAuditIssue } from './fixtures/ui-audit';

test.use({ serviceWorkers: 'block' });

const FAST_VIEWPORTS = [
  { name: 'phone-360', width: 360, height: 800 },
  { name: 'phone-390', width: 390, height: 844 },
  { name: 'desktop-1440', width: 1440, height: 900 },
] as const;

type AuditRecord = {
  route: string;
  state: string;
  theme: 'light' | 'dark';
  viewport: { name: string; width: number; height: number };
  scroll: 'top' | 'bottom';
  issues: UiAuditIssue[];
};

async function settlePage(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    const visibleImages = [...document.images].filter((image) => {
      if (image.complete || image.loading !== 'lazy') return true;
      const rect = image.getBoundingClientRect();
      return rect.bottom >= -window.innerHeight && rect.top <= window.innerHeight * 2;
    });
    await Promise.all(
      visibleImages
        .filter((image) => !image.complete)
        .map(
          (image) =>
            new Promise<void>((resolve) => {
              const timeoutId = window.setTimeout(resolve, 3_000);
              const finish = () => {
                window.clearTimeout(timeoutId);
                resolve();
              };
              image.addEventListener('load', finish, { once: true });
              image.addEventListener('error', finish, { once: true });
            }),
        ),
    );
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
}

async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
}

async function auditPosition(
  page: Page,
  testInfo: TestInfo,
  records: AuditRecord[],
  context: Omit<AuditRecord, 'scroll' | 'issues'>,
  scroll: 'top' | 'bottom',
): Promise<void> {
  if (scroll === 'top') {
    await page.evaluate(() => window.scrollTo(0, 0));
  } else {
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.evaluate(
      () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
    );
  }
  const report = await collectUiAudit(page, {
    checkTouchTargets: context.viewport.width <= 900,
  });
  records.push({ ...context, scroll, issues: report.issues });
  if (report.issues.length > 0) {
    await attachUiAuditReport(
      testInfo,
      `${context.route.replaceAll(/[^a-z0-9]+/gi, '-')}-${scroll}`,
      report,
    );
  }
}

async function auditPage(
  page: Page,
  testInfo: TestInfo,
  records: AuditRecord[],
  context: Omit<AuditRecord, 'scroll' | 'issues'>,
): Promise<void> {
  await auditPosition(page, testInfo, records, context, 'top');
  await auditPosition(page, testInfo, records, context, 'bottom');
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function expectNoAuditIssues(records: AuditRecord[]): Promise<void> {
  const issues = records.flatMap((record) =>
    record.issues.map(({ ...issue }) => ({
      route: record.route,
      state: record.state,
      theme: record.theme,
      viewport: record.viewport,
      scroll: record.scroll,
      ...issue,
    })),
  );
  expect(issues, JSON.stringify(issues, null, 2)).toEqual([]);
}

async function expectAppReady(page: Page): Promise<void> {
  await expect(page.locator('.app-shell')).toBeVisible();
  await expect(page.locator('main').first()).toBeVisible();
  await settlePage(page);
}

test('@ui-audit-pr fast high-signal gate covers public, app and shared shell geometry', async ({
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const records: AuditRecord[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: '2026-09-16',
    measurementHistory: 'many',
  });

  for (const theme of ['light', 'dark'] as const) {
    await setTheme(page, theme);
    for (const viewport of FAST_VIEWPORTS) {
      await page.setViewportSize(viewport);

      await page.goto('/');
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await settlePage(page);
      await auditPage(page, testInfo, records, {
        route: '/',
        state: 'landing-ready',
        theme,
        viewport,
      });

      await page.goto('/app?section=today');
      await expectAppReady(page);
      await auditPage(page, testInfo, records, {
        route: '/app?section=today',
        state: 'today-planned',
        theme,
        viewport,
      });

      await page.goto('/app?section=profile');
      await expectAppReady(page);
      await auditPage(page, testInfo, records, {
        route: '/app?section=profile',
        state: 'profile-settings',
        theme,
        viewport,
      });
    }
  }

  await testInfo.attach('ui-quality-gate-summary.json', {
    body: JSON.stringify({ records, pageErrors }, null, 2),
    contentType: 'application/json',
  });
  expect(pageErrors).toEqual([]);
  await expectNoAuditIssues(records);
});

test('@ui-audit-pr shared sheets and drawers keep overlay geometry and focus clean', async ({
  page,
}, testInfo) => {
  test.setTimeout(180_000);
  const records: AuditRecord[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: '2026-09-16',
    measurementHistory: 'many',
  });

  for (const theme of ['light', 'dark'] as const) {
    await setTheme(page, theme);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/app?section=today');
    await expectAppReady(page);

    await page.getByRole('button', { name: 'Быстро добавить' }).click();
    await expect(page.getByRole('dialog', { name: 'Что добавить?' })).toBeVisible();
    await settlePage(page);
    await auditPage(page, testInfo, records, {
      route: '/app?section=today',
      state: 'quick-add-sheet',
      theme,
      viewport: { name: 'phone-390', width: 390, height: 844 },
    });
    await page.screenshot({
      path: testInfo.outputPath(`quick-add-sheet-phone-390-${theme}.png`),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Закрыть быстрые действия' }).click();

    const moreTrigger = page.getByRole('button', { name: 'Открыть профиль и настройки' });
    await moreTrigger.focus();
    await moreTrigger.press('Enter');
    await expect(page.locator('#appMorePanel')).toBeVisible();
    await settlePage(page);
    await auditPage(page, testInfo, records, {
      route: '/app?section=today',
      state: 'more-drawer',
      theme,
      viewport: { name: 'phone-390', width: 390, height: 844 },
    });
    await expect(page.getByRole('button', { name: 'Закрыть меню' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(moreTrigger).toBeFocused();
  }

  await testInfo.attach('ui-quality-gate-overlays.json', {
    body: JSON.stringify({ records, pageErrors }, null, 2),
    contentType: 'application/json',
  });
  expect(pageErrors).toEqual([]);
  await expectNoAuditIssues(records);
});

test('@ui-audit-pr workout active and completion states keep critical controls clean', async ({
  browser,
}, testInfo) => {
  test.setTimeout(180_000);
  const records: AuditRecord[] = [];
  const pageErrors: string[] = [];
  const stateViewports = [
    { name: 'phone-390', width: 390, height: 844 },
    { name: 'desktop-1440', width: 1440, height: 900 },
  ] as const;

  for (const theme of ['light', 'dark'] as const) {
    for (const state of ['active-workout', 'workout-completion'] as const) {
      for (const viewport of stateViewports) {
        const context = await browser.newContext({
          colorScheme: theme,
          locale: 'ru-RU',
          timezoneId: 'Europe/Moscow',
          viewport,
        });
        const page = await context.newPage();
        page.on('pageerror', (error) => pageErrors.push(`${state}/${theme}: ${error.message}`));
        await setTheme(page, theme);
        await installPlatformApi(page, {
          browserSession: true,
          fixedDate: '2026-09-16',
          measurementHistory: 'many',
          workoutStatus: state === 'active-workout' ? 'in_progress' : 'planned',
        });
        await page.goto('/app?section=today');
        await expectAppReady(page);

        if (state === 'active-workout') {
          await page.getByRole('button', { name: 'Продолжить тренировку' }).click();
          await expect(page.locator('.active-workout')).toBeVisible();
        } else {
          await page.getByRole('button', { name: 'Начать тренировку' }).click();
          await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
          await page.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
          await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
          await expect(page.getByText('Синхронизировано')).toBeVisible();
          await page.getByRole('button', { name: 'Завершить тренировку' }).click();
          await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
        }

        await settlePage(page);
        await auditPage(page, testInfo, records, {
          route: '/app?section=today',
          state,
          theme,
          viewport,
        });
        await page.screenshot({
          path: testInfo.outputPath(`${state}-${viewport.name}-${theme}.png`),
          fullPage: true,
        });
        await context.close();
      }
    }
  }

  await testInfo.attach('ui-quality-gate-workout-states.json', {
    body: JSON.stringify({ records, pageErrors }, null, 2),
    contentType: 'application/json',
  });
  expect(pageErrors).toEqual([]);
  await expectNoAuditIssues(records);
});
