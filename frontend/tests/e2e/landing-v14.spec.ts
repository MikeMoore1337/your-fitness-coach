import { expect, test } from '@playwright/test';

for (const width of [320, 360, 390, 393, 430, 768, 1024, 1280, 1440, 1920]) {
  for (const theme of ['light', 'dark'] as const) {
    for (const audience of ['athlete', 'coach'] as const) {
      test(`${audience} ${theme} ${width}: V14 hero and navigation`, async ({ page }) => {
        await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await page.goto(audience === 'coach' ? '/for-trainers?utm_source=v14' : '/?utm_source=v14');
        const hero = page.locator('.ref-hero');
        await expect(hero.locator('h1')).toBeVisible();
        await expect(hero.locator('[aria-current="page"]')).toHaveText(
          audience === 'coach' ? 'Для тренера' : 'Для себя',
        );
        await expect(
          hero.getByRole('link', { name: audience === 'coach' ? 'Для себя' : 'Для тренера' }),
        ).toHaveAttribute('href', /utm_source=v14/);
        await expect(hero.locator('.landing-hero__actions a').nth(1)).toHaveAttribute(
          'href',
          audience === 'coach'
            ? '/demo?cabinet=1&scenario=trainer&section=trainer'
            : '/demo?cabinet=1&scenario=self_training&section=today',
        );
        await expect(hero.locator('.landing-v10-hero-tertiary')).toHaveAttribute(
          'href',
          audience === 'coach' ? '#coach-work' : '#training',
        );
        const geometry = await hero.evaluate((element) => {
          const image = element.querySelector('.landing-hero__image')!.getBoundingClientRect();
          const copy = element.querySelector('.landing-hero__copy')!.getBoundingClientRect();
          const heading = element.querySelector('h1')!.getBoundingClientRect();
          return {
            overflow: document.documentElement.scrollWidth - innerWidth,
            imageBottom: image.bottom,
            copyTop: copy.top,
            headingRight: heading.right,
            viewport: innerWidth,
          };
        });
        expect(geometry.overflow).toBeLessThanOrEqual(1);
        expect(geometry.headingRight).toBeLessThanOrEqual(geometry.viewport + 1);
        for (const line of await hero.locator('h1 span').all()) {
          const fits = await line.evaluate(
            (element) => element.scrollWidth <= element.clientWidth + 1,
          );
          expect(fits).toBe(true);
        }
        if (width <= 680) expect(geometry.imageBottom - geometry.copyTop).toBeLessThanOrEqual(20);

        if (width <= 850) {
          const menu = page.locator('.landing-menu-toggle');
          await expect(menu).toHaveAccessibleName('Открыть меню');
          await menu.click();
          await expect(menu).toHaveAttribute('aria-expanded', 'true');
          await expect(menu).toHaveAccessibleName('Закрыть меню');
          await page.keyboard.press('Escape');
          await expect(menu).toBeFocused();
          await expect(menu).toHaveAttribute('aria-expanded', 'false');
        }
      });
    }
  }
}

test('strength stages stay operable with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 500 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.addInitScript(() => localStorage.setItem('app-theme', 'dark'));
  await page.goto('/#strength');
  const scene = page.locator('.strength-scene');
  await expect(scene).toHaveAttribute('id', 'strength');
  const result = scene.getByRole('button', { name: 'Результат' });
  await expect(result).toHaveAttribute('aria-pressed', 'true');
  const contrast = await scene.evaluate((element) => {
    const channels = (value: string) =>
      value
        .match(/\d+/g)!
        .slice(0, 3)
        .map(Number)
        .map((v) => {
          const c = v / 255;
          return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
        });
    const luminance = (value: string) => {
      const [r, g, b] = channels(value);
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const ratio = (foreground: Element, background: Element) => {
      const fg = luminance(getComputedStyle(foreground).color);
      const bg = luminance(getComputedStyle(background).backgroundColor);
      return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
    };
    return {
      note: ratio(element.querySelector('.strength-scene__copy > p:last-child')!, element),
      record: ratio(
        element.querySelector('[data-record]')!,
        element.querySelector('.strength-scene__record')!,
      ),
    };
  });
  expect(contrast.note).toBeGreaterThanOrEqual(4.5);
  expect(contrast.record).toBeGreaterThanOrEqual(4.5);
  const effort = scene.getByRole('button', { name: 'Усилие' });
  const record = scene.getByRole('button', { name: 'Запись' });
  await effort.focus();
  await page.keyboard.press('Enter');
  await expect(effort).toHaveAttribute('aria-pressed', 'true');
  await expect(effort).toBeFocused();
  await expect(scene.locator('[data-reps]')).toHaveText('2');
  await record.click();
  await expect(record).toHaveAttribute('aria-pressed', 'true');
  await expect(scene.locator('[data-record]')).toHaveText('18 кг × 3');
  await result.click();
  await expect(result).toHaveAttribute('aria-pressed', 'true');
  await expect(scene.locator('.strength-scene__result')).toBeVisible();
});

test('strength scene stays in flow in a short viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 500 });
  await page.goto('/');
  const scene = page.locator('.strength-scene');
  await scene.scrollIntoViewIfNeeded();
  await expect(scene.locator('.strength-scene__sticky')).toHaveCSS('position', 'relative');
  await expect(
    scene.getByText('Движение не распознаётся автоматически. Результат отмечаете вы.'),
  ).toBeVisible();
  await scene.getByRole('button', { name: 'Результат' }).click();
  await expect(scene.locator('.strength-scene__result')).toBeVisible();
});

for (const theme of ['light', 'dark'] as const) {
  test(`scene choices use the shared selected state in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await page.goto('/for-trainers');
    const choices = page.locator('#coach-program .ref-tabs button');
    await expect(choices.first()).toHaveAttribute('data-yfc-choice', 'compact');
    await choices.nth(1).click();
    await expect(choices.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await expect(choices.first()).toHaveAttribute('aria-pressed', 'false');
    await expect(choices.nth(1)).toHaveCSS('background-image', /linear-gradient/);
  });
}
