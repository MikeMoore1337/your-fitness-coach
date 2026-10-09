import { expect, test, type Page } from '@playwright/test';
async function open(page: Page, route: string, theme: 'light' | 'dark', width: number) {
  await page.setViewportSize({ width, height: width < 700 ? 844 : 1100 });
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript((v) => localStorage.setItem('app-theme', v), theme);
  await page.goto(route, { waitUntil: 'networkidle' });
  await expect(page.locator('.ref-hero h1')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
}
for (const width of [320, 360, 390, 430, 768, 1280, 1366, 1440, 1498, 1600, 1920])
  for (const theme of ['light', 'dark'] as const)
    for (const audience of ['athlete', 'coach'] as const) {
      test(`${audience} ${theme} ${width}: geometry, labels and destinations`, async ({ page }) => {
        await open(page, audience === 'coach' ? '/for-trainers' : '/', theme, width);
        await expect(page.locator('#faq h2')).toHaveText(
          audience === 'coach' ? 'Понятные правила.' : 'Понятные границы.',
        );
        const hero = page.locator('.ref-hero');
        for (const label of ['Для себя', 'Для тренера'])
          await expect(hero.getByRole('link', { name: label, exact: true })).toBeVisible();
        await expect(hero.locator('[aria-current="page"]')).toHaveText(
          audience === 'coach' ? 'Для тренера' : 'Для себя',
        );
        await expect(
          hero.getByRole('link', {
            name: audience === 'coach' ? 'Как работает Coach OS' : 'Посмотреть пример тренировки',
          }),
        ).toHaveAttribute('href', audience === 'coach' ? '#coach-work' : '#training');
        await expect(
          hero.getByRole('link', {
            name: audience === 'coach' ? 'Начать как тренер' : 'Начать со своими данными',
          }),
        ).toHaveAttribute(
          'href',
          audience === 'coach' ? '/login?next=%2Fapp%3Ftrainer_intent%3D1' : '/app',
        );
        await expect(
          hero.getByRole('link', {
            name:
              audience === 'coach' ? 'Попробовать демо для тренера' : 'Попробовать демо тренировки',
          }),
        ).toHaveAttribute(
          'href',
          audience === 'coach'
            ? '/demo?cabinet=1&scenario=trainer&section=trainer'
            : '/demo?cabinet=1&scenario=self_training&section=today',
        );
        await expect(hero.locator('.landing-hero__actions a').first()).toHaveAttribute(
          'href',
          audience === 'coach' ? '/login?next=%2Fapp%3Ftrainer_intent%3D1' : '/app',
        );
        await expect(hero.locator('.landing-hero__actions a').nth(1)).toHaveAttribute(
          'href',
          audience === 'coach'
            ? '/demo?cabinet=1&scenario=trainer&section=trainer'
            : '/demo?cabinet=1&scenario=self_training&section=today',
        );
        await expect(page.getByRole('link', { name: 'Войти', exact: true })).toBeVisible();
        await expect(
          page.locator('.public-shell__header .landing-v10-audience-switch'),
        ).toHaveCount(0);
        await expect(page.locator('.public-shell__header')).not.toContainText('Сценарий');
        await expect(hero.locator('.landing-v10-audience-switch')).toHaveCount(1);
        const headerMaterial = await page.locator('.public-shell__header').evaluate((element) => {
          const style = getComputedStyle(element);
          const headerRect = element.getBoundingClientRect();
          const heroRect = document.querySelector('.ref-hero')?.getBoundingClientRect();
          return {
            backgroundColor: style.backgroundColor,
            backgroundImage: style.backgroundImage,
            position: style.position,
            width: headerRect.width,
            heroTop: heroRect?.top ?? null,
            backdropFilter:
              style.backdropFilter ||
              (style as CSSStyleDeclaration & { webkitBackdropFilter?: string })
                .webkitBackdropFilter ||
              '',
          };
        });
        expect(headerMaterial.backgroundColor).toMatch(/rgba?\(/);
        expect(headerMaterial.backgroundColor).not.toMatch(/rgba?\([^)]*,\s*1\s*\)/);
        expect(headerMaterial.backgroundImage).not.toBe('none');
        expect(headerMaterial.backdropFilter).toContain('blur');
        if (width >= 681) {
          expect(headerMaterial.position).toBe('sticky');
          expect(headerMaterial.width).toBeGreaterThanOrEqual(width - 1);
          expect(headerMaterial.heroTop).toBeLessThanOrEqual(1);
        }
        const tertiary = hero.locator('.landing-v10-hero-tertiary');
        await expect(tertiary).toBeVisible();
        await expect(tertiary).toHaveAttribute('data-glass');
        await expect(tertiary).toHaveAttribute('data-glass-variant', 'clear');
        const ctaOrder = await hero.evaluate((element) => {
          const actions = element.querySelector('.landing-hero__actions')!;
          const tertiary = element.querySelector('.landing-v10-hero-tertiary')!;
          const platform = element.querySelector('.landing-hero__platform')!;
          return {
            actionsBeforeTertiary: Boolean(
              actions.compareDocumentPosition(tertiary) & Node.DOCUMENT_POSITION_FOLLOWING,
            ),
            tertiaryBeforePlatform: Boolean(
              tertiary.compareDocumentPosition(platform) & Node.DOCUMENT_POSITION_FOLLOWING,
            ),
          };
        });
        expect(ctaOrder.actionsBeforeTertiary).toBe(true);
        expect(ctaOrder.tertiaryBeforePlatform).toBe(true);
        const geometry = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth - innerWidth,
          boxes: [
            ...document.querySelectorAll<HTMLElement>(
              '.ref-hero h1 span, .ref-hero .landing-button, .landing-header__actions > *, .landing-v10-hero-audience a',
            ),
          ]
            .filter((e) => e.offsetWidth)
            .map((e) => ({
              text: e.textContent,
              rect: e.getBoundingClientRect().toJSON(),
              scroll: e.scrollWidth,
              width: e.clientWidth,
            })),
          overlap:
            document.querySelector('.landing-v10-hero-audience')!.getBoundingClientRect().bottom >
            document.querySelector('h1')!.getBoundingClientRect().top,
        }));
        expect(geometry.overflow).toBe(0);
        expect(geometry.overlap).toBe(false);
        for (const box of geometry.boxes) {
          expect(box.rect.left, box.text ?? '').toBeGreaterThanOrEqual(0);
          expect(box.rect.right, box.text ?? '').toBeLessThanOrEqual(width + 1);
          expect(box.scroll).toBeLessThanOrEqual(box.width + 1);
        }
        expect(
          await hero
            .locator('h1 span')
            .last()
            .evaluate((e) => {
              const r = document.createRange();
              r.selectNodeContents(e);
              return r.getClientRects().length;
            }),
        ).toBe(1);
        for (const target of await hero
          .locator('.landing-button, .landing-v10-audience-switch__link')
          .all())
          expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
        await expect(page.locator('.strength-scene')).toHaveCount(audience === 'athlete' ? 1 : 0);
        await expect(page.locator('#coach-work')).toHaveCount(audience === 'coach' ? 1 : 0);
        await expect(page.locator('#coach-promo')).toHaveCount(audience === 'athlete' ? 1 : 0);
        await expect(page.locator('#training')).toHaveCount(audience === 'athlete' ? 1 : 0);
        await expect(page.locator('#nutrition')).toHaveCount(audience === 'athlete' ? 1 : 0);
        await expect(page.locator('#progress')).toHaveCount(audience === 'athlete' ? 1 : 0);
        const cycleHeading = page.locator('#product h2');
        await expect(cycleHeading).toHaveText(
          audience === 'coach' ? 'Сопровождение. С продолжением.' : 'Продолжение имеет значение.',
        );
        expect(
          await cycleHeading.evaluate((element) => (element as HTMLElement).innerText),
        ).not.toMatch(/Продолжениеимеет|Сопровождение\.С/);
        for (const section of await page.locator('main > section').all()) {
          await section.scrollIntoViewIfNeeded();
          if ((await section.getAttribute('id')) === 'progress') {
            await expect(section.getByRole('heading', { name: 'Объём тренировок' })).toBeVisible();
            await expect(section.locator('.data-viz-chart')).toBeVisible();
            await expect(section.getByText('Загружаем пример прогресса…')).toHaveCount(0);
            await expect(section.locator('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
          }
          expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(
            0,
          );
        }
      });
    }
