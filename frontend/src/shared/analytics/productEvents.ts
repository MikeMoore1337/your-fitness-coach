export const PRODUCT_EVENT_NAME = 'yfc:product-event';
export const PRODUCT_ANALYTICS_STATUS_NAME = 'yfc:product-analytics-status';
export const PRODUCT_EVENT_SCHEMA_VERSION = 2 as const;

export type ProductAnalyticsEnvironment = 'production' | 'staging' | 'development' | 'test';
export type ProductSurface = 'desktop_web' | 'mobile_web' | 'tma';
export type FoodEntryMethod =
  | 'quick_add'
  | 'recent'
  | 'favorite'
  | 'frequent'
  | 'personal'
  | 'search'
  | 'recipe'
  | 'barcode'
  | 'custom'
  | 'label_scan';
export type NutritionFoodAddPath = 'photo' | 'search' | 'manual' | 'repeat' | 'quick_add';
export type NutritionFoodSearchOutcome = 'success' | 'no_result';
export type NutritionFoodSource =
  'personal' | 'frequent' | 'recent' | 'favorite' | 'shared' | 'local' | 'external';
export type NutritionFoodClassification = 'commercial' | 'personal';
export type NutritionFoodContributionOutcome = 'created' | 'reused' | 'duplicate' | 'conflict';
export type NutritionFoodRepeatScope = 'product' | 'meal' | 'day';
export type NutritionFoodRepeatOutcome = 'started' | 'completed';
export type NutritionFoodCompletenessStatus = 'complete' | 'incomplete' | 'unlogged' | 'fasted';
export type NutritionPowerFlow = 'meal_template' | 'natural_input';
export type NutritionPowerOutcome = 'success' | 'validation_error' | 'unavailable';
export type ProductCoreAction =
  | 'program_activated'
  | 'workout_started'
  | 'workout_completed'
  | 'food_logged'
  | 'measurement_logged'
  | 'weekly_review_completed';
export type NextActionAnalyticsKind =
  | 'active_workout'
  | 'trainer_feedback'
  | 'scheduled_workout'
  | 'weekly_review'
  | 'ready_program'
  | 'create_program'
  | 'workout_result'
  | 'nutrition'
  | 'activity'
  | 'profile';
export type NextActionPosition = 'primary' | 'secondary';
export type ProductSection =
  'today' | 'progress' | 'programs' | 'nutrition' | 'catalog' | 'profile' | 'coach' | 'admin';
export type QuickAddAnalyticsKind = 'food' | 'water' | 'cardio' | 'measurement' | 'wellbeing';
export type OnboardingLatencyBucket =
  'under_10s' | '10_30s' | '30_60s' | '1_5m' | '5_15m' | 'over_15m';
export type PwaServiceWorkerErrorCategory =
  'registration' | 'update' | 'cache' | 'navigation' | 'install' | 'activate';
export type LandingTelegramPlacement = 'hero' | 'continuity' | 'footer';
export type EditorialCtaDestination = 'tma' | 'web' | 'landing' | 'article';
export type EditorialCtaCampaign = 'telegram_editorial_v1';
export type PublicArticleCtaDestination = 'tma' | 'web' | 'landing';
export type AiCoachEntryPoint =
  'today' | 'workout' | 'nutrition' | 'program' | 'progress' | 'profile';
export type CoachAttentionKind =
  'workout_feedback' | 'weekly_check_in' | 'missed_workout' | 'skipped_workout' | 'without_program';
export type CoachAttentionLatencyBucket = 'under_250ms' | '250_1000ms' | 'over_1s';
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
export type DemoAnalyticsScenario = 'self_training' | 'nutrition' | 'trainer';
export type DemoLandingPlacement = 'hero' | 'section' | 'continuity' | 'footer';
export type DemoMeaningfulAction = 'finish_workout' | 'add_recent' | 'save_comment';

export const IMPLEMENTED_GROWTH_EVENT_NAMES = [
  'registration_started',
  'registration_completed',
  'onboarding_completed',
  'first_workout_started',
  'first_workout_completed',
  'first_food_entry_added',
  'program_added',
  'trainer_application_started',
  'trainer_application_completed',
  'client_invited',
  'share_created',
  'calculator_started',
  'calculator_result',
] as const;

