import { expect, test, type Locator, type Page } from '@playwright/test';
import { installTelegramHarness } from './fixtures/mobile-tma';
import { installPlatformApi } from './fixtures/platform-api';
import { progressOverview } from './fixtures/locators';

const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
const captureVisualImpactFix = env?.YFC_CAPTURE_PULSE_VISUAL_IMPACT === '1';
const capture = env?.YFC_CAPTURE_TASK_75C === '1' || captureVisualImpactFix;
const screenshotRoot = captureVisualImpactFix
  ? '../.artifacts/runtime/tests/screenshots/bug-20260828-01-pulse-visual-impact/review'
  : '../.artifacts/runtime/tests/screenshots/task-75c/final';

interface PulseLabState {
  cls: number;
  frameGaps: number[];
  longTasks: number[];
  recording: boolean;
}

type PulseLabWindow = typeof window & {
  __pulseLab?: PulseLabState;
  __yfcTmaHarness?: {
    contentSafeArea(value: { top: number; right: number; bottom: number; left: number }): void;
    safeArea(value: { top: number; right: number; bottom: number; left: number }): void;
  };
};

async function expectNoHorizontalOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
}

async function expectNoOverlap(first: Locator, second: Locator) {
  const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  const overlaps = !(
    firstBox!.x + firstBox!.width <= secondBox!.x ||
    secondBox!.x + secondBox!.width <= firstBox!.x ||
    firstBox!.y + firstBox!.height <= secondBox!.y ||
    secondBox!.y + secondBox!.height <= firstBox!.y
  );
  expect(overlaps).toBe(false);
}

async function completeWorkout(page: Page) {
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await page.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
  await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();
  return page.locator('.workout-completion');
}

test('current action and floating dock preserve the shared navigation contract', async ({
  page,
}) => {
  await installPlatformApi(page, {
    browserSession: true,
    workoutStatus: 'planned',
    cardioState: 'planned',
  });

  for (const viewport of [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/app?section=today');
    const action = page.getByRole('button', { name: 'Начать тренировку' });
    const dock = page.locator('#appBottomNav');
    await expect(action).toBeVisible();
    await expect(page.locator('.ui-semantic-artwork')).toHaveCount(0);
    await expect(page.locator('.today-workout-spotlight')).toHaveCSS('background-image', 'none');
    await expect(dock).toHaveCSS('position', 'fixed');
    await expect(dock).toHaveCSS('border-radius', '12px');
    await expectNoOverlap(action, dock);
    await expectNoHorizontalOverflow(page);

    const geometry = await dock.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const targets = Array.from(
        element.querySelectorAll<HTMLElement>(
          '.app-bottom-nav__primary > a, .app-bottom-nav__primary > button',
        ),
      ).map((target) => {
        const targetBox = target.getBoundingClientRect();
        return { height: targetBox.height, width: targetBox.width };
      });
      return {
        bottomGap: window.innerHeight - box.bottom,
        left: box.left,
        rightGap: window.innerWidth - box.right,
        targets,
      };
    });
    expect(geometry.left).toBeGreaterThanOrEqual(8);
    expect(geometry.rightGap).toBeGreaterThanOrEqual(8);
    expect(geometry.bottomGap).toBeGreaterThanOrEqual(8);
    expect(Math.min(...geometry.targets.map((target) => target.height))).toBeGreaterThanOrEqual(44);
    expect(Math.min(...geometry.targets.map((target) => target.width))).toBeGreaterThanOrEqual(44);

    const frequentMotion = await action.evaluate((button) => {
      const root = getComputedStyle(document.documentElement);
      const response = getComputedStyle(button, '::after');
      const durationMs = (value: string) =>
        value.trim().endsWith('ms') ? Number.parseFloat(value) : Number.parseFloat(value) * 1_000;
      return {
        press: durationMs(root.getPropertyValue('--motion-press')),
        state: durationMs(root.getPropertyValue('--motion-state')),
        transitions: response.transitionDuration,
      };
    });
    expect(frequentMotion).toEqual({
      press: 120,
      state: 180,
      transitions: '0.18s, 0.18s',
    });

    if (capture && viewport.width === 390) {
      await page.screenshot({ path: `${screenshotRoot}/today-mobile-web-390-light.png` });
    }
  }

  await page.evaluate(() => {
    document.documentElement.dataset.yfcKeyboard = 'visible';
  });
  await expect(page.locator('#appBottomNav')).toHaveCSS('visibility', 'hidden');
  await page.evaluate(() => {
    delete document.documentElement.dataset.yfcKeyboard;
  });
  await expect(page.locator('#appBottomNav')).toHaveCSS('visibility', 'visible');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/app?section=today');
  const desktopNavigation = page.locator('#appBottomNav');
  await expect(desktopNavigation).toHaveCSS('width', '220px');
  await expect(desktopNavigation).toHaveCSS('border-radius', '0px');
  await page.getByRole('button', { name: 'Добавить фактическое кардио' }).click();
  const cardioFieldTops = await page.locator('.cardio-form__core').evaluate((form) => {
    const top = (selector: string) =>
      form.querySelector<HTMLElement>(selector)!.getBoundingClientRect().top;
    return {
      activity: top('#cardio-activity-new'),
      duration: top('#cardio-duration-new'),
      scheduledAt: top('#cardio-scheduled-new'),
    };
  });
  expect(Math.abs(cardioFieldTops.activity - cardioFieldTops.duration)).toBeLessThanOrEqual(1);
  expect(cardioFieldTops.scheduledAt).toBeGreaterThanOrEqual(cardioFieldTops.activity);
  if (capture) {
    await page.locator('.cardio-log').screenshot({
      path: `${screenshotRoot}/today-desktop-cardio-1440-light.png`,
    });
    await page.screenshot({
      path: `${screenshotRoot}/today-desktop-1440-light.png`,
      fullPage: true,
    });
  }
});

