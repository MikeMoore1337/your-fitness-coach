export const PRODUCT_EVENT_NAME = 'yfc:product-event';
export const PRODUCT_ANALYTICS_STATUS_NAME = 'yfc:product-analytics-status';
export const PRODUCT_EVENT_SCHEMA_VERSION = 2 as const;

export type ProductAnalyticsEnvironment = 'production' | 'staging' | 'development' | 'test';
export type ProductSurface = 'desktop_web' | 'mobile_web' | 'tma';
export type FoodEntryMethod =
  'quick_add' | 'recent' | 'favorite' | 'search' | 'recipe' | 'barcode' | 'custom';
export type ProductCoreAction =
  | 'program_activated'
  | 'workout_started'
  | 'workout_completed'
  | 'food_logged'
  | 'measurement_logged'
  | 'weekly_review_completed';
export type PwaServiceWorkerErrorCategory =
  'registration' | 'update' | 'cache' | 'navigation' | 'install' | 'activate';
export type LandingTelegramPlacement = 'hero' | 'continuity' | 'footer';
export type EditorialCtaDestination = 'tma' | 'web' | 'landing' | 'article';
export type EditorialCtaCampaign = 'telegram_editorial_v1';
export type PublicArticleCtaDestination = 'tma' | 'web' | 'landing';
export type AiCoachEntryPoint = 'today' | 'progress' | 'nutrition' | 'profile';
export type AiCoachMode = 'generic' | 'personal';
export type AiCoachOutcome =
  | 'answer'
  | 'unavailable'
  | 'rate_limited'
  | 'safety_refusal'
  | 'insufficient_data'
  | 'invalid_output'
  | 'consent_required';
export type AiCoachFailureClass = 'network' | 'timeout' | 'validation' | 'unknown';
export type AiCoachHelpfulness = 'helpful' | 'not_helpful';

type ContextFreeProductEventName =
  | 'landing_viewed'
  | 'landing_app_selected'
  | 'landing_demo_selected'
  | 'landing_login_selected'
  | 'demo_started'
  | 'demo_meaningful_action_completed'
  | 'demo_login_selected'
  | 'login_started'
  | 'login_completed'
  | 'onboarding_started'
  | 'onboarding_completed'
  | 'program_recommendation_started'
  | 'program_recommendation_completed'
  | 'program_import_started'
  | 'program_import_previewed'
  | 'program_import_confirmed'
  | 'program_import_cancelled'
  | 'program_import_failed'
  | 'program_activated'
  | 'today_viewed'
  | 'workout_started'
  | 'workout_completed'
  | 'workout_completion_summary_viewed'
  | 'measurement_logged'
  | 'check_in_logged'
  | 'weekly_review_started'
  | 'weekly_review_completed'
  | 'weekly_review_skipped'
  | 'weekly_review_proposal_accepted'
  | 'weekly_review_proposal_rejected'
  | 'nutrition_incomplete_day_confirmed'
  | 'workout_adaptation_started'
  | 'workout_adaptation_completed'
  | 'progression_suggestion_shown'
  | 'progression_suggestion_dismissed'
  | 'notification_preferences_changed'
  | 'web_push_unsupported'
  | 'web_push_permission_prompted'
  | 'web_push_permission_granted'
  | 'web_push_permission_denied'
  | 'web_push_permission_dismissed'
  | 'web_push_subscription_registered'
  | 'web_push_subscription_revoked'
  | 'data_export_requested'
  | 'account_delete_started'
  | 'account_delete_completed'
  | 'cardio_logged'
  | 'trainer_workspace_viewed'
  | 'trainer_client_opened'
  | 'trainer_program_assigned'
  | 'trainer_comment_added'
  | 'trainer_mode_activated'
  | 'tma_launched'
  | 'pwa_install_option_shown'
  | 'pwa_install_option_dismissed'
  | 'pwa_install_option_accepted'
  | 'pwa_standalone_launched'
  | 'pwa_workout_resume_success'
  | 'pwa_workout_resume_failure'
  | 'pwa_update_available'
  | 'pwa_update_applied';

type ContextFreeProductEvent = {
  [Name in ContextFreeProductEventName]: {
    name: Name;
    surface: ProductSurface;
  };
}[ContextFreeProductEventName];

