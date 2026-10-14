import { expect, test, type Page } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(process.cwd(), '..');
const packageDir = resolve(root, 'docs/ux/final-issues-acceptance/visual-package-20261013');
const capture = process.env.CAPTURE_UX_CLOSEOUT === '1';
const routePath = '/docs/ux/final-issues-acceptance/visual-package-20261013/prototypes';

async function servePrototypes(page: Page) {
  await page.route('**/docs/ux/**', async (route) => {
    const name = new URL(route.request().url()).pathname.split('/').pop();
    if (!['compact-hydration.html', 'completed-workout.html'].includes(name ?? '')) {
      return route.abort();
    }
    await route.fulfill({
      contentType: 'text/html',
      body: await readFile(resolve(packageDir, 'prototypes', name!)),
    });
  });
  await page.route('**/frontend/public/assets/fonts/*.woff2', async (route) => {
    const name = new URL(route.request().url()).pathname.split('/').pop()!;
    if (!/^(?:inter|oswald)-(?:cyrillic|latin)\.woff2$/.test(name)) return route.abort();
    await route.fulfill({
      contentType: 'font/woff2',
      body: await readFile(resolve(root, 'frontend/public/assets/fonts', name)),
    });
  });
}

async function checkGeometry(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  expect(
    await page.evaluate(async () => {
      const groups = await Promise.all([
        document.fonts.load('400 16px Inter', 'Питание и тренировка ABC 123'),
        document.fonts.load('700 16px Oswald', 'Питание и тренировка ABC 123'),
      ]);
      return groups.every(
        (faces) => faces.length > 0 && faces.every((face) => face.status === 'loaded'),
      );
    }),
  ).toBe(true);
  for (const heading of await page.locator('h1, h2, h3').all()) {
    await expect(heading).toHaveCSS('font-family', 'Oswald, sans-serif');
    await expect(heading).toHaveCSS('font-weight', '700');
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    (await page.viewportSize())!.width,
  );
  for (const summary of await page.locator('summary').all()) {
    await expect(summary.locator('svg[data-icon="disclosure-closed"]')).toHaveCount(1);
    await expect(summary.locator('svg')).toHaveAttribute('aria-hidden', 'true');
    expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await expect(summary).not.toHaveCSS('font-family', 'serif');
  }
}

test('design-only prototype labels remain literal DOM text', async ({ page }) => {
  await servePrototypes(page);
  const original = await readFile(resolve(packageDir, 'prototypes/compact-hydration.html'), 'utf8');
  const body = original.replace(
    /(<summary[^>]*>)\s*Личный ориентир\s*(<\/summary>)/,
    '$1&lt;span data-prototype-text&gt;Личный ориентир&lt;/span&gt;$2',
  );
  expect(body).not.toBe(original);
  await page.route('**/compact-hydration.html*', (route) =>
    route.fulfill({ contentType: 'text/html', body }),
  );
  await page.goto(`${routePath}/compact-hydration.html`);
  await expect(page.locator('summary').filter({ hasText: 'data-prototype-text' })).toHaveText(
    '<span data-prototype-text>Личный ориентир</span>',
  );
  await expect(page.locator('[data-prototype-text]')).toHaveCount(0);
});