test('rest-day action stays clear without decorative artwork', async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'none' });
  await page.goto('/app?section=today');

  await expect(page.getByRole('heading', { name: 'Сегодня без тренировки' })).toBeVisible();
  const surface = page.locator('.today-workout-spotlight');
  await expect(surface).toHaveClass(/today-workout-spotlight--rest-day/);
  await expect(surface.locator('.ui-semantic-artwork')).toHaveCount(0);
  await expect(surface).toHaveCSS('background-image', 'none');
  await expectNoHorizontalOverflow(page);

  if (capture) {
    await page.screenshot({
      path: `${screenshotRoot}/today-rest-day-mobile-web-430-light.png`,
    });
  }
});

test('frequent current action feedback is interruptible, repeatable and reduced-motion safe', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  await page.goto('/app?section=today');
  const action = page.getByRole('button', { name: 'Начать тренировку' });
  await action.evaluate((button) => {
    button.addEventListener('click', (event) => event.stopImmediatePropagation(), true);
  });
  const actionBox = await action.boundingBox();
  expect(actionBox).not.toBeNull();
  await page.mouse.move(actionBox!.x + actionBox!.width / 2, actionBox!.y + actionBox!.height / 2);

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.mouse.down();
    await expect
      .poll(() =>
        action.evaluate((button) => Number.parseFloat(getComputedStyle(button, '::after').opacity)),
      )
      .toBeGreaterThan(0);
    expect(
      await action.evaluate((button) => getComputedStyle(button, '::after').transform),
    ).not.toBe('none');
    if (capture && attempt === 0) {
      await page.screenshot({
        path: `${screenshotRoot}/today-frequent-full-390-light-pressed.png`,
      });
    }
    await page.mouse.up();
    await action.evaluate(async (button) => {
      await Promise.all(
        button.getAnimations({ subtree: true }).map((animation) => animation.finished),
      );
    });
    expect(await action.evaluate((button) => button.getAnimations({ subtree: true }).length)).toBe(
      0,
    );
  }
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Силовая база' })).toBeVisible();

  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.goto('/app?section=today');
  const reducedAction = page.getByRole('button', { name: 'Начать тренировку' });
  await reducedAction.evaluate((button) => {
    button.addEventListener('click', (event) => event.stopImmediatePropagation(), true);
  });
  const reducedBox = await reducedAction.boundingBox();
  expect(reducedBox).not.toBeNull();
  await page.mouse.move(
    reducedBox!.x + reducedBox!.width / 2,
    reducedBox!.y + reducedBox!.height / 2,
  );
  await page.mouse.down();
  await expect
    .poll(() =>
      reducedAction.evaluate((button) =>
        Number.parseFloat(getComputedStyle(button, '::after').opacity),
      ),
    )
    .toBeGreaterThan(0);
  const reducedTransform = await reducedAction.evaluate((button) => {
    const value = getComputedStyle(button, '::after').transform;
    const matrix = value === 'none' ? new DOMMatrix() : new DOMMatrix(value);
    return { scaleX: matrix.a, scaleY: matrix.d, translateX: matrix.e, translateY: matrix.f };
  });
  expect(reducedTransform).toEqual({ scaleX: 1, scaleY: 1, translateX: 0, translateY: 0 });
  if (capture) {
    await page.screenshot({
      path: `${screenshotRoot}/today-frequent-reduced-390-dark-pressed.png`,
    });
  }
  await page.mouse.up();
  await reducedAction.evaluate(async (button) => {
    await Promise.all(
      button.getAnimations({ subtree: true }).map((animation) => animation.finished),
    );
  });
  expect(
    await reducedAction.evaluate((button) => button.getAnimations({ subtree: true }).length),
  ).toBe(0);
});