export type ProductEvent =
  | ContextFreeProductEvent
  | {
      name: 'landing_telegram_selected';
      surface: ProductSurface;
      placement: LandingTelegramPlacement;
    }
  | {
      name: 'onboarding_next_action_selected';
      surface: ProductSurface;
      next_action: 'today' | 'nutrition' | 'programs' | 'continuation';
    }
  | {
      name: 'today_primary_action_selected';
      surface: ProductSurface;
      destination: 'workout' | 'nutrition' | 'weekly_review' | 'programs' | 'progress';
    }
  | {
      name: 'today_week_navigated';
      surface: ProductSurface;
      direction: 'workout_day';
    }
  | {
      name: 'food_log_started' | 'food_logged';
      surface: ProductSurface;
      entry_method: FoodEntryMethod;
    }
  | {
      name: 'tma_core_action_completed';
      surface: 'tma';
      action: ProductCoreAction;
    }
  | {
      name: 'telegram_news_cta_clicked';
      surface: ProductSurface;
      destination: EditorialCtaDestination;
      campaign: EditorialCtaCampaign;
    }
  | {
      name: 'article_viewed';
      surface: ProductSurface;
      content_key: string;
    }
  | {
      name: 'article_cta_clicked';
      surface: ProductSurface;
      content_key: string;
      destination: PublicArticleCtaDestination;
    }
  | {
      name: 'pwa_service_worker_error';
      surface: ProductSurface;
      category: PwaServiceWorkerErrorCategory;
    }
  | {
      name: 'ai_coach_entry_opened';
      surface: ProductSurface;
      entry_point: AiCoachEntryPoint;
    }
  | {
      name: 'ai_coach_request_started';
      surface: ProductSurface;
      mode: AiCoachMode;
    }
  | {
      name: 'ai_coach_response_received';
      surface: ProductSurface;
      mode: AiCoachMode;
      outcome: AiCoachOutcome;
    }
  | {
      name: 'ai_coach_request_failed';
      surface: ProductSurface;
      mode: AiCoachMode;
      failure: AiCoachFailureClass;
    }
  | {
      name: 'ai_coach_consent_changed';
      surface: ProductSurface;
      enabled: boolean;
    }
  | {
      name: 'ai_coach_helpfulness_submitted';
      surface: ProductSurface;
      value: AiCoachHelpfulness;
    };

export type ProductEventName = ProductEvent['name'];

export type ProductEventEnvelope = ProductEvent & {
  schema_version: typeof PRODUCT_EVENT_SCHEMA_VERSION;
  environment: ProductAnalyticsEnvironment;
  occurred_at: string;
};

export type ProductAnalyticsStatus = {
  provider: string;
  environment: ProductAnalyticsEnvironment;
  reason: 'provider_unavailable';
};

export interface ProductAnalyticsProvider {
  name: string;
  environment: ProductAnalyticsEnvironment;
  /** Delivery stays disabled until the provider-specific config and consent gate passes. */
  isDeliveryAllowed(): boolean;
  send(event: ProductEventEnvelope): void | Promise<void>;
}

export type ProductEventTrackOptions = {
  dedupe?: 'none' | 'session';
  /** Ephemeral in-memory scope only; it is never added to the event envelope. */
  dedupeKey?: string;
};

type ProductAnalyticsRuntimeOptions = {
  target: EventTarget;
  environment: ProductAnalyticsEnvironment;
  now?: () => Date;
};

