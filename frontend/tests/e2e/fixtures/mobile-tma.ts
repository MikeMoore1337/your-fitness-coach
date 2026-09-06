import {
  expect,
  test as base,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test';

export const MOBILE_CONTEXTS = {
  compact: { width: 360, height: 800 },
  baseline: { width: 390, height: 844 },
  large: { width: 430, height: 932 },
} as const;

export type MobileContextName = keyof typeof MOBILE_CONTEXTS;

interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface TelegramHarnessOptions {
  initData?: string;
  version?: string;
  platform?: string;
  colorScheme?: 'light' | 'dark';
  viewportHeight?: number;
  viewportStableHeight?: number;
  safeAreaInset?: Insets;
  contentSafeAreaInset?: Insets;
}

export interface TelegramHarnessState {
  ready: number;
  expand: number;
  version: string;
  platform: string;
  active: boolean;
  colorScheme: 'light' | 'dark';
  viewportHeight: number;
  viewportStableHeight: number;
  backButton: { visible: boolean; shown: number; hidden: number; clicks: number };
  platformButtons: {
    main: { visible: boolean; shown: number; hidden: number };
    secondary: { visible: boolean; shown: number; hidden: number };
  };
  haptics: { impacts: string[]; notifications: string[] };
  shellColors: { header: string[]; background: string[]; bottomBar: string[] };
  downloads: Array<{ url: string; fileName: string }>;
  openedLinks: string[];
}

interface TelegramWindowBridge {
  theme(colorScheme: 'light' | 'dark'): void;
  viewport(viewportHeight: number, viewportStableHeight: number, isStateStable: boolean): void;
  safeArea(value: Insets): void;
  contentSafeArea(value: Insets): void;
  active(value: boolean): void;
  back(): void;
  state(): TelegramHarnessState;
}

export async function installTelegramHarness(
  page: Page,
  options: TelegramHarnessOptions = {},
): Promise<void> {
  const zeroInsets = { top: 0, right: 0, bottom: 0, left: 0 };
  const config = {
    initData:
      options.initData ?? 'query_id=test&user=%7B%22id%22%3A7%7D&auth_date=1700000000&hash=test',
    version: options.version ?? '8.0',
    platform: options.platform ?? 'android',
    colorScheme: options.colorScheme ?? 'light',
    viewportHeight: options.viewportHeight ?? MOBILE_CONTEXTS.baseline.height,
    viewportStableHeight: options.viewportStableHeight ?? MOBILE_CONTEXTS.baseline.height,
    safeAreaInset: options.safeAreaInset ?? zeroInsets,
    contentSafeAreaInset: options.contentSafeAreaInset ?? zeroInsets,
  };

  await page.addInitScript((initial) => {
    type EventHandler = (payload?: { isStateStable: boolean }) => void;
    const handlers = new Map<string, Set<EventHandler>>();
    const shellColors = {
      header: [] as string[],
      background: [] as string[],
      bottomBar: [] as string[],
    };
    const backState = { visible: false, shown: 0, hidden: 0, clicks: 0 };
    const mainButtonState = { visible: false, shown: 0, hidden: 0 };
    const secondaryButtonState = { visible: false, shown: 0, hidden: 0 };
    const haptics = { impacts: [] as string[], notifications: [] as string[] };
    const downloads: Array<{ url: string; fileName: string }> = [];
    const openedLinks: string[] = [];
    let ready = 0;
    let expand = 0;
    const emit = (event: string, payload?: { isStateStable: boolean }) => {
      handlers.get(event)?.forEach((handler) => handler(payload));
    };
    const platformButton = (
      event: 'mainButtonClicked' | 'secondaryButtonClicked',
      state: typeof mainButtonState,
    ) => ({
      get isVisible() {
        return state.visible;
      },
      show() {
        state.visible = true;
        state.shown += 1;
      },
      hide() {
        state.visible = false;
        state.hidden += 1;
      },
      onClick(callback: EventHandler) {
        const callbacks = handlers.get(event) ?? new Set<EventHandler>();
        callbacks.add(callback);
        handlers.set(event, callbacks);
      },
      offClick(callback: EventHandler) {
        handlers.get(event)?.delete(callback);
      },
      setText() {},
      enable() {},
      disable() {},
    });
    const telegram = {
      initData: initial.initData,
      initDataUnsafe: {},
      version: initial.version,
      platform: initial.platform,
      colorScheme: initial.colorScheme as 'light' | 'dark',
      themeParams: {},
      isActive: true,
      viewportHeight: initial.viewportHeight,
      viewportStableHeight: initial.viewportStableHeight,
      safeAreaInset: initial.safeAreaInset,
      contentSafeAreaInset: initial.contentSafeAreaInset,
      BackButton: {
        get isVisible() {
          return backState.visible;
        },
        show() {
          backState.visible = true;
          backState.shown += 1;
        },
        hide() {
          backState.visible = false;
          backState.hidden += 1;
        },
        onClick(callback: EventHandler) {
          const callbacks = handlers.get('backButtonClicked') ?? new Set<EventHandler>();
          callbacks.add(callback);
          handlers.set('backButtonClicked', callbacks);
        },
        offClick(callback: EventHandler) {
          handlers.get('backButtonClicked')?.delete(callback);
        },
      },
      MainButton: platformButton('mainButtonClicked', mainButtonState),
      SecondaryButton: platformButton('secondaryButtonClicked', secondaryButtonState),
      HapticFeedback: {
        impactOccurred(style: string) {
          haptics.impacts.push(style);
        },
        notificationOccurred(type: string) {
          haptics.notifications.push(type);
        },
      },
      ready() {
        ready += 1;
      },
      expand() {
        expand += 1;
      },
      downloadFile(
        params: { url: string; file_name: string },
        callback?: (accepted: boolean) => void,
      ) {
        downloads.push({ url: params.url, fileName: params.file_name });
        callback?.(true);
      },
      openLink(url: string) {
        openedLinks.push(url);
      },
      onEvent(event: string, callback: EventHandler) {
        const callbacks = handlers.get(event) ?? new Set<EventHandler>();
        callbacks.add(callback);
        handlers.set(event, callbacks);
      },
      offEvent(event: string, callback: EventHandler) {
        handlers.get(event)?.delete(callback);
      },
      setHeaderColor(color: string) {
        shellColors.header.push(color);
      },
      setBackgroundColor(color: string) {
        shellColors.background.push(color);
      },
      setBottomBarColor(color: string) {
        shellColors.bottomBar.push(color);
      },
    };

    Object.assign(window, {
      Telegram: { WebApp: telegram },
      __yfcTmaHarness: {
        theme(colorScheme: 'light' | 'dark') {
          telegram.colorScheme = colorScheme;
          telegram.themeParams = {};
          emit('themeChanged');
        },
        viewport(viewportHeight: number, viewportStableHeight: number, isStateStable: boolean) {
          telegram.viewportHeight = viewportHeight;
          telegram.viewportStableHeight = viewportStableHeight;
          emit('viewportChanged', { isStateStable });
        },
        safeArea(value: Insets) {
          telegram.safeAreaInset = value;
          emit('safeAreaChanged');
        },
        contentSafeArea(value: Insets) {
          telegram.contentSafeAreaInset = value;
          emit('contentSafeAreaChanged');
        },
        active(value: boolean) {
          telegram.isActive = value;
          emit(value ? 'activated' : 'deactivated');
        },
        back() {
          backState.clicks += 1;
          emit('backButtonClicked');
        },
        state() {
          return {
            ready,
            expand,
            version: telegram.version,
            platform: telegram.platform,
            active: telegram.isActive,
            colorScheme: telegram.colorScheme,
            viewportHeight: telegram.viewportHeight,
            viewportStableHeight: telegram.viewportStableHeight,
            backButton: { ...backState },
            platformButtons: {
              main: { ...mainButtonState },
              secondary: { ...secondaryButtonState },
            },
            haptics: {
              impacts: [...haptics.impacts],
              notifications: [...haptics.notifications],
            },
            shellColors: {
              header: [...shellColors.header],
              background: [...shellColors.background],
              bottomBar: [...shellColors.bottomBar],
            },
            downloads: [...downloads],
            openedLinks: [...openedLinks],
          };
        },
      },
    });
  }, config);
}

export class TelegramHarness {
  constructor(private readonly page: Page) {}

  async setTheme(colorScheme: 'light' | 'dark'): Promise<void> {
    await this.page.evaluate(
      (value) =>
        (
          window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
        ).__yfcTmaHarness.theme(value),
      colorScheme,
    );
  }

  async setViewport(
    viewportHeight: number,
    viewportStableHeight: number,
    isStateStable = true,
  ): Promise<void> {
    await this.page.evaluate(
      ([current, stable, isStable]) =>
        (
          window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
        ).__yfcTmaHarness.viewport(current, stable, isStable),
      [viewportHeight, viewportStableHeight, isStateStable] as const,
    );
  }

  async setSafeArea(value: Insets): Promise<void> {
    await this.page.evaluate(
      (insets) =>
        (
          window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
        ).__yfcTmaHarness.safeArea(insets),
      value,
    );
  }

  async setContentSafeArea(value: Insets): Promise<void> {
    await this.page.evaluate(
      (insets) =>
        (
          window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
        ).__yfcTmaHarness.contentSafeArea(insets),
      value,
    );
  }

  async setActive(active: boolean): Promise<void> {
    await this.page.evaluate(
      (value) =>
        (
          window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
        ).__yfcTmaHarness.active(value),
      active,
    );
  }

  async clickBack(): Promise<void> {
    await this.page.evaluate(() =>
      (
        window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
      ).__yfcTmaHarness.back(),
    );
  }

  async state(): Promise<TelegramHarnessState> {
    return this.page.evaluate(() =>
      (
        window as unknown as Window & { __yfcTmaHarness: TelegramWindowBridge }
      ).__yfcTmaHarness.state(),
    );
  }
}

export async function newMobilePage(
  browser: Browser,
  viewport: MobileContextName = 'baseline',
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    viewport: MOBILE_CONTEXTS[viewport],
    hasTouch: true,
    isMobile: true,
    reducedMotion: 'reduce',
  });
  return { context, page: await context.newPage() };
}

