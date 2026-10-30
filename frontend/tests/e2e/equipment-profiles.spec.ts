import { expect, test, type Page } from '@playwright/test';
import { installPlatformApi } from './fixtures/platform-api';
import {
  expectNoHorizontalOverflow,
  expectTouchTargets,
  installTelegramHarness,
  TelegramHarness,
} from './fixtures/mobile-tma';

type Profile = { id: string; name: string; equipment_ids: string[] };
type State = { revision: number; active_profile_id: string | null; profiles: Profile[] };

const homeId = '00000000-0000-4000-8000-000000000001';
const exercises = [
  {
    id: 1,
    slug: 'bodyweight-squat',
    title: 'Присед без веса',
    equipment: 'Собственный вес',
    equipment_ids: ['bodyweight'],
    required_equipment_ids: [],
  },
  {
    id: 2,
    slug: 'dumbbell-bench-press',
    title: 'Жим гантелей',
    equipment: 'Гантели',
    equipment_ids: ['dumbbell'],
    required_equipment_ids: ['dumbbell', 'bench'],
  },
  {
    id: 3,
    slug: 'bench-press',
    title: 'Жим штанги',
    equipment: 'Штанга',
    equipment_ids: ['barbell'],
    required_equipment_ids: ['barbell', 'bench', 'rack'],
  },
  {
    id: 4,
    slug: 'unknown',
    title: 'Непроверенное движение',
    equipment: 'Тренажёр',
    equipment_ids: ['machine'],
    required_equipment_ids: null,
  },
  {
    id: 5,
    slug: 'custom',
    title: 'Моё движение',
    equipment: 'Гантели',
    equipment_ids: ['dumbbell'],
    required_equipment_ids: null,
    is_custom: true,
  },
].map((item) => ({
  primary_muscle: 'Ноги',
  primary_muscle_ids: [],
  secondary_muscle_ids: [],
  alternatives: [],
  difficulty_level: 'beginner',
  is_custom: false,
  is_personalized: false,
  has_guide: false,
  ...item,
}));

