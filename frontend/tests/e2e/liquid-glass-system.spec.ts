import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import { expectNoHorizontalOverflow } from './fixtures/mobile-tma';

test.use({ serviceWorkers: 'block' });

for (const theme of ['light', 'dark'] as const) {
  for (const width of [390, 768, 1440]) {
    test(`liquid controls ${theme} ${width}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'no-preference' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await page.clock.setFixedTime(new Date('2026-09-12T09:00:00Z'));
      const api = await installPlatformApi(page, { browserSession: true, fixedDate: '2026-09-12' });
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      await page.goto('/app?section=today');
      await expect(page.locator('.today-dashboard')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      if (width < 900) {
        const header = page.locator('.app-mobile-header');
        await expect(header).not.toHaveAttribute('data-glass');
        await expect(header).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
        await expect(header).toHaveCSS('background-image', 'none');
        await expect(header).toHaveCSS('box-shadow', 'none');
        await expect(header).toHaveCSS('border-bottom-width', '0px');
        const avatar = header.locator('button');
        await expect(avatar).not.toHaveAttribute('data-glass');
        await expect(avatar).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
        await expect(avatar).toHaveCSS('border-width', '2px');
        await expect(avatar).toHaveCSS('border-color', 'rgb(178, 245, 32)');
      } else {
        await expect(page.locator('.app-mobile-header')).toHaveCount(0);
      }
      const nav = page.getByRole('navigation', { name: 'Основная навигация' });
      await expect(nav).toHaveAttribute('data-glass-variant', 'regular');
      await expect(nav).toHaveCSS('background-image', /radial-gradient.*linear-gradient/);
      await expect(nav).toHaveCSS('box-shadow', /inset/);
      await expect(nav).toHaveCSS('backdrop-filter', width < 900 ? /blur\(6px\)/ : 'none');
      await expectNoHorizontalOverflow(page);
      // Content containers remain ordinary surfaces; navigation alone carries this material.
      await expect(
        page.locator('.today-dashboard[data-glass], .today-panel[data-glass], input[data-glass]'),
      ).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath(`today-${width}-${theme}.png`) });

      const add = page.getByRole('button', { name: 'Быстро добавить', exact: true });
      await add.hover();
      await expect
        .poll(() => add.evaluate((element) => element.style.getPropertyValue('--glass-x')))
        .not.toBe('');
      await add.focus();
      await page.keyboard.press('Enter');
      const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
      await expect(sheet).toBeVisible();
      await expect(sheet).toHaveAttribute('data-glass-variant', 'tinted');
      await page.screenshot({ path: testInfo.outputPath(`quick-add-${width}-${theme}.png`) });
      await page.keyboard.press('Escape');
      await expect(sheet).toBeHidden();
      await expect(add).toBeFocused();

      await page.getByRole('button', { name: 'Начать тренировку', exact: true }).click();
      await page.getByRole('spinbutton', { name: /^Вес,/ }).first().fill('18');
      await page
        .getByRole('spinbutton', { name: /^Повторы,/ })
        .first()
        .fill('10');
      await expect
        .poll(() => api.workoutValues())
        .toMatchObject({ actualWeight: 18, actualReps: 10 });
      await page.getByRole('button', { name: /^Завершить:.*подход 1/ }).click();
      await expect.poll(() => api.workoutValues().completed).toBe(true);
      const rest = page.getByRole('timer').filter({ hasText: 'Отдых' });
      await expect(rest).toBeVisible();
      const remaining = async () => {
        const value = await rest.locator('.active-workout-rest__time strong').innerText();
        const parts = value.split(':').map(Number);
        return (parts[0] ?? 0) * 60 + (parts[1] ?? 0);
      };
      const before = await remaining();
      await rest.getByRole('button', { name: '+30 сек' }).click();
      await expect.poll(remaining).toBe(before + 30);
      await expect(rest.locator('button').first()).toHaveCSS('backdrop-filter', 'none');
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: testInfo.outputPath(`rest-${width}-${theme}.png`) });
      await rest.getByRole('button', { name: 'Пропустить', exact: true }).click();
      await expect(rest).toBeHidden();

      await page.goto('/app?section=progress');
      const tabs = page.getByRole('tablist').first();
      await expect(tabs).toBeVisible();
      const nextTab = tabs.getByRole('tab', { name: '90 дней', exact: true });
      await nextTab.click();
      await expect(nextTab).toHaveAttribute('aria-selected', 'true');
      await expect(nextTab).toHaveCSS('backdrop-filter', 'none');
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await add.hover();
      const durations = await add.evaluate((element) =>
        getComputedStyle(element).transitionDuration.split(',').map(Number.parseFloat),
      );
      expect(durations.every((duration) => duration <= 0.0001)).toBe(true);
      await expect
        .poll(() => add.evaluate((element) => element.style.getPropertyValue('--glass-x')))
        .toBe('');
      await expectNoHorizontalOverflow(page);
      if (width === 390) {
        await page.goto('/app?section=today');
        await expect(page.locator('.today-dashboard')).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        const sample = () =>
          page.evaluate(async () => {
            const times: number[] = [];
            let previous = performance.now();
            for (let index = 0; index < 70; index++) {
              const timestamp = await new Promise<number>((resolve) =>
                requestAnimationFrame(resolve),
              );
              if (index >= 10) times.push(timestamp - previous);
              previous = timestamp;
              const maximum = document.documentElement.scrollHeight - innerHeight;
              window.scrollTo(0, maximum * ((index % 20) / 20));
            }
            window.scrollTo(0, 0);
            times.sort((a, b) => a - b);
            const planes = [...document.querySelectorAll<HTMLElement>('[data-glass]')].filter(
              (element) => {
                const rect = element.getBoundingClientRect();
                return (
                  rect.width &&
                  rect.height &&
                  rect.top < innerHeight &&
                  rect.bottom > 0 &&
                  getComputedStyle(element).backdropFilter !== 'none'
                );
              },
            );
            return {
              p50: times[30],
              p95: times[57],
              framesOver32ms: times.filter((value) => value > 32).length,
              visibleBlurPlanes: planes.length,
            };
          });
        const material = await sample();
        const off = await page.addStyleTag({
          content:
            '[data-glass] { backdrop-filter: none !important; -webkit-backdrop-filter: none !important; background-image: none !important; box-shadow: none !important; }',
        });
        const withoutMaterial = await sample();
        await off.evaluate((element) => element.parentNode?.removeChild(element));
        expect(material.visibleBlurPlanes).toBeLessThanOrEqual(6);
        await testInfo.attach('material-cost.json', {
          body: JSON.stringify({
            material,
            withoutMaterial,
            note: 'Local headless scroll probe; not physical-device FPS or field INP',
          }),
          contentType: 'application/json',
        });
      }

      expect(errors).toEqual([]);
    });
  }
}
