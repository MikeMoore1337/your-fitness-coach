import { expect, test, type Page } from '@playwright/test';

const configuredProviders = ['telegram', 'google', 'yandex', 'vk'];

type MockAuthOptions = {
  authenticated?: boolean;
  providers?: string[];
  initialUser?: ReturnType<typeof userPayload>;
  telegramUser?: ReturnType<typeof userPayload>;
  rejectTelegramInit?: boolean;
};

type MockAuthCalls = {
  refresh: number;
  telegramInit: number;
  meAuthorization: string[];
  oauthStarts: string[];
};

function userPayload() {
  return {
    id: 17,
    telegram_user_id: 7017,
    username: 'browser_user',
    first_name: 'Браузер',
    is_coach: false,
    is_admin: false,
    has_active_program: false,
    has_workout_history: false,
    auth_providers: ['telegram', 'google'],
    profile: { full_name: 'Тестовый пользователь', timezone: 'Europe/Moscow', kbju: null },
    trainer: null,
  };
}

async function mockAuthApi(
  page: Page,
  {
    authenticated = false,
    providers = configuredProviders,
    initialUser = userPayload(),
    telegramUser = userPayload(),
    rejectTelegramInit = false,
  }: MockAuthOptions = {},
): Promise<MockAuthCalls> {
  let hasSession = authenticated;
  let activeUser = initialUser;
  const calls: MockAuthCalls = {
    refresh: 0,
    telegramInit: 0,
    meAuthorization: [],
    oauthStarts: [],
  };
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/public/config')) {
      return route.fulfill({
        json: {
          app_env: 'prod',
          enable_dev_auth: false,
          enable_web_auth: providers.length > 0,
          enable_email_auth: false,
          telegram_bot_username: 'fitness_bot',
          oauth_providers: providers,
        },
      });
    }
    if (path.endsWith('/auth/refresh')) {
      calls.refresh += 1;
      return hasSession
        ? route.fulfill({ json: { access_token: 'refreshed-token' } })
        : route.fulfill({ status: 401, json: { detail: 'Сессия отсутствует' } });
    }
    if (path.includes('/auth/oauth/') && path.endsWith('/start')) {
      calls.oauthStarts.push(request.url());
      return route.fulfill({ status: 204 });
    }
    if (path.endsWith('/auth/telegram/init')) {
      calls.telegramInit += 1;
      if (rejectTelegramInit) {
        return route.fulfill({ status: 401, json: { detail: 'Telegram initData истекли' } });
      }
      hasSession = true;
      activeUser = telegramUser;
      return route.fulfill({ json: { access_token: 'telegram-token' } });
    }
    if (path.endsWith('/me')) {
      calls.meAuthorization.push(request.headers().authorization ?? '');
      return hasSession
        ? route.fulfill({ json: activeUser })
        : route.fulfill({ status: 401, json: { detail: 'Требуется вход' } });
    }
    if (path.endsWith('/workouts/today')) {
      return route.fulfill({ status: 404, json: { detail: 'На сегодня тренировка не назначена' } });
    }
    if (path.endsWith('/workouts/progress/summary')) {
      return route.fulfill({
        json: {
          user_id: 17,
          period_days: 30,
          period_start: '2026-07-22',
          period_end: '2026-08-20',
          training: { last_completed_workout_on: null, next_workout: null },
          nutrition: { visible: false },
          body: { latest_measurement: null, trends: [], priority: null, guidance: {} },
          adherence: {
            formula_version: 'adherence-v1',
            overall_percent: null,
            included_components: [],
            workouts: {},
            cardio: {},
            calories: {},
            protein: {},
          },
          data_sufficiency: {},
        },
      });
    }
    if (path.endsWith('/nutrition/diary')) {
      return route.fulfill({
        json: {
          diary_date: '2026-08-20',
          timezone: 'Europe/Moscow',
          meals: [],
          totals: {
            energy_kcal: '0',
            protein_g: '0',
            fat_g: '0',
            carbs_g: '0',
            fiber_g: null,
          },
          targets: null,
          remaining: null,
        },
      });
    }
    if (path.endsWith('/workouts/progress')) {
      return route.fulfill({
        json: {
          workouts_total: 0,
          workouts_completed: 0,
          workouts_skipped: 0,
          workouts_missed: 0,
          adherence_percent: 0,
          current_streak: 0,
          weight_change_kg: null,
          weights: [],
          weekly_volume: [],
          personal_records: [],
        },
      });
    }
    if (
      path.endsWith('/workouts/schedule') ||
      path.endsWith('/workouts/history') ||
      path.endsWith('/workouts/week')
    ) {
      return route.fulfill({ json: [] });
    }
    if (path.endsWith('/workouts/history/summary')) {
      return route.fulfill({ json: { workouts_completed: 0, completed_sets: 0, volume_kg: 0 } });
    }
    return route.fulfill({ json: [] });
  });
  return calls;
}

