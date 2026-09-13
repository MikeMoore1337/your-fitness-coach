export const AUTHENTICATED_USER_ID_STORAGE_KEY = 'fit_authenticated_user_id';

export const ACTIVE_WORKOUT_STORAGE_PREFIXES = {
  queue: 'fit_active_workout_v1_',
  rest: 'fit_active_workout_rest_v1_',
  pointer: 'fit_active_workout_current_v1_user_',
} as const;

export const LEGACY_ACTIVE_WORKOUT_STORAGE_PREFIXES = [
  'fit_workout_set_',
  'fit_workout_pending_',
  'fit_workout_rest_deadline_',
] as const;

export const USER_SCOPED_PERSISTENT_STORAGE_REGISTRY = [
  {
    domain: 'active_workout',
    prefixes: [
      ACTIVE_WORKOUT_STORAGE_PREFIXES.queue,
      ACTIVE_WORKOUT_STORAGE_PREFIXES.rest,
      ACTIVE_WORKOUT_STORAGE_PREFIXES.pointer,
      ...LEGACY_ACTIVE_WORKOUT_STORAGE_PREFIXES,
    ],
  },
  { domain: 'food_draft', prefixes: ['fit_food_draft_'] },
  { domain: 'nutrition_label_draft', prefixes: ['fit_nutrition_label_draft_v1_'] },
  { domain: 'measurement_draft', prefixes: ['fit_measurement_draft_'] },
  { domain: 'nutrition_draft', prefixes: ['fit_nutrition_draft_v2_', 'fit_nutrition_draft_'] },
  { domain: 'profile_draft', prefixes: ['fit_profile_draft_'] },
  { domain: 'training_preferences_draft', prefixes: ['fit_training_preferences_draft_'] },
  { domain: 'coach_client_profile_draft', prefixes: ['fit_coach_client_profile_draft_'] },
  { domain: 'notification_draft', prefixes: ['fit_notification_draft_'] },
  { domain: 'weekly_review_draft', prefixes: ['fit_weekly_review_draft_v1_'] },
  {
    domain: 'program_draft',
    prefixes: [
      'fit_program_title_',
      'fit_program_goal_',
      'fit_program_level_',
      'fit_program_days_',
      'fit_program_rest_',
      'fit_program_start_',
      'fit_program_duration_',
      'fit_program_weekdays_',
    ],
  },
] as const;

const SENSITIVE_LOCAL_STORAGE_EXACT_KEYS = ['fit_access_token', 'fit_refresh_token'] as const;

const sensitiveLocalStoragePrefixes = USER_SCOPED_PERSISTENT_STORAGE_REGISTRY.flatMap(
  ({ prefixes }) => prefixes,
);

export function activeWorkoutQueueStorageKey(userId: number, workoutId: number): string {
  return `${ACTIVE_WORKOUT_STORAGE_PREFIXES.queue}user_${userId}_workout_${workoutId}`;
}

export function activeWorkoutRestStorageKey(userId: number, workoutId: number): string {
  return `${ACTIVE_WORKOUT_STORAGE_PREFIXES.rest}user_${userId}_workout_${workoutId}`;
}

export function activeWorkoutPointerStorageKey(userId: number): string {
  return `${ACTIVE_WORKOUT_STORAGE_PREFIXES.pointer}${userId}`;
}

export function legacyWorkoutSetStorageKey(setId: number): string {
  return `fit_workout_set_${setId}`;
}

export function legacyWorkoutPendingStorageKey(setId: number): string {
  return `fit_workout_pending_${setId}`;
}

export function legacyWorkoutRestStorageKey(workoutId: number): string {
  return `fit_workout_rest_deadline_${workoutId}`;
}

export function foodDraftStorageKey(
  userId: number | 'anonymous',
  diaryDate: string,
  mealType: string,
): string {
  return `fit_food_draft_${userId}_${diaryDate}_${mealType}`;
}

export function nutritionLabelDraftStorageKey(userId: number | 'anonymous'): string {
  return `fit_nutrition_label_draft_v1_${userId}`;
}

export function measurementDraftStorageKey(scope: string): string {
  return `fit_measurement_draft_${scope}`;
}

export function nutritionDraftStorageKey(scope: string): string {
  return `fit_nutrition_draft_v2_${scope}`;
}

export function profileDraftStorageKey(userId: number | 'anonymous'): string {
  return `fit_profile_draft_${userId}`;
}

export function trainingPreferencesDraftStorageKey(userId: number | 'anonymous'): string {
  return `fit_training_preferences_draft_${userId}`;
}

export function coachClientProfileDraftStorageKey(clientId: number | null | undefined): string {
  return `fit_coach_client_profile_draft_${clientId}`;
}

export function notificationDraftStorageKey(userId: number | 'anonymous'): string {
  return `fit_notification_draft_${userId}`;
}

export function weeklyReviewDraftStorageKey(userId: number | 'anonymous'): string {
  return `fit_weekly_review_draft_v1_${userId}`;
}

export function programDraftStorageKey(
  field: 'title' | 'goal' | 'level' | 'days' | 'rest' | 'start' | 'duration' | 'weekdays',
  scope: string,
): string {
  return `fit_program_${field}_${scope}`;
}

export function clearSensitiveUserScopedStorage(): void {
  try {
    const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index));
    for (const key of keys) {
      if (
        key &&
        (SENSITIVE_LOCAL_STORAGE_EXACT_KEYS.some((candidate) => candidate === key) ||
          sensitiveLocalStoragePrefixes.some((prefix) => key.startsWith(prefix)))
      ) {
        localStorage.removeItem(key);
      }
    }
  } catch {
    // Storage is optional in restrictive webviews.
  }

  try {
    sessionStorage.removeItem(AUTHENTICATED_USER_ID_STORAGE_KEY);
  } catch {
    // Storage is optional in restrictive webviews.
  }
}
