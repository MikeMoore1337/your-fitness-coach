import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiMock = vi.hoisted(() => vi.fn());

vi.mock('../../../../src/shared/api/client', () => ({ api: apiMock }));

import {
  buildFirstTouchAttribution,
  captureFirstTouchAttribution,
  FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY,
  safeAttributionReferrer,
  syncFirstTouchAttribution,
} from '../../../../src/shared/analytics/attribution';

const NOW = new Date('2026-09-13T06:30:00.000Z');

describe('first-touch attribution', () => {
  beforeEach(() => {
    localStorage.clear();
    apiMock.mockReset();
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('classifies allowlisted UTM, search, Telegram and direct sources', () => {
    expect(
      buildFirstTouchAttribution(
        'https://app.example.test/public?utm_source=Google&utm_medium=CPC&utm_campaign=Autumn',
        'https://www.google.com/search?q=private',
        NOW,
        false,
      ),
    ).toMatchObject({
      first_touch_source: 'utm',
      first_touch_medium: 'cpc',
      first_touch_campaign: 'autumn',
      first_referrer: 'https://www.google.com/search',
      utm_source: 'google',
    });
    expect(
      buildFirstTouchAttribution(
        'https://app.example.test/articles',
        'https://yandex.ru/search/?text=private',
        NOW,
        false,
      ).first_touch_source,
    ).toBe('yandex');
    expect(
      buildFirstTouchAttribution('https://app.example.test/app', null, NOW, true)
        .first_touch_source,
    ).toBe('telegram');
    expect(
      buildFirstTouchAttribution('https://app.example.test/', null, NOW, false).first_touch_source,
    ).toBe('direct');
  });

  it('keeps only safe referrers and rejects private query values', () => {
    expect(safeAttributionReferrer('https://example.test/article?email=private#comment')).toBe(
      'https://example.test/article',
    );
    const record = buildFirstTouchAttribution(
      'https://app.example.test/?utm_source=user%40example.test&utm_term=79001234567',
      'https://partner.example.test/path?email=private',
      NOW,
      false,
    );
    expect(record.first_touch_source).toBe('referral');
    expect(record.utm_source).toBeNull();
    expect(record.utm_term).toBeNull();
    expect(JSON.stringify(record)).not.toContain('private');
    expect(JSON.stringify(record)).not.toContain('79001234567');
  });

  it('captures the first landing context once and never overwrites it', () => {
    window.history.replaceState({}, '', '/landing?utm_source=google&utm_medium=organic');
    const first = captureFirstTouchAttribution();
    window.history.replaceState({}, '', '/later?utm_source=yandex&utm_medium=cpc');
    const second = captureFirstTouchAttribution();

    expect(second).toEqual(first);
    expect(JSON.parse(localStorage.getItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY) ?? 'null')).toEqual(
      first,
    );
    expect(first.first_landing_path).toBe('/landing');
  });

  it('binds the stored record only after auth and retains it after a failed request', async () => {
    window.history.replaceState({}, '', '/landing?utm_source=google&utm_medium=organic');
    const stored = captureFirstTouchAttribution();
    apiMock.mockResolvedValueOnce(undefined);

    await syncFirstTouchAttribution(42);

    expect(apiMock).toHaveBeenCalledWith('/api/v1/me/acquisition', {
      method: 'POST',
      body: stored,
      retryAuth: false,
    });
    expect(localStorage.getItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY)).toBeNull();

    window.history.replaceState({}, '', '/later');
    const retryRecord = captureFirstTouchAttribution();
    apiMock.mockRejectedValueOnce(new Error('offline'));
    await syncFirstTouchAttribution(42);
    expect(localStorage.getItem(FIRST_TOUCH_ATTRIBUTION_STORAGE_KEY)).toBe(
      JSON.stringify(retryRecord),
    );
  });
});