const CONTEXT_FREE_EVENT_NAMES = new Set<ProductEventName>([
  'landing_viewed',
  'landing_app_selected',
  'landing_demo_selected',
  'landing_login_selected',
  'demo_started',
  'demo_meaningful_action_completed',
  'demo_login_selected',
  'login_started',
  'login_completed',
  'onboarding_started',
  'onboarding_completed',
  'program_recommendation_started',
  'program_recommendation_completed',
  'program_import_started',
  'program_import_previewed',
  'program_import_confirmed',
  'program_import_cancelled',
  'program_import_failed',
  'program_activated',
  'today_viewed',
  'workout_started',
  'workout_completed',
  'workout_completion_summary_viewed',
  'measurement_logged',
  'check_in_logged',
  'weekly_review_started',
  'weekly_review_completed',
  'weekly_review_skipped',
  'weekly_review_proposal_accepted',
  'weekly_review_proposal_rejected',
  'nutrition_incomplete_day_confirmed',
  'workout_adaptation_started',
  'workout_adaptation_completed',
  'progression_suggestion_shown',
  'progression_suggestion_dismissed',
  'notification_preferences_changed',
  'web_push_unsupported',
  'web_push_permission_prompted',
  'web_push_permission_granted',
  'web_push_permission_denied',
  'web_push_permission_dismissed',
  'web_push_subscription_registered',
  'web_push_subscription_revoked',
  'data_export_requested',
  'account_delete_started',
  'account_delete_completed',
  'cardio_logged',
  'trainer_workspace_viewed',
  'trainer_client_opened',
  'trainer_program_assigned',
  'trainer_comment_added',
  'trainer_mode_activated',
  'tma_launched',
  'pwa_install_option_shown',
  'pwa_install_option_dismissed',
  'pwa_install_option_accepted',
  'pwa_standalone_launched',
  'pwa_workout_resume_success',
  'pwa_workout_resume_failure',
  'pwa_update_available',
  'pwa_update_applied',
]);
const PRODUCT_SURFACES = new Set<ProductSurface>(['desktop_web', 'mobile_web', 'tma']);
const PRODUCT_ANALYTICS_ENVIRONMENTS = new Set<ProductAnalyticsEnvironment>([
  'production',
  'staging',
  'development',
  'test',
]);
const ONBOARDING_NEXT_ACTIONS = new Set(['today', 'nutrition', 'programs', 'continuation']);
const TODAY_DESTINATIONS = new Set([
  'workout',
  'nutrition',
  'weekly_review',
  'programs',
  'progress',
]);
const TODAY_WEEK_DIRECTIONS = new Set(['workout_day']);
const FOOD_ENTRY_METHODS = new Set<FoodEntryMethod>([
  'quick_add',
  'recent',
  'favorite',
  'search',
  'recipe',
  'barcode',
  'custom',
]);
const PRODUCT_CORE_ACTIONS = new Set<ProductCoreAction>([
  'program_activated',
  'workout_started',
  'workout_completed',
  'food_logged',
  'measurement_logged',
  'weekly_review_completed',
]);
const PWA_SERVICE_WORKER_ERROR_CATEGORIES = new Set<PwaServiceWorkerErrorCategory>([
  'registration',
  'update',
  'cache',
  'navigation',
  'install',
  'activate',
]);
const AI_COACH_ENTRY_POINTS = new Set<AiCoachEntryPoint>([
  'today',
  'progress',
  'nutrition',
  'profile',
]);
const AI_COACH_MODES = new Set<AiCoachMode>(['generic', 'personal']);
const AI_COACH_OUTCOMES = new Set<AiCoachOutcome>([
  'answer',
  'unavailable',
  'rate_limited',
  'safety_refusal',
  'insufficient_data',
  'invalid_output',
  'consent_required',
]);
const AI_COACH_FAILURES = new Set<AiCoachFailureClass>([
  'network',
  'timeout',
  'validation',
  'unknown',
]);
const AI_COACH_HELPFULNESS = new Set<AiCoachHelpfulness>(['helpful', 'not_helpful']);
const LANDING_TELEGRAM_PLACEMENTS = new Set<LandingTelegramPlacement>([
  'hero',
  'continuity',
  'footer',
]);
const BASE_EVENT_KEYS = ['name', 'surface'] as const;
const ENVELOPE_KEYS = ['schema_version', 'environment', 'occurred_at'] as const;
const PROVIDER_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/;
const LOGIN_ATTEMPT_STORAGE_KEY = 'fit_product_analytics_login_attempt';
let loginAttemptPending = false;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowedKeys: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === allowedKeys.length && keys.every((key) => allowedKeys.includes(key));
}

function eventPropertyKeys(name: string): readonly string[] {
  if (name === 'landing_telegram_selected') return ['placement'];
  if (name === 'onboarding_next_action_selected') return ['next_action'];
  if (name === 'today_primary_action_selected') return ['destination'];
  if (name === 'today_week_navigated') return ['direction'];
  if (name === 'food_log_started' || name === 'food_logged') return ['entry_method'];
  if (name === 'tma_core_action_completed') return ['action'];
  if (name === 'telegram_news_cta_clicked') return ['destination', 'campaign'];
  if (name === 'article_viewed') return ['content_key'];
  if (name === 'article_cta_clicked') return ['content_key', 'destination'];
  if (name === 'pwa_service_worker_error') return ['category'];
  if (name === 'ai_coach_entry_opened') return ['entry_point'];
  if (name === 'ai_coach_request_started') return ['mode'];
  if (name === 'ai_coach_response_received') return ['mode', 'outcome'];
  if (name === 'ai_coach_request_failed') return ['mode', 'failure'];
  if (name === 'ai_coach_consent_changed') return ['enabled'];
  if (name === 'ai_coach_helpfulness_submitted') return ['value'];
  return [];
}

