import { demoFixture } from './fixtures/demo-session';
import { test, expect } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';
for (const width of [360, 390, 768, 1440])
  for (const theme of ['light', 'dark'] as const) {
    test(`approved design ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.clock.setFixedTime(new Date('2026-09-09T12:00:00Z'));
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((t) => localStorage.setItem('app-theme', t), theme);
      await installPlatformApi(page, {
        browserSession: true,
        fixedDate: '2026-09-09',
        measurementHistory: 'many',
        programHistory: 'many',
      });
      for (const section of ['today', 'programs', 'nutrition', 'progress', 'profile']) {
        await page.goto('/app?section=' + section);
        await expect(page.locator('.app-shell')).toBeVisible();
        await expect(page.locator('[role="status"][aria-busy="true"]')).toHaveCount(0);
        await page.evaluate(() => document.fonts.ready);
        await expectNoHorizontalOverflow(page);
        await page.screenshot({
          path: testInfo.outputPath(`${section}-${width}-${theme}.png`),
          fullPage: true,
        });
        if (section === 'today') {
          await page.getByRole('button', { name: 'Начать тренировку', exact: true }).click();
          await expect(page.locator('.active-workout')).toBeVisible();
          await expectNoHorizontalOverflow(page);
          await page.screenshot({
            path: testInfo.outputPath(`workout-${width}-${theme}.png`),
            fullPage: true,
          });
        }
      }
    });
    test(`approved public design ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((t) => localStorage.setItem('app-theme', t), theme);
      await installPlatformApi(page, { browserSession: false });
      await page.route('**/api/v1/demo/sessions**', (route) =>
        route.fulfill({
          json: {
            ...demoFixture('self_training'),
            session_token: 'd'.repeat(64),
          },
        }),
      );
      await page.route('**/api/v1/public/config', (route) =>
        route.fulfill({
          json: {
            app_env: 'test',
            enable_dev_auth: false,
            enable_web_auth: true,
            enable_email_auth: true,
            telegram_bot_username: 'fit_test_bot',
            oauth_providers: [],
          },
        }),
      );
      for (const [name, path] of [
        ['landing', '/'],
        ['login', '/login'],
      ] as const) {
        await page.goto(path);
        await expect(page.locator('h1')).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        for (const photo of await page.locator('img[loading="lazy"]').all()) {
          await photo.scrollIntoViewIfNeeded();
          await expect
            .poll(() => photo.evaluate((node: HTMLImageElement) => node.naturalWidth))
            .toBeGreaterThan(0);
        }
        await page.locator('h1').scrollIntoViewIfNeeded();
        await expectNoHorizontalOverflow(page);
        if (name === 'landing') {
          const header = await page.locator('.public-shell__header').boundingBox();
          expect(header?.x).toBe(0);
          expect(header?.width).toBe(width);
          await expect(page.locator('.landing-hero__actions .landing-button').first()).toHaveCSS(
            'border-radius',
            '14px',
          );
          await expect(page.locator('.landing-practice__entry > img')).toHaveAttribute(
            'src',
            '/assets/marketing/practice-recording.webp',
          );
          await expect(page.locator('.landing-practice__entry > img')).toHaveCSS(
            'border-radius',
            '24px',
          );
          for (const step of await page.locator('.landing-start__steps li').all()) {
            const alignment = await step.evaluate((node) =>
              ['span', 'small', 'h3'].map((selector) => {
                const box = node.querySelector(selector)!.getBoundingClientRect();
                return box.y + box.height / 2;
              }),
            );
            expect(Math.max(...alignment) - Math.min(...alignment)).toBeLessThan(2);
          }
        }
        await page.screenshot({
          path: testInfo.outputPath(`${name}-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    });
  }
