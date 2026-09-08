import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createProductAnalytics,
  clearProductLoginAttempt,
  isProductEvent,
  isProductEventEnvelope,
  markProductLoginStarted,
  PRODUCT_ANALYTICS_STATUS_NAME,
  PRODUCT_EVENT_NAME,
  PRODUCT_EVENT_SCHEMA_VERSION,
  productAnalyticsEnvironment,
  productEventSurface,
  trackProductLoginCompletedIfStarted,
  type ProductAnalyticsStatus,
  type ProductAnalyticsProvider,
  type ProductEvent,
  type ProductEventEnvelope,
} from '../../../../src/shared/analytics/productEvents';

function testAnalytics(target = new EventTarget()) {
  return {
    target,
    analytics: createProductAnalytics({
      target,
      environment: 'test',
      now: () => new Date('2026-08-24T10:00:00.000Z'),
    }),
  };
}

function allowedProvider(send: ProductAnalyticsProvider['send'] = vi.fn()) {
  return {
    name: 'test_sink',
    environment: 'test' as const,
    isDeliveryAllowed: () => true,
    send,
  };
}

afterEach(() => {
  clearProductLoginAttempt();
  vi.unstubAllGlobals();
  delete window.Telegram;
});

describe('product event contract', () => {
  it('emits a versioned provider-neutral envelope with a privacy-safe surface', () => {
    const { target, analytics } = testAnalytics();
    const events: ProductEventEnvelope[] = [];
    target.addEventListener(PRODUCT_EVENT_NAME, (event) => {
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    });

    expect(analytics.track({ name: 'workout_completed', surface: 'tma' })).toBe(true);
    expect(events).toEqual([
      {
        name: 'workout_completed',
        surface: 'tma',
        schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
        environment: 'test',
        occurred_at: '2026-08-24T10:00:00.000Z',
      },
    ]);
    expect(isProductEventEnvelope(events[0])).toBe(true);
  });

  it('classifies desktop web, mobile web and TMA without user-agent fingerprinting', () => {
    const matchMedia = vi.fn().mockReturnValue({ matches: false });
    vi.stubGlobal('matchMedia', matchMedia);
    expect(productEventSurface()).toBe('desktop_web');
    expect(matchMedia).toHaveBeenCalledWith('(max-width: 767px)');

    matchMedia.mockReturnValue({ matches: true });
    expect(productEventSurface()).toBe('mobile_web');

    window.Telegram = { WebApp: { initData: 'signed-init-data' } };
    expect(productEventSurface()).toBe('tma');
  });

  it('deduplicates StrictMode and foreground repeats while keeping distinct journey scopes', () => {
    const { target, analytics } = testAnalytics();
    const listener = vi.fn();
    target.addEventListener(PRODUCT_EVENT_NAME, listener);
    const event = { name: 'workout_completion_summary_viewed', surface: 'mobile_web' } as const;

    expect(analytics.track(event, { dedupe: 'session', dedupeKey: 'workout:101' })).toBe(true);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(analytics.track(event, { dedupe: 'session', dedupeKey: 'workout:101' })).toBe(false);
    expect(analytics.track(event, { dedupe: 'session', dedupeKey: 'workout:102' })).toBe(true);
    expect(listener).toHaveBeenCalledTimes(2);

    expect(
      analytics.track({
        name: 'food_logged',
        surface: 'mobile_web',
        entry_method: 'recent',
      }),
    ).toBe(true);
    expect(
      analytics.track({
        name: 'food_logged',
        surface: 'mobile_web',
        entry_method: 'recent',
      }),
    ).toBe(true);
    expect(listener).toHaveBeenCalledTimes(4);
  });

  it('completes auth only for a pending attempt and consumes the cross-navigation marker', () => {
    const events: ProductEventEnvelope[] = [];
    const listener = (event: Event) => {
      events.push((event as CustomEvent<ProductEventEnvelope>).detail);
    };
    window.addEventListener(PRODUCT_EVENT_NAME, listener);

    expect(trackProductLoginCompletedIfStarted()).toBe(false);
    markProductLoginStarted();
    expect(window.sessionStorage.getItem('fit_product_analytics_login_attempt')).toBe('1');
    expect(trackProductLoginCompletedIfStarted()).toBe(true);
    expect(trackProductLoginCompletedIfStarted()).toBe(false);
    expect(events.map((event) => event.name)).toEqual(['login_started', 'login_completed']);
    expect(events.every((event) => Object.keys(event).length === 5)).toBe(true);

    window.removeEventListener(PRODUCT_EVENT_NAME, listener);
  });

  it.each([
    ['food_contents', 'Борщ'],
    ['food_name', 'Овсянка'],
    ['weight_kg', 81.4],
    ['waist_cm', 92],
    ['calories', 2400],
    ['distance_km', 5],
    ['heart_rate', 155],
    ['trainer_comment', 'private'],
    ['support_message', 'private'],
    ['ai_conversation', 'private'],
    ['access_token', 'secret'],
    ['init_data', 'secret'],
    ['user_id', 42],
    ['url', '/app?token=secret'],
  ])('rejects forbidden or unversioned payload field %s', (field, value) => {
    const { target, analytics } = testAnalytics();
    const listener = vi.fn();
    target.addEventListener(PRODUCT_EVENT_NAME, listener);
    const unsafeEvent = {
      name: 'measurement_logged',
      surface: 'mobile_web',
      [field]: value,
    } as unknown as ProductEvent;

    expect(isProductEvent(unsafeEvent)).toBe(false);
    expect(analytics.track(unsafeEvent)).toBe(false);
    expect(listener).not.toHaveBeenCalled();
  });

  it('validates constrained event context values and surface combinations', () => {
    expect(
      isProductEvent({
        name: 'landing_telegram_selected',
        surface: 'desktop_web',
        placement: 'continuity',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'landing_telegram_selected',
        surface: 'mobile_web',
        placement: 'header',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'onboarding_next_action_selected',
        surface: 'mobile_web',
        next_action: 'programs',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'food_logged',
        surface: 'desktop_web',
        entry_method: 'favorite',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'today_primary_action_selected',
        surface: 'tma',
        destination: 'workout',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'onboarding_next_action_selected',
        surface: 'mobile_web',
        next_action: '/private/path?token=secret',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'tma_core_action_completed',
        surface: 'mobile_web',
        action: 'workout_completed',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'telegram_news_cta_clicked',
        surface: 'telegram',
        destination: 'tma',
        campaign: 'telegram_editorial_v1',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'telegram_news_cta_clicked',
        surface: 'tma',
        destination: 'article',
        campaign: 'telegram_editorial_v1',
      }),
    ).toBe(true);
  });

  it('keeps PWA analytics context-free and limits service-worker error categories', () => {
    expect(isProductEvent({ name: 'pwa_install_option_shown', surface: 'mobile_web' })).toBe(true);
    expect(isProductEvent({ name: 'pwa_workout_resume_failure', surface: 'desktop_web' })).toBe(
      true,
    );
    expect(
      isProductEvent({
        name: 'pwa_service_worker_error',
        surface: 'mobile_web',
        category: 'navigation',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'pwa_service_worker_error',
        surface: 'mobile_web',
        category: 'network-stack',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'pwa_update_applied',
        surface: 'desktop_web',
        user_id: 7,
      } as unknown as ProductEvent),
    ).toBe(false);
  });

  it('keeps public article analytics limited to a slug and canonical CTA destination', () => {
    expect(
      isProductEvent({
        name: 'article_viewed',
        surface: 'mobile_web',
        content_key: 'kak-nachat-silovye-trenirovki',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'article_cta_clicked',
        surface: 'desktop_web',
        content_key: 'kak-nachat-silovye-trenirovki',
        destination: 'tma',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'article_viewed',
        surface: 'desktop_web',
        content_key: 'article?query=private',
      }),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'article_cta_clicked',
        surface: 'desktop_web',
        content_key: 'article-slug',
        destination: 'https://example.com/private',
      } as unknown as ProductEvent),
    ).toBe(false);
  });

  it('keeps AI Coach analytics at outcome level without accepting prompt-like fields', () => {
    expect(
      isProductEvent({
        name: 'ai_coach_response_received',
        surface: 'mobile_web',
        mode: 'personal',
        outcome: 'insufficient_data',
      }),
    ).toBe(true);
    expect(
      isProductEvent({
        name: 'ai_coach_response_received',
        surface: 'mobile_web',
        mode: 'personal',
        outcome: 'secret-provider-error',
      } as unknown as ProductEvent),
    ).toBe(false);
    expect(
      isProductEvent({
        name: 'ai_coach_request_started',
        surface: 'mobile_web',
        mode: 'generic',
        prompt: 'private question',
      } as unknown as ProductEvent),
    ).toBe(false);
  });

  it('rejects unknown schema versions, legacy surfaces and malformed timestamps', () => {
    const envelope = {
      name: 'workout_started',
      surface: 'desktop_web',
      schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
      environment: 'test',
      occurred_at: '2026-08-24T10:00:00.000Z',
    };

    expect(isProductEventEnvelope({ ...envelope, schema_version: 1 })).toBe(false);
    expect(isProductEventEnvelope({ ...envelope, surface: 'web' })).toBe(false);
    expect(isProductEventEnvelope({ ...envelope, occurred_at: '2026-99-99' })).toBe(false);
    expect(isProductEventEnvelope({ ...envelope, name: 'unknown_event' })).toBe(false);
  });

  it('keeps environments isolated and evaluates consent/config at delivery time', () => {
    const { analytics } = testAnalytics();
    let deliveryAllowed = false;
    const testProvider = {
      name: 'test_sink',
      environment: 'test' as const,
      isDeliveryAllowed: () => deliveryAllowed,
      send: vi.fn(),
    };
    const productionProvider = {
      name: 'production_sink',
      environment: 'production' as const,
      isDeliveryAllowed: () => true,
      send: vi.fn(),
    };
    analytics.subscribe(testProvider);
    analytics.subscribe(productionProvider);

    analytics.track({ name: 'landing_viewed', surface: 'desktop_web' });
    expect(testProvider.send).not.toHaveBeenCalled();

    deliveryAllowed = true;
    analytics.track({ name: 'landing_app_selected', surface: 'desktop_web' });
    expect(testProvider.send).toHaveBeenCalledOnce();
    expect(productionProvider.send).not.toHaveBeenCalled();
    expect(productAnalyticsEnvironment('production')).toBe('production');
    expect(productAnalyticsEnvironment('staging')).toBe('staging');
    expect(productAnalyticsEnvironment('test')).toBe('test');
    expect(productAnalyticsEnvironment('custom-local-mode')).toBe('development');
  });

  it('ignores forged bus payloads before they reach a provider', () => {
    const { target, analytics } = testAnalytics();
    const provider = allowedProvider();
    analytics.subscribe(provider);

    target.dispatchEvent(
      new CustomEvent(PRODUCT_EVENT_NAME, {
        detail: {
          name: 'food_logged',
          surface: 'mobile_web',
          entry_method: 'recent',
          food_contents: 'private',
          schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
          environment: 'test',
          occurred_at: '2026-08-24T10:00:00.000Z',
        },
      }),
    );

    expect(provider.send).not.toHaveBeenCalled();
  });

  it('isolates an unavailable provider from the product flow', async () => {
    const { target, analytics } = testAnalytics();
    const statuses: ProductAnalyticsStatus[] = [];
    target.addEventListener(PRODUCT_ANALYTICS_STATUS_NAME, (event) => {
      statuses.push((event as CustomEvent<ProductAnalyticsStatus>).detail);
    });
    analytics.subscribe(
      allowedProvider(() => Promise.reject(new Error('provider payload must not escape'))),
    );

    expect(analytics.track({ name: 'login_completed', surface: 'desktop_web' })).toBe(true);
    await Promise.resolve();
    await Promise.resolve();

    expect(statuses).toEqual([
      { provider: 'test_sink', environment: 'test', reason: 'provider_unavailable' },
    ]);
    expect(JSON.stringify(statuses)).not.toContain('provider payload must not escape');
  });
});
