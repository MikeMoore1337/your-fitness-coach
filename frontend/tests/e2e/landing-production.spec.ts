import { expect, test, type Page } from '@playwright/test';

async function openLanding(
  page: Page,
  path: string,
  theme: 'light' | 'dark',
  viewport: { width: number; height: number },
) {
  await page.setViewportSize(viewport);
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => localStorage.removeItem('app-theme'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('[data-landing-audience]')).toBeVisible();
  await expect(page.locator('.landing-hero__image')).toHaveJSProperty('complete', true);
  await expect(page.locator('.landing-hero__image')).toHaveAttribute('alt', /.+/);
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
}

async function expectNoHorizontalOverflow(page: Page, width: number) {
  await expect
    .poll(() =>
      page.evaluate(() => ({
        content: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      })),
    )
    .toEqual({ content: width, viewport: width });
}

async function expectDesktopHeaderNavigationToBeUnframed(page: Page) {
  const navigation = page.locator('.landing-v10-header-navigation');
  const styles = await navigation.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      borderTopWidth: computed.borderTopWidth,
      borderTopStyle: computed.borderTopStyle,
      background: computed.backgroundColor,
      boxShadow: computed.boxShadow,
      backdropFilter: computed.backdropFilter,
    };
  });
  expect(styles.borderTopWidth).toBe('0px');
  expect(styles.borderTopStyle).toBe('none');
  expect(styles.background).toBe('rgba(0, 0, 0, 0)');
  expect(styles.boxShadow).toBe('none');
  expect(styles.backdropFilter).toBe('none');
  await expect(
    navigation.locator('.landing-v10-header-audience .landing-v10-audience-switch__label'),
  ).toHaveCSS('color', 'rgba(255, 255, 255, 0.78)');
  await expect(
    navigation.locator('.landing-v10-header-audience .landing-v10-audience-switch'),
  ).toHaveAttribute('aria-label', 'Выбор аудитории');
}

async function expectAccessibleDarkButton(locator: ReturnType<Page['locator']>) {
  const contrast = await locator.evaluate((element) => {
    const parseRgb = (value: string) => {
      const channels = value.match(/[\d.]+/g)?.map(Number);
      if (!channels || channels.length < 3) return null;
      return channels.slice(0, 3).map((channel) => channel / 255);
    };
    const luminance = (rgb: number[]) =>
      rgb.reduce((sum, channel, index) => {
        const linear = channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
        return sum + linear * [0.2126, 0.7152, 0.0722][index]!;
      }, 0);
    const styles = getComputedStyle(element);
    const foreground = parseRgb(styles.color);
    const background = parseRgb(styles.backgroundColor);
    if (!foreground || !background) return 0;
    const foregroundLuminance = luminance(foreground);
    const backgroundLuminance = luminance(background);
    const lighter = Math.max(foregroundLuminance, backgroundLuminance);
    const darker = Math.min(foregroundLuminance, backgroundLuminance);
    return (lighter + 0.05) / (darker + 0.05);
  });
  expect(contrast).toBeGreaterThanOrEqual(4.5);
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await page.emulateMedia({ reducedMotion: 'reduce' });
});

test('approved athlete and trainer compositions stay audience-specific', async ({ page }) => {
  await openLanding(page, '/', 'dark', { width: 1440, height: 900 });

  await expect(page.getByRole('heading', { level: 1, name: 'СИЛА В ДЕЙСТВИИ.' })).toBeVisible();
  await expect(page.locator('[data-landing-audience="athlete"]')).toBeVisible();
  await expect(page.locator('.landing-v10-coach-promo')).toHaveCount(1);
  await expect(
    page.getByRole('heading', { name: /Вы тренер\? Знакомьтесь с Coach OS/ }),
  ).toHaveCount(1);
  await expect(page.getByText(/Не потерять важное/)).toHaveCount(0);
  await expect(
    page.locator(
      '.landing-v10-header-audience .landing-v10-audience-switch__link[data-audience="coach"]',
    ),
  ).toHaveAttribute('href', '/for-trainers');
  await expect(page.getByRole('link', { name: 'Попробовать демо тренировки' })).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=self_training&section=today',
  );
  await expect(page.getByRole('link', { name: 'Посмотреть пример тренировки' })).toHaveAttribute(
    'href',
    '#training',
  );
  await expect(page.getByRole('link', { name: 'Демо', exact: true })).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=self_training&section=today',
  );
  await expect(page.getByRole('link', { name: 'Вопросы' })).toHaveAttribute('href', '#faq');

  await openLanding(page, '/for-trainers', 'dark', { width: 1440, height: 900 });
  await expect(
    page.getByRole('heading', { level: 1, name: 'ВАШ МЕТОД В ДЕЙСТВИИ.' }),
  ).toBeVisible();
  await expect(page.locator('[data-landing-audience="coach"]')).toBeVisible();
  await expect(page.locator('[data-coach-chapter="coach-today"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="coach-today-preview"]')).toHaveCount(1);
  await expect(page.locator('.strength-scene')).toHaveCount(0);
  await expect(page.locator('.landing-v10-coach-promo')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Как работает Coach OS' })).toHaveAttribute(
    'href',
    '#coach-work',
  );
  await expect(page.getByRole('link', { name: 'Демо', exact: true })).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=trainer&section=trainer',
  );
  await expect(
    page.locator(
      '.landing-v10-header-audience .landing-v10-audience-switch__link[data-audience="athlete"]',
    ),
  ).toHaveAttribute('href', '/for-athletes');
});

