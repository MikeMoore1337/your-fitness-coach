import { writeFile } from 'node:fs/promises';
import { expect, test } from '../../../../frontend/tests/e2e/fixtures/mobile-tma';
import { installPlatformApi } from '../../../../frontend/tests/e2e/fixtures/platform-api';

for (const theme of ['light', 'dark'] as const) {
  test(`desktop legacy flows ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await page.addInitScript((value) => localStorage.setItem('app-theme', value), theme);
    const api = await installPlatformApi(page, { browserSession: true });
    const capture = async (scenario: string) => {
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ scale: 'css', path: info.outputPath(`${scenario}.png`) });
      await writeFile(info.outputPath(`${scenario}.json`), JSON.stringify({
        scenario, browser: info.project.name, theme, viewport: page.viewportSize(),
        userAgent: await page.evaluate(() => navigator.userAgent),
        devicePixelRatio: await page.evaluate(() => devicePixelRatio),
      }, null, 2));
    };
    await page.goto('/app?section=progress&focus=measurements');
    const diary = page.locator('#measurement-diary');
    await expect(diary.getByRole('heading', { name: 'Новый замер' })).toBeVisible();
    await diary.getByRole('heading', { name: 'Новый замер' }).scrollIntoViewIfNeeded();
    await capture('measurement-unchanged');
    await diary.getByLabel('Вес, кг').fill('70.2');
    await diary.getByRole('button', { name: 'Вернуться' }).click();
    const measurementConfirm = page.getByRole('dialog', { name: 'Вернуться без сохранения?' });
    await expect(measurementConfirm).toContainText('останутся в черновике');
    await capture('measurement-confirmation');
    await page.keyboard.press('Escape');
    await expect(diary.getByLabel('Вес, кг')).toHaveValue('70.2');
    await diary.getByRole('button', { name: 'Вернуться' }).click();
    await measurementConfirm.getByRole('button', { name: 'Вернуться' }).click();
    await expect(page).toHaveURL(/section=progress$/);
    await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();

    const floatingAdd = page.locator('.app-quick-add-trigger--floating');
    await expect(floatingAdd).toBeVisible();
    await page.goto('/app?section=today&wellbeing=1');
    const wellbeing = page.locator('form.daily-wellbeing__form');
    await expect(wellbeing).toBeVisible();
    await expect(floatingAdd).toBeHidden();
    await page.getByRole('heading', { name: 'Сон и настроение' }).scrollIntoViewIfNeeded();
    await capture('wellbeing-unchanged');
    await wellbeing.getByRole('radio', { name: 'Очень плохо' }).check();
    await wellbeing.getByRole('button', { name: 'Вернуться' }).click();
    const wellbeingConfirm = page.getByRole('dialog', { name: 'Выйти без сохранения?' });
    await expect(wellbeingConfirm).toContainText('Введённые данные будут потеряны');
    await capture('wellbeing-confirmation');
    await page.keyboard.press('Escape');
    await expect(wellbeing.getByRole('radio', { name: 'Очень плохо' })).toBeChecked();
    await wellbeing.getByRole('button', { name: 'Вернуться' }).click();
    await wellbeingConfirm.getByRole('button', { name: 'Выйти' }).click();
    await expect(page).toHaveURL(/section=today$/);
    await expect(floatingAdd).toBeVisible();
    await expect(page.getByRole('button', { name: 'Быстро добавить' })).toBeFocused();

    await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('link', { name: 'Питание', exact: true }).click();
    await page.getByRole('button', { name: /Быстрый ввод/ }).click();
    const calories = page.getByRole('spinbutton', { name: 'Калории' });
    const time = page.getByLabel('Время (необязательно)');
    await calories.fill('512.5');
    await time.fill('23:59');
    await time.focus();
    await expect(time).toBeFocused();
    const boxes = await page.locator('#nutrition-quick-calories, .nutrition-quick-add__primary-fields .time-control').evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().toJSON()));
    expect(boxes).toHaveLength(2);
    expect(Math.abs(boxes[0].height - boxes[1].height)).toBeLessThanOrEqual(1);
    expect(Math.abs(boxes[0].bottom - boxes[1].bottom)).toBeLessThanOrEqual(1);
    await capture('quick-add-filled');
    await page.getByRole('button', { name: 'Закрыть добавление' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(api.measurementSaveCalls()).toBe(0);
  });
}