export async function setNetworkOffline(page: Page, offline: boolean): Promise<void> {
  await page.context().setOffline(offline);
  await page.evaluate((isOffline) => {
    window.dispatchEvent(new Event(isOffline ? 'offline' : 'online'));
  }, offline);
}

export async function setDocumentVisibility(
  page: Page,
  state: 'hidden' | 'visible',
): Promise<void> {
  await page.evaluate((visibilityState) => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibilityState,
    });
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => visibilityState === 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  }, state);
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    )
    .toBe(true);
}

export async function expectElementsWithinHorizontalViewport(
  page: Page,
  selector: string,
): Promise<void> {
  const boxes = await page.locator(selector).evaluateAll((elements) => {
    const viewportWidth = document.documentElement.clientWidth;
    return elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
        viewportWidth,
      };
    });
  });
  expect(boxes.length).toBeGreaterThan(0);
  expect(boxes.filter((box) => box.left < -1 || box.right > box.viewportWidth + 1)).toEqual([]);
}

export async function expectDockWithinViewport(page: Page, selector = '#appBottomNav') {
  const dock = page.locator(selector);
  const box = await dock.boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(-1);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width + 1);
  expect(box!.y).toBeGreaterThanOrEqual(-1);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height + 1);
}

export async function expectTouchTargets(locator: Locator, minimum = 44): Promise<void> {
  const boxes = await locator.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(boxes.length).toBeGreaterThan(0);
  for (const box of boxes) {
    expect(Math.min(box.width, box.height)).toBeGreaterThanOrEqual(minimum);
  }
}

