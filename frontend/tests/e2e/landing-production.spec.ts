import { expect, test, type Page } from '@playwright/test';

const captureTask109 =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TASK_109 === '1';
const captureTelegramAccess =
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TELEGRAM_ACCESS === '1';
const captureEvidence =
  captureTask109 ||
  captureTelegramAccess ||
  (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.YFC_CAPTURE_TASK_73A === '1';
const screenshotRoot = captureTask109
  ? '../.artifacts/runtime/tests/landing/task-109'
  : captureTelegramAccess
    ? '../.artifacts/runtime/tests/landing/telegram-access'
    : '../.artifacts/runtime/tests/landing/owner-review';

async function openLanding(page: Page, theme: 'light' | 'dark') {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.evaluate((value) => localStorage.setItem('app-theme', value), theme);
  await page.reload({ waitUntil: 'domcontentloaded' });
}

async function expectNoHorizontalOverflow(page: Page, width: number) {
  expect(
    await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    })),
  ).toEqual({ content: width, viewport: width });
}

async function expectLandingReady(page: Page) {
  await expect(page.getByRole('heading', { level: 1, name: 'СИЛА В ДЕЙСТВИИ.' })).toBeVisible();
  await page.locator('.strength-scene').scrollIntoViewIfNeeded();
  for (const image of await page.locator('.strength-scene img').all()) {
    await expect(image).toHaveJSProperty('complete', true);
    expect(
      await image.evaluate((element) => (element as HTMLImageElement).naturalWidth),
    ).toBeGreaterThan(0);
    await image.evaluate((element) => (element as HTMLImageElement).decode());
  }
  await page.locator('h1').scrollIntoViewIfNeeded();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

async function loadAllProductProofs(page: Page) {
  for (const image of await page.locator('.landing-product-image img').all()) {
    await image.scrollIntoViewIfNeeded();
    await expect(image).toHaveJSProperty('complete', true);
    expect(
      await image.evaluate((element) => (element as HTMLImageElement).naturalWidth),
    ).toBeGreaterThan(0);
    await image.evaluate((element) => (element as HTMLImageElement).decode());
  }
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function settleForScreenshot(page: Page) {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.getSelection()?.removeAllRanges();
    window.scrollTo(0, 0);
  });
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
}

test('landing keeps the approved sports composition across themes and viewports', async ({
  page,
}, testInfo) => {
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark'] as const) {
    for (const viewport of [
      { width: 1440, height: 1000 },
      { width: 1280, height: 900 },
      { width: 1024, height: 900 },
      { width: 768, height: 900 },
      { width: 720, height: 900 },
      { width: 430, height: 932 },
      { width: 390, height: 844 },
      { width: 360, height: 800 },
    ]) {
      await page.setViewportSize(viewport);
      await openLanding(page, theme);
      await expectLandingReady(page);
      await expect(page.locator('html')).toHaveAttribute('data-color-scheme', theme);
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('.strength-scene img')).toHaveCount(2);
      await expect(page.locator('.strength-scene svg[data-icon="exercise"]')).toHaveCount(2);
      await expect(page.locator('.landing-energy-path')).toHaveCount(0);
      await expect(page.getByRole('link', { name: 'Начать', exact: true })).toHaveAttribute(
        'href',
        '/app',
      );
      await expect(
        page.locator('.landing-hero__actions').getByRole('link', { name: 'Попробовать демо' }),
      ).toHaveAttribute('href', '/demo?cabinet=1&scenario=self_training&section=today');
      await expect(page.locator('.strength-scene')).toContainText('Иллюстрация движения');
      await expect(page.locator('.landing-feature')).toHaveCount(2);
      await expect(page.locator('.landing-trainer')).toBeVisible();
      await expectNoHorizontalOverflow(page, viewport.width);
      const geometry = await page.evaluate(() => {
        const primary = document.querySelector<HTMLElement>(
          '.landing-hero__actions .landing-button',
        )!;
        const secondary = document.querySelector<HTMLElement>('.landing-button--secondary')!;
        const photo = document.querySelector<HTMLElement>('.strength-scene__photo')!;
        const record = document.querySelector<HTMLElement>('.strength-scene__record')!;
        return {
          buttonHeight: primary.getBoundingClientRect().height,
          primaryBottom: primary.getBoundingClientRect().bottom,
          radius: parseFloat(getComputedStyle(primary).borderRadius),
          secondaryBorder: parseFloat(getComputedStyle(secondary).borderTopWidth),
          photoBottom: photo.getBoundingClientRect().bottom,
          recordTop: record.getBoundingClientRect().top,
        };
      });
      expect(geometry.buttonHeight).toBeGreaterThanOrEqual(44);
      expect(geometry.primaryBottom).toBeLessThan(viewport.height);
      expect(geometry.radius).toBeGreaterThanOrEqual(8);
      expect(geometry.radius).toBeLessThanOrEqual(14);
      expect(geometry.secondaryBorder).toBeGreaterThanOrEqual(1);
      expect(geometry.recordTop).toBeGreaterThanOrEqual(geometry.photoBottom - 1);
      await page.screenshot({
        path: testInfo.outputPath(`landing-${viewport.width}-${theme}.png`),
      });
    }
  }
  expect(errors).toEqual([]);
});