test.describe('cold progress loading', () => {
  // The PWA can serve its cached chunk without hitting the test's network gate.
  test.use({ serviceWorkers: 'block' });
  for (const theme of ['light', 'dark'] as const)
    for (const width of [320, 390, 430, 1440])
      test(`progress waits for its real lazy chunk ${theme} ${width}`, async ({ page }) => {
        let release!: () => void;
        const responseGate = new Promise<void>((resolve) => {
          release = resolve;
        });
        let requested = false;
        await page.route('**/assets/LandingProgressContent-*.js', async (route) => {
          requested = true;
          await responseGate;
          await route.continue();
        });
        try {
          await open(page, '/', theme, width);
          const progress = page.locator('#progress');
          await progress.scrollIntoViewIfNeeded();
          await expect(progress.getByText('Загружаем пример прогресса…')).toBeVisible();
          await expect.poll(() => requested).toBe(true);
          await expect(progress.locator('[aria-busy]')).toHaveAttribute('aria-busy', 'true');
          await expect(progress.getByRole('heading', { name: 'Объём тренировок' })).toHaveCount(0);
          release();
          await expect(progress.getByRole('heading', { name: 'Объём тренировок' })).toBeVisible();
          await expect(progress.locator('.data-viz-chart')).toBeVisible();
          await expect(progress.getByText('Загружаем пример прогресса…')).toHaveCount(0);
          await expect(progress.locator('[aria-busy]')).toHaveAttribute('aria-busy', 'false');
          await expect(progress.getByRole('link', { name: 'Открыть прогресс' })).toHaveAttribute(
            'href',
            '/demo?cabinet=1&scenario=self_training&section=progress',
          );
        } finally {
          release();
        }
      });
});

