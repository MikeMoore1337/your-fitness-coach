import { expect, test, type Page } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';

const longTitle = 'Присед со штангой с контролируемой паузой в нижней точке и медленным подъёмом';
const exercises = Array.from({ length: 12 }, (_, index) => ({
  id: 11 + index,
  title: index === 0 ? longTitle : `Присед со штангой, вариант ${index + 1}`,
  slug: `squat-${index + 1}`,
  primary_muscle: 'Квадрицепс',
  equipment: 'Штанга',
  primary_muscle_ids: ['quadriceps'],
  secondary_muscle_ids: [],
  equipment_ids: ['barbell'],
  alternatives: [],
  difficulty_level: 'intermediate',
  is_custom: false,
  is_personalized: false,
  has_guide: false,
}));

async function setModeledVisualViewport(page: Page, height: number, offsetTop = 0) {
  await page.evaluate(
    ({ height, offsetTop }) => {
      const viewport = window.visualViewport;
      if (!viewport) throw new Error('A visual viewport is required for the keyboard model');
      Object.defineProperty(viewport, 'height', { configurable: true, value: height });
      Object.defineProperty(viewport, 'offsetTop', { configurable: true, value: offsetTop });
      viewport.dispatchEvent(new Event('resize'));
    },
    { height, offsetTop },
  );
  await expect(page.locator('html')).toHaveCSS('--yfc-viewport-height', `${height}px`);
}

test('#861 modeled TMA keyboard respects safe areas and Back restores the editor draft', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installTelegramHarness(page, {
    platform: 'ios',
    colorScheme: 'dark',
    viewportHeight: 844,
    viewportStableHeight: 844,
    safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
  });
  const telegram = new TelegramHarness(page);
  await installPlatformApi(page, { programHistory: 'many' });
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.goto('/app?section=programs&view=manage&start=templates');
  await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
  const editor = page.locator('.program-editor-modal');
  await expect(
    editor.getByRole('button', { name: 'Закрыть редактирование', exact: true }),
  ).toBeFocused();
  const draftTitle = editor.getByLabel('Название', { exact: true });
  await draftTitle.fill('Черновик Telegram');
  await expect(draftTitle).toHaveValue('Черновик Telegram');
  await editor.getByRole('button', { name: 'Добавить упражнение', exact: true }).click();
  const trigger = page
    .getByRole('dialog', { name: 'Параметры упражнения' })
    .getByRole('button', { name: 'Поиск упражнения', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Выбор упражнения', exact: true });
  await expect(dialog.getByRole('searchbox')).toBeFocused();
  await dialog.getByRole('searchbox').fill('присд');
  await expect(dialog.locator('.exercise-picker__option')).toHaveCount(exercises.length);
  await expect(trigger).toContainText('Выбрать упражнение');
  await dialog.getByRole('searchbox').fill('присед');
  await setModeledVisualViewport(page, 420, 48);
  await telegram.setViewport(420, 844, false);
  await expect
    .poll(async () => {
      const box = await dialog.boundingBox();
      return box ? box.y + box.height : Infinity;
    })
    .toBeLessThanOrEqual(48 + 420 - 34);
  const box = await dialog.boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(48 + 24);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: info.outputPath('after-tma-keyboard-safe-area.png') });
  await telegram.clickBack();
  await expect(dialog).toHaveCount(0);
  await expect(editor).toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(draftTitle).toHaveValue('Черновик Telegram');
});

test.use({ hasTouch: true, serviceWorkers: 'block' });