function hasValidEventProperties(value: Record<string, unknown>): boolean {
  if (CONTEXT_FREE_EVENT_NAMES.has(value.name as ProductEventName)) return true;
  if (value.name === 'landing_telegram_selected') {
    return LANDING_TELEGRAM_PLACEMENTS.has(value.placement as LandingTelegramPlacement);
  }
  if (value.name === 'onboarding_next_action_selected') {
    return ONBOARDING_NEXT_ACTIONS.has(value.next_action as string);
  }
  if (value.name === 'today_primary_action_selected') {
    return TODAY_DESTINATIONS.has(value.destination as string);
  }
  if (value.name === 'today_week_navigated') {
    return TODAY_WEEK_DIRECTIONS.has(value.direction as string);
  }
  if (value.name === 'food_log_started' || value.name === 'food_logged') {
    return FOOD_ENTRY_METHODS.has(value.entry_method as FoodEntryMethod);
  }
  if (value.name === 'tma_core_action_completed') {
    return value.surface === 'tma' && PRODUCT_CORE_ACTIONS.has(value.action as ProductCoreAction);
  }
  if (value.name === 'telegram_news_cta_clicked') {
    return (
      ['tma', 'web', 'landing', 'article'].includes(value.destination as string) &&
      value.campaign === 'telegram_editorial_v1'
    );
  }
  if (value.name === 'article_viewed') {
    return (
      typeof value.content_key === 'string' && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value.content_key)
    );
  }
  if (value.name === 'article_cta_clicked') {
    return (
      typeof value.content_key === 'string' &&
      /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value.content_key) &&
      ['tma', 'web', 'landing'].includes(value.destination as string)
    );
  }
  if (value.name === 'pwa_service_worker_error') {
    return PWA_SERVICE_WORKER_ERROR_CATEGORIES.has(value.category as PwaServiceWorkerErrorCategory);
  }
  if (value.name === 'ai_coach_entry_opened') {
    return AI_COACH_ENTRY_POINTS.has(value.entry_point as AiCoachEntryPoint);
  }
  if (value.name === 'ai_coach_request_started') {
    return AI_COACH_MODES.has(value.mode as AiCoachMode);
  }
  if (value.name === 'ai_coach_response_received') {
    return (
      AI_COACH_MODES.has(value.mode as AiCoachMode) &&
      AI_COACH_OUTCOMES.has(value.outcome as AiCoachOutcome)
    );
  }
  if (value.name === 'ai_coach_request_failed') {
    return (
      AI_COACH_MODES.has(value.mode as AiCoachMode) &&
      AI_COACH_FAILURES.has(value.failure as AiCoachFailureClass)
    );
  }
  if (value.name === 'ai_coach_consent_changed') {
    return typeof value.enabled === 'boolean';
  }
  if (value.name === 'ai_coach_helpfulness_submitted') {
    return AI_COACH_HELPFULNESS.has(value.value as AiCoachHelpfulness);
  }
  return false;
}

function isProductEventRecord(value: unknown, envelope: boolean): boolean {
  if (!isRecord(value) || typeof value.name !== 'string') return false;

  const eventKeys = [...BASE_EVENT_KEYS, ...eventPropertyKeys(value.name)];
  const allowedKeys = envelope ? [...eventKeys, ...ENVELOPE_KEYS] : eventKeys;
  if (!hasOnlyKeys(value, allowedKeys)) return false;
  if (!PRODUCT_SURFACES.has(value.surface as ProductSurface)) return false;
  if (!hasValidEventProperties(value)) return false;
  if (!envelope) return true;

  if (
    typeof value.occurred_at !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value.occurred_at)
  ) {
    return false;
  }
  const occurredAtTime = Date.parse(value.occurred_at);

  return (
    value.schema_version === PRODUCT_EVENT_SCHEMA_VERSION &&
    PRODUCT_ANALYTICS_ENVIRONMENTS.has(value.environment as ProductAnalyticsEnvironment) &&
    Number.isFinite(occurredAtTime) &&
    new Date(occurredAtTime).toISOString() === value.occurred_at
  );
}

export function isProductEvent(value: unknown): value is ProductEvent {
  return isProductEventRecord(value, false);
}

export function isProductEventEnvelope(value: unknown): value is ProductEventEnvelope {
  return isProductEventRecord(value, true);
}

export function productAnalyticsEnvironment(mode: string): ProductAnalyticsEnvironment {
  if (mode === 'production' || mode === 'staging' || mode === 'test') return mode;
  return 'development';
}

export function productEventSurface(): ProductSurface {
  if (window.Telegram?.WebApp?.initData?.trim()) return 'tma';
  return window.matchMedia?.('(max-width: 767px)').matches ? 'mobile_web' : 'desktop_web';
}

