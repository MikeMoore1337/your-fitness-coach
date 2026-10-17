import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

const widths = [320, 360, 393, 430] as const;
const themes = ['dark', 'light'] as const;
const phase = process.env.YFC_REVIEW_PHASE === 'before' ? 'before' : 'after';

for (const theme of themes) {
  for (const width of widths) {
    test(`#869 nutrition keeps hydration and secondary planner accessible - ${theme} ${width}`, async ({
      page,
    }, testInfo) => {
      await page.clock.setFixedTime(new Date('2026-10-10T12:00:00+03:00'));
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-10' });
      await page.goto('/app?section=nutrition&date=2026-10-10');

      const hydration = page.getByRole('region', { name: 'Гидратация' });
      const presets = hydration.locator('.hydration-presets button');
      await expect(presets).toHaveCount(3);
      await expect(presets.nth(1)).toContainText('350 мл');
      await expect(page.getByText('План питания', { exact: true })).toBeVisible();
      await expect(page.getByText('Список покупок', { exact: true })).toBeVisible();
      const planningDetails = page.locator(
        '.nutrition-experience > .meal-planner, .nutrition-experience > .grocery-list',
      );
      await expect(planningDetails).toHaveCount(2);
      if (phase === 'after') {
        const cardStyles = await planningDetails.evaluateAll((elements) =>
          elements.map((element) => {
            const styles = getComputedStyle(element);
            return {
              backgroundColor: styles.backgroundColor,
              borderWidths: [
                styles.borderTopWidth,
                styles.borderRightWidth,
                styles.borderBottomWidth,
                styles.borderLeftWidth,
              ],
              borderRadius: styles.borderTopLeftRadius,
            };
          }),
        );
        for (const style of cardStyles) {
          expect(style.backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
          expect(style.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
          expect(style.borderRadius).not.toBe('0px');
        }
      }
      for (const detail of await planningDetails.all()) {
        const summary = detail.locator(':scope > summary');
        const disclosure = summary.locator('svg[data-icon="disclosure-closed"]');
        await expect(disclosure).toHaveCount(1);
        await expect(disclosure).toBeVisible();
        const closedTransform =
          phase === 'after'
            ? await disclosure.evaluate((element) => getComputedStyle(element).transform)
            : null;
        if (phase === 'after') await expect(summary).toHaveAttribute('aria-expanded', 'false');
        await summary.press('Enter');
        await expect(detail).toHaveAttribute('open', '');
        if (phase === 'after') await expect(summary).toHaveAttribute('aria-expanded', 'true');
        if (phase === 'after') {
          await expect
            .poll(() => disclosure.evaluate((element) => getComputedStyle(element).transform))
            .not.toBe(closedTransform);
        }
        await summary.press('Space');
        await expect(detail).not.toHaveAttribute('open', '');
        if (phase === 'after') await expect(summary).toHaveAttribute('aria-expanded', 'false');
      }
      await hydration.scrollIntoViewIfNeeded();
      await hydration.screenshot({
        path: testInfo.outputPath(`${phase}-869-hydration-${theme}-${width}.png`),
      });
      const planning = page.locator(
        '.nutrition-experience > .meal-planner, .nutrition-experience > .grocery-list',
      );
      await expect(planning).toHaveCount(2);
      await planning.first().scrollIntoViewIfNeeded();
      await page.screenshot({
        path: testInfo.outputPath(`${phase}-869-planning-${theme}-${width}.png`),
      });

      const dimensions = await presets.evaluateAll((buttons) =>
        buttons.map((button) => {
          const text = button.querySelector('span');
          const volume = button.querySelector('strong');
          const parent = button.getBoundingClientRect();
          return {
            height: parent.height,
            labelFits: text ? text.scrollWidth <= text.clientWidth + 1 : false,
            volumeFits: volume ? volume.scrollWidth <= volume.clientWidth + 1 : false,
          };
        }),
      );
      expect(dimensions.every((it) => it.height >= 44 && it.volumeFits)).toBe(true);
      if (phase === 'after') {
        expect(
          await presets
            .first()
            .locator('strong')
            .evaluate((node) => getComputedStyle(node).whiteSpace),
        ).toBe('nowrap');
        await page.route('**/api/v1/nutrition/hydration/entries', async (route) => {
          if (route.request().method() !== 'POST') return route.fallback();
          await route.fulfill({
            status: 201,
            json: {
              id: 901,
              volume_ml: 350,
              beverage_type: 'water',
              occurred_at: '2026-10-10T09:00:00Z',
              diary_date: '2026-10-10',
              timezone: 'Europe/Moscow',
              source: 'quick_preset',
              created_at: '2026-10-10T09:00:00Z',
              updated_at: '2026-10-10T09:00:00Z',
            },
          });
        });
        let writes = 0;
        page.on('request', (request) => {
          if (request.method() === 'POST' && request.url().includes('/nutrition/hydration/entries'))
            writes += 1;
        });
        await presets.nth(1).evaluate((button) => {
          (button as HTMLButtonElement).click();
          (button as HTMLButtonElement).click();
        });
        await expect(hydration.getByText('Добавлено 350 мл')).toBeVisible();
        expect(writes).toBe(1);
      }
    });

    test(`#870 profile keeps goals, anchor navigation and preferences usable - ${theme} ${width}`, async ({
      page,
    }, testInfo) => {
      await page.clock.setFixedTime(new Date('2026-10-10T12:00:00+03:00'));
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-10' });
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({
          json: Array.from({ length: 40 }, (_, index) => ({
            id: 1000 + index,
            title: `Упражнение для проверки длинного списка ${index + 1}`,
            created_by_user_id: null,
            is_custom: false,
            equipment: 'Тренажёр',
          })),
        }),
      );
      await page.goto('/app?section=profile');
      const nav = page.getByRole('navigation', { name: 'Разделы профиля' });
      if (phase === 'before') {
        await expect(nav).toBeVisible();
        await nav.screenshot({
          path: testInfo.outputPath(`${phase}-870-nav-${theme}-${width}.png`),
        });
        const links = nav.locator('a[href^="#"]');
        expect(await links.count()).toBeGreaterThanOrEqual(5);
        for (const href of await links.evaluateAll((elements) =>
          elements.map((element) => element.getAttribute('href')),
        )) {
          expect(href).toBeTruthy();
          expect(await page.locator(href!).count()).toBe(1);
        }
      } else {
        await expect(nav).toHaveCount(0);
        for (const target of [
          '#profile-personal',
          '#profile-fitness',
          '#profile-trainer',
          '#profile-notifications',
          '#profile-security',
        ]) {
          await expect(page.locator(target)).toHaveCount(1);
        }
      }
      await page.locator('.profile-primary-card > summary').click();
      const goal = page.locator('#profile-goal');
      await expect(goal).toBeVisible();
      await goal.selectOption('recomposition');
      const hint = page.locator('#profile-goal-value');
      await expect(hint).toHaveText('Улучшить форму без фокуса на вес');
      if (phase === 'after') {
        const geometry = await hint.evaluate((node) => ({
          overflowY: getComputedStyle(node).overflowY,
          whiteSpace: getComputedStyle(node).whiteSpace,
          clipped: node.scrollHeight > node.clientHeight + 1,
        }));
        expect(geometry.clipped).toBe(false);
        expect(geometry.whiteSpace).toBe('normal');
      }
      await goal.scrollIntoViewIfNeeded();
      await page.locator('#profile-fitness').screenshot({
        path: testInfo.outputPath(`${phase}-870-goal-${theme}-${width}.png`),
      });
      await page.locator('.training-preferences-card > summary').click();
      const preferences = page.locator('.training-preferences-exercise-list');
      await page.getByText('Предпочитаемые упражнения', { exact: true }).click();
      await expect(preferences.first()).toBeVisible();
      await expect(preferences.first().locator('.training-preferences-choice')).toHaveCount(24);
      await preferences.first().screenshot({
        path: testInfo.outputPath(`${phase}-870-preferences-${theme}-${width}.png`),
      });
      const scrollRule = await preferences
        .first()
        .evaluate((element) => getComputedStyle(element).overflowY);
      if (width <= 430 && phase === 'after') expect(scrollRule).not.toBe('auto');
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      ).toBe(true);
    });
  }
}

for (const theme of themes) {
  test(`#1047 desktop keeps nutrition section cards intact - ${theme}`, async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-10T12:00:00+03:00'));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await installPlatformApi(page, { browserSession: true, fixedDate: '2026-10-10' });
    await page.goto('/app?section=nutrition&date=2026-10-10');

    const planningDetails = page.locator(
      '.nutrition-experience > .meal-planner, .nutrition-experience > .grocery-list',
    );
    await expect(planningDetails).toHaveCount(2);
    const cardStyles = await planningDetails.evaluateAll((elements) =>
      elements.map((element) => {
        const styles = getComputedStyle(element);
        return {
          borderWidths: [
            styles.borderTopWidth,
            styles.borderRightWidth,
            styles.borderBottomWidth,
            styles.borderLeftWidth,
          ],
          borderRadius: styles.borderTopLeftRadius,
        };
      }),
    );
    for (const style of cardStyles) {
      expect(style.borderWidths).toEqual(['1px', '1px', '1px', '1px']);
      expect(style.borderRadius).not.toBe('0px');
    }
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    ).toBe(true);
  });
}