test('landing hero fills the desktop first viewport without horizontal overflow', async ({
  page,
}, testInfo) => {
  await page.route('**/api/v1/public/articles*', (route) => route.fulfill({ json: [] }));
  await page.emulateMedia({ reducedMotion: 'reduce' });

  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 2560, height: 1440 },
  ]) {
    await page.setViewportSize(viewport);
    await openLanding(page, 'dark');
    await expect(page.locator('.landing-hero')).toBeVisible();
    await expect(page.locator('.landing-hero__image')).toHaveJSProperty('complete', true);
    await page
      .locator('.landing-hero__image')
      .evaluate((element) => (element as HTMLImageElement).decode());
    await page.evaluate(() => window.scrollTo(0, 0));

    const geometry = await page.evaluate(() => {
      const hero = document.querySelector<HTMLElement>('.landing-hero')!;
      const nextSection = hero.nextElementSibling as HTMLElement | null;
      const heroBounds = hero.getBoundingClientRect();
      const nextBounds = nextSection?.getBoundingClientRect();
      const ctaBounds = document
        .querySelector<HTMLElement>('.landing-hero__actions')!
        .getBoundingClientRect();
      const platformBounds = document
        .querySelector<HTMLElement>('.landing-hero__platform-note')!
        .getBoundingClientRect();
      return {
        heroBottom: heroBounds.bottom,
        nextTop: nextBounds?.top ?? null,
        ctaBottom: ctaBounds.bottom,
        platformBottom: platformBounds.bottom,
        viewportHeight: window.innerHeight,
        scrollTop: window.scrollY,
      };
    });

    expect(geometry.scrollTop).toBe(0);
    expect(geometry.heroBottom).toBeGreaterThanOrEqual(geometry.viewportHeight - 1);
    expect(geometry.nextTop).toBeGreaterThanOrEqual(geometry.viewportHeight - 1);
    expect(geometry.ctaBottom).toBeLessThanOrEqual(geometry.viewportHeight);
    expect(geometry.platformBottom).toBeLessThanOrEqual(geometry.viewportHeight);
    await expectNoHorizontalOverflow(page, viewport.width);
    if (viewport.width === 1920 || viewport.width === 2560) {
      await page.screenshot({
        path: testInfo.outputPath(`landing-${viewport.width}x${viewport.height}-hero.png`),
      });
    }
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page, 'dark');
  await expect(page.locator('.landing-hero')).toBeVisible();
  await expect(page.locator('.landing-hero__actions')).toBeVisible();
  await expect(page.locator('.landing-hero__platform-note')).toBeVisible();
  await expectNoHorizontalOverflow(page, 390);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath('landing-390x844-hero.png') });
});

