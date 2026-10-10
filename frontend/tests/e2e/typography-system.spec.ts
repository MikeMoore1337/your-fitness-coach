import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { makeProgressReportFixture } from '../fixtures/progress-report';

test.use({ serviceWorkers: 'block' });

for (const width of [360, 393])
  for (const theme of ['dark', 'light'] as const) {
    test(`shared typography ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, {
        browserSession: true,
        trainerActive: true,
        fixedDate: '2026-10-09',
        programHistory: 'many',
        progressState: 'populated',
        measurementHistory: 'many',
      });
      await page.route(/\/api\/v1\/workouts\/progress\/report(?:\?|$)/, (route) =>
        route.fulfill({ json: makeProgressReportFixture('full') }),
      );
      const routes = [
        '/app?section=today',
        '/app?section=programs',
        '/app?section=programs&view=manage',
        '/app?section=nutrition',
        '/app?section=progress',
        ...['body', 'training', 'nutrition', 'cardio', 'wellbeing', 'history'].map(
          (view) => `/app?section=progress&progress_view=${view}`,
        ),
        '/app?section=profile',
        '/app?section=catalog',
        '/app/report',
        '/coach',
        '/coach?tab=clients',
        '/coach?tab=programs',
        '/coach?tab=tools',
      ];
      for (const route of routes) {
        await page.goto(route);
        const surface = page.locator(
          route === '/app/report' ? '.progress-report-page' : '#appContent',
        );
        await expect(surface.locator('h1').first()).toBeVisible();
        await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        const mismatches = await surface.evaluate((element) => {
          const family = (node: Element) =>
            getComputedStyle(node).fontFamily.replace(/,.*/, '').replaceAll(/["']/g, '');
          return [
            ...element.querySelectorAll('h1,h2,h3,p,label,input,select,textarea,td,dd,strong'),
          ]
            .filter((node) => node.getBoundingClientRect().height > 0)
            .filter((node) => !node.closest('h1,h2,h3') || /^H[123]$/.test(node.tagName))
            .filter((node) => family(node) !== (/^H[123]$/.test(node.tagName) ? 'Oswald' : 'Inter'))
            .map((node) => ({
              tag: node.tagName,
              text: node.textContent?.slice(0, 80),
              family: family(node),
            }));
        });
        expect(mismatches, route).toEqual([]);
        await expect(surface.locator('h1').first()).toHaveCSS('font-weight', '700');
      }
      const fonts = await page.evaluate(async () => {
        const results = [];
        for (const family of ['Inter', 'Oswald'])
          for (const weight of family === 'Inter'
            ? [400, 500, 600, 700, 800]
            : [400, 500, 600, 700]) {
            const faces = await document.fonts.load(
              `${weight} 16px ${family}`,
              'Прогресс Ёё ABC 123 №',
            );
            results.push({
              family,
              weight,
              faces: faces.length,
              loaded: faces.every((face) => face.status === 'loaded'),
            });
          }
        return results;
      });
      for (const font of fonts) {
        expect(font.faces, JSON.stringify(font)).toBe(2);
        expect(font.loaded, JSON.stringify(font)).toBe(true);
      }
      await page.goto('/app?section=programs&view=manage&start=templates');
      await expect(page.locator('.program-current-block h4')).toBeVisible();
      await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
      const editor = page.getByRole('dialog');
      await expect(editor.getByRole('heading').first()).toHaveCSS('font-family', /^Oswald,/);
      await editor.getByRole('button', { name: 'Добавить упражнение', exact: true }).click();
      await editor.getByRole('button', { name: 'Поиск упражнения', exact: true }).click();
      const picker = page.getByRole('dialog', { name: 'Выбор упражнения', exact: true });
      await expect(picker.getByRole('heading').first()).toHaveCSS('font-family', /^Oswald,/);
      await expect(picker.getByRole('searchbox')).toHaveCSS('font-family', /^Inter,/);
    });
  }