test('Landing ведёт на canonical Login, а protected route сохраняет safe next', async ({
  page,
}) => {
  await mockAuthApi(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'Войти' }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator('#login-title .login-title--desktop')).toBeVisible();
  await expect(page.locator('#login-title')).toContainText('Вернитесь к своему плану.');

  await page.goto('/coach');
  await expect(page).toHaveURL(/\/login\?next=%2Fcoach$/);
  await expect(page.getByRole('link', { name: 'Продолжить с Google' })).toHaveAttribute(
    'href',
    '/api/v1/auth/oauth/google/start?next=%2Fcoach',
  );
});

test('Login использует surface-aware logo и не дублирует Войти в mobile header', async ({
  page,
}) => {
  await mockAuthApi(page);
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/login');

  await expect(page.locator('.login-continuation-brand .yfc-lockup__mark')).toHaveAttribute(
    'src',
    '/assets/brand/yfc-mark-dark.svg',
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('link', { name: 'Войти', exact: true })).toHaveCount(0);
  await expect(page.locator('.public-shell__header .yfc-lockup__wordmark')).toBeVisible();
  await expect(page.locator('.public-shell__header .yfc-lockup__wordmark')).toContainText(
    'Your FitnessCoach',
  );
});

test('Login сохраняет фирменные provider icons во всех темах и viewport', async ({ page }) => {
  await mockAuthApi(page);
  const providerIcons = [
    ['telegram', 'rgb(34, 158, 217)'],
    ['google', 'rgb(255, 255, 255)'],
    ['yandex', 'rgb(252, 63, 29)'],
    ['vk', 'rgb(0, 119, 255)'],
  ] as const;

  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto('/login');

      if (viewport.width >= 1024) {
        await expect(page.locator('.oauth-auth')).toHaveCSS('width', '300px');
      }

      for (const [provider, backgroundColor] of providerIcons) {
        const icon = page.locator(`.oauth-button--${provider} .oauth-button__icon`);
        const action = page.locator(`.oauth-button--${provider}`);
        await expect(icon).toBeVisible();
        await expect(icon).toHaveCSS('width', '28px');
        await expect(icon).toHaveCSS('height', '28px');
        await expect(icon).toHaveCSS('background-color', backgroundColor);
        await expect(action).toHaveCSS('white-space', 'nowrap');
        expect(await action.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
          true,
        );
      }
    }
  }
});

test('Login показывает только configured providers и контролируемую OAuth ошибку', async ({
  page,
}) => {
  await mockAuthApi(page, { providers: ['google', 'vk'] });
  await page.goto('/login?next=%2Fadmin&auth_error=denied&code=secret-code');

  await expect(page.getByText('Вход отменён')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Продолжить с Google' })).toHaveAttribute(
    'href',
    '/api/v1/auth/oauth/google/start?next=%2Fadmin',
  );
  await expect(page.getByRole('link', { name: 'Войти с VK ID' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Войти через Telegram' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Войти с Яндекс ID' })).toHaveCount(0);
  await expect(page.getByText('secret-code')).toHaveCount(0);
});

test('Telegram fallback сохраняет контраст, когда browser providers недоступны', async ({
  page,
}) => {
  await mockAuthApi(page, { providers: [] });
  await page.goto('/login');

  const fallback = page.getByRole('link', { name: 'Открыть в Telegram' });
  await expect(fallback).toBeVisible();
  await expect(fallback).toHaveCSS('min-height', '48px');
  await expect(fallback).toHaveCSS('background-color', 'rgb(240, 240, 240)');
  await expect(fallback).toHaveCSS('color', 'rgb(21, 21, 21)');
});