test('weight bento trend keeps smooth truthful geometry, area fill and measurement alternative', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installPlatformApi(page, {
    browserSession: true,
    measurementHistory: 'many',
    workoutStatus: 'completed',
  });
  await page.goto('/app?section=progress');
  const insight = progressOverview(page).locator('.progress-bento__trend');
  await insight.scrollIntoViewIfNeeded();
  const chart = insight.locator('.data-viz-chart');
  await expect(chart).toBeVisible();
  await expect(chart.locator('.data-viz-chart__area')).toHaveCount(1);
  await expect(chart.getByRole('table', { name: /Вес/ })).toBeAttached();
  const lineContract = await chart.locator('.data-viz-chart__actual').evaluate((line) => ({
    caps: getComputedStyle(line).strokeLinecap,
    joins: getComputedStyle(line).strokeLinejoin,
    path: line.getAttribute('d'),
    width: Number.parseFloat(getComputedStyle(line).strokeWidth),
  }));
  expect(lineContract.caps).toBe('round');
  expect(lineContract.joins).toBe('round');
  expect(lineContract.path).toContain(' C ');
  expect(lineContract.width).toBeGreaterThanOrEqual(2.5);
  const areaOpacity = await chart
    .locator('.data-viz-chart__area-start')
    .evaluate((stop) => Number.parseFloat(getComputedStyle(stop).stopOpacity));
  expect(areaOpacity).toBeGreaterThanOrEqual(0.28);
  await expect(chart).toHaveAttribute('data-motion-phase', 'idle');
  await expectNoHorizontalOverflow(page);
  await expectNoOverlap(chart, page.locator('#appBottomNav'));
  if (capture) {
    await page.screenshot({ path: `${screenshotRoot}/progress-mobile-web-390-light-chart.png` });
  }

  const measurementHistory = page.locator('.measurement-history');
  await measurementHistory.scrollIntoViewIfNeeded();
  await expect(measurementHistory).toBeVisible();
  await expectNoOverlap(
    measurementHistory.locator('.measurement-history__row').last(),
    page.locator('#appBottomNav'),
  );
  if (capture) {
    await page.screenshot({
      path: `${screenshotRoot}/progress-mobile-web-390-light-measurements.png`,
    });
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/app?section=progress');
  const desktopInsight = progressOverview(page).locator('.progress-bento__trend');
  await desktopInsight.scrollIntoViewIfNeeded();
  await expect(desktopInsight.locator('.data-viz-chart__area')).toHaveCount(1);
  if (capture) {
    await page.screenshot({
      path: `${screenshotRoot}/progress-desktop-1440-light.png`,
      fullPage: true,
    });
  }
});

test('mocked TMA dark uses the same chart and safe-area floating dock', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installTelegramHarness(page, {
    colorScheme: 'dark',
    contentSafeAreaInset: { top: 32, right: 0, bottom: 18, left: 0 },
    safeAreaInset: { top: 22, right: 2, bottom: 24, left: 2 },
  });
  await installPlatformApi(page, { measurementHistory: 'many', workoutStatus: 'completed' });
  await page.goto('/app?section=progress');
  const dock = page.locator('#appBottomNav');
  const insight = progressOverview(page).locator('.progress-bento__trend');
  await insight.scrollIntoViewIfNeeded();
  await expect(page.locator('html')).toHaveAttribute('data-color-scheme', 'dark');
  await expect(insight.locator('.data-viz-chart__area')).toHaveCount(1);
  await expect(insight.getByRole('table', { name: /Вес/ })).toBeAttached();
  await expectNoOverlap(insight.locator('.data-viz-chart'), dock);
  const dockBottomGap = await dock.evaluate(
    (element) => window.innerHeight - element.getBoundingClientRect().bottom,
  );
  expect(dockBottomGap).toBeGreaterThanOrEqual(24);

  await page.evaluate(() => {
    const harness = (window as PulseLabWindow).__yfcTmaHarness;
    harness?.safeArea({ top: 26, right: 4, bottom: 28, left: 4 });
    harness?.contentSafeArea({ top: 36, right: 0, bottom: 20, left: 0 });
  });
  await expect
    .poll(() => dock.evaluate((element) => getComputedStyle(element).bottom))
    .toBe('28px');
  await expect(insight.locator('.data-viz-chart')).toHaveAttribute('data-motion-phase', 'idle');
  await expectNoHorizontalOverflow(page);
  if (capture) {
    await page.screenshot({ path: `${screenshotRoot}/progress-mocked-tma-390-dark.png` });
  }
});