test('public audience routes keep SEO and deep-link contracts', async ({ page }) => {
  await openLanding(page, '/', 'light', { width: 390, height: 844 });
  await expect(page).toHaveTitle(/тренировки, питание и прогресс/i);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'http://127.0.0.1:4173/',
  );

  await openLanding(page, '/for-athletes?utm_source=owner#coach-work', 'light', {
    width: 390,
    height: 844,
  });
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'http://127.0.0.1:4173/',
  );
  await expect(page.locator('[data-coach-chapter="coach-today"]')).toHaveCount(0);

  await openLanding(page, '/for-trainers', 'light', { width: 390, height: 844 });
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'index, follow');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'http://127.0.0.1:4173/for-trainers',
  );
  await expectNoHorizontalOverflow(page, 390);
});

test('glass header, CTAs and keyboard skip target remain usable on desktop and mobile', async ({
  page,
}, testInfo) => {
  for (const state of [
    { name: 'athlete-desktop-light', path: '/', theme: 'light' as const, width: 1440, height: 900 },
    { name: 'athlete-desktop-dark', path: '/', theme: 'dark' as const, width: 1440, height: 900 },
    {
      name: 'athlete-mobile-light',
      path: '/for-athletes',
      theme: 'light' as const,
      width: 390,
      height: 844,
    },
    {
      name: 'athlete-mobile-dark',
      path: '/for-athletes',
      theme: 'dark' as const,
      width: 390,
      height: 844,
    },
    {
      name: 'athlete-mobile-320-light',
      path: '/for-athletes',
      theme: 'light' as const,
      width: 320,
      height: 800,
    },
    {
      name: 'athlete-mobile-320-dark',
      path: '/for-athletes',
      theme: 'dark' as const,
      width: 320,
      height: 800,
    },
    {
      name: 'trainer-desktop-light',
      path: '/for-trainers',
      theme: 'light' as const,
      width: 1440,
      height: 900,
    },
    {
      name: 'trainer-desktop-dark',
      path: '/for-trainers',
      theme: 'dark' as const,
      width: 1440,
      height: 900,
    },
    {
      name: 'trainer-mobile-light',
      path: '/for-trainers',
      theme: 'light' as const,
      width: 390,
      height: 844,
    },
    {
      name: 'trainer-mobile-dark',
      path: '/for-trainers',
      theme: 'dark' as const,
      width: 390,
      height: 844,
    },
    {
      name: 'trainer-mobile-320-light',
      path: '/for-trainers',
      theme: 'light' as const,
      width: 320,
      height: 800,
    },
    {
      name: 'trainer-mobile-320-dark',
      path: '/for-trainers',
      theme: 'dark' as const,
      width: 320,
      height: 800,
    },
  ]) {
    await openLanding(page, state.path, state.theme, {
      width: state.width,
      height: state.height,
    });
    await expect(page.locator('.landing-header')).toHaveCSS('backdrop-filter', /blur/);
    await expect(page.getByRole('link', { name: 'К содержимому' })).toBeVisible();
    await expect(page.locator('.landing-button--compact')).toBeVisible();
    await expectNoHorizontalOverflow(page, state.width);

    const activeAudience = state.path === '/for-trainers' ? 'coach' : 'athlete';
    const audienceSwitch =
      state.width <= 680
        ? page.locator('.landing-v10-hero-audience .landing-v10-audience-switch')
        : page.locator('.landing-v10-header-audience .landing-v10-audience-switch');
    await expect(audienceSwitch).toBeVisible();
    await expect(audienceSwitch.locator('.landing-v10-audience-switch__label')).toHaveCount(
      state.width <= 680 ? 0 : 1,
    );
    if (state.width <= 680) {
      const brandBox = await page.locator('.landing-brand').boundingBox();
      const headerActionsBox = await page.locator('.landing-header__actions').boundingBox();
      expect(brandBox).not.toBeNull();
      expect(headerActionsBox).not.toBeNull();
      expect(brandBox!.y).toBeLessThan(headerActionsBox!.y + headerActionsBox!.height);
      expect(headerActionsBox!.y).toBeLessThan(brandBox!.y + brandBox!.height);
      for (const control of await page
        .locator('.landing-header__actions :is(.landing-button--compact, .landing-menu-toggle)')
        .all()) {
        expect((await control.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      }
    }
    for (const audience of ['athlete', 'coach'] as const) {
      const link = audienceSwitch.locator(
        `.landing-v10-audience-switch__link[data-audience="${audience}"]`,
      );
      await expect(link).toBeVisible();
      expect((await link.boundingBox())?.height).toBeGreaterThanOrEqual(44);
      const colors = await link.evaluate((element) => {
        const styles = getComputedStyle(element);
        return { color: styles.color, background: styles.backgroundColor };
      });
      expect(colors.color).toMatch(/^rgb/);
      if (audience === activeAudience) {
        expect(colors.background).toBe('rgb(182, 242, 56)');
      }
    }

    const navigation = page.getByRole('navigation', { name: 'Навигация по странице' });
    if (state.width <= 680) {
      const menuButton = page.getByRole('button', { name: 'Открыть меню' });
      await expect(menuButton).toBeVisible();
      await expect(navigation).toBeHidden();
      await menuButton.click();
      await expect(page.getByRole('button', { name: 'Закрыть меню' })).toBeVisible();
      await expect(navigation).toBeVisible();
      await expect(navigation.getByRole('link', { name: 'Продукт' })).toBeFocused();
      const menuAudience = page.locator(
        '.landing-v10-mobile-menu-controls .landing-v10-audience-switch',
      );
      await expect(menuAudience).toBeVisible();
      await expect(menuAudience.locator('.landing-v10-audience-switch__label')).toHaveCount(0);
      const menuTheme = page.locator('.app-theme-toggle--nav');
      await expect(menuTheme).toBeVisible();
      await page.keyboard.press('Shift+Tab');
      await expect(menuTheme).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(navigation.getByRole('link', { name: 'Продукт' })).toBeFocused();
      const themeBefore = await page.locator('html').getAttribute('data-color-scheme');
      await menuTheme.click();
      await expect(page.locator('html')).toHaveAttribute(
        'data-color-scheme',
        themeBefore === 'dark' ? 'light' : 'dark',
      );
      await menuTheme.click();
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', themeBefore!);
      await page.screenshot({
        path: testInfo.outputPath(`${state.name}-menu-open.png`),
        fullPage: false,
      });
    } else {
      await expect(navigation).toBeVisible();
      await expectDesktopHeaderNavigationToBeUnframed(page);
    }
    await expect(navigation.getByRole('link', { name: 'Продукт' })).toHaveAttribute(
      'href',
      '#product',
    );
    await expect(navigation.getByRole('link', { name: 'Демо' })).toHaveAttribute(
      'href',
      activeAudience === 'athlete'
        ? '/demo?cabinet=1&scenario=self_training&section=today'
        : '/demo?cabinet=1&scenario=trainer&section=trainer',
    );
    await expect(navigation.getByRole('link', { name: 'Вопросы' })).toHaveAttribute('href', '#faq');
    if (state.width <= 680) {
      await page.getByRole('button', { name: 'Закрыть меню' }).click();
      await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeFocused();
    }

    const skipLink = page.getByRole('link', { name: 'К содержимому' });
    await skipLink.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#landing-v10-content')).toBeFocused();

    if (activeAudience === 'athlete') {
      const athleteDemo = page.getByRole('link', {
        name: 'Попробовать демо тренировки',
        exact: true,
      });
      await expect(athleteDemo).toHaveAttribute(
        'href',
        '/demo?cabinet=1&scenario=self_training&section=today',
      );
      await expectAccessibleDarkButton(athleteDemo);
      await expect(page.getByRole('link', { name: 'Возможности для тренера' })).toHaveAttribute(
        'href',
        '/for-trainers',
      );
      await expect(
        page.getByRole('link', { name: 'Посмотреть пример тренировки' }),
      ).toHaveAttribute('href', '#training');
      if (state.width <= 680) {
        const heroSwitchBox = await audienceSwitch.boundingBox();
        const heroActionsBox = await page.locator('.landing-hero__actions').boundingBox();
        expect(heroSwitchBox).not.toBeNull();
        expect(heroActionsBox).not.toBeNull();
        expect(heroSwitchBox!.y + heroSwitchBox!.height).toBeLessThan(heroActionsBox!.y);
      }
      await expect(page.getByRole('link', { name: 'Посмотреть пример тренировки' })).toHaveCSS(
        'backdrop-filter',
        /blur/,
      );
      await expectAccessibleDarkButton(
        page.getByRole('link', { name: 'Посмотреть пример тренировки' }),
      );
    } else if (state.path === '/for-trainers') {
      await expect(page.getByRole('link', { name: 'Начать как тренер' }).first()).toHaveAttribute(
        'href',
        '/login?next=%2Fapp%3Ftrainer_intent%3D1',
      );
      const trainerDemo = page.getByRole('link', { name: 'Попробовать демо для тренера' }).first();
      await expect(trainerDemo).toHaveAttribute(
        'href',
        '/demo?cabinet=1&scenario=trainer&section=trainer',
      );
      await expectAccessibleDarkButton(trainerDemo);
      await expect(page.getByRole('link', { name: 'Как работает Coach OS' })).toHaveAttribute(
        'href',
        '#coach-work',
      );
      await expect(page.getByRole('link', { name: 'Как работает Coach OS' })).toHaveCSS(
        'backdrop-filter',
        /blur/,
      );
      await expectAccessibleDarkButton(page.getByRole('link', { name: 'Как работает Coach OS' }));
    }

    if (
      state.name.includes('-desktop-') ||
      state.name === 'athlete-mobile-dark' ||
      state.name === 'athlete-mobile-320-light' ||
      state.name === 'trainer-mobile-320-dark'
    ) {
      await page.locator('.landing-header').screenshot({
        path: testInfo.outputPath(`${state.name}-header.png`),
      });
    }

    await page.screenshot({
      path: testInfo.outputPath(`${state.name}.png`),
      fullPage: false,
    });
  }
});

test('responsive header contract holds across required widths and themes', async ({ page }) => {
  for (const width of [768, 1280, 360, 375, 430]) {
    for (const theme of ['light', 'dark'] as const) {
      for (const path of ['/', '/for-trainers']) {
        await openLanding(page, path, theme, { width, height: width <= 680 ? 800 : 900 });
        await expectNoHorizontalOverflow(page, width);

        const isMobile = width <= 680;
        const audienceSwitch = page.locator(
          isMobile
            ? '.landing-v10-hero-audience .landing-v10-audience-switch'
            : '.landing-v10-header-audience .landing-v10-audience-switch',
        );
        await expect(audienceSwitch).toBeVisible();
        await expect(audienceSwitch.locator('.landing-v10-audience-switch__label')).toHaveCount(
          isMobile ? 0 : 1,
        );

        const navigation = page.getByRole('navigation', { name: 'Навигация по странице' });
        if (isMobile) {
          await expect(page.getByRole('button', { name: 'Открыть меню' })).toBeVisible();
          await page.getByRole('button', { name: 'Открыть меню' }).click();
          await expect(navigation).toBeVisible();
          await expect(
            page.locator('.landing-v10-mobile-menu-controls .app-theme-toggle--nav'),
          ).toBeVisible();
          await page.getByRole('button', { name: 'Закрыть меню' }).click();
        } else {
          await expect(navigation).toBeVisible();
          await expectDesktopHeaderNavigationToBeUnframed(page);
          await expect(page.getByRole('link', { name: 'Войти' })).toBeVisible();
        }
      }
    }
  }
});

test('audience switching preserves campaign context and browser history', async ({ page }) => {
  await openLanding(page, '/for-athletes?utm_campaign=v10#coach-work', 'dark', {
    width: 390,
    height: 844,
  });
  await page
    .locator('.landing-v10-hero-audience .landing-v10-audience-switch__link[data-audience="coach"]')
    .click();
  await expect(page).toHaveURL('/for-trainers?utm_campaign=v10#coach-work');
  await expect(page.locator('[data-coach-chapter="coach-today"]')).toBeVisible();
  await expect(page.locator('[data-coach-chapter="coach-today"]')).toBeInViewport();
  await page.goBack();
  await expect(page).toHaveURL('/for-athletes?utm_campaign=v10#coach-work');
  await expect(page.locator('[data-coach-chapter="coach-today"]')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(300);
});