for (const theme of ['dark', 'light'] as const) {
  for (const width of [320, 360, 390, 393, 430, 1280]) {
    test(`design-only prototypes keep icons, history and results truthful ${width}px ${theme}`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await servePrototypes(page);
      const hydrationDir = resolve(packageDir, 'visuals/869');
      const workoutDir = resolve(packageDir, 'visuals/871');
      if (capture) {
        await mkdir(hydrationDir, { recursive: true });
        await mkdir(workoutDir, { recursive: true });
      }

      for (const total of [0, 1, 2, 3, 4, 5]) {
        await page.goto(`${routePath}/compact-hydration.html?theme=${theme}&entries=${total}`);
        await expect(page.locator('summary')).toHaveCount(4);
        await checkGeometry(page);
        const rows = page.locator('#history .history-row');
        const toggle = page.getByRole('button', { name: 'Показать всю историю' });
        await expect(rows).toHaveCount(Math.min(total, 3));
        if (total <= 3) {
          await expect(toggle).toBeHidden();
          await expect(page.locator('#history-count')).toHaveText(
            `${total} ${total === 1 ? 'запись' : total === 0 ? 'записей' : 'записи'}`,
          );
        } else {
          await expect(page.locator('#history-count')).toHaveText(`Последние 3 · всего ${total}`);
          await toggle.focus();
          await page.keyboard.press('Enter');
          await expect(rows).toHaveCount(total);
          await expect(page.locator('#history-toggle')).toHaveAttribute('aria-expanded', 'true');
          await expect(page.locator('#history-toggle svg')).toHaveCSS(
            'transform',
            'matrix(0, 1, -1, 0, 0, 0)',
          );
          await page.getByRole('button', { name: 'Свернуть историю' }).press('Space');
          await expect(rows).toHaveCount(3);
          await expect(page.locator('#history-toggle')).toHaveAttribute('aria-expanded', 'false');
        }
      }

      await page.goto(`${routePath}/compact-hydration.html?theme=${theme}&entries=4`);
      await checkGeometry(page);
      const viewportName = width === 1280 ? 'desktop1280' : `mobile${width}`;
      if (capture && (width === 390 || width === 1280)) {
        await page.screenshot({
          path: resolve(
            hydrationDir,
            `hydration-${info.project.name}-${theme}-${viewportName}.png`,
          ),
          fullPage: true,
        });
      }
      for (const summary of await page.locator('summary').all()) {
        const iconBefore = await summary.locator('svg').boundingBox();
        await summary.focus();
        await summary.press('Enter');
        await expect(summary).toHaveAttribute('aria-expanded', 'true');
        await expect(summary.locator('svg')).toHaveCSS('transform', 'matrix(0, 1, -1, 0, 0, 0)');
        expect((await summary.locator('svg').boundingBox())!.width).toBeCloseTo(
          iconBefore!.width,
          0,
        );
        await summary.press('Space');
        await expect(summary).toHaveAttribute('aria-expanded', 'false');
        await expect(summary.locator('svg')).toHaveCSS('transform', 'none');
      }
      await page.getByRole('button', { name: 'Показать всю историю' }).click();
      if (capture && width === 390) {
        await page.screenshot({
          path: resolve(
            hydrationDir,
            `hydration-${info.project.name}-${theme}-${viewportName}-expanded.png`,
          ),
          fullPage: true,
        });
      }
      await page.getByRole('button', { name: 'Стакан 250 мл' }).click();
      await expect(page.locator('#history-count')).toHaveText('Вся история · всего 5');
      await expect(page.locator('#history .history-row')).toHaveCount(5);
      await expect(page.locator('#hydration-amount')).toHaveText('1 530 из 2 200 мл');
      await page.getByRole('button', { name: 'Свернуть историю' }).click();
      await expect(page.locator('#history .history-row')).toHaveCount(3);
      await page.getByText('Личный ориентир', { exact: true }).click();
      await page.getByLabel('Ориентир, мл в день').fill('3000');
      await page.getByRole('button', { name: 'Сохранить ориентир' }).click();
      await expect(page.locator('#hydration-amount')).toHaveText('1 530 из 3 000 мл');
      await page.getByLabel('Другой объём, мл').fill('400');
      await page.getByLabel('Напиток', { exact: true }).fill('Чай');
      await page.getByRole('button', { name: 'Добавить', exact: true }).click();
      await expect(page.locator('#hydration-amount')).toHaveText('1 930 из 3 000 мл');
      await page.getByText('Мои кружки и бутылки', { exact: true }).click();
      await page.getByLabel('Название', { exact: true }).fill('Моя кружка');
      await page.getByLabel('Объём, мл', { exact: true }).fill('300');
      await page.getByRole('button', { name: 'Добавить ёмкость' }).click();
      await page.getByRole('button', { name: 'Моя кружка 300 мл' }).click();
      await expect(page.locator('#hydration-amount')).toHaveText('2 230 из 3 000 мл');
      await expect(page.locator('#history-count')).toHaveText('Последние 3 · всего 7');
      await checkGeometry(page);

      await page.goto(`${routePath}/completed-workout.html?theme=${theme}`);
      await expect(page.locator('summary')).toHaveCount(1);
      await checkGeometry(page);
      await expect(page.getByText('Демонстрационная выборка.', { exact: false })).toBeVisible();
      await expect(
        page.getByText('3 из 5 упражнений · 8 из 14 подходов', { exact: false }),
      ).toBeVisible();
      const summary = page.locator('.results summary');
      await expect(summary).toHaveText('Скрыть упражнения и подходы');
      await expect(summary).toHaveAttribute('aria-expanded', 'true');
      await expect(summary.locator('svg')).toHaveCSS('transform', 'matrix(0, 1, -1, 0, 0, 0)');
      await expect(page.locator('.ai button')).toHaveCount(0);
      if (capture && (width === 390 || width === 1280)) {
        await page.screenshot({
          path: resolve(workoutDir, `workout-${info.project.name}-${theme}-${viewportName}.png`),
          fullPage: true,
        });
      }
      await summary.focus();
      await page.keyboard.press('Space');
      await expect(summary).toHaveText('Показать упражнения и подходы');
      await expect(summary).toHaveAttribute('aria-expanded', 'false');
      await expect(page.locator('.results .records')).toBeHidden();
      await expect(summary.locator('svg')).toHaveCSS('transform', 'none');
      if (capture && width === 390) {
        await page.screenshot({
          path: resolve(
            workoutDir,
            `workout-${info.project.name}-${theme}-${viewportName}-collapsed.png`,
          ),
          fullPage: true,
        });
      }
      await page.keyboard.press('Enter');
      await expect(summary).toHaveText('Скрыть упражнения и подходы');
      await expect(page.locator('.results .records')).toBeVisible();
      await expect(summary).toBeFocused();
    });
  }
}
