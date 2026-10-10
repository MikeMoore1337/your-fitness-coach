import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  installMobileLayoutAdapter,
  readMobileViewportSnapshot,
  YFC_PLATFORM_ACTIVATED_EVENT,
} from '../../../../src/shared/telegram/layout';
import { createTelegramMock } from '../../../helpers/telegramMock';

function telegramLayoutMock() {
  return createTelegramMock({
    isActive: true,
    viewportHeight: 560,
    viewportStableHeight: 844,
    safeAreaInset: { top: 28, right: 2, bottom: 20, left: 2 },
    contentSafeAreaInset: { top: 44, right: 0, bottom: 16, left: 0 },
  });
}

describe('Mobile Web/TMA layout adapter', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.documentElement.removeAttribute('style');
    delete document.documentElement.dataset.yfcKeyboard;
    delete document.documentElement.dataset.yfcLayoutSurface;
    delete document.documentElement.dataset.yfcViewportActive;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('uses the smaller iOS visual viewport while the Telegram keyboard is open', () => {
    vi.stubGlobal('visualViewport', { height: 392 });
    const controller = createTelegramMock({
      viewportHeight: 844,
      viewportStableHeight: 844,
      isActive: true,
    });

    expect(readMobileViewportSnapshot(controller.webApp)).toMatchObject({
      viewportHeight: 392,
      viewportStableHeight: 844,
    });
  });

  it('normalizes Telegram stable/current viewport and both safe-area layers', () => {
    const controller = telegramLayoutMock();
    const telegram = controller.webApp;

    expect(readMobileViewportSnapshot(telegram)).toEqual({
      active: true,
      viewportHeight: 560,
      viewportStableHeight: 844,
      safeArea: { top: 28, right: 2, bottom: 20, left: 2 },
      contentSafeArea: { top: 44, right: 0, bottom: 16, left: 0 },
    });

    const cleanup = installMobileLayoutAdapter(telegram);
    const root = document.documentElement;
    expect(root.dataset.yfcLayoutSurface).toBe('telegram');
    expect(root.style.getPropertyValue('--yfc-viewport-height')).toBe('560px');
    expect(root.style.getPropertyValue('--yfc-viewport-bottom')).toBe(
      `${Math.max(0, window.innerHeight - 560)}px`,
    );
    expect(root.style.getPropertyValue('--yfc-viewport-stable-height')).toBe('844px');
    expect(root.style.getPropertyValue('--yfc-tg-safe-top')).toBe('28px');
    expect(root.style.getPropertyValue('--yfc-tg-content-safe-top')).toBe('44px');

    cleanup();
    expect(controller.calls.unsubscribed).toEqual([
      'viewportChanged',
      'safeAreaChanged',
      'contentSafeAreaChanged',
      'activated',
      'deactivated',
    ]);
  });

  it('hides navigation state only while an editable control owns focus', () => {
    const telegram = telegramLayoutMock().webApp;
    const input = document.createElement('input');
    document.body.append(input);
    const cleanup = installMobileLayoutAdapter(telegram);

    input.focus();
    expect(document.documentElement.dataset.yfcKeyboard).toBe('visible');

    input.blur();
    document.body.focus();
    window.dispatchEvent(new Event('resize'));
    expect(document.documentElement.dataset.yfcKeyboard).toBe('hidden');

    cleanup();
  });

  it('updates layout values from Telegram events without recreating application state', () => {
    const controller = telegramLayoutMock();
    const telegram = controller.webApp;
    const cleanup = installMobileLayoutAdapter(telegram);

    controller.setViewport(720, 900);

    expect(document.documentElement.style.getPropertyValue('--yfc-viewport-height')).toBe('720px');
    expect(document.documentElement.style.getPropertyValue('--yfc-viewport-stable-height')).toBe(
      '900px',
    );

    cleanup();
  });

  it('keeps the dock hidden through the pointer that blurs an input', () => {
    const frames: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frames.push(callback);
      return frames.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
    const input = document.createElement('input');
    const button = document.createElement('button');
    document.body.append(input, button);
    const cleanup = installMobileLayoutAdapter(null);
    input.focus();
    button.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    button.focus();
    window.dispatchEvent(new Event('resize'));
    expect(document.documentElement.dataset.yfcKeyboard).toBe('visible');
    button.dispatchEvent(new Event('pointerup', { bubbles: true }));
    expect(document.documentElement.dataset.yfcKeyboard).toBe('visible');
    frames.at(-1)?.(0);
    expect(document.documentElement.dataset.yfcKeyboard).toBe('hidden');
    cleanup();
  });

  it('falls back from invalid zero heights and emits one recovery event on activation', () => {
    const controller = telegramLayoutMock();
    controller.webApp.viewportHeight = 0;
    controller.webApp.viewportStableHeight = 0;
    const onActivated = vi.fn();
    window.addEventListener(YFC_PLATFORM_ACTIVATED_EVENT, onActivated);

    const snapshot = readMobileViewportSnapshot(controller.webApp);
    expect(snapshot.viewportHeight).toBeGreaterThan(0);
    expect(snapshot.viewportStableHeight).toBeGreaterThan(0);

    const dispose = installMobileLayoutAdapter(controller.webApp);
    controller.setActive(false);
    controller.setActive(true);
    expect(onActivated).toHaveBeenCalledTimes(1);

    dispose();
    window.removeEventListener(YFC_PLATFORM_ACTIVATED_EVENT, onActivated);
  });
});