test('full Pulse completion motion exposes facts immediately and settles within its budget', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    const lab: PulseLabState = { cls: 0, frameGaps: [], longTasks: [], recording: false };
    (window as PulseLabWindow).__pulseLab = lab;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!(entry as PerformanceEntry & { hadRecentInput?: boolean }).hadRecentInput) {
          lab.cls += (entry as PerformanceEntry & { value?: number }).value ?? 0;
        }
      }
    }).observe({ type: 'layout-shift', buffered: true });
    new PerformanceObserver((list) => {
      lab.longTasks.push(...list.getEntries().map((entry) => entry.duration));
    }).observe({ type: 'longtask', buffered: true });
    let previous: number | null = null;
    const frame = (timestamp: number) => {
      if (!lab.recording) {
        previous = null;
        requestAnimationFrame(frame);
        return;
      }
      if (previous != null) lab.frameGaps.push(timestamp - previous);
      previous = timestamp;
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  await page.goto('/app?section=today');
  await page.getByRole('button', { name: 'Начать тренировку' }).click();
  await page.getByRole('spinbutton', { name: 'Повторы, Приседания, подход 1' }).fill('8');
  await page.getByRole('spinbutton', { name: 'Вес, Приседания, подход 1' }).fill('40');
  await page.getByRole('button', { name: 'Завершить: Приседания, подход 1' }).click();
  await expect(page.getByText('Синхронизировано')).toBeVisible();
  await page.evaluate(() => {
    const lab = (window as PulseLabWindow).__pulseLab!;
    lab.cls = 0;
    lab.frameGaps = [];
    lab.longTasks = [];
    lab.recording = true;
  });
  await page.getByRole('button', { name: 'Завершить тренировку' }).click();

  const completion = page.locator('.workout-completion');
  await expect(completion).toHaveAttribute('data-motion-phase', 'enter');
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await expect(page.getByText('1 ч')).toBeVisible();
  await expect(page.getByText('1', { exact: true }).first()).toBeVisible();
  const durations = await completion.evaluate((element) =>
    element
      .getAnimations({ subtree: true })
      .map((animation) => Number(animation.effect?.getTiming().duration ?? 0)),
  );
  expect(durations.length).toBeGreaterThanOrEqual(3);
  expect(Math.max(...durations)).toBeLessThanOrEqual(760);

  if (capture) {
    await completion.locator('.workout-completion__hero').scrollIntoViewIfNeeded();
    await completion.evaluate((element) => {
      element.getAnimations({ subtree: true }).forEach((animation) => {
        animation.pause();
        animation.currentTime = 180;
      });
    });
    await page.screenshot({ path: `${screenshotRoot}/completion-full-390-light-180ms.png` });
    await completion.evaluate((element) => {
      element.getAnimations({ subtree: true }).forEach((animation) => animation.play());
    });
  }

  await expect(completion).toHaveAttribute('data-motion-phase', 'idle', { timeout: 2_000 });
  await page.evaluate(() => {
    (window as PulseLabWindow).__pulseLab!.recording = false;
  });
  const lab = await page.evaluate(() => (window as PulseLabWindow).__pulseLab!);
  const sortedFrameGaps = [...lab.frameGaps].sort((left, right) => left - right);
  const p95FrameGap = sortedFrameGaps[Math.floor(sortedFrameGaps.length * 0.95)] ?? 0;
  expect(lab.longTasks).toEqual([]);
  expect(lab.cls).toBeLessThanOrEqual(0.01);
  expect(p95FrameGap).toBeLessThanOrEqual(34);
  await expect(completion.locator('.ui-semantic-artwork')).toHaveCount(0);
  await expect(completion.locator('.workout-completion__hero')).toHaveCSS(
    'background-image',
    'none',
  );
  await expect(completion.locator('.workout-completion__check')).toBeVisible();
  if (capture) {
    await page.screenshot({ path: `${screenshotRoot}/completion-full-390-light-final.png` });
  }
});

test('reduced motion keeps completion confirmation and final values without travel', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await installPlatformApi(page, { browserSession: true, workoutStatus: 'planned' });
  const completion = await completeWorkout(page);
  await expect(completion).toHaveAttribute('data-motion-phase', 'idle');
  await expect(page.getByRole('heading', { name: 'Тренировка завершена' })).toBeVisible();
  await expect(page.getByText(/максимальный вес 40 кг/)).toBeVisible();
  const finalState = await completion.evaluate((element) => ({
    animations: element.getAnimations({ subtree: true }).length,
    artworkCount: element.querySelectorAll('.ui-semantic-artwork').length,
    boundary: getComputedStyle(element.querySelector<HTMLElement>('.workout-completion__hero')!)
      .borderLeftColor,
  }));
  expect(finalState.animations).toBe(0);
  expect(finalState.artworkCount).toBe(0);
  expect(finalState.boundary).not.toBe('rgba(0, 0, 0, 0)');
  await expectNoHorizontalOverflow(page);
  if (capture) {
    await completion.locator('.workout-completion__hero').scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${screenshotRoot}/completion-reduced-390-dark.png` });
  }
});