test('Повторить сохраняет контраст и единый hover с provider-кнопками', async ({ page }) => {
  await mockAuthApi(page, { providers: ['google'] });

  for (const scheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
    await page.goto('/login?auth_error=provider_failure');

    const retry = page.getByRole('link', { name: 'Повторить' });
    const provider = page.getByRole('link', { name: 'Продолжить с Google' });
    await retry.hover();
    const retryStyles = await retry.evaluate((element) => {
      const styles = getComputedStyle(element);
      return {
        backgroundColor: styles.backgroundColor,
        borderColor: styles.borderColor,
        color: styles.color,
        transform: styles.transform,
      };
    });
    await provider.hover();
    const providerStyles = await provider.evaluate((element) => {
      const styles = getComputedStyle(element);
      return {
        backgroundColor: styles.backgroundColor,
        borderColor: styles.borderColor,
        color: styles.color,
        transform: styles.transform,
      };
    });

    expect(retryStyles).toEqual(providerStyles);
    expect(retryStyles.backgroundColor).toBe(
      scheme === 'light' ? 'rgb(240, 240, 240)' : 'rgb(27, 31, 31)',
    );
    expect(retryStyles.color).toBe(scheme === 'light' ? 'rgb(21, 21, 21)' : 'rgb(245, 245, 245)');
  }
});

test('OAuth invalid_state retry starts a fresh provider flow without reload loop', async ({
  page,
}) => {
  const calls = await mockAuthApi(page, { providers: ['google'] });
  await page.goto(
    '/login?next=%2Fcoach&auth_error=invalid_state&oauth_provider=google&code=secret-code',
  );

  const retry = page.getByRole('link', { name: 'Повторить вход через Google' });
  await expect(retry).toHaveAttribute('href', '/api/v1/auth/oauth/google/start?next=%2Fcoach');
  await retry.click();

  expect(calls.oauthStarts).toHaveLength(1);
  const oauthStart = calls.oauthStarts[0];
  if (!oauthStart) throw new Error('OAuth start request was not captured');
  expect(new URL(oauthStart).pathname).toBe('/api/v1/auth/oauth/google/start');
  expect(oauthStart).toContain('next=%2Fcoach');
  expect(oauthStart).not.toContain('secret-code');
});

test('already authenticated Login возвращает в safe destination', async ({ page }) => {
  await mockAuthApi(page, { authenticated: true });
  await page.goto('/login?next=%2Fapp');

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
});

test('valid Telegram launch authenticates automatically without browser Login', async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: 'signed-init-data',
        initDataUnsafe: {},
        colorScheme: 'dark',
        ready() {},
        expand() {},
        BackButton: {
          show() {},
          hide() {},
          onClick() {},
          offClick() {},
        },
      },
    };
  });
  await mockAuthApi(page);
  await page.goto('/app?tgWebAppPlatform=android');

  await expect(page).toHaveURL(/\/app\?tgWebAppPlatform=android$/);
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Продолжить в Your Fitness Coach' })).toHaveCount(
    0,
  );
});

test('Telegram launch replaces a stale browser identity before loading current user', async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('fit_access_token', 'web-token');
    window.Telegram = {
      WebApp: {
        initData: 'signed-init-data-for-telegram-user',
        initDataUnsafe: {},
        colorScheme: 'dark',
        ready() {},
        expand() {},
        BackButton: {
          show() {},
          hide() {},
          onClick() {},
          offClick() {},
        },
      },
    };
  });
  const calls = await mockAuthApi(page, {
    authenticated: true,
    initialUser: { ...userPayload(), id: 18, first_name: 'Web A' },
    telegramUser: {
      ...userPayload(),
      id: 19,
      telegram_user_id: 7019,
      first_name: 'Telegram B',
    },
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?tgWebAppPlatform=android');

  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
  expect(calls.telegramInit).toBe(1);
  expect(calls.refresh).toBe(0);
  expect(calls.meAuthorization).toEqual(['Bearer telegram-token']);
});