export const FUTURE_GROWTH_EVENT_NAMES = [
  'calculator_saved',
  'public_program_opened',
  'public_program_saved',
  'exercise_added_from_public_page',
] as const;

export type ImplementedGrowthEventName = (typeof IMPLEMENTED_GROWTH_EVENT_NAMES)[number];
export type GrowthEventName =
  ImplementedGrowthEventName | (typeof FUTURE_GROWTH_EVENT_NAMES)[number];

export const GROWTH_GOAL_IDS: Readonly<Record<GrowthEventName, GrowthEventName>> = {
  registration_started: 'registration_started',
  registration_completed: 'registration_completed',
  onboarding_completed: 'onboarding_completed',
  first_workout_started: 'first_workout_started',
  first_workout_completed: 'first_workout_completed',
  first_food_entry_added: 'first_food_entry_added',
  program_added: 'program_added',
  trainer_application_started: 'trainer_application_started',
  trainer_application_completed: 'trainer_application_completed',
  client_invited: 'client_invited',
  share_created: 'share_created',
  calculator_started: 'calculator_started',
  calculator_result: 'calculator_result',
  calculator_saved: 'calculator_saved',
  public_program_opened: 'public_program_opened',
  public_program_saved: 'public_program_saved',
  exercise_added_from_public_page: 'exercise_added_from_public_page',
};

type ContextFreeProductEventName =
  | 'landing_viewed'
  | 'landing_app_selected'
  | 'landing_login_selected'
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
  | 'previous_set_reuse_used'
  | 'pwa_update_available'
  | 'pwa_update_applied'
  | 'nutrition_label_scan_started'
  | 'nutrition_label_scan_capture_selected'
  | 'nutrition_label_scan_recognition_succeeded'
  | 'nutrition_label_scan_recognition_failed'
  | 'nutrition_label_scan_result_success'
  | 'nutrition_label_scan_result_retake'
  | 'nutrition_label_scan_result_unavailable'
  | 'nutrition_label_scan_retry'
  | 'nutrition_label_scan_correction_occurred'
  | 'nutrition_label_scan_barcode_hit'
  | 'nutrition_label_scan_barcode_miss'
  | 'nutrition_label_scan_reviewed'
  | 'nutrition_label_scan_confirmed'
  | 'nutrition_label_scan_cancelled'
  | 'nutrition_label_catalog_saved_shared'
  | 'nutrition_label_catalog_saved_private'
  | 'nutrition_label_community_product_reused'
  | 'yfc_food_catalog_local_hit'
  | 'yfc_food_catalog_external_fallback';

type ContextFreeProductEvent = {
  name: ContextFreeProductEventName;
  surface: ProductSurface;
};

type GrowthProductEvent = {
  name: GrowthEventName;
  surface: ProductSurface;
};

