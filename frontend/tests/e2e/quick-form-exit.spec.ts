import type { Locator, Page, TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, expectNoHorizontalOverflow, test } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';

const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Moscow' });
const previousDay = () => {
  const value = new Date(`${today()}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() - 1);
  return value.toISOString().slice(0, 10);
};

async function capture(page: Page, name: string, info: TestInfo) {
  const output = process.env.YFC_QUICK_EXIT_EVIDENCE_DIR;
  if (!output) return;
  await mkdir(output, { recursive: true });
  const viewport = page.viewportSize()!;
  const stem = `${info.project.name}-${info.title.replaceAll(' ', '-')}-${name}-${viewport.width}x${viewport.height}`;
  await page.screenshot({ path: resolve(output, `${stem}.png`), fullPage: false });
  await writeFile(
    resolve(output, `${stem}.json`),
    JSON.stringify(
      {
        scenario: name,
        browser: info.project.name,
        viewport,
        theme: await page.locator('html').getAttribute('data-color-scheme'),
        controls: await page
          .locator(
            '.measurement-diary__header .ui-button, .daily-wellbeing__actions .ui-button, .modal__panel',
          )
          .evaluateAll((elements) =>
            elements.map((element) => ({
              text: element.textContent?.trim(),
              bounds: element.getBoundingClientRect().toJSON(),
              clientWidth: element.clientWidth,
              scrollWidth: element.scrollWidth,
            })),
          ),
      },
      null,
      2,
    ),
  );
}

async function openQuickAction(page: Page, name: 'Замер' | 'Самочувствие') {
  await page.getByRole('button', { name: 'Быстро добавить' }).click();
  await page
    .getByRole('dialog', { name: 'Что добавить?' })
    .getByRole('link', { name: new RegExp(`^${name}`) })
    .click();
}

async function expectVisibleReturn(page: Page, button: Locator) {
  await button.scrollIntoViewIfNeeded();
  await expect(button).toBeVisible();
  const rect = await button.boundingBox();
  expect(rect).not.toBeNull();
  expect(rect!.height).toBeGreaterThanOrEqual(44);
  expect(rect!.x).toBeGreaterThanOrEqual(0);
  expect(rect!.x + rect!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  expect(rect!.y).toBeGreaterThanOrEqual(0);
  expect(rect!.y + rect!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
  await expect
    .poll(() =>
      button.evaluate((element) => {
        const box = element.getBoundingClientRect();
        return [0.15, 0.5, 0.85].every((fraction) =>
          element.contains(
            document.elementFromPoint(box.left + box.width * fraction, box.top + box.height / 2),
          ),
        );
      }),
    )
    .toBe(true);
}

for (const platform of ['web', 'mocked-tma'] as const) {
  for (const width of platform === 'web' ? [320, 360, 390, 393, 430] : [390]) {
    for (const theme of ['dark', 'light'] as const) {
      test(`quick exits ${platform} ${theme} ${width}`, async ({
        mobilePage,
        tmaPage,
        tma,
      }, info) => {
        test.setTimeout(90_000);
        const page = platform === 'web' ? mobilePage : tmaPage;
        const api = await installPlatformApi(page, { browserSession: true });
        await page.route(/\/workouts\/diary\/custom-definitions(?:\?|$)/, (route) =>
          route.fulfill({ json: [] }),
        );
        const writes: string[] = [];
        page.on('request', (request) => {
          if (
            /\/workouts\/diary|\/check-ins\/daily/.test(request.url()) &&
            ['POST', 'PUT', 'DELETE'].includes(request.method())
          )
            writes.push(request.method());
        });
        await page.setViewportSize({ width, height: 844 });
        await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
        await page.goto('/app?section=progress&focus=measurements');
        const diary = page.locator('#measurement-diary');
        const measurementExit = diary.getByRole('button', { name: 'Вернуться' });
        await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
        if (platform === 'mocked-tma') await tma.setTheme(theme);
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
        await expectVisibleReturn(page, measurementExit);
        await expectNoHorizontalOverflow(page);
        await capture(page, 'measurement-unchanged', info);
        await measurementExit.focus();
        await measurementExit.press('Enter');
        await expect(page).toHaveURL(/\/app\?section=progress$/);
        await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();
        await expect(page.getByRole('dialog')).toHaveCount(0);

        await openQuickAction(page, 'Замер');
        const weight = diary.getByLabel('Вес, кг');
        await weight.fill('70.2');
        await diary
          .getByRole('textbox', { name: 'Заметка', exact: true })
          .fill('Синтетический черновик длинной формы. '.repeat(8));
        await diary.getByLabel('Дата').fill(previousDay());
        await expect(weight).toHaveValue('70.2');
        await expect(diary.getByLabel('Дата')).toHaveValue(previousDay());
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await capture(page, 'measurement-dirty', info);
        await diary.getByRole('textbox', { name: 'Заметка', exact: true }).focus();
        await page.setViewportSize({ width, height: 430 });
        if (platform === 'mocked-tma') await tma.setViewport(430, 844, false);
        await expectVisibleReturn(page, measurementExit);
        await capture(page, 'measurement-simulated-keyboard', info);
        await measurementExit.focus();
        await measurementExit.press('Enter');
        const measurementConfirm = page.getByRole('dialog', { name: 'Вернуться без сохранения?' });
        await expect(measurementConfirm).toContainText('останутся в черновике на этом устройстве');
        await capture(page, 'measurement-confirmation', info);
        await page.keyboard.press('Escape');
        await expect(measurementConfirm).toHaveCount(0);
        await expect(measurementExit).toBeFocused();
        await expect(weight).toHaveValue('70.2');
        if (platform === 'mocked-tma') {
          await tma.clickBack();
          await expect(measurementConfirm).toBeVisible();
          await tma.clickBack();
          await expect(measurementConfirm).toHaveCount(0);
          await expect(measurementExit).toBeFocused();
          await expect(weight).toHaveValue('70.2');
          await tma.clickBack();
        } else await measurementExit.press('Enter');
        await measurementConfirm.getByRole('button', { name: 'Вернуться' }).click();
        await expect(page).toHaveURL(/\/app\?section=progress$/);
        await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();
        await page.setViewportSize({ width, height: 844 });
        if (platform === 'mocked-tma') await tma.setViewport(844, 844, true);
        await openQuickAction(page, 'Замер');
        await expect(weight).toHaveValue('70.2');
        await expect(diary.getByLabel('Дата')).toHaveValue(previousDay());

        await page.goto('/app?section=today&wellbeing=1');
        const wellbeing = page.locator('form.daily-wellbeing__form');
        const wellbeingExit = wellbeing.getByRole('button', { name: 'Вернуться' });
        await expect(wellbeingExit).toBeVisible();
        if (platform === 'mocked-tma') await tma.setTheme(theme);
        await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
        await expectNoHorizontalOverflow(page);
        await expectVisibleReturn(page, wellbeingExit);
        await capture(page, 'wellbeing-unchanged', info);
        await wellbeingExit.focus();
        await wellbeingExit.press('Enter');
        await expect(page).toHaveURL(/\/app\?section=today$/);
        await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await openQuickAction(page, 'Самочувствие');
        await wellbeing.getByRole('radio', { name: 'Очень плохо' }).check();
        await wellbeing.getByLabel('Сколько спали, часов').fill('7');
        await page.locator('.daily-wellbeing__note > summary').click();
        const note = wellbeing.getByLabel('Заметка для себя');
        const noteText = 'Синтетическая заметка для проверки выхода. '.repeat(8);
        await note.fill(noteText);
        await capture(page, 'wellbeing-dirty', info);
        await wellbeing.getByLabel('День').fill(previousDay());
        const dateConfirm = page.getByRole('dialog', { name: 'Сменить день без сохранения?' });
        await dateConfirm.getByRole('button', { name: 'Отмена' }).click();
        await expect(wellbeing.getByLabel('День')).toHaveValue(today());
        await expect(note).toHaveValue(noteText);
        await note.focus();
        await page.setViewportSize({ width, height: 430 });
        if (platform === 'mocked-tma') await tma.setViewport(430, 844, false);
        await expectVisibleReturn(page, wellbeingExit);
        await capture(page, 'wellbeing-simulated-keyboard', info);
        await wellbeingExit.focus();
        await wellbeingExit.press('Enter');
        const wellbeingConfirm = page.getByRole('dialog', { name: 'Выйти без сохранения?' });
        await expect(wellbeingConfirm).toContainText('Введённые данные будут потеряны');
        await capture(page, 'wellbeing-confirmation', info);
        await page.keyboard.press('Escape');
        await expect(wellbeingConfirm).toHaveCount(0);
        await expect(wellbeingExit).toBeFocused();
        await expect(note).toHaveValue(noteText);
        if (platform === 'mocked-tma') {
          await tma.clickBack();
          await expect(wellbeingConfirm).toBeVisible();
          await tma.clickBack();
          await expect(wellbeingConfirm).toHaveCount(0);
          await expect(wellbeingExit).toBeFocused();
          await expect(note).toHaveValue(noteText);
          await tma.clickBack();
        } else await wellbeingExit.press('Enter');
        await wellbeingConfirm.getByRole('button', { name: 'Выйти' }).click();
        await expect(page).toHaveURL(/\/app\?section=today$/);
        await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();
        await page.setViewportSize({ width, height: 844 });
        if (platform === 'mocked-tma') await tma.setViewport(844, 844, true);
        await openQuickAction(page, 'Самочувствие');
        await expect(wellbeing.getByRole('radio', { name: 'Очень плохо' })).not.toBeChecked();
        await expect(wellbeing.getByLabel('Сколько спали, часов')).toHaveValue('');
        expect(api.measurementSaveCalls()).toBe(0);
        expect(writes).toEqual([]);
      });
    }
  }
}

test('quick measurement protects editing and unrelated history deletion without duplicate writes', async ({
  mobilePage: page,
}) => {
  const api = await installPlatformApi(page, { browserSession: true, measurementHistory: 'many' });
  await page.route(/\/workouts\/diary\/custom-definitions(?:\?|$)/, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto('/app?section=progress&focus=measurements');
  const diary = page.locator('#measurement-diary');
  const rows = diary.locator('.measurement-history__row');
  await expect(rows).toHaveCount(4);
  await rows.first().getByRole('button', { name: 'Изменить' }).click();
  const exit = diary.getByRole('button', { name: 'Вернуться' });
  await exit.click();
  await expect(page).toHaveURL(/\/app\?section=progress$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await openQuickAction(page, 'Замер');
  await expect(diary.getByRole('heading', { name: 'Изменить замер' })).toBeVisible();
  await diary.getByLabel('Вес, кг').fill('80.5');
  await diary.getByRole('button', { name: 'Отменить изменение' }).click();
  const cancel = page.getByRole('dialog', { name: 'Отменить изменения?' });
  await cancel.getByRole('button', { name: 'Отмена' }).click();
  await expect(diary.getByLabel('Вес, кг')).toHaveValue('80.5');
  await rows.last().getByRole('button', { name: 'Удалить' }).click();
  const deletion = page.getByRole('dialog', { name: 'Удалить замер?' });
  await deletion.getByRole('button', { name: 'Отмена' }).click();
  await expect(rows).toHaveCount(4);
  await rows.last().getByRole('button', { name: 'Удалить' }).click();
  const deleted = page.waitForResponse(
    (response) =>
      /\/workouts\/diary\/104$/.test(response.url()) && response.request().method() === 'DELETE',
  );
  await deletion.getByRole('button', { name: 'Удалить' }).click();
  expect((await deleted).status()).toBe(204);
  await expect(rows).toHaveCount(3);
  await expect(diary.getByLabel('Вес, кг')).toHaveValue('80.5');
  const saved = page.waitForRequest(
    (request) => request.url().endsWith('/workouts/diary') && request.method() === 'POST',
  );
  await diary.getByRole('button', { name: 'Сохранить изменения' }).click();
  expect((await saved).postDataJSON()).not.toHaveProperty('editingDate');
  await expect(rows.filter({ hasText: '80,5 кг' })).toHaveCount(1);
  await expect(rows).toHaveCount(3);
  expect(api.measurementSaveCalls()).toBe(1);
  await page.reload();
  await expect(rows.filter({ hasText: '80,5 кг' })).toHaveCount(1);
  await expect(diary.getByLabel('Вес, кг')).toHaveValue('');
});

for (const theme of ['dark', 'light'] as const) {
  test(`desktop wellbeing return stays unobscured ${theme}`, async ({ page }, info) => {
    await installPlatformApi(page, { browserSession: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    await page.goto('/app?section=today&wellbeing=1');
    const wellbeing = page.locator('form.daily-wellbeing__form');
    const exit = wellbeing.getByRole('button', { name: 'Вернуться' });
    const floatingAdd = page.getByRole('button', { name: 'Быстро добавить' });
    await expect(exit).toBeVisible();
    await page.getByRole('heading', { name: 'Сон и настроение' }).scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await exit.scrollIntoViewIfNeeded();
    const geometry = await exit.evaluate((button) => {
      const box = button.getBoundingClientRect();
      const fab = document.querySelector<HTMLElement>('.app-quick-add-trigger--floating');
      const fabBox = fab?.getBoundingClientRect();
      const fabVisible = fab && getComputedStyle(fab).visibility !== 'hidden';
      return {
        exit: box.toJSON(),
        fab: fabBox?.toJSON(),
        overlap: Boolean(
          fabVisible &&
          fabBox &&
          box.left < fabBox.right &&
          box.right > fabBox.left &&
          box.top < fabBox.bottom &&
          box.bottom > fabBox.top,
        ),
        hits: [0.15, 0.5, 0.85].map((fraction) =>
          button.contains(
            document.elementFromPoint(box.left + box.width * fraction, box.top + box.height / 2),
          ),
        ),
      };
    });
    await info.attach('wellbeing-return-hit-test', {
      body: JSON.stringify(geometry, null, 2),
      contentType: 'application/json',
    });
    expect(geometry.overlap).toBe(false);
    expect(geometry.hits).toEqual([true, true, true]);
    await expect(floatingAdd).toBeHidden();
    const sleep = wellbeing.getByRole('radio', { name: 'Очень плохо' });
    await sleep.scrollIntoViewIfNeeded();
    expect(
      await sleep.evaluate((input) => {
        const box = input.closest('label')!.getBoundingClientRect();
        return input
          .closest('label')!
          .contains(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2));
      }),
    ).toBe(true);
    await page.locator('details.daily-wellbeing-card > summary').click();
    await expect(floatingAdd).toBeVisible();
    await page.locator('details.daily-wellbeing-card > summary').click();
    await expect(floatingAdd).toBeHidden();
    await exit.click();
    await expect(page).toHaveURL(/\/app\?section=today$/);
    await expect(floatingAdd).toBeVisible();
    await expect(floatingAdd).toBeFocused();
  });
}
