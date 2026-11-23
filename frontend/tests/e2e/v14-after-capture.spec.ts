import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const evidenceDir = process.env.YFC_V14_AFTER_DIR;
const routes = [
  { name: 'today', url: '/app?section=today', selector: '.today-dashboard' },
  { name: 'plan', url: '/app?section=programs', heading: 'План' },
  { name: 'nutrition', url: '/app?section=nutrition', heading: 'Питание' },
  { name: 'progress', url: '/app?section=progress', heading: 'Прогресс' },
  { name: 'profile', url: '/app?section=profile', heading: 'Профиль и настройки' },
  { name: 'coach', url: '/coach', text: 'Следующий шаг по клиентам' },
];

if (evidenceDir) {
  for (const width of [320, 360, 390, 393, 430, 768, 1024, 1280, 1440]) {
    for (const theme of ['light', 'dark'] as const) {
      test(`V14 AFTER ${width}px ${theme}`, async ({ page }, info) => {
        test.setTimeout(120_000);
        await page.setViewportSize({ width, height: width >= 768 ? 900 : 852 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await installPlatformApi(page, { browserSession: true, trainerActive: true });
        const pageErrors: string[] = [];
        page.on('pageerror', (error) => pageErrors.push(error.message));
        const measurements: Array<{ route: string; clientWidth: number; scrollWidth: number }> = [];
        await mkdir(evidenceDir, { recursive: true });
        for (const route of routes) {
          await page.goto(route.url);
          if (route.selector) await expect(page.locator(route.selector)).toBeVisible();
          if (route.heading)
            await expect(
              page.getByRole('heading', { name: route.heading, exact: true }),
            ).toBeVisible();
          if (route.text) await expect(page.getByText(route.text)).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          measurements.push({
            route: route.name,
            ...(await page.evaluate(() => ({
              clientWidth: document.documentElement.clientWidth,
              scrollWidth: document.documentElement.scrollWidth,
            }))),
          });
          await page.screenshot({
            path: resolve(evidenceDir, `${info.project.name}-${theme}-${width}-${route.name}.png`),
            animations: 'disabled',
          });
        }
        await writeFile(
          resolve(evidenceDir, `${info.project.name}-${theme}-${width}.json`),
          JSON.stringify({ measurements, pageErrors }, null, 2),
        );
        expect(pageErrors).toEqual([]);
        expect(
          measurements.filter(({ clientWidth, scrollWidth }) => scrollWidth > clientWidth + 1),
        ).toEqual([]);
      });
    }
  }
}
