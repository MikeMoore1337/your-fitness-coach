import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  attachUiAuditReport,
  collectUiAudit,
  UI_AUDIT_VIEWPORTS,
  type UiAuditIssue,
} from './fixtures/ui-audit';

const FULL_ROUTES = [
  { path: '/', state: 'landing-ready' },
  { path: '/login?auth_error=invalid_state', state: 'login-error' },
  { path: '/training', state: 'public-content' },
  { path: '/nutrition', state: 'public-nutrition' },
  { path: '/progress', state: 'public-progress' },
  { path: '/for-trainers', state: 'public-for-trainers' },
  { path: '/exercises', state: 'public-exercises' },
  { path: '/knowledge', state: 'public-knowledge' },
  { path: '/articles', state: 'public-articles-empty' },
  { path: '/verify-email?token=invalid', state: 'verify-email-error' },
  { path: '/reset-password?token=invalid', state: 'reset-password-error' },
  { path: '/app?section=today', state: 'today-planned' },
  { path: '/app?section=programs', state: 'programs-summary' },
  { path: '/app?section=nutrition', state: 'nutrition-diary' },
  { path: '/app?section=progress', state: 'progress-overview' },
  { path: '/app?section=profile', state: 'profile-settings' },
  { path: '/app?section=profile#profile-ai-coach', state: 'profile-ai-coach-unavailable' },
  { path: '/app/report', state: 'progress-report' },
  { path: '/coach', state: 'coach-empty-roster' },
  { path: '/not-a-production-route', state: 'not-found' },
] as const;

type SweepRecord = {
  route: string;
  state: string;
  theme: 'light' | 'dark';
  viewport: (typeof UI_AUDIT_VIEWPORTS)[number];
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

async function auditRoute(
  page: Page,
  testInfo: TestInfo,
  records: SweepRecord[],
  route: (typeof FULL_ROUTES)[number],
  theme: 'light' | 'dark',
  viewport: (typeof UI_AUDIT_VIEWPORTS)[number],
): Promise<void> {
  await page.goto(route.path);
  await expect(page.locator('main').first()).toBeVisible();
  await settlePage(page);

  for (const scroll of ['top', 'bottom'] as const) {
    if (scroll === 'top') await page.evaluate(() => window.scrollTo(0, 0));
    else {
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.evaluate(
        () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())),
      );
    }
    const report = await collectUiAudit(page, {
      checkTouchTargets: viewport.width <= 900,
    });
    records.push({
      route: route.path,
      state: route.state,
      theme,
      viewport,
      scroll,
      issues: report.issues,
    });
    if (report.issues.length > 0) {
      await attachUiAuditReport(
        testInfo,
        `${route.state}-${viewport.name}-${theme}-${scroll}`,
        report,
      );
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0));
}

test('full UI quality sweep covers the production route/state matrix', async ({
  browser,
}, testInfo) => {
  test.setTimeout(1_200_000);
  const records: SweepRecord[] = [];
  const pageErrors: string[] = [];
  const routes = FULL_ROUTES;
  const viewports = UI_AUDIT_VIEWPORTS;

  for (const theme of ['light', 'dark'] as const) {
    for (const viewport of viewports) {
      for (const route of routes) {
        const context = await browser.newContext({
          baseURL: process.env.PW_BASE_URL ?? 'http://127.0.0.1:4173',
          colorScheme: theme,
          locale: 'ru-RU',
          serviceWorkers: 'block',
          timezoneId: 'Europe/Moscow',
          viewport: { width: viewport.width, height: viewport.height },
        });
        const page = await context.newPage();
        const contextPageErrors: string[] = [];
        page.on('pageerror', (error) => contextPageErrors.push(error.message));
        try {
          await context.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
          await installPlatformApi(page, {
            browserSession: true,
            fixedDate: '2026-09-16',
            measurementHistory: 'many',
            trainerActive: true,
          });
          await auditRoute(page, testInfo, records, route, theme, viewport);
          if (
            viewport.width === 390 &&
            (route.path === '/' || route.path === '/app?section=today')
          ) {
            await page.screenshot({
              path: testInfo.outputPath(
                `${route.state}-${viewport.width}x${viewport.height}-${theme}.png`,
              ),
              fullPage: true,
            });
          }
        } finally {
          pageErrors.push(...contextPageErrors);
          await context.close();
        }
      }
    }
  }

  await testInfo.attach('ui-quality-sweep-summary.json', {
    body: JSON.stringify({ routes, records, pageErrors }, null, 2),
    contentType: 'application/json',
  });
  expect(pageErrors).toEqual([]);
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
});