test('invalid Telegram initData does not expose the stale browser identity', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('fit_access_token', 'web-token');
    window.Telegram = {
      WebApp: {
        initData: 'expired-init-data',
        initDataUnsafe: {},
        colorScheme: 'dark',
        ready() {},
        expand() {},
        BackButton: {
          show() {},
          hide() {},
          onClick() {},
          offClick() {},
        },
      },
    };
  });
  const calls = await mockAuthApi(page, { authenticated: true, rejectTelegramInit: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app?tgWebAppPlatform=android');

  await expect(page.getByRole('heading', { name: 'Не удалось подтвердить вход' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Основная навигация' })).toHaveCount(0);
  expect(calls.telegramInit).toBe(1);
  expect(calls.refresh).toBe(0);
  expect(calls.meAuthorization).toEqual([]);
});

test('linking callback показывает success и conflict без raw данных', async ({ page }) => {
  await mockAuthApi(page, { authenticated: true });
  await page.goto('/app?auth_linked=google');
  await expect(
    page.getByRole('status').filter({ hasText: 'Google привязан к аккаунту' }),
  ).toBeVisible();

  await page.goto('/app?auth_error=conflict&identity=provider-secret');
  await expect(page.getByRole('alert')).toContainText(
    'Этот способ входа уже привязан к другому аккаунту',
  );
  await expect(page.getByText('provider-secret')).toHaveCount(0);
});

test('Login адаптивен, доступен с клавиатуры и уважает reduced motion', async ({ browser }) => {
  for (const width of [2560, 1440, 1280, 1024, 768, 390, 360]) {
    const context = await browser.newContext({
      viewport: { width, height: width < 768 ? 844 : 900 },
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    try {
      await mockAuthApi(page);
      await page.goto('/login?next=%2Fapp');
      const title = page.locator('#login-title');
      await expect(title).toBeVisible();
      await expect(
        title.locator(width >= 1024 ? '.login-title--desktop' : '.login-title--mobile'),
      ).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);

      const themeControl = page.getByRole('button', { name: /Включить .* тему/ });
      await expect(themeControl).toBeHidden();
      await expect(page.getByRole('combobox')).toHaveCount(0);

      const google = page.getByRole('link', { name: 'Продолжить с Google' });
      await expect(google).toHaveCSS('border-radius', '14px');
      const googleBox = await google.boundingBox();
      expect(googleBox).not.toBeNull();

      if (width >= 1024) {
        const [layoutBox, introBox, cardBox, titleStyles] = await Promise.all([
          page.locator('.login-layout').boundingBox(),
          page.locator('.login-intro').boundingBox(),
          page.locator('.login-card').boundingBox(),
          title.evaluate((element) => {
            const styles = getComputedStyle(element);
            return { fontSize: styles.fontSize, whiteSpace: styles.whiteSpace };
          }),
        ]);
        expect(layoutBox).not.toBeNull();
        expect(introBox).not.toBeNull();
        expect(cardBox).not.toBeNull();
        const expectedLayoutWidth = Math.min(width - 48, 1180);
        expect(layoutBox!.width).toBeCloseTo(expectedLayoutWidth, 0);
        expect(layoutBox!.x).toBeCloseTo((width - expectedLayoutWidth) / 2, 0);
        expect(introBox!.width / cardBox!.width).toBeCloseTo(1.04 / 0.96, 2);
        expect(introBox!.width + cardBox!.width).toBeCloseTo(layoutBox!.width, 0);
        expect(titleStyles).toEqual({ fontSize: '35px', whiteSpace: 'nowrap' });
        expect(googleBox!.width).toBeCloseTo(300, 0);
      } else {
        await expect(page.locator('.login-title--desktop')).toBeHidden();
        await expect(page.locator('.login-title--mobile')).toBeVisible();
        expect(googleBox!.height).toBeGreaterThanOrEqual(48);
      }

      await google.focus();
      await expect(google).toBeFocused();
      const transitionDuration = await google.evaluate((element) =>
        Number.parseFloat(getComputedStyle(element).transitionDuration),
      );
      expect(transitionDuration).toBeLessThanOrEqual(0.001);
    } finally {
      await context.close();
    }
  }
});