test('landing secondary actions keep contrast tied to their section surface', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });

  const surfaceCases = [
    { selector: '.landing-feature--0 .landing-button', className: 'on-light' },
    { selector: '.landing-feature--1 .landing-button', className: 'on-dark' },
    {
      selector: '.landing-trainer__actions .landing-button--secondary',
      className: 'on-light',
    },
    { selector: '.landing-contact__actions .landing-button--secondary', className: 'on-dark' },
  ];

  for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
    await openLanding(page, theme);

    for (const item of surfaceCases) {
      const cta = page.locator(item.selector);
      await expect(cta).toHaveClass(new RegExp(`landing-button--secondary-${item.className}`));
      const metrics = await cta.evaluate((element) => {
        const parse = (color: string) => {
          const channels = (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
          if (channels.length !== 3) throw new Error(`Unsupported color: ${color}`);
          return channels;
        };
        const luminance = (color: string) => {
          const [red, green, blue] = parse(color).map((channel) => {
            const normalized = channel / 255;
            return normalized <= 0.03928
              ? normalized / 12.92
              : ((normalized + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * red! + 0.7152 * green! + 0.0722 * blue!;
        };
        const contrast = (foreground: string, background: string) => {
          const foregroundLuminance = luminance(foreground);
          const backgroundLuminance = luminance(background);
          return (
            (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
            (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
          );
        };
        const style = getComputedStyle(element);
        const icon = element.querySelector('.yfc-icon');
        const iconColor = icon ? getComputedStyle(icon).color : null;
        return {
          background: style.backgroundColor,
          border: style.borderTopColor,
          color: style.color,
          iconColor,
          textContrast: contrast(style.color, style.backgroundColor),
          borderContrast: contrast(style.borderTopColor, style.backgroundColor),
        };
      });
      expect(metrics.textContrast).toBeGreaterThanOrEqual(4.5);
      if (metrics.iconColor) expect(metrics.iconColor).toBe(metrics.color);
      expect(metrics.borderContrast).toBeGreaterThanOrEqual(3);

      await cta.focus();
      const focus = await cta.evaluate((element) => {
        const style = getComputedStyle(element);
        return { outlineStyle: style.outlineStyle, outlineWidth: parseFloat(style.outlineWidth) };
      });
      expect(focus.outlineStyle).not.toBe('none');
      expect(focus.outlineWidth).toBeGreaterThanOrEqual(2);

      await cta.hover();
      const hover = await cta.evaluate((element) => {
        const style = getComputedStyle(element);
        return { background: style.backgroundColor, color: style.color };
      });
      expect(hover.color).toBe(metrics.color);
      expect(hover.background).not.toBe('rgba(0, 0, 0, 0)');
    }

    const trainerButtons = await page
      .locator('.landing-trainer__actions .landing-button')
      .evaluateAll((elements) =>
        elements.map((element) => {
          const rect = element.getBoundingClientRect();
          return { bottom: rect.bottom, left: rect.left, right: rect.right, top: rect.top };
        }),
      );
    expect(trainerButtons).toHaveLength(2);
    const first = trainerButtons[0]!;
    const second = trainerButtons[1]!;
    const separated =
      Math.abs(first.top - second.top) < 1 ? second.left - first.right : second.top - first.bottom;
    expect(separated).toBeGreaterThanOrEqual(11);

    if (theme === 'dark') {
      await page.locator('.landing-feature--0').screenshot({
        path: testInfo.outputPath('desktop-dark-nutrition.png'),
      });
      await page.locator('.landing-trainer').screenshot({
        path: testInfo.outputPath('desktop-dark-trainer.png'),
      });
    } else {
      await page.locator('.landing-feature--1').screenshot({
        path: testInfo.outputPath('desktop-light-progress.png'),
      });
      await page.locator('.landing-contact').screenshot({
        path: testInfo.outputPath('desktop-light-final.png'),
      });
    }
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page, 'dark');
  await page.locator('.strength-scene').screenshot({
    path: testInfo.outputPath('mobile-dark-strength.png'),
  });
  await page.locator('.landing-trainer').screenshot({
    path: testInfo.outputPath('mobile-dark-trainer.png'),
  });
});

test('media failures preserve the story and reserve the scene layout', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.route('**/assets/marketing/**', (route) => route.abort());
  await openLanding(page, 'light');
  await expect(page.getByText('Фото не загрузилось. Все действия доступны.')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Начать', exact: true })).toHaveAttribute(
    'href',
    '/app',
  );
  const frame = page.locator('.strength-scene__photo');
  await frame.scrollIntoViewIfNeeded();
  const bounds = await frame.boundingBox();
  expect(bounds?.height).toBeGreaterThanOrEqual(260);
  expect(bounds?.width).toBeGreaterThan(400);
  await expect(page.locator('.strength-scene__record')).toBeVisible();
  await expectNoHorizontalOverflow(page, 1280);
});

test('keyboard, menu, FAQ and canonical public actions stay operable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openLanding(page, 'light');

  const skipLink = page.getByRole('link', { name: 'К содержимому' });
  await skipLink.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#landing-content')).toBeFocused();

  for (const telegramAction of [
    page.locator('.landing-hero__telegram-link'),
    page.locator('.landing-continuity__action'),
    page.locator('.landing-footer__telegram-app'),
  ]) {
    await telegramAction.focus();
    await expect(telegramAction).toBeFocused();
    expect(
      await telegramAction.evaluate((element) => {
        const style = getComputedStyle(element);
        return style.outlineStyle !== 'none' && Number.parseFloat(style.outlineWidth) >= 2;
      }),
    ).toBe(true);
  }

  const menu = page.getByRole('button', { name: 'Открыть меню' });
  await menu.click();
  await expect(page.getByRole('navigation', { name: 'Навигация по странице' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');

  await page.locator('#faq').scrollIntoViewIfNeeded();
  const question = page.getByText('Telegram обязателен?', { exact: true });
  await question.click();
  await expect(page.getByText(/доступны в браузере/i)).toBeVisible();

  const knowledgeDetails = page.locator('.landing-assurance__details > details').first();
  await knowledgeDetails.locator('summary').click();
  await expect(
    knowledgeDetails.getByRole('link', { name: 'Тренировки и программы' }),
  ).toBeVisible();

  const mobileReadability = await page.evaluate(() => {
    const linkSelectors = [
      '.landing-hero__telegram-link',
      '.landing-continuity__action',
      '.landing-feature a',
      '.landing-core__self-link',
      '.landing-assurance__details nav a',
      '.landing-footer nav a',
    ];
    const textSelectors = [
      '.landing-feature > div > p:not(.landing-kicker)',
      '.landing-trainer__copy > p:not(.landing-kicker)',
      '.landing-start__steps p',
      '.landing-faq-list details > p',
      '.landing-assurance__details details > div > p',
      '.landing-contact > div > p:not(.landing-kicker)',
      '.landing-footer__brand p',
      '.landing-footer__privacy p',
    ];
    const numberSelectors = [
      '.landing-core__feature-label > span',
      '.landing-start__steps small',
      '.landing-start__demo nav > a > span',
    ];
    return {
      linkHeights: linkSelectors.flatMap((selector) =>
        [...document.querySelectorAll<HTMLElement>(selector)].map(
          (element) => element.getBoundingClientRect().height,
        ),
      ),
      textSizes: textSelectors.flatMap((selector) =>
        [...document.querySelectorAll<HTMLElement>(selector)].map((element) =>
          Number.parseFloat(getComputedStyle(element).fontSize),
        ),
      ),
      numberSizes: numberSelectors.flatMap((selector) =>
        [...document.querySelectorAll<HTMLElement>(selector)].map((element) =>
          Number.parseFloat(getComputedStyle(element).fontSize),
        ),
      ),
    };
  });
  expect(mobileReadability.linkHeights.length).toBeGreaterThan(0);
  expect(Math.min(...mobileReadability.linkHeights)).toBeGreaterThanOrEqual(44);
  expect(Math.min(...mobileReadability.textSizes)).toBeGreaterThanOrEqual(13);
  expect(Math.min(...mobileReadability.numberSizes)).toBeGreaterThanOrEqual(15);

  await expect(page.locator('.landing-start__demo-cta')).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=self_training&section=today',
  );
  const demoScenarioLinks = page.locator('.landing-start__demo nav > a');
  await expect(demoScenarioLinks).toHaveCount(3);
  await expect(demoScenarioLinks.nth(0)).toContainText('Тренировка');
  await expect(demoScenarioLinks.nth(0)).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=self_training&section=today',
  );
  await expect(demoScenarioLinks.nth(1)).toContainText('Питание и прогресс');
  await expect(demoScenarioLinks.nth(1)).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=nutrition&section=nutrition',
  );
  await expect(demoScenarioLinks.nth(2)).toContainText('Работа тренера');
  await expect(demoScenarioLinks.nth(2)).toHaveAttribute(
    'href',
    '/demo?cabinet=1&scenario=trainer&section=trainer',
  );
  await page.getByRole('link', { name: 'Приватность и данные' }).click();
  await expect(page).toHaveURL(/#privacy$/);
  await expect(page.locator('#privacy')).toBeInViewport();
});

test('motion has an immediate reduced-motion final state', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(page, 'dark');
  await expectLandingReady(page);

  const motionState = await page.locator('.strength-scene').evaluate((element) => ({
    phase: element.getAttribute('data-phase'),
    animations: element
      .getAnimations({ subtree: true })
      .filter((animation) => animation.playState === 'running').length,
    clip: getComputedStyle(element.querySelector('.strength-scene__photo')!).clipPath,
  }));
  expect(motionState.phase).toBe('2');
  expect(motionState.animations).toBe(0);
  expect(motionState.clip).toBe('none');
  await expect(page.getByRole('link', { name: 'Начать', exact: true })).toBeInViewport();
});

test('captures the owner-review packet when requested', async ({ page, browser }) => {
  if (!captureEvidence) return;

  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const theme of ['light', 'dark'] as const) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await openLanding(page, theme);
    await expectLandingReady(page);
    await settleForScreenshot(page);
    await page.screenshot({ path: `${screenshotRoot}/desktop-1440-${theme}-hero.png` });
    if (captureTelegramAccess) {
      await page.locator('.landing-assurance__platform').screenshot({
        path: `${screenshotRoot}/desktop-1440-${theme}-telegram-platform.png`,
      });
      await page.locator('.landing-footer').screenshot({
        path: `${screenshotRoot}/desktop-1440-${theme}-footer.png`,
      });
    }
    await loadAllProductProofs(page);
    await page.locator('#product').screenshot({
      path: `${screenshotRoot}/desktop-1440-${theme}-product.png`,
    });
    await page.locator('.landing-trainer').screenshot({
      path: `${screenshotRoot}/desktop-1440-${theme}-trainer.png`,
    });
    if (captureTask109) {
      await page.locator('.landing-contact').screenshot({
        path: `${screenshotRoot}/desktop-1440-${theme}-final-cta.png`,
      });
    }
    await settleForScreenshot(page);
    await page.screenshot({
      path: `${screenshotRoot}/desktop-1440-${theme}-full.png`,
      fullPage: true,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await openLanding(page, theme);
    await expectLandingReady(page);
    await settleForScreenshot(page);
    await page.screenshot({ path: `${screenshotRoot}/mobile-390-${theme}-hero.png` });
    if (captureTelegramAccess) {
      await page.locator('.landing-assurance__platform').screenshot({
        path: `${screenshotRoot}/mobile-390-${theme}-telegram-platform.png`,
      });
      await page.locator('.landing-footer').screenshot({
        path: `${screenshotRoot}/mobile-390-${theme}-footer.png`,
      });
    }
    if (captureTask109) {
      await page.locator('.landing-hero').screenshot({
        path: `${screenshotRoot}/mobile-390-${theme}-hero-section.png`,
      });
    }
    await loadAllProductProofs(page);
    await page.addStyleTag({ content: '.public-shell__skip-link { display: none !important; }' });
    await page.locator('#product').screenshot({
      path: `${screenshotRoot}/mobile-390-${theme}-product.png`,
    });
    if (captureTask109) {
      await page.locator('.landing-contact').screenshot({
        path: `${screenshotRoot}/mobile-390-${theme}-final-cta.png`,
      });
    }
    await settleForScreenshot(page);
    await page.screenshot({
      path: `${screenshotRoot}/mobile-390-${theme}-full.png`,
      fullPage: true,
    });
  }

  const mobile360Context = await browser.newContext({
    viewport: { width: 360, height: 800 },
    deviceScaleFactor: 2,
  });
  const mobile360Page = await mobile360Context.newPage();
  await mobile360Page.emulateMedia({ reducedMotion: 'reduce' });
  await openLanding(mobile360Page, 'light');
  await expectLandingReady(mobile360Page);
  await expectNoHorizontalOverflow(mobile360Page, 360);
  await settleForScreenshot(mobile360Page);
  await mobile360Page.screenshot({
    path: `${screenshotRoot}/mobile-360-light-overflow-crop.png`,
  });
  await mobile360Context.close();
});