async function setup(page: Page, initial?: State) {
  await installPlatformApi(page, { browserSession: true, programHistory: 'many' });
  let state: State = initial ?? { revision: 0, active_profile_id: null, profiles: [] };
  let fail = false;
  await page.route('**/api/v1/programs/exercises', (route) => route.fulfill({ json: exercises }));
  await page.route('**/api/v1/me/equipment-profiles', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: state });
    const body = route.request().postDataJSON() as State;
    if (fail) {
      fail = false;
      return route.fulfill({ status: 503, json: { detail: 'Unavailable' } });
    }
    if (body.revision !== state.revision)
      return route.fulfill({ status: 409, json: { detail: 'Conflict' } });
    state = {
      ...body,
      revision: state.revision + 1,
      profiles: body.profiles.map((item, index) => ({
        ...item,
        id: item.id ?? `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
      })),
    };
    return route.fulfill({ json: state });
  });
  return {
    state: () => state,
    failNextSave: () => {
      fail = true;
    },
    changeElsewhere: (next: Profile) => {
      state = {
        ...state,
        revision: state.revision + 1,
        profiles: state.profiles.map((item) => (item.id === next.id ? next : item)),
      };
    },
  };
}

async function chooseProfile(page: Page, name: RegExp) {
  await page.getByRole('button', { name: 'Изменить профиль оборудования' }).click();
  const dialog = page.getByRole('dialog', { name: 'Выбрать профиль' });
  await dialog.getByRole('radio', { name }).check();
  await dialog.getByRole('button', { name: 'Выбрать', exact: true }).click();
  await expect(dialog).toHaveCount(0);
}

test('CRUD, availability and unknown exercises remain visible', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  const api = await setup(page);
  await page.goto('/app?section=catalog');
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(5);
  await page.getByRole('link', { name: 'Управлять профилями' }).click();
  const dialog = page.locator('.equipment-profiles__panel');
  await dialog.getByRole('button', { name: 'Создать профиль' }).click();
  await page.getByLabel('Название профиля').fill('Дом');
  await page.getByLabel('Гантели', { exact: true }).check();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(dialog.getByText('Дом', { exact: true })).toBeVisible();
  await dialog.getByRole('radio', { name: /Дом/ }).click();
  await expect.poll(() => api.state().active_profile_id).toBe(homeId);
  await expect(dialog.getByRole('radio', { name: /Дом/ })).toBeChecked();
  await dialog.getByRole('button', { name: 'Изменить', exact: true }).click();
  await page.getByLabel('Название профиля').fill('Домашний зал');
  await page.getByLabel('Скамья', { exact: true }).check();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await dialog.getByRole('link', { name: 'К упражнениям' }).click();
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(4);
  await expect(page.locator('.exercise-catalog-list')).not.toContainText('Жим штанги');
  await expect(page.locator('.exercise-catalog-list')).toContainText('Проверить оборудование');
  await page.getByRole('tab', { name: 'Все упражнения' }).click();
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(5);
  await page.getByRole('tab', { name: 'Доступное' }).click();
  await page.getByLabel('Поиск', { exact: true }).fill('Жим штанги');
  await expect(page.getByText('Ничего не найдено')).toBeVisible();
  await page.getByRole('button', { name: 'Показать все упражнения' }).click();
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(1);
  await page.getByRole('link', { name: 'Управлять профилями' }).click();
  await dialog.getByRole('button', { name: 'Изменить', exact: true }).click();
  await page.getByRole('button', { name: 'Удалить профиль' }).click();
  await page.getByRole('button', { name: 'Подтвердить удаление' }).click();
  await expect.poll(() => api.state().profiles.length).toBe(0);
  expect(api.state().active_profile_id).toBeNull();
  await expectNoHorizontalOverflow(page);
});

test('offline, API failure and conflict retain the draft until explicitly resolved', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const initial: State = {
    revision: 2,
    active_profile_id: homeId,
    profiles: [{ id: homeId, name: 'Дом', equipment_ids: ['dumbbell'] }],
  };
  const api = await setup(page, initial);
  await page.goto('/app?section=catalog');
  await page.getByRole('link', { name: 'Управлять профилями' }).click();
  const dialog = page.locator('.equipment-profiles__panel');
  await dialog.getByRole('button', { name: 'Изменить', exact: true }).click();
  const name = page.getByLabel('Название профиля');
  await name.fill('Мой черновик');
  await context.setOffline(true);
  await expect(
    page.getByText('Нет подключения. Изменения пока не сохранены на сервере.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled();
  await context.setOffline(false);
  api.failNextSave();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(page.getByText('Не удалось сохранить профиль')).toBeVisible();
  await expect(name).toHaveValue('Мой черновик');
  api.changeElsewhere({ id: homeId, name: 'Другое устройство', equipment_ids: ['bench'] });
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(page.getByText('Профили изменились на другом устройстве')).toBeVisible();
  await page.getByRole('button', { name: 'Загрузить актуальные данные' }).click();
  await expect(page.getByText('Сейчас на сервере: Другое устройство')).toBeVisible();
  await expect(name).toHaveValue('Мой черновик');
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect.poll(() => api.state().profiles[0]?.name).toBe('Мой черновик');
});

test('program picker filters without changing the program draft', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await setup(page, {
    revision: 1,
    active_profile_id: homeId,
    profiles: [{ id: homeId, name: 'Дом', equipment_ids: ['dumbbell', 'bench'] }],
  });
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await builder.getByLabel('Название', { exact: true }).fill('Мой черновик');
  await builder.locator('.copy-editor__exercise').first().click();
  await page
    .getByRole('dialog', { name: 'Параметры упражнения' })
    .getByRole('button', { name: 'Поиск упражнения' })
    .click();
  const picker = page.getByRole('dialog', { name: 'Выбор упражнения' });
  await expect(picker.locator('.exercise-picker__option')).toHaveCount(4);
  await expect(picker).toContainText('Проверить оборудование');
  await chooseProfile(page, /Без профиля/);
  await expect(picker.locator('.exercise-picker__option')).toHaveCount(5);
  await chooseProfile(page, /Дом/);
  await expect(picker.locator('.exercise-picker__option')).toHaveCount(4);
  await picker.getByRole('tab', { name: 'Все упражнения' }).click();
  await expect(picker.locator('.exercise-picker__option')).toHaveCount(5);
  await picker.getByRole('button', { name: 'Закрыть выбор упражнения' }).click();
  await expect(builder.getByLabel('Название', { exact: true })).toHaveValue('Мой черновик');
  await expectNoHorizontalOverflow(page);
});

test('empty and no profile remain explicit across mobile widths and keyboard switching', async ({
  page,
  context,
}) => {
  await setup(page, {
    revision: 1,
    active_profile_id: homeId,
    profiles: [
      { id: homeId, name: 'Дом', equipment_ids: ['dumbbell', 'bench'] },
      { id: '00000000-0000-4000-8000-000000000002', name: 'Поездка', equipment_ids: [] },
    ],
  });
  await page.goto('/app?section=catalog');
  await chooseProfile(page, /Поездка/);
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(3);
  await expect(page.locator('.exercise-catalog-list')).toContainText('Моё движение');
  await expect(page.locator('.exercise-catalog-list')).toContainText('Непроверенное движение');
  await context.setOffline(true);
  await expect(
    page.getByText('Нет подключения. Показано последнее загруженное состояние.'),
  ).toBeVisible();
  await context.setOffline(false);
  const available = page.getByRole('tab', { name: 'Доступное' });
  await available.focus();
  await available.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'Все упражнения' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(5);
  for (const width of [320, 360, 393, 430]) {
    await page.setViewportSize({ width, height: 852 });
    await expectNoHorizontalOverflow(page);
  }
  await chooseProfile(page, /Без профиля/);
  await expect(page.locator('.exercise-catalog-item')).toHaveCount(5);
  await expect(available).toHaveCount(0);
});

test('nested profile selection respects mocked TMA safe areas and Back', async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 852 });
  await installTelegramHarness(page, {
    platform: 'ios',
    colorScheme: 'dark',
    viewportHeight: 852,
    viewportStableHeight: 852,
    safeAreaInset: { top: 24, right: 0, bottom: 34, left: 0 },
  });
  await setup(page, {
    revision: 1,
    active_profile_id: homeId,
    profiles: [{ id: homeId, name: 'Дом', equipment_ids: ['dumbbell', 'bench'] }],
  });
  await page.goto('/app?section=programs&view=manage&start=create');
  const builder = page.locator('#program-builder');
  await builder.getByLabel('Название', { exact: true }).fill('Черновик Telegram');
  await builder.locator('.copy-editor__exercise').first().click();
  await page
    .getByRole('dialog', { name: 'Параметры упражнения' })
    .getByRole('button', { name: 'Поиск упражнения' })
    .click();
  const picker = page.getByRole('dialog', { name: 'Выбор упражнения' });
  await picker.getByRole('button', { name: 'Изменить профиль оборудования' }).click();
  const selector = page.getByRole('dialog', { name: 'Выбрать профиль' });
  await expect(selector).toBeVisible();
  const box = await selector.locator('.equipment-profile-dialog__panel').boundingBox();
  expect(box!.y).toBeGreaterThanOrEqual(24);
  expect(box!.y + box!.height).toBeLessThanOrEqual(852 - 34);
  await expectTouchTargets(selector.locator('button'));
  await new TelegramHarness(page).clickBack();
  await expect(selector).toHaveCount(0);
  await expect(picker).toBeVisible();
  await picker.getByRole('button', { name: 'Закрыть выбор упражнения' }).click();
  await expect(builder.getByLabel('Название', { exact: true })).toHaveValue('Черновик Telegram');
});

test.describe('PWA profile recovery', () => {
  test.use({ serviceWorkers: 'allow' });
  test('keeps unsaved changes offline and saves them after reconnect', async ({
    page,
    context,
  }) => {
    const api = await setup(page, {
      revision: 1,
      active_profile_id: homeId,
      profiles: [{ id: homeId, name: 'Дом', equipment_ids: ['dumbbell'] }],
    });
    await page.goto('/app?section=catalog&source=pwa');
    await page.waitForFunction(() => navigator.serviceWorker.ready.then(() => true));
    if (!(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))))
      await page.reload();
    await expect
      .poll(() => page.evaluate(() => navigator.serviceWorker.controller?.scriptURL ?? ''))
      .toContain('/sw.js');
    await page.getByRole('link', { name: 'Управлять профилями' }).click();
    await page
      .locator('.equipment-profiles__panel')
      .getByRole('button', { name: 'Изменить', exact: true })
      .click();
    await page.getByLabel('Название профиля').fill('Дом после восстановления сети');
    await context.setOffline(true);
    await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled();
    expect(api.state().revision).toBe(1);
    await context.setOffline(false);
    await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await expect.poll(() => api.state().profiles[0]?.name).toBe('Дом после восстановления сети');
  });
});
