import type { components } from './schema';

export type ApiSchemas = components['schemas'];
export type User = ApiSchemas['UserResponse'];
export type UserProfile = ApiSchemas['UserProfileResponse'];
export type UserProfileUpdate = ApiSchemas['UserProfileUpdate'];
export type Exercise = ApiSchemas['ExerciseCatalogItem'];
export type ExerciseGuide = ApiSchemas['ExerciseGuide'];
export type PublicExerciseSummary = ApiSchemas['PublicExerciseSummary'];
export type PublicExerciseDetail = ApiSchemas['PublicExerciseDetail'];
export type ArticleKind =
  | 'evergreen_explainer'
  | 'practical_guide'
  | 'evidence_review'
  | 'myth_busting'
  | 'research_update'
  | 'comparison'
  | 'product_education';
export interface WebArticleCard {
  slug: string;
  title: string;
  description: string;
  lead: string;
  topics: string[];
  article_kind: ArticleKind;
  published_at: string;
  updated_at: string;
  canonical_url: string;
}
export interface WebArticle extends WebArticleCard {
  body_sections: Array<{ heading: string; paragraphs: string[]; points: string[] }>;
  search_intent: 'informational' | 'how_to' | 'comparison' | 'definition' | 'evidence' | 'mixed';
  primary_query: string;
  secondary_queries: string[];
  risk_level: 'low' | 'moderate' | 'high' | 'critical' | 'unknown';
  evidence_level: 'high' | 'moderate' | 'limited' | 'preliminary' | 'conflicting' | 'unknown';
  claims: Array<{ claim_id: string; claim_text: string; normalized_claim: string }>;
  sources: Array<{
    source_id: string;
    title: string;
    publisher: string;
    url: string;
    source_type: string;
    published_at: string | null;
    limitations: string;
  }>;
  claim_source_matrix: Array<{
    claim_id: string;
    source_ids: string[];
    support_level: 'supports' | 'partially_supports' | 'does_not_support' | 'unclear';
    limitations: string;
    review_status: 'pending' | 'verified' | 'blocked';
  }>;
  author: { name: string; type: 'Organization' | 'Person' };
  editor: { name: string; type: 'Organization' | 'Person' };
  domain_reviewer: { name: string; type: 'Organization' | 'Person' } | null;
  related_slugs: string[];
  cta: { destination: 'tma' | 'web' | 'landing'; label: string; description: string };
  content_version: number;
  generated_with_ai: boolean;
  research_assistance: boolean;
}
export type ProgramTemplate = ApiSchemas['ProgramTemplateResponse'];
export type ProgramTemplateCreate = ApiSchemas['ProgramTemplateCreate'];
export type ProgramImport = ApiSchemas['ProgramImportResponse'];
export type ProgramImportConfirmResponse = ApiSchemas['ProgramImportConfirmResponse'];
export type ProgramImportRow = ApiSchemas['ProgramImportRow'];
export type ProgramImportCandidate = ApiSchemas['ProgramImportCandidate'];
export type ProgramRecommendationRequest = ApiSchemas['ProgramRecommendationRequest'];
export type ProgramRecommendationResponse = ApiSchemas['ProgramRecommendationResponse'];
export type Client = ApiSchemas['ClientResponse'];
export type CoachAssignedProgram = ApiSchemas['CoachAssignedProgramResponse'];
export type Workout = ApiSchemas['WorkoutTodayResponse'];
export type WorkoutStatus = ApiSchemas['WorkoutStatusResponse'];
export type WorkoutScheduleItem = ApiSchemas['WorkoutScheduleItem'];
export type WorkoutHistoryItem = ApiSchemas['WorkoutHistoryItem'];
export type WorkoutHistorySummary = ApiSchemas['WorkoutHistorySummary'];
export type WorkoutAdaptationRequest = ApiSchemas['WorkoutAdaptationRequest'];
export type WorkoutAdaptationPreview = ApiSchemas['WorkoutAdaptationPreviewResponse'];
export type WorkoutAdaptationApply = ApiSchemas['WorkoutAdaptationApplyResponse'];
export type WorkoutAlternative = ApiSchemas['WorkoutAlternativeItem'];
export type BodyMeasurement = ApiSchemas['BodyMeasurementResponse'];
export type BodyMeasurementSave = ApiSchemas['BodyMeasurementSave'];
export type CardioSession = ApiSchemas['CardioSessionResponse'];
export type CardioSessionCreate = ApiSchemas['CardioSessionCreate'];
export type CardioSessionUpdate = ApiSchemas['CardioSessionUpdate'];
export type FoodDiaryDay = ApiSchemas['FoodDiaryDayResponse'];
export type FoodDiaryEntry = ApiSchemas['FoodDiaryEntryResponse'];
export type FoodDiaryMeal = ApiSchemas['FoodDiaryMeal'];
export type FoodDiaryNutrition = ApiSchemas['FoodDiaryNutrition'];
export type Food = ApiSchemas['FoodResponse'];
export type FoodList = ApiSchemas['FoodListResponse'];
export type FoodSearch = ApiSchemas['FoodSearchResponse'];
export type FoodBarcodeLookup = ApiSchemas['FoodBarcodeLookupResponse'];
export type ExternalFood = ApiSchemas['ExternalFoodResponse'];
export type UserFoodCreate = ApiSchemas['UserFoodCreate'];
export type UserFoodUpdate = ApiSchemas['UserFoodUpdate'];
export type Recipe = ApiSchemas['RecipeResponse'];
export type RecipeList = ApiSchemas['RecipeListResponse'];
export type RecipeCreate = ApiSchemas['RecipeCreate'];
export type FoodDiaryCopyResponse = ApiSchemas['FoodDiaryCopyResponse'];
export type NutritionTarget = ApiSchemas['NutritionTargetResponse'];
export type NutritionTargetHistory = ApiSchemas['NutritionTargetHistoryResponse'];
export type NutritionTargetSave = ApiSchemas['NutritionTargetSave'];
export type HydrationDay = ApiSchemas['HydrationDayResponse'];
export type HydrationEntry = ApiSchemas['HydrationEntryResponse'];
export type HydrationGoal = ApiSchemas['HydrationGoalResponse'];
export type HydrationPreset = ApiSchemas['HydrationPresetResponse'];
export type EnergyCalibration = ApiSchemas['EnergyCalibrationResponse'];
export type EnergyCalibrationHistory = ApiSchemas['EnergyCalibrationHistoryResponse'];
export type NotificationItem = ApiSchemas['NotificationResponse'];
export type NotificationSetting = ApiSchemas['NotificationSettingResponse'];
export type WebPushConfig = ApiSchemas['WebPushConfigResponse'];
export type WebPushStatus = ApiSchemas['WebPushStatusResponse'];
export type WebPushSubscriptionRequest = ApiSchemas['WebPushSubscriptionRequest'];
export type ReminderTemplate = ApiSchemas['ReminderTemplateResponse'];
export type ReminderTemplateUpdate = ApiSchemas['ReminderTemplateUpdate'];
export type WeeklyCheckInCurrent = ApiSchemas['WeeklyCheckInCurrentResponse'];
export type WeeklyCheckInHistory = ApiSchemas['WeeklyCheckInHistoryResponse'];
export type WeeklyCheckInSubmit = ApiSchemas['WeeklyCheckInSubmitRequest'];
export type DailyWellbeingCheckIn = ApiSchemas['DailyWellbeingCheckInResponse'];
export type DailyWellbeingCurrent = ApiSchemas['DailyWellbeingCurrentResponse'];
export type DailyWellbeingSave = ApiSchemas['DailyWellbeingCheckInSaveRequest'];
export type DailyWellbeingReport = ApiSchemas['DailyWellbeingReport'];
export type AdminUserSearchResult = ApiSchemas['AdminUserSearchRow'];
export type AdminUserDetail = ApiSchemas['AdminUserDetail'];
export type AdminIdentity = ApiSchemas['AdminIdentityRow'];
export type AdminRelationship = ApiSchemas['AdminRelationshipRow'];
export type AdminJob = ApiSchemas['AdminJobRow'];
export type AdminAudit = ApiSchemas['AdminAuditRow'];
export type AdminFunnel = ApiSchemas['AdminFunnelResponse'];
export type AdminOperationReason = ApiSchemas['AdminOperationRequest']['reason'];
export type TrainerCapability = ApiSchemas['TrainerCapabilityResponse'];
export type InviteLink = ApiSchemas['CoachInviteLinkResponse'];
export type CoachInvitePreview = ApiSchemas['CoachInvitePreviewResponse'];
export type TelegramLinkCreate = ApiSchemas['TelegramLinkCreateResponse'];
export type OAuthLinkCreate = ApiSchemas['OAuthLinkCreateResponse'];
export type AccountExportStatus = ApiSchemas['AccountExportStatusResponse'];
export type AccountExportDownloadLink = ApiSchemas['AccountExportDownloadLinkResponse'];
export type ProgressVolumePoint = ApiSchemas['ProgressVolumePoint'];
export type WorkoutProgress = ApiSchemas['WorkoutProgressResponse'];
export type WorkoutTimelineItem = ApiSchemas['WorkoutTimelineItem'];
export type WorkoutComment = ApiSchemas['WorkoutCommentResponse'];
export type ProgressSummary = ApiSchemas['ProgressSummaryResponse'];
export type ProgressReport = ApiSchemas['ProgressReportResponse'];
export type ProgressReportDownloadLink = ApiSchemas['ProgressReportDownloadLinkResponse'];
export type ReportHandoff = ApiSchemas['ReportHandoffResponse'];
export type ReportHandoffView = ApiSchemas['ReportHandoffViewResponse'];
export type NutritionReport = ApiSchemas['NutritionReportResponse'];
export type NutritionReportPeriod = ApiSchemas['NutritionReportPeriod'];
export type TrainingAnalytics = ApiSchemas['TrainingAnalyticsResponse'];
export type TrainerClientProgressSummary = ApiSchemas['TrainerClientProgressSummary'];
export type TrainerClientProgressList = ApiSchemas['TrainerClientProgressListResponse'];
export type AiCoachResponse = ApiSchemas['AiCoachResponse'];
export type AiCoachConsentResponse = ApiSchemas['AiCoachConsentResponse'];
export type AiCoachStatus = ApiSchemas['AiCoachStatusResponse'];

export interface PublicConfig {
  app_env: string;
  enable_dev_auth: boolean;
  enable_web_auth: boolean;
  enable_email_auth: boolean;
  telegram_bot_username: string;
  oauth_providers: string[];
}
