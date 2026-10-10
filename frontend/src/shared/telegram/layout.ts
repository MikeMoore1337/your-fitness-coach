import type { TelegramInsets, TelegramWebApp } from './types';

export interface MobileViewportSnapshot {
  active: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  safeArea: TelegramInsets;
  contentSafeArea: TelegramInsets;
}

export const YFC_PLATFORM_ACTIVATED_EVENT = 'yfc:platform-activated';

const SIDES = ['top', 'right', 'bottom', 'left'] as const;
const LAYOUT_EVENTS = [
  'viewportChanged',
  'safeAreaChanged',
  'contentSafeAreaChanged',
  'activated',
  'deactivated',
] as const;

function boundedMetric(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function positiveMetric(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback;
}

function normalizedInsets(value: Partial<TelegramInsets> | undefined): TelegramInsets {
  return {
    top: boundedMetric(value?.top, 0),
    right: boundedMetric(value?.right, 0),
    bottom: boundedMetric(value?.bottom, 0),
    left: boundedMetric(value?.left, 0),
  };
}

export function readMobileViewportSnapshot(
  telegram: TelegramWebApp | null,
): MobileViewportSnapshot {
  const browserHeight = positiveMetric(window.visualViewport?.height, window.innerHeight);
  const stableFallback = positiveMetric(window.innerHeight, browserHeight);
  const isMiniApp = Boolean(telegram?.initData);
  const viewportHeight = isMiniApp
    ? Math.min(positiveMetric(telegram?.viewportHeight, browserHeight), browserHeight)
    : browserHeight;

  return {
    active: isMiniApp ? telegram?.isActive !== false : document.visibilityState !== 'hidden',
    viewportHeight,
    viewportStableHeight: isMiniApp
      ? positiveMetric(telegram?.viewportStableHeight, stableFallback)
      : stableFallback,
    safeArea: isMiniApp ? normalizedInsets(telegram?.safeAreaInset) : normalizedInsets(undefined),
    contentSafeArea: isMiniApp
      ? normalizedInsets(telegram?.contentSafeAreaInset)
      : normalizedInsets(undefined),
  };
}

function editableTarget(target: Element | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (!(target instanceof HTMLInputElement)) return false;
  return ![
    'button',
    'checkbox',
    'color',
    'file',
    'hidden',
    'image',
    'radio',
    'range',
    'reset',
    'submit',
  ].includes(target.type);
}

export function applyMobileViewportSnapshot(
  snapshot: MobileViewportSnapshot,
  telegram: TelegramWebApp | null,
): void {
  const root = document.documentElement;
  root.dataset.yfcViewportActive = String(snapshot.active);
  root.dataset.yfcLayoutSurface = telegram?.initData ? 'telegram' : 'browser';
  root.style.setProperty('--yfc-viewport-height', `${snapshot.viewportHeight}px`);
  root.style.setProperty('--yfc-viewport-stable-height', `${snapshot.viewportStableHeight}px`);
  root.style.setProperty(
    '--yfc-viewport-bottom',
    `${Math.max(0, window.innerHeight - snapshot.viewportHeight - (window.visualViewport?.offsetTop ?? 0))}px`,
  );

  for (const side of SIDES) {
    root.style.setProperty(`--yfc-tg-safe-${side}`, `${snapshot.safeArea[side]}px`);
    root.style.setProperty(`--yfc-tg-content-safe-${side}`, `${snapshot.contentSafeArea[side]}px`);
  }

  root.dataset.yfcKeyboard = editableTarget(document.activeElement) ? 'visible' : 'hidden';
}

export function installMobileLayoutAdapter(telegram: TelegramWebApp | null): () => void {
  let previousActive: boolean | null = null;
  let editablePointerInFlight = false;
  const update = () => {
    const keepDockHidden =
      editablePointerInFlight && document.documentElement.dataset.yfcKeyboard === 'visible';
    const snapshot = readMobileViewportSnapshot(telegram);
    applyMobileViewportSnapshot(snapshot, telegram);
    // Keep the dock out of the pointer path until the input-blurring click completes.
    if (keepDockHidden) document.documentElement.dataset.yfcKeyboard = 'visible';
    if (previousActive === false && snapshot.active) {
      window.dispatchEvent(new Event(YFC_PLATFORM_ACTIVATED_EVENT));
    }
    previousActive = snapshot.active;
  };
  let focusFrame: number | null = null;
  const updateAfterFocus = () => {
    if (focusFrame !== null) window.cancelAnimationFrame(focusFrame);
    focusFrame = window.requestAnimationFrame(() => {
      focusFrame = null;
      update();
    });
  };
  const onPointerDown = () => {
    editablePointerInFlight = editableTarget(document.activeElement);
  };
  const onPointerEnd = () => {
    editablePointerInFlight = false;
    updateAfterFocus();
  };

  update();
  LAYOUT_EVENTS.forEach((event) => telegram?.onEvent?.(event, update));
  window.visualViewport?.addEventListener('resize', update);
  window.visualViewport?.addEventListener('scroll', update);
  window.addEventListener('resize', update);
  document.addEventListener('visibilitychange', update);
  document.addEventListener('focusin', update);
  document.addEventListener('focusout', updateAfterFocus);
  document.addEventListener('pointerdown', onPointerDown, true);
  document.addEventListener('pointerup', onPointerEnd, true);
  document.addEventListener('pointercancel', onPointerEnd, true);

  return () => {
    if (focusFrame !== null) window.cancelAnimationFrame(focusFrame);
    LAYOUT_EVENTS.forEach((event) => telegram?.offEvent?.(event, update));
    window.visualViewport?.removeEventListener('resize', update);
    window.visualViewport?.removeEventListener('scroll', update);
    window.removeEventListener('resize', update);
    document.removeEventListener('visibilitychange', update);
    document.removeEventListener('focusin', update);
    document.removeEventListener('focusout', updateAfterFocus);
    document.removeEventListener('pointerdown', onPointerDown, true);
    document.removeEventListener('pointerup', onPointerEnd, true);
    document.removeEventListener('pointercancel', onPointerEnd, true);
  };
}