export type ProductEvent =
  | ContextFreeProductEvent
  | GrowthProductEvent
  | {
      name: 'landing_demo_selected';
      surface: ProductSurface;
      placement: DemoLandingPlacement;
      scenario: DemoAnalyticsScenario;
    }
  | {
      name:
        | 'demo_started'
        | 'demo_scenario_selected'
        | 'demo_route_started'
        | 'demo_route_completed'
        | 'demo_route_hidden'
        | 'demo_route_reopened'
        | 'demo_own_data_selected';
      surface: ProductSurface;
      scenario: DemoAnalyticsScenario;
    }
  | {
      name: 'demo_meaningful_action_completed';
      surface: ProductSurface;
      scenario: DemoAnalyticsScenario;
      action: DemoMeaningfulAction;
    }
  | {
      name: 'demo_other_scenario_selected';
      surface: ProductSurface;
      from_scenario: DemoAnalyticsScenario;
      to_scenario: DemoAnalyticsScenario;
    }
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
      name: 'next_action_shown' | 'next_action_clicked' | 'next_action_completed';
      surface: ProductSurface;
      action_kind: NextActionAnalyticsKind;
      position: NextActionPosition;
    }
  | {
      name: 'onboarding_first_useful_action';
      surface: ProductSurface;
      latency_bucket: OnboardingLatencyBucket;
    }
  | {
      name: 'quick_add_action_selected';
      surface: ProductSurface;
      action: QuickAddAnalyticsKind;
    }
  | {
      name: 'section_navigation_selected';
      surface: ProductSurface;
      from_section: ProductSection;
      to_section: ProductSection;
    }
  | {
      name: 'food_log_started' | 'food_logged';
      surface: ProductSurface;
      entry_method: FoodEntryMethod;
    }
  | {
      name: 'nutrition_food_add_path_selected';
      surface: ProductSurface;
      path: NutritionFoodAddPath;
    }
  | {
      name: 'nutrition_food_search_result';
      surface: ProductSurface;
      outcome: NutritionFoodSearchOutcome;
    }
  | {
      name: 'nutrition_food_source_selected';
      surface: ProductSurface;
      source: NutritionFoodSource;
    }
  | {
      name: 'nutrition_food_classification_selected';
      surface: ProductSurface;
      classification: NutritionFoodClassification;
    }
  | {
      name: 'nutrition_food_catalog_contribution_outcome';
      surface: ProductSurface;
      outcome: NutritionFoodContributionOutcome;
    }
  | {
      name: 'nutrition_food_flow_timing';
      surface: ProductSurface;
      path: NutritionFoodAddPath;
      duration_bucket: OnboardingLatencyBucket;
    }
  | {
      name: 'nutrition_food_repeat_used';
      surface: ProductSurface;
      scope: NutritionFoodRepeatScope;
      outcome: NutritionFoodRepeatOutcome;
    }
  | {
      name: 'nutrition_food_completeness_set';
      surface: ProductSurface;
      status: NutritionFoodCompletenessStatus;
    }
  | {
      name: 'nutrition_power_flow_completed';
      surface: ProductSurface;
      flow: NutritionPowerFlow;
      outcome: NutritionPowerOutcome;
    }
  | {
      name: 'nutrition_power_flow_timing';
      surface: ProductSurface;
      flow: NutritionPowerFlow;
      duration_bucket: OnboardingLatencyBucket;
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
      name: 'coach_attention_shown' | 'coach_attention_opened' | 'coach_attention_resolved';
      surface: ProductSurface;
      kind: CoachAttentionKind;
    }
  | {
      name: 'coach_attention_load_timing';
      surface: ProductSurface;
      latency_bucket: CoachAttentionLatencyBucket;
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
  'landing_login_selected',
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
  'previous_set_reuse_used',
  'pwa_update_available',
  'pwa_update_applied',
  'nutrition_label_scan_started',
  'nutrition_label_scan_capture_selected',
  'nutrition_label_scan_recognition_succeeded',
  'nutrition_label_scan_recognition_failed',
  'nutrition_label_scan_result_success',
  'nutrition_label_scan_result_retake',
  'nutrition_label_scan_result_unavailable',
  'nutrition_label_scan_retry',
  'nutrition_label_scan_correction_occurred',
  'nutrition_label_scan_barcode_hit',
  'nutrition_label_scan_barcode_miss',
  'nutrition_label_scan_reviewed',
  'nutrition_label_scan_confirmed',
  'nutrition_label_scan_cancelled',
  'nutrition_label_catalog_saved_shared',
  'nutrition_label_catalog_saved_private',
  'nutrition_label_community_product_reused',
  'yfc_food_catalog_local_hit',
  'yfc_food_catalog_external_fallback',
  ...IMPLEMENTED_GROWTH_EVENT_NAMES,
  ...FUTURE_GROWTH_EVENT_NAMES,
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
  'label_scan',
  'personal',
  'frequent',
]);
const NUTRITION_FOOD_ADD_PATHS = new Set<NutritionFoodAddPath>([
  'photo',
  'search',
  'manual',
  'repeat',
  'quick_add',
]);
const NUTRITION_FOOD_SEARCH_OUTCOMES = new Set<NutritionFoodSearchOutcome>([
  'success',
  'no_result',
]);
const NUTRITION_FOOD_SOURCES = new Set<NutritionFoodSource>([
  'personal',
  'frequent',
  'recent',
  'favorite',
  'shared',
  'local',
  'external',
]);
const NUTRITION_FOOD_CLASSIFICATIONS = new Set<NutritionFoodClassification>([
  'commercial',
  'personal',
]);
const NUTRITION_FOOD_CONTRIBUTION_OUTCOMES = new Set<NutritionFoodContributionOutcome>([
  'created',
  'reused',
  'duplicate',
  'conflict',
]);
const NUTRITION_FOOD_REPEAT_SCOPES = new Set<NutritionFoodRepeatScope>(['product', 'meal', 'day']);
const NUTRITION_FOOD_REPEAT_OUTCOMES = new Set<NutritionFoodRepeatOutcome>([
  'started',
  'completed',
]);
const NUTRITION_FOOD_COMPLETENESS_STATUSES = new Set<NutritionFoodCompletenessStatus>([
  'complete',
  'incomplete',
  'unlogged',
  'fasted',
]);
const NUTRITION_POWER_FLOWS = new Set<NutritionPowerFlow>(['meal_template', 'natural_input']);
const NUTRITION_POWER_OUTCOMES = new Set<NutritionPowerOutcome>([
  'success',
  'validation_error',
  'unavailable',
]);
const PRODUCT_CORE_ACTIONS = new Set<ProductCoreAction>([
  'program_activated',
  'workout_started',
  'workout_completed',
  'food_logged',
  'measurement_logged',
  'weekly_review_completed',
]);
const NEXT_ACTION_KINDS = new Set<NextActionAnalyticsKind>([
  'active_workout',
  'trainer_feedback',
  'scheduled_workout',
  'weekly_review',
  'ready_program',
  'create_program',
  'workout_result',
  'nutrition',
  'activity',
  'profile',
]);
const NEXT_ACTION_POSITIONS = new Set<NextActionPosition>(['primary', 'secondary']);
const PRODUCT_SECTIONS = new Set<ProductSection>([
  'today',
  'progress',
  'programs',
  'nutrition',
  'catalog',
  'profile',
  'coach',
  'admin',
]);
const QUICK_ADD_ACTIONS = new Set<QuickAddAnalyticsKind>([
  'food',
  'water',
  'cardio',
  'measurement',
  'wellbeing',
]);
const ONBOARDING_LATENCY_BUCKETS = new Set<OnboardingLatencyBucket>([
  'under_10s',
  '10_30s',
  '30_60s',
  '1_5m',
  '5_15m',
  'over_15m',
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
  'workout',
  'progress',
  'nutrition',
  'program',
  'profile',
]);
const COACH_ATTENTION_KINDS = new Set<CoachAttentionKind>([
  'workout_feedback',
  'weekly_check_in',
  'missed_workout',
  'skipped_workout',
  'without_program',
]);
const COACH_ATTENTION_LATENCY_BUCKETS = new Set<CoachAttentionLatencyBucket>([
  'under_250ms',
  '250_1000ms',
  'over_1s',
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
const DEMO_SCENARIOS = new Set<DemoAnalyticsScenario>(['self_training', 'nutrition', 'trainer']);
const DEMO_LANDING_PLACEMENTS = new Set<DemoLandingPlacement>([
  'hero',
  'section',
  'continuity',
  'footer',
]);
const DEMO_MEANINGFUL_ACTIONS = new Set<DemoMeaningfulAction>([
  'finish_workout',
  'add_recent',
  'save_comment',
]);
const LANDING_TELEGRAM_PLACEMENTS = new Set<LandingTelegramPlacement>([
  'hero',
  'continuity',
  'footer',
]);
const BASE_EVENT_KEYS = ['name', 'surface'] as const;
const ENVELOPE_KEYS = ['schema_version', 'environment', 'occurred_at'] as const;
const PROVIDER_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/;
const LOGIN_ATTEMPT_STORAGE_KEY = 'fit_product_analytics_login_attempt';
const ONBOARDING_COMPLETED_AT_STORAGE_KEY = 'fit_product_analytics_onboarding_completed_at';
const MAX_ONBOARDING_FIRST_ACTION_AGE_MS = 30 * 24 * 60 * 60 * 1000;
let loginAttemptPending = false;

const USEFUL_ACTION_EVENT_NAMES = new Set<ProductEventName>([
  'next_action_clicked',
  'next_action_completed',
  'previous_set_reuse_used',
  'quick_add_action_selected',
  'section_navigation_selected',
  'workout_started',
  'workout_completed',
  'food_logged',
  'measurement_logged',
  'weekly_review_completed',
  'cardio_logged',
  'check_in_logged',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowedKeys: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === allowedKeys.length && keys.every((key) => allowedKeys.includes(key));
}

function eventPropertyKeys(name: string): readonly string[] {
  if (name === 'landing_demo_selected') return ['placement', 'scenario'];
  if (
    name === 'demo_started' ||
    name === 'demo_scenario_selected' ||
    name === 'demo_route_started' ||
    name === 'demo_route_completed' ||
    name === 'demo_route_hidden' ||
    name === 'demo_route_reopened' ||
    name === 'demo_own_data_selected'
  )
    return ['scenario'];
  if (name === 'demo_meaningful_action_completed') return ['scenario', 'action'];
  if (name === 'demo_other_scenario_selected') return ['from_scenario', 'to_scenario'];
  if (name === 'landing_telegram_selected') return ['placement'];
  if (name === 'onboarding_next_action_selected') return ['next_action'];
  if (name === 'today_primary_action_selected') return ['destination'];
  if (name === 'today_week_navigated') return ['direction'];
  if (
    name === 'next_action_shown' ||
    name === 'next_action_clicked' ||
    name === 'next_action_completed'
  )
    return ['action_kind', 'position'];
  if (name === 'onboarding_first_useful_action') return ['latency_bucket'];
  if (name === 'quick_add_action_selected') return ['action'];
  if (name === 'section_navigation_selected') return ['from_section', 'to_section'];
  if (name === 'food_log_started' || name === 'food_logged') return ['entry_method'];
  if (name === 'nutrition_food_add_path_selected') return ['path'];
  if (name === 'nutrition_food_search_result') return ['outcome'];
  if (name === 'nutrition_food_source_selected') return ['source'];
  if (name === 'nutrition_food_classification_selected') return ['classification'];
  if (name === 'nutrition_food_catalog_contribution_outcome') return ['outcome'];
  if (name === 'nutrition_food_flow_timing') return ['path', 'duration_bucket'];
  if (name === 'nutrition_food_repeat_used') return ['scope', 'outcome'];
  if (name === 'nutrition_food_completeness_set') return ['status'];
  if (name === 'nutrition_power_flow_completed') return ['flow', 'outcome'];
  if (name === 'nutrition_power_flow_timing') return ['flow', 'duration_bucket'];
  if (name === 'tma_core_action_completed') return ['action'];
  if (name === 'telegram_news_cta_clicked') return ['destination', 'campaign'];
  if (name === 'article_viewed') return ['content_key'];
  if (name === 'article_cta_clicked') return ['content_key', 'destination'];
  if (name === 'pwa_service_worker_error') return ['category'];
  if (name === 'ai_coach_entry_opened') return ['entry_point'];
  if (
    name === 'coach_attention_shown' ||
    name === 'coach_attention_opened' ||
    name === 'coach_attention_resolved'
  )
    return ['kind'];
  if (name === 'coach_attention_load_timing') return ['latency_bucket'];
  if (name === 'ai_coach_request_started') return ['mode'];
  if (name === 'ai_coach_response_received') return ['mode', 'outcome'];
  if (name === 'ai_coach_request_failed') return ['mode', 'failure'];
  if (name === 'ai_coach_consent_changed') return ['enabled'];
  if (name === 'ai_coach_helpfulness_submitted') return ['value'];
  return [];
}

function hasValidEventProperties(value: Record<string, unknown>): boolean {
  if (CONTEXT_FREE_EVENT_NAMES.has(value.name as ProductEventName)) return true;
  if (value.name === 'landing_demo_selected') {
    return (
      DEMO_LANDING_PLACEMENTS.has(value.placement as DemoLandingPlacement) &&
      DEMO_SCENARIOS.has(value.scenario as DemoAnalyticsScenario)
    );
  }
  if (
    value.name === 'demo_started' ||
    value.name === 'demo_scenario_selected' ||
    value.name === 'demo_route_started' ||
    value.name === 'demo_route_completed' ||
    value.name === 'demo_route_hidden' ||
    value.name === 'demo_route_reopened' ||
    value.name === 'demo_own_data_selected'
  ) {
    return DEMO_SCENARIOS.has(value.scenario as DemoAnalyticsScenario);
  }
  if (value.name === 'demo_meaningful_action_completed') {
    return (
      DEMO_SCENARIOS.has(value.scenario as DemoAnalyticsScenario) &&
      DEMO_MEANINGFUL_ACTIONS.has(value.action as DemoMeaningfulAction)
    );
  }
  if (value.name === 'demo_other_scenario_selected') {
    return (
      DEMO_SCENARIOS.has(value.from_scenario as DemoAnalyticsScenario) &&
      DEMO_SCENARIOS.has(value.to_scenario as DemoAnalyticsScenario) &&
      value.from_scenario !== value.to_scenario
    );
  }
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
  if (
    value.name === 'next_action_shown' ||
    value.name === 'next_action_clicked' ||
    value.name === 'next_action_completed'
  ) {
    return (
      NEXT_ACTION_KINDS.has(value.action_kind as NextActionAnalyticsKind) &&
      NEXT_ACTION_POSITIONS.has(value.position as NextActionPosition)
    );
  }
  if (value.name === 'onboarding_first_useful_action') {
    return ONBOARDING_LATENCY_BUCKETS.has(value.latency_bucket as OnboardingLatencyBucket);
  }
  if (value.name === 'quick_add_action_selected') {
    return QUICK_ADD_ACTIONS.has(value.action as QuickAddAnalyticsKind);
  }
  if (value.name === 'section_navigation_selected') {
    return (
      PRODUCT_SECTIONS.has(value.from_section as ProductSection) &&
      PRODUCT_SECTIONS.has(value.to_section as ProductSection) &&
      value.from_section !== value.to_section
    );
  }
  if (value.name === 'food_log_started' || value.name === 'food_logged') {
    return FOOD_ENTRY_METHODS.has(value.entry_method as FoodEntryMethod);
  }
  if (value.name === 'nutrition_food_add_path_selected') {
    return NUTRITION_FOOD_ADD_PATHS.has(value.path as NutritionFoodAddPath);
  }
  if (value.name === 'nutrition_food_search_result') {
    return NUTRITION_FOOD_SEARCH_OUTCOMES.has(value.outcome as NutritionFoodSearchOutcome);
  }
  if (value.name === 'nutrition_food_source_selected') {
    return NUTRITION_FOOD_SOURCES.has(value.source as NutritionFoodSource);
  }
  if (value.name === 'nutrition_food_classification_selected') {
    return NUTRITION_FOOD_CLASSIFICATIONS.has(value.classification as NutritionFoodClassification);
  }
  if (value.name === 'nutrition_food_catalog_contribution_outcome') {
    return NUTRITION_FOOD_CONTRIBUTION_OUTCOMES.has(
      value.outcome as NutritionFoodContributionOutcome,
    );
  }
  if (value.name === 'nutrition_food_flow_timing') {
    return (
      NUTRITION_FOOD_ADD_PATHS.has(value.path as NutritionFoodAddPath) &&
      ONBOARDING_LATENCY_BUCKETS.has(value.duration_bucket as OnboardingLatencyBucket)
    );
  }
  if (value.name === 'nutrition_food_repeat_used') {
    return (
      NUTRITION_FOOD_REPEAT_SCOPES.has(value.scope as NutritionFoodRepeatScope) &&
      NUTRITION_FOOD_REPEAT_OUTCOMES.has(value.outcome as NutritionFoodRepeatOutcome)
    );
  }
  if (value.name === 'nutrition_food_completeness_set') {
    return NUTRITION_FOOD_COMPLETENESS_STATUSES.has(
      value.status as NutritionFoodCompletenessStatus,
    );
  }
  if (value.name === 'nutrition_power_flow_completed') {
    return (
      NUTRITION_POWER_FLOWS.has(value.flow as NutritionPowerFlow) &&
      NUTRITION_POWER_OUTCOMES.has(value.outcome as NutritionPowerOutcome)
    );
  }
  if (value.name === 'nutrition_power_flow_timing') {
    return (
      NUTRITION_POWER_FLOWS.has(value.flow as NutritionPowerFlow) &&
      ONBOARDING_LATENCY_BUCKETS.has(value.duration_bucket as OnboardingLatencyBucket)
    );
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
  if (
    value.name === 'coach_attention_shown' ||
    value.name === 'coach_attention_opened' ||
    value.name === 'coach_attention_resolved'
  ) {
    return COACH_ATTENTION_KINDS.has(value.kind as CoachAttentionKind);
  }
  if (value.name === 'coach_attention_load_timing') {
    return COACH_ATTENTION_LATENCY_BUCKETS.has(value.latency_bucket as CoachAttentionLatencyBucket);
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

export function isQuickAddAnalyticsKind(value: string): value is QuickAddAnalyticsKind {
  return QUICK_ADD_ACTIONS.has(value as QuickAddAnalyticsKind);
}

function onboardingLatencyBucket(elapsedMs: number): OnboardingLatencyBucket {
  if (elapsedMs < 10_000) return 'under_10s';
  if (elapsedMs < 30_000) return '10_30s';
  if (elapsedMs < 60_000) return '30_60s';
  if (elapsedMs < 5 * 60_000) return '1_5m';
  if (elapsedMs < 15 * 60_000) return '5_15m';
  return 'over_15m';
}

export function markProductOnboardingCompleted(): void {
  try {
    window.sessionStorage.setItem(ONBOARDING_COMPLETED_AT_STORAGE_KEY, String(Date.now()));
  } catch {
    // Analytics must stay non-blocking when browser storage is unavailable.
  }
}

export function clearProductOnboardingCompletionMarker(): void {
  try {
    window.sessionStorage.removeItem(ONBOARDING_COMPLETED_AT_STORAGE_KEY);
  } catch {
    // Analytics must stay non-blocking when browser storage is unavailable.
  }
}

function trackOnboardingFirstUsefulActionIfPending(): void {
  let completedAt: number | null = null;
  try {
    const raw = window.sessionStorage.getItem(ONBOARDING_COMPLETED_AT_STORAGE_KEY);
    const parsed = raw === null ? Number.NaN : Number(raw);
    if (Number.isFinite(parsed)) completedAt = parsed;
  } catch {
    return;
  }
  if (completedAt === null) return;

  const elapsedMs = Math.max(0, Date.now() - completedAt);
  clearProductOnboardingCompletionMarker();
  if (elapsedMs > MAX_ONBOARDING_FIRST_ACTION_AGE_MS) return;
  trackProductEvent({
    name: 'onboarding_first_useful_action',
    surface: productEventSurface(),
    latency_bucket: onboardingLatencyBucket(elapsedMs),
  });
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
  const tracked = browserProductAnalytics.track(event, options);
  if (tracked && USEFUL_ACTION_EVENT_NAMES.has(event.name)) {
    trackOnboardingFirstUsefulActionIfPending();
  }
  return tracked;
}

export function trackGrowthEvent(
  name: ImplementedGrowthEventName,
  options?: ProductEventTrackOptions,
): boolean {
  return trackProductEvent({ name, surface: productEventSurface() }, options);
}

export function isGrowthGoalEvent(name: ProductEventName): name is GrowthEventName {
  return Object.prototype.hasOwnProperty.call(GROWTH_GOAL_IDS, name);
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
  const tracked = trackProductEvent(event, options);
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