export async function expectNoOverlap(first: Locator, second: Locator): Promise<void> {
  const firstBox = await first.boundingBox();
  const secondBox = await second.boundingBox();
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  const overlaps =
    firstBox!.x < secondBox!.x + secondBox!.width &&
    firstBox!.x + firstBox!.width > secondBox!.x &&
    firstBox!.y < secondBox!.y + secondBox!.height &&
    firstBox!.y + firstBox!.height > secondBox!.y;
  expect(overlaps).toBe(false);
}

export async function sharedSurfaceSignature(page: Page) {
  return page.evaluate(() => {
    const rootStyle = getComputedStyle(document.documentElement);
    const section = document.querySelector<HTMLElement>('.app-section');
    const navigationItems = Array.from(
      document.querySelectorAll<HTMLElement>(
        '.app-bottom-nav__primary > a, .app-bottom-nav__primary > button',
      ),
    ).map((element) => element.textContent?.trim());
    return {
      sectionClass: section?.className,
      navigationItems,
      tokens: ['--bg', '--card', '--text', '--accent', '--border'].map((token) =>
        rootStyle.getPropertyValue(token).trim(),
      ),
    };
  });
}

type MobileTmaFixtures = {
  mobilePage: Page;
  tmaPage: Page;
  tma: TelegramHarness;
};

export const test = base.extend<MobileTmaFixtures>({
  mobilePage: async ({ browser }, provide) => {
    const { context, page } = await newMobilePage(browser);
    await provide(page);
    await context.close();
  },
  tmaPage: async ({ browser }, provide) => {
    const { context, page } = await newMobilePage(browser);
    await installTelegramHarness(page);
    await provide(page);
    await context.close();
  },
  tma: async ({ tmaPage }, provide) => {
    await provide(new TelegramHarness(tmaPage));
  },
});

export { expect };
