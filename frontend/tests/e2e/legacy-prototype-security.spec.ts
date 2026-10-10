import { readFile } from 'node:fs/promises';
import { expect, test, type Page } from '@playwright/test';

async function installPrototype(page: Page, path: string) {
  const files = new Map(
    await Promise.all(
      ['index.html', 'app.js', 'styles.css', 'approved-icons.js'].map(async (name) => {
        const source = new URL(`../../../${path}/${name}`, import.meta.url);
        const body = await readFile(source, 'utf8').catch((error: NodeJS.ErrnoException) => {
          if (name === 'approved-icons.js' && error.code === 'ENOENT') return '';
          throw error;
        });
        return [name, body] as const;
      }),
    ),
  );
  await page.route('**/__legacy-prototype/**', async (route) => {
    const name = new URL(route.request().url()).pathname.split('/').at(-1) ?? '';
    const body = files.get(name);
    if (body === undefined) return route.abort();
    return route.fulfill({
      body,
      contentType: name.endsWith('.js')
        ? 'text/javascript'
        : name.endsWith('.css')
          ? 'text/css'
          : 'text/html',
    });
  });
}

test('stage-0 prototype keeps known directions and normalizes URL and DOM input', async ({
  page,
}) => {
  await installPrototype(page, 'docs/app-experience-v3/stage-0/prototype');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const direction of ['command', 'radar', 'stage', '"><img src=x onerror=alert(1)>']) {
    await page.goto(`/__legacy-prototype/index.html?direction=${encodeURIComponent(direction)}`);
    const expected = direction.startsWith('">') ? 'command' : direction;
    await expect(page.locator('.direction-panel')).toHaveClass(
      `direction-panel direction-panel--${expected}`,
    );
    await expect(page.locator('#mainContent h1')).toBeVisible();
    expect(await page.locator('#mainContent img').count()).toBe(0);
  }
  await page
    .locator('[data-action="screen"]')
    .first()
    .evaluate((element) => {
      const control = element as HTMLElement;
      control.id = 'injected-direction';
      control.dataset.action = 'direction';
      control.dataset.value = '"><img src=x onerror=alert(1)>';
    });
  await page.locator('#injected-direction').click();
  await expect(page.locator('.direction-panel')).toHaveClass(
    'direction-panel direction-panel--command',
  );
  expect(errors).toEqual([]);
});

test('reset prototype renders every known screen and rejects inherited or injected names', async ({
  page,
}) => {
  await installPrototype(page, 'docs/ux/post-release-reset/prototype');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/__legacy-prototype/index.html');
  const screens = await page
    .locator('#screenSelect option')
    .evaluateAll((options) => options.map((option) => (option as HTMLOptionElement).value));
  expect(screens).toHaveLength(13);
  for (const screen of screens) {
    await page.locator('#screenSelect').selectOption(screen);
    await expect(page.locator('#app > .screen')).toHaveAttribute('data-screen-state', screen);
    await expect(page.locator('#app h1')).toBeVisible();
  }
  for (const screen of ['constructor', 'toString', '__proto__', '"><img src=x onerror=alert(1)>']) {
    await page.goto(
      `/__legacy-prototype/index.html?variant=constructor&screen=${encodeURIComponent(screen)}`,
    );
    await expect(page.locator('#app > .screen')).toHaveAttribute(
      'data-screen-state',
      'today-workout',
    );
    await expect(page.locator('#directionLabel')).toHaveText('Command Stack');
  }
  await page.locator('#screenSelect').evaluate((element) => {
    const select = element as HTMLSelectElement;
    select.add(new Option('invalid', '"><img src=x onerror=alert(1)>'));
    select.value = '"><img src=x onerror=alert(1)>';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await expect(page.locator('#app > .screen')).toHaveAttribute(
    'data-screen-state',
    'today-workout',
  );
  await page
    .locator('#app [data-screen]')
    .first()
    .evaluate((element) => {
      (element as HTMLElement).dataset.screen = 'constructor';
    });
  await page.locator('#app [data-screen]').first().click();
  await expect(page.locator('#app > .screen')).toHaveAttribute(
    'data-screen-state',
    'today-workout',
  );
  expect(await page.locator('#app img').count()).toBe(0);
  expect(errors).toEqual([]);
});