export function createProductAnalytics({
  target,
  environment,
  now = () => new Date(),
}: ProductAnalyticsRuntimeOptions) {
  const sessionDedupe = new Set<string>();

  const reportProviderUnavailable = (provider: ProductAnalyticsProvider) => {
    target.dispatchEvent(
      new CustomEvent<ProductAnalyticsStatus>(PRODUCT_ANALYTICS_STATUS_NAME, {
        detail: Object.freeze({
          provider: provider.name,
          environment,
          reason: 'provider_unavailable',
        }),
      }),
    );
  };

  return {
    track(event: ProductEvent, options: ProductEventTrackOptions = {}): boolean {
      if (!isProductEvent(event)) return false;

      const dedupeKey = `${PRODUCT_EVENT_SCHEMA_VERSION}:${environment}:${event.surface}:${event.name}:${options.dedupeKey ?? 'event'}`;
      if (options.dedupe === 'session') {
        if (sessionDedupe.has(dedupeKey)) return false;
        sessionDedupe.add(dedupeKey);
      }

      const envelope = Object.freeze({
        ...event,
        schema_version: PRODUCT_EVENT_SCHEMA_VERSION,
        environment,
        occurred_at: now().toISOString(),
      }) as ProductEventEnvelope;
      target.dispatchEvent(
        new CustomEvent<ProductEventEnvelope>(PRODUCT_EVENT_NAME, { detail: envelope }),
      );
      return true;
    },

    subscribe(provider: ProductAnalyticsProvider): () => void {
      if (!PROVIDER_NAME_PATTERN.test(provider.name)) {
        throw new Error('Product analytics provider name must be a safe lowercase identifier');
      }
      if (provider.environment !== environment) return () => undefined;

      const listener = (rawEvent: Event) => {
        if (!(rawEvent instanceof CustomEvent) || !isProductEventEnvelope(rawEvent.detail)) return;
        if (rawEvent.detail.environment !== provider.environment) return;

        try {
          if (!provider.isDeliveryAllowed()) return;
          void Promise.resolve(provider.send(rawEvent.detail)).catch(() => {
            reportProviderUnavailable(provider);
          });
        } catch {
          reportProviderUnavailable(provider);
        }
      };
      target.addEventListener(PRODUCT_EVENT_NAME, listener);
      return () => target.removeEventListener(PRODUCT_EVENT_NAME, listener);
    },
  };
}

const browserProductAnalytics = createProductAnalytics({
  target: window,
  environment: productAnalyticsEnvironment(import.meta.env.MODE),
});

export function trackProductEvent(
  event: ProductEvent,
  options?: ProductEventTrackOptions,
): boolean {
  return browserProductAnalytics.track(event, options);
}

export function markProductLoginStarted(): void {
  loginAttemptPending = true;
  try {
    window.sessionStorage.setItem(LOGIN_ATTEMPT_STORAGE_KEY, '1');
  } catch {
    // Analytics must stay non-blocking when browser storage is unavailable.
  }
  trackProductEvent({ name: 'login_started', surface: productEventSurface() });
}

export function clearProductLoginAttempt(): void {
  loginAttemptPending = false;
  try {
    window.sessionStorage.removeItem(LOGIN_ATTEMPT_STORAGE_KEY);
  } catch {
    // Analytics must stay non-blocking when browser storage is unavailable.
  }
}

export function trackProductLoginCompletedIfStarted(): boolean {
  let storedAttempt = false;
  try {
    storedAttempt = window.sessionStorage.getItem(LOGIN_ATTEMPT_STORAGE_KEY) === '1';
  } catch {
    // The in-memory marker still covers SPA login when browser storage is unavailable.
  }
  if (!loginAttemptPending && !storedAttempt) return false;

  clearProductLoginAttempt();
  return trackProductEvent({ name: 'login_completed', surface: productEventSurface() });
}

export function trackCoreProductEvent(
  event: ProductEvent,
  coreAction: ProductCoreAction,
  options?: ProductEventTrackOptions,
): boolean {
  const tracked = browserProductAnalytics.track(event, options);
  if (tracked && event.surface === 'tma') {
    browserProductAnalytics.track({
      name: 'tma_core_action_completed',
      surface: 'tma',
      action: coreAction,
    });
  }
  return tracked;
}

export function subscribeProductAnalyticsProvider(provider: ProductAnalyticsProvider): () => void {
  return browserProductAnalytics.subscribe(provider);
}
