import { expect, test } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';

for (const width of [320, 360, 390, 393, 430]) {
  for (const theme of ['light', 'dark'] as const) {
    test(`personal navigation remains readable with enlarged text at ${width}px ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 852 });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
      await page.goto('/app?section=today');
      const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
      const items = navigation.locator('.app-bottom-nav__primary .app-bottom-nav__btn');
      await expect(items).toHaveCount(5);
      await page.evaluate(() => {
        document.documentElement.style.fontSize = '32px';
      });
      await page.evaluate(() => document.fonts.ready);
      await expect(items.first().locator('.app-bottom-nav__label')).toHaveCSS(
        'font-size',
        width < 360 ? '22px' : '24px',
      );
      await expect
        .poll(async () =>
          items.evaluateAll((elements) =>
            elements.map((element) => {
              const label = element.querySelector<HTMLElement>('.app-bottom-nav__label')!;
              const bounds = element.getBoundingClientRect();
              return {
                text: label.textContent?.trim(),
                width: Math.round(bounds.width),
                height: Math.round(bounds.height),
                fits: label.scrollWidth <= label.clientWidth + 1,
              };
            }),
          ),
        )
        .toEqual([
          expect.objectContaining({ text: 'Сегодня', fits: true }),
          expect.objectContaining({ text: 'План', fits: true }),
          expect.objectContaining({ text: 'Питание', fits: true }),
          expect.objectContaining({ text: 'Прогресс', fits: true }),
          expect.objectContaining({ text: 'Добавить', fits: true }),
        ]);
      for (const item of await items.all()) {
        const box = (await item.boundingBox())!;
        expect(box.width).toBeGreaterThanOrEqual(44);
        expect(box.height).toBeGreaterThanOrEqual(44);
      }
      await expect(navigation.getByRole('link', { name: 'Сегодня', exact: true })).toHaveAttribute(
        'aria-current',
        'page',
      );
      await expect(navigation.getByRole('button', { name: 'Быстро добавить' })).toBeVisible();
    });
  }
}

test('navigation adapts to intermediate text sizes and restores its ordinary layout', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
  await page.goto('/app?section=today');
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  const items = nav.locator('.app-bottom-nav__primary .app-bottom-nav__btn');
  await expect(items).toHaveCount(5);
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeLessThanOrEqual(76);
  for (const size of [20, 24, 32]) {
    await page.evaluate((value) => {
      document.documentElement.style.fontSize = `${value}px`;
    }, size);
    await expect(items.first().locator('.app-bottom-nav__label')).toHaveCSS(
      'font-size',
      `${size * 0.6875}px`,
    );
    await expect
      .poll(() =>
        items.evaluateAll((elements) =>
          elements.every((element) => {
            const label = element.querySelector<HTMLElement>('.app-bottom-nav__label')!;
            return label.scrollWidth <= label.clientWidth + 1;
          }),
        ),
      )
      .toBe(true);
  }
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '16px';
  });
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeLessThanOrEqual(76);

  await page.setViewportSize({ width: 160, height: 426 });
  await expect
    .poll(() =>
      items.evaluateAll((elements) => {
        const boxes = elements.map((element) => element.getBoundingClientRect());
        return elements.every((element, index) => {
          const label = element.querySelector<HTMLElement>('.app-bottom-nav__label')!;
          const box = boxes[index]!;
          return (
            label.scrollWidth <= label.clientWidth + 1 &&
            box.width >= 44 &&
            box.height >= 44 &&
            boxes.every(
              (other, otherIndex) =>
                index === otherIndex ||
                Math.min(box.right, other.right) <= Math.max(box.left, other.left) ||
                Math.min(box.bottom, other.bottom) <= Math.max(box.top, other.top),
            )
          );
        });
      }),
    )
    .toBe(true);
  await page.setViewportSize({ width: 320, height: 852 });
  await expect.poll(async () => (await nav.boundingBox())!.height).toBeLessThanOrEqual(76);
});

test('narrow zoom viewport keeps the approved two-column dock', async ({ page }) => {
  await page.setViewportSize({ width: 215, height: 426 });
  await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
  await page.goto('/app?section=today');
  const navigation = page.getByRole('navigation', { name: 'Основная навигация' });
  await expect(navigation.getByRole('button', { name: 'Быстро добавить' })).toBeVisible();
  await expect(navigation).toHaveAttribute('data-dock-columns', '2');
});

test('Today primary action remains fully visible in a narrow zoom viewport', async ({ page }) => {
  await page.setViewportSize({ width: 160, height: 426 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
  await page.goto('/app?section=today');
  const action = page.getByRole('button', { name: 'Начать тренировку', exact: true });
  await expect(action).toBeVisible();
  await action.evaluate((element) =>
    element.scrollIntoView({ block: 'center', inline: 'nearest' }),
  );
  const geometry = await action.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const dock = document.querySelector('#appBottomNav')!.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    return {
      box: box.toJSON(),
      dockTop: dock.top,
      lines: Array.from(range.getClientRects(), (line) => line.toJSON()),
    };
  });
  expect(geometry.box.top).toBeGreaterThanOrEqual(0);
  expect(geometry.box.bottom).toBeLessThanOrEqual(geometry.dockTop);
  for (const line of geometry.lines) {
    expect(line.left).toBeGreaterThanOrEqual(geometry.box.left - 1);
    expect(line.right).toBeLessThanOrEqual(geometry.box.right + 1);
  }
});

test('Today and Quick Add preserve readable text and keyboard actions at 200% text', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, { browserSession: true, fixedDate: '2026-11-17' });
  await page.goto('/app?section=today');
  const trigger = page.getByRole('button', { name: 'Быстро добавить', exact: true });
  await expect(trigger).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '32px';
  });
  await expect
    .poll(() =>
      page.locator('.today-dashboard__header h1').evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return range.getBoundingClientRect().right <= innerWidth + 1;
      }),
    )
    .toBe(true);
  await trigger.click();
  const sheet = page.getByRole('dialog', { name: 'Что добавить?' });
  await expect(sheet).toBeVisible();
  const links = sheet.getByRole('link');
  await expect(links).toHaveText(['Еда', 'Вода', 'Кардио', 'Замер', 'Самочувствие']);
  for (const link of await links.all()) {
    await link.scrollIntoViewIfNeeded();
    const visible = await link.evaluate((element) => {
      const text = element.querySelector('strong')!;
      const copy = text.parentElement!.getBoundingClientRect();
      const list = element.closest('.app-quick-add-panel__actions')!.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(text);
      return Array.from(range.getClientRects()).every(
        (line) =>
          line.left >= copy.left - 1 &&
          line.right <= copy.right + 1 &&
          line.top >= list.top - 1 &&
          line.bottom <= list.bottom + 1,
      );
    });
    expect(visible).toBe(true);
  }
  await expect(sheet.getByRole('link', { name: 'Вода', exact: true })).toHaveAttribute(
    'href',
    '/app?section=nutrition&hydration=quick',
  );
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('Active Workout keeps editable fields reachable above the enlarged dock', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 852 });
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: '2026-11-17',
    workoutStatus: 'in_progress',
  });
  await page.goto('/app?section=today');
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '32px';
  });
  await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
  const field = page.locator('.active-workout-exercise input:not([type="checkbox"])').first();
  await expect(field).toBeVisible();
  await field.scrollIntoViewIfNeeded();
  await field.focus();
  await expect(field).toBeFocused();
  const unobscured = await field.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return hit === element || element.contains(hit);
  });
  expect(unobscured).toBe(true);
  await field.fill('12');
  await expect(field).toHaveValue('12');
  await expect(page.locator('html')).toHaveAttribute('data-yfc-keyboard', 'visible');
  await expect(page.locator('#appBottomNav')).toBeHidden();
  await field.blur();
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
});

test('Active Workout restores navigation after keyboard input at a narrow zoom viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 160, height: 426 });
  await installPlatformApi(page, {
    browserSession: true,
    fixedDate: '2026-11-17',
    workoutStatus: 'in_progress',
  });
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Продолжить тренировку', exact: true }).click();
  const field = page.locator('.active-workout-exercise input:not([type="checkbox"])').first();
  await expect(field).toBeVisible();
  await field.scrollIntoViewIfNeeded();
  await field.focus();
  await expect(field).toBeFocused();
  await expect(page.locator('#appBottomNav')).toBeHidden();
  await field.fill('12');
  await expect(field).toHaveValue('12');
  await field.blur();
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
});