test('mobile menu focus, theme, audience, Escape and resize', async ({ page }) => {
  await open(page, '/', 'light', 320);
  const trigger = page.getByRole('button', { name: 'Открыть меню' });
  await trigger.click();
  const nav = page.getByRole('navigation', { name: 'Навигация по странице' });
  await expect(nav.getByRole('link', { name: 'Продукт' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  const toggle = page.locator('.app-theme-toggle--nav');
  await expect(toggle).toBeFocused();
  await toggle.click();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(nav).toBeHidden();
  await trigger.click();
  await expect(nav.getByRole('link', { name: 'Для тренера', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(nav).toBeHidden();
  await page
    .locator('.landing-v10-hero-audience')
    .getByRole('link', { name: 'Для тренера', exact: true })
    .click();
  await expect(page).toHaveURL('/for-trainers');
  await expect(page.locator('.landing-v10-hero-audience [aria-current="page"]')).toHaveText(
    'Для тренера',
  );
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(nav).toBeVisible();
  await expect(page.getByRole('link', { name: 'Войти', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'К содержимому' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('main')).toBeFocused();
});
test('canonical, alias indexation, campaign and hash history', async ({ page }) => {
  await open(page, '/?utm_campaign=v10#coach-work', 'dark', 390);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new URL('/', page.url()).href,
  );
  await expect(page.locator('#product')).toBeInViewport();
  await page
    .locator('.landing-v10-hero-audience')
    .getByRole('link', { name: 'Для тренера', exact: true })
    .click();
  await expect(page).toHaveURL('/for-trainers?utm_campaign=v10#coach-work');
  await expect(page.locator('#coach-work')).toBeInViewport();
  await page.goBack();
  await expect(page).toHaveURL('/?utm_campaign=v10#coach-work');
  await expect(page.locator('#product')).toBeInViewport();
  await page.goto('/for-athletes');
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  await page.goto('/for-trainers#coach-promo');
  await expect(page.locator('#coach-work')).toBeInViewport();
});
test('all archive interactive states remain explicit and local', async ({ page }) => {
  await open(page, '/', 'dark', 1440);
  const writes: string[] = [];
  page.on('request', (r) => {
    if (r.url().includes('/api/') && r.method() !== 'GET') writes.push(r.url());
  });
  const training = page.locator('#training');
  await training.getByRole('button', { name: 'Начать тренировку' }).click();
  for (let i = 0; i < 3; i++)
    await training.getByRole('button', { name: 'Завершить текущий подход' }).click();
  await training.getByRole('button', { name: 'Завершить тренировку' }).click();
  await expect(training.getByText('24 мин')).toBeVisible();
  await training.getByRole('button', { name: 'Перейти к прогрессу' }).click();
  await expect(training.getByText('+4.2%')).toBeVisible();
  await page.getByRole('button', { name: 'Покупки', exact: true }).click();
  await expect(page.getByText('60 г', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Дневник', exact: true }).click();
  await expect(page.getByText('Записи пока нет')).toBeVisible();
  await page.getByRole('button', { name: 'Отметить съеденное в примере' }).click();
  await expect(page.getByRole('button', { name: 'Запись сохранена в примере' })).toBeDisabled();
  await page.locator('#progress').scrollIntoViewIfNeeded();
  await expect(page.locator('#progress [aria-busy="false"]')).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await page.getByRole('button', { name: 'Открыть изменения' }).click();
  await page.getByRole('button', { name: 'Посмотреть перед применением' }).click();
  await page.getByRole('button', { name: 'Подтвердить в примере', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Подтверждено в примере' })).toBeDisabled();
  await page.getByRole('button', { name: 'Сообщение', exact: true }).click();
  await page.getByRole('textbox', { name: 'Текст черновика' }).fill('Локальный пример');
  await page.getByRole('button', { name: 'Подтвердить черновик в примере' }).click();
  await expect(page.getByRole('textbox')).toHaveValue('Локальный пример');
  expect(writes).toEqual([]);
});
import { installTelegramHarness } from './fixtures/mobile-tma';
for (const theme of ['light', 'dark'] as const)
  test(`mocked TMA public surface, safe-area and resize ${theme}`, async ({ page }) => {
    await installTelegramHarness(page, {
      initData: '',
      colorScheme: theme,
      safeAreaInset: { top: 24, bottom: 34, left: 0, right: 0 },
      contentSafeAreaInset: { top: 24, bottom: 0, left: 0, right: 0 },
    });
    for (const route of ['/', '/for-trainers']) {
      await open(page, route, theme, 390);
      await expect(page.locator('.ref-hero')).toBeVisible();
      await page.getByRole('button', { name: 'Открыть меню' }).click();
      await expect(page.getByRole('navigation', { name: 'Навигация по странице' })).toBeVisible();
      await page.keyboard.press('Escape');
      await page.setViewportSize({ width: 320, height: 640 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
      await expect(page.getByRole('link', { name: 'Войти', exact: true })).toBeVisible();
    }
  });
test('archive legal placeholder is explicit and returns keyboard focus', async ({ page }) => {
  await open(page, '/', 'dark', 390);
  const button = page.getByRole('button', { name: 'Условия использования', exact: true });
  await button.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(
    page.getByText('Это предварительная версия лендинга. Юридический документ ещё не подключён.'),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(button).toBeFocused();
});