test('#1202 suggests a typo match without selecting an exercise', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 844 });
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  await page.route('**/api/v1/programs/exercises', (route) =>
    route.fulfill({
      json: [
        { ...exercises[0], id: 101, title: 'Жим гантелей лёжа', slug: 'dumbbell-press' },
        { ...exercises[0], id: 102, title: 'Жим штанги лёжа', slug: 'barbell-press' },
      ],
    }),
  );
  await page.goto('/app?section=programs&view=manage');
  const builder = page.locator('#program-builder');
  await builder.locator('.copy-editor__exercise').first().click();
  const parameters = page.getByRole('dialog', { name: 'Параметры упражнения' });
  const trigger = parameters.getByRole('button', { name: 'Поиск упражнения', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: 'Выбор упражнения', exact: true });
  await dialog.getByRole('searchbox').fill('жим гантелй');
  await expect(dialog.locator('.exercise-picker__option')).toHaveCount(1);
  await expect(dialog.locator('.exercise-picker__option')).toContainText('Жим гантелей лёжа');
  await expect(trigger).toContainText('Выбрать упражнение');
  await expectNoHorizontalOverflow(page);
  await dialog.locator('.exercise-picker__option').click();
  await expect(trigger).toContainText('Жим гантелей лёжа');
});

for (const width of [320, 360, 390, 393, 430]) {
  for (const theme of ['dark', 'light'] as const) {
    test(`#861 editor picker retains focus and results with modeled keyboard at ${width}px ${theme}`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
      await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
      await page.route('**/api/v1/programs/exercises', (route) =>
        route.fulfill({ json: exercises }),
      );
      const catalogResponse = page.waitForResponse('**/api/v1/programs/exercises');
      await page.goto('/app?section=programs&view=manage&start=templates');
      await page.getByRole('button', { name: 'Редактировать шаблон', exact: true }).click();
      const response = await catalogResponse;
      expect(response.status()).toBe(200);
      expect(await response.json()).toHaveLength(exercises.length);
      const editor = page.locator('.program-editor-modal');
      await expect(
        editor.getByRole('button', { name: 'Закрыть редактирование', exact: true }),
      ).toBeFocused();
      const draftTitle = editor.getByLabel('Название', { exact: true });
      await draftTitle.fill('Черновик редактора');
      await expect(draftTitle).toHaveValue('Черновик редактора');
      await editor.getByRole('button', { name: 'Добавить упражнение', exact: true }).click();
      const trigger = page
        .getByRole('dialog', { name: 'Параметры упражнения' })
        .getByRole('button', { name: 'Поиск упражнения', exact: true });
      await trigger.click();
      const dialog = page.getByRole('dialog', { name: 'Выбор упражнения', exact: true });
      const search = dialog.getByRole('searchbox');
      const clear = dialog.getByRole('button', { name: 'Очистить поиск', exact: true });
      const options = dialog.locator('.exercise-picker__option');
      const results = dialog.locator('.exercise-picker__results');
      await expect(search).toBeFocused();
      await search.fill('присед');
      await expect(options).toHaveCount(exercises.length);
      await search.press('Tab');
      await expect(clear).toBeFocused();
      await clear.press('Shift+Tab');
      await expect(search).toBeFocused();
      await setModeledVisualViewport(page, 420, 48);
      await expect
        .poll(async () => {
          const box = await dialog.boundingBox();
          return box ? box.y + box.height : Infinity;
        })
        .toBeLessThanOrEqual(468);
      await page.evaluate(() => document.fonts.ready);

      const geometry = await dialog.evaluate((panel) => {
        const rect = (element: Element) => element.getBoundingClientRect().toJSON();
        const first = panel.querySelector('.exercise-picker-sheet__row')!;
        const option = first.querySelector('.exercise-picker__option')!;
        const title = first.querySelector('strong')!;
        const meta = first.querySelector('small')!;
        return {
          panel: rect(panel),
          search: rect(panel.querySelector('input')!),
          first: rect(first),
          option: rect(option),
          title: rect(title),
          meta: rect(meta),
          clear: rect(panel.querySelector('.exercise-picker-sheet__clear')!),
          close: rect(panel.querySelector('header button')!),
          guide: rect(first.querySelector('.exercise-picker__guide')!),
          scroll: rect(panel.querySelector('.exercise-picker__results')!),
          titleWhiteSpace: getComputedStyle(title).whiteSpace,
          titleOverflow: title.scrollWidth > title.clientWidth,
          panelOverflow: panel.scrollWidth > panel.clientWidth,
          viewport: { height: visualViewport!.height, offsetTop: visualViewport!.offsetTop },
        };
      });
      const geometryPath = info.outputPath('picker-keyboard-geometry.json');
      await writeFile(geometryPath, JSON.stringify(geometry, null, 2));
      await info.attach('picker-keyboard-geometry.json', {
        path: geometryPath,
        contentType: 'application/json',
      });
      expect(geometry.panel.top).toBeGreaterThanOrEqual(geometry.viewport.offsetTop);
      expect(geometry.panel.bottom).toBeLessThanOrEqual(
        geometry.viewport.offsetTop + geometry.viewport.height,
      );
      expect(geometry.first.bottom).toBeLessThanOrEqual(geometry.scroll.bottom);
      expect(geometry.search.bottom).toBeLessThan(geometry.first.top);
      expect(geometry.title.bottom).toBeLessThanOrEqual(geometry.meta.top);
      expect(geometry.meta.bottom).toBeLessThanOrEqual(geometry.guide.top);
      expect(geometry.titleOverflow).toBe(false);
      expect(geometry.panelOverflow).toBe(false);
      expect(geometry.titleWhiteSpace).toBe('normal');
      for (const control of [geometry.option, geometry.clear, geometry.close, geometry.guide]) {
        expect(control.width).toBeGreaterThanOrEqual(44);
        expect(control.height).toBeGreaterThanOrEqual(44);
      }
      await expectNoHorizontalOverflow(page);
      await page.screenshot({ path: info.outputPath('after-keyboard-query.png') });

      const searchBeforeScroll = await search.boundingBox();
      await options.last().scrollIntoViewIfNeeded();
      await expect(options.last()).toBeInViewport();
      expect(await results.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
      expect((await search.boundingBox())!.y).toBe(searchBeforeScroll!.y);
      await page.screenshot({ path: info.outputPath('after-keyboard-last-result.png') });
      await search.fill('присед со');
      expect(await results.evaluate((element) => element.scrollTop)).toBe(0);

      // Model keyboard dismissal on blur so a tap cannot move its target before click.
      await search.evaluate((element) => {
        element.addEventListener(
          'blur',
          () => {
            const viewport = window.visualViewport!;
            Object.defineProperty(viewport, 'height', { configurable: true, value: 844 });
            Object.defineProperty(viewport, 'offsetTop', { configurable: true, value: 0 });
            viewport.dispatchEvent(new Event('resize'));
          },
          { once: true },
        );
      });
      await clear.tap();
      await expect(search).toHaveValue('');
      await expect(search).toBeFocused();
      await expect(page.locator('html')).toHaveCSS('--yfc-viewport-height', '420px');
      await expect(options).toHaveCount(exercises.length);
      await search.fill('несуществующее упражнение');
      await expect(dialog.getByRole('status')).toHaveText('Ничего не найдено');
      await page.screenshot({ path: info.outputPath('after-keyboard-empty.png') });
      await clear.tap();
      await search.fill('присед');
      await options.first().tap();
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect(trigger).toContainText(longTitle);
      await expect(draftTitle).toHaveValue('Черновик редактора');
      await setModeledVisualViewport(page, 844);
      await expectNoHorizontalOverflow(page);

      await trigger.click();
      await expect(search).toBeFocused();
      await expect(search).toHaveValue(longTitle);
      await search.fill('другой запрос');
      await dialog.getByRole('button', { name: 'Закрыть выбор упражнения' }).click();
      await expect(trigger).toBeFocused();
      await trigger.click();
      await expect(search).toBeFocused();
      await expect(search).toHaveValue(longTitle);
      await search.press('Escape');
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await expect(draftTitle).toHaveValue('Черновик редактора');
      await page.screenshot({ path: info.outputPath('after-selection-editor-draft.png') });
    });
  }
}
