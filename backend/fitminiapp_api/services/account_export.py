from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from fitminiapp_api.models.ai_coach import AiCoachConsent, AiCoachMemory, AiCoachMemoryConsent
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.auth_identity import AuthIdentity, LocalCredential
from fitminiapp_api.models.cardio import CardioSession
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.daily_wellbeing import DailyWellbeingCheckIn
from fitminiapp_api.models.exercise import (
    Exercise,
    ExerciseAlternative,
    ExerciseEquipment,
    ExerciseMuscle,
)
from fitminiapp_api.models.feedback import WorkoutComment
from fitminiapp_api.models.food import Food, FoodFavorite
from fitminiapp_api.models.food_diary import (
    FoodDiaryCopyOperation,
    FoodDiaryDayStatus,
    FoodDiaryEntry,
)
from fitminiapp_api.models.hydration import HydrationEntry, HydrationGoal, HydrationPreset
from fitminiapp_api.models.notification import (
    Notification,
    NotificationDelivery,
    NotificationSetting,
    WebPushSubscription,
)
from fitminiapp_api.models.nutrition import EnergyCalibration, NutritionTarget
from fitminiapp_api.models.program import (
    HiddenProgramTemplate,
    ProgramTemplate,
    ProgramTemplateDay,
    ProgramTemplateExercise,
    TrainingBlock,
    TrainingBlockPriorityMuscle,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.recipe import Recipe
from fitminiapp_api.models.reminder_template import ReminderTemplateSchedule
from fitminiapp_api.models.report_handoff import ReportHandoff
from fitminiapp_api.models.user import (
    BodyMeasurement,
    CoachClient,
    CoachRoleApplication,
    User,
)
from fitminiapp_api.models.weekly_digest import WeeklyDigestDelivery, WeeklyDigestPreference
from fitminiapp_api.services.profile import serialize_body_priority

if TYPE_CHECKING:
    from fitminiapp_api.models.recipe import RecipeIngredient


ACCOUNT_EXPORT_SCHEMA_VERSION = 11

# Every ORM table whose rows can be reached from users through ownership or actor FKs must be
# classified here. Tests compare this inventory with SQLAlchemy metadata so a new persistent user
# domain cannot silently bypass an export/privacy decision.
ACCOUNT_EXPORT_DATA_INVENTORY: dict[str, str] = {
    "users": "account",
    "auth_identities": "auth_identities",
    "local_credentials": "local_credential",
    "user_profiles": "profile",
    "user_profile_priority_muscles": "profile",
    "body_measurements": "measurements",
    "cardio_sessions": "cardio_sessions",
    "nutrition_targets": "nutrition",
    "hydration_goals": "hydration",
    "hydration_entries": "hydration",
    "hydration_presets": "hydration",
    "energy_calibrations": "energy_calibrations",
    "weekly_check_ins": "weekly_check_ins",
    "daily_wellbeing_check_ins": "daily_wellbeing_check_ins",
    "foods": "private_foods",
    "food_favorites": "food_favorites",
    "recipes": "recipes",
    "recipe_ingredients": "recipes",
    "food_diary_entries": "food_diary_entries",
    "food_diary_day_statuses": "food_diary_day_statuses",
    "food_diary_copy_operations": "food_diary_copy_operations",
    "program_templates": "program_templates",
    "program_template_days": "program_templates",
    "program_template_exercises": "program_templates",
    "program_template_exercise_weeks": "program_templates",
    "hidden_program_templates": "hidden_program_templates",
    "user_programs": "programs",
    "program_revisions": "programs",
    "training_blocks": "programs",
    "training_block_priority_muscles": "programs",
    "user_workouts": "programs",
    "workout_adaptations": "programs",
    "user_workout_exercises": "programs",
    "user_workout_sets": "programs",
    "exercises": "custom_exercises",
    "exercise_muscles": "custom_exercises",
    "exercise_equipment": "custom_exercises",
    "exercise_guide_metadata": "custom_exercises",
    "exercise_alternatives": "custom_exercises",
    "coach_clients": "coaching_relationships",
    "coach_role_applications": "coach_role_applications",
    "workout_comments": "workout_comments",
    "workout_comment_revisions": "workout_comments",
    "notification_settings": "notification_settings",
    "reminder_template_schedules": "reminder_template_schedules",
    "notifications": "notifications",
    "web_push_subscriptions": "web_push_subscriptions",
    "notification_deliveries": "notification_deliveries",
    "report_handoffs": "report_handoffs",
    "weekly_digest_preferences": "weekly_digest_preference",
    "weekly_digest_deliveries": "weekly_digest_deliveries",
    "audit_events": "audit_events",
    "ai_coach_consents": "ai_coach_consent",
    "ai_coach_memory_consents": "ai_coach_memory_consent",
    "ai_coach_memories": "ai_coach_memories",
}

ACCOUNT_EXPORT_EXCLUDED_DATA_INVENTORY: dict[str, str] = {
    "account_data_exports": "short-lived generated archive bytes and download capability metadata",
    "auth_action_tokens": "hashed authentication actions and session-family metadata",
    "oauth_transactions": "short-lived browser OAuth state, PKCE, nonce, and recovery metadata",
    "refresh_tokens": "hashed session credentials and revocation metadata",
    "coach_client_invites": "hashed invitations and managed-client identity data",
    "payments": "retired operational billing/provider records",
    "subscriptions": "retired operational billing records",
    "workout_set_mutations": "idempotency fingerprints used only for sync correctness",
    "program_imports": (
        "short-lived owner-scoped import drafts; source is never persisted and normalized content "
        "is cleared on terminal state"
    ),
}


def _fields(row: object, names: tuple[str, ...]) -> dict[str, object]:
    return {name: getattr(row, name) for name in names}


FOOD_FIELDS = (
    "id",
    "name",
    "brand",
    "barcode",
    "energy_kcal_per_100g",
    "protein_g_per_100g",
    "fat_g_per_100g",
    "carbs_g_per_100g",
    "fiber_g_per_100g",
    "standard_serving_amount",
    "standard_serving_unit",
    "standard_serving_weight_g",
    "food_type",
    "provenance",
    "source_name",
    "source_version",
    "source_license",
    "source_url",
    "source_license_url",
    "external_id",
    "trust_level",
    "status",
    "created_at",
    "updated_at",
)

SNAPSHOT_NUTRIENT_FIELDS = (
    "food_name",
    "food_brand",
    "energy_kcal_per_100g",
    "protein_g_per_100g",
    "fat_g_per_100g",
    "carbs_g_per_100g",
    "fiber_g_per_100g",
    "serving_amount",
    "serving_unit",
    "serving_weight_g",
)

NUTRITION_FIELDS = (
    "id",
    "effective_from",
    "effective_to",
    "source",
    "created_by_user_id",
    "created_at",
    "note",
    "superseded_by_id",
    "sex",
    "weight_kg",
    "height_cm",
    "age",
    "daily_activity_level",
    "daily_routine",
    "steps_range",
    "strength_trainings_per_week",
    "strength_training_duration_minutes",
    "strength_training_type",
    "strength_rest",
    "cardio_trainings_per_week",
    "cardio_training_duration_minutes",
    "cardio_intensity",
    "cardio_trainings",
    "goal",
    "bmr",
    "tdee",
    "calories",
    "protein_g",
    "fat_g",
    "carbs_g",
    "saved_at",
)

ENERGY_CALIBRATION_FIELDS = (
    "id",
    "ruleset_version",
    "status",
    "sufficiency_status",
    "period_start",
    "period_end",
    "goal",
    "logged_day_count",
    "eligible_day_count",
    "weight_point_count",
    "weight_span_days",
    "average_intake_kcal",
    "smoothed_start_weight_kg",
    "smoothed_end_weight_kg",
    "estimated_expenditure_kcal",
    "estimate_low_kcal",
    "estimate_high_kcal",
    "previous_target_calories",
    "previous_target_saved_at",
    "proposed_target_calories",
    "sufficiency_counters",
    "sufficiency_reason_keys",
    "rationale_keys",
    "created_at",
    "decided_at",
)

WEEKLY_CHECK_IN_FIELDS = (
    "id",
    "week_start",
    "week_end",
    "submitted_on",
    "timezone",
    "status",
    "summary_version",
    "summary",
    "training_load",
    "recovery",
    "hunger",
    "adherence_difficulty",
    "note",
    "created_at",
)

DAILY_WELLBEING_FIELDS = (
    "id",
    "local_date",
    "timezone_at_entry",
    "sleep_quality",
    "sleep_duration_minutes",
    "mood",
    "note",
    "source",
    "created_at",
    "updated_at",
)

MEASUREMENT_FIELDS = (
    "id",
    "measured_on",
    "weight_kg",
    "chest_cm",
    "waist_cm",
    "hips_cm",
    "biceps_cm",
    "thigh_cm",
    "note",
    "created_at",
)


def _serialize_food(food: Food) -> dict[str, object]:
    return _fields(food, FOOD_FIELDS)


def _serialize_recipe_ingredient(ingredient: RecipeIngredient) -> dict[str, object]:
    return {
        "id": ingredient.id,
        "food_id": ingredient.food_id,
        "position": ingredient.position,
        "amount": ingredient.amount,
        "amount_unit": ingredient.amount_unit,
        "weight_g": ingredient.weight_g,
        **_fields(ingredient, SNAPSHOT_NUTRIENT_FIELDS),
    }


def _serialize_program_template(template: ProgramTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "slug": template.slug,
        "title": template.title,
        "goal": template.goal,
        "level": template.level,
        "split_type": template.split_type,
        "is_public": template.is_public,
        "default_duration_weeks": template.effective_duration_weeks,
        "created_at": template.created_at,
        "days": [
            {
                "id": day.id,
                "day_number": day.day_number,
                "title": day.title,
                "exercises": [
                    _fields(
                        exercise,
                        (
                            "id",
                            "exercise_id",
                            "sort_order",
                            "prescribed_sets",
                            "prescribed_reps",
                            "prescribed_duration_minutes",
                            "rest_seconds",
                            "notes",
                            "superset_group",
                            "superset_order",
                        ),
                    )
                    | {
                        "exercise_title": exercise.exercise.title,
                        "metric_type": exercise.exercise.metric_type or "strength",
                        "weekly_prescriptions": [
                            _fields(
                                prescription,
                                (
                                    "id",
                                    "exercise_id",
                                    "week_number",
                                    "prescribed_sets",
                                    "prescribed_reps",
                                    "prescribed_duration_minutes",
                                    "rest_seconds",
                                ),
                            )
                            for prescription in exercise.weekly_prescriptions
                        ],
                    }
                    for exercise in day.exercises
                ],
            }
            for day in template.days
        ],
    }


def _serialize_program(program: UserProgram) -> dict[str, object]:
    return {
        "id": program.id,
        "title": program.template.title if program.template else "Архивная программа",
        "assigned_by_user_id": program.assigned_by_user_id,
        "assigned_at": program.assigned_at,
        "start_date": program.start_date,
        "duration_weeks": program.duration_weeks,
        "schedule_weekdays": program.schedule_weekdays,
        "status": program.status,
        "is_active": program.is_active,
        "completed_at": program.completed_at,
        "archived_at": program.archived_at,
        "current_revision_number": program.current_revision_number,
        "revisions": [
            _fields(
                revision,
                (
                    "revision_number",
                    "changed_by_user_id",
                    "actor_role",
                    "change_kind",
                    "reason",
                    "changed_fields",
                    "snapshot",
                    "created_at",
                ),
            )
            for revision in program.revisions
        ],
        "training_blocks": [
            {
                **_fields(
                    block,
                    (
                        "id",
                        "title",
                        "start_date",
                        "end_date",
                        "purpose",
                        "notes",
                        "is_deload",
                        "status",
                        "created_by_user_id",
                        "created_at",
                        "updated_at",
                    ),
                ),
                "priority_muscle_ids": [link.muscle.identifier for link in block.priority_links],
            }
            for block in program.training_blocks
        ],
        "workouts": [
            {
                **_fields(
                    workout,
                    (
                        "id",
                        "scheduled_date",
                        "scheduled_time",
                        "day_number",
                        "week_number",
                        "title",
                        "status",
                        "started_at",
                        "completed_at",
                        "completion_feedback",
                        "completion_note",
                        "completion_feedback_updated_at",
                    ),
                ),
                "adaptations": [
                    _fields(
                        adaptation,
                        (
                            "id",
                            "reason",
                            "request_payload",
                            "original_snapshot",
                            "applied_diff",
                            "ruleset_version",
                            "applied_at",
                        ),
                    )
                    for adaptation in workout.adaptations
                ],
                "exercises": [
                    {
                        **_fields(
                            exercise,
                            (
                                "id",
                                "exercise_id",
                                "sort_order",
                                "prescribed_sets",
                                "prescribed_reps",
                                "prescribed_duration_minutes",
                                "rest_seconds",
                                "notes",
                                "superset_group",
                                "superset_order",
                            ),
                        ),
                        "title": exercise.exercise.title if exercise.exercise else None,
                        "metric_type": exercise.metric_type
                        or (
                            exercise.exercise.metric_type or "strength"
                            if exercise.exercise
                            else "strength"
                        ),
                        "sets": [
                            _fields(
                                workout_set,
                                (
                                    "id",
                                    "set_number",
                                    "actual_reps",
                                    "actual_weight",
                                    "duration_minutes",
                                    "distance_km",
                                    "average_heart_rate_bpm",
                                    "heart_rate_zone",
                                    "rir",
                                    "set_kind",
                                    "reached_failure",
                                    "is_completed",
                                    "version",
                                ),
                            )
                            for workout_set in exercise.sets
                        ],
                    }
                    for exercise in workout.exercises
                ],
            }
            for workout in sorted(program.workouts, key=lambda row: (row.scheduled_date, row.id))
        ],
    }


def build_account_export(db: Session, user: User) -> dict[str, object]:
    """Build schema v1 from data owned by the current account, without credentials."""

    programs = (
        db.query(UserProgram)
        .options(
            joinedload(UserProgram.template),
            selectinload(UserProgram.workouts)
            .selectinload(UserWorkout.exercises)
            .joinedload(UserWorkoutExercise.exercise),
            selectinload(UserProgram.workouts)
            .selectinload(UserWorkout.exercises)
            .selectinload(UserWorkoutExercise.sets),
            selectinload(UserProgram.workouts).selectinload(UserWorkout.adaptations),
            selectinload(UserProgram.revisions),
            selectinload(UserProgram.training_blocks)
            .selectinload(TrainingBlock.priority_links)
            .joinedload(TrainingBlockPriorityMuscle.muscle),
        )
        .filter(UserProgram.user_id == user.id)
        .order_by(UserProgram.assigned_at.asc(), UserProgram.id.asc())
        .all()
    )
    measurements = (
        db.query(BodyMeasurement)
        .filter(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.measured_on.asc(), BodyMeasurement.id.asc())
        .all()
    )
    cardio_sessions = (
        db.query(CardioSession)
        .filter(CardioSession.user_id == user.id)
        .order_by(CardioSession.scheduled_at.asc(), CardioSession.id.asc())
        .all()
    )
    nutrition_history = (
        db.query(NutritionTarget)
        .filter(NutritionTarget.user_id == user.id)
        .order_by(NutritionTarget.effective_from.asc(), NutritionTarget.id.asc())
        .all()
    )
    nutrition = next((row for row in nutrition_history if row.effective_to is None), None)
    hydration_goals = (
        db.query(HydrationGoal)
        .filter(HydrationGoal.user_id == user.id)
        .order_by(HydrationGoal.effective_from.asc(), HydrationGoal.id.asc())
        .all()
    )
    hydration_entries = (
        db.query(HydrationEntry)
        .filter(HydrationEntry.user_id == user.id)
        .order_by(HydrationEntry.occurred_at.asc(), HydrationEntry.id.asc())
        .all()
    )
    hydration_presets = (
        db.query(HydrationPreset)
        .filter(HydrationPreset.user_id == user.id)
        .order_by(HydrationPreset.position.asc(), HydrationPreset.id.asc())
        .all()
    )
    energy_calibrations = (
        db.query(EnergyCalibration)
        .filter(EnergyCalibration.user_id == user.id)
        .order_by(EnergyCalibration.created_at.asc(), EnergyCalibration.id.asc())
        .all()
    )
    weekly_check_ins = (
        db.query(WeeklyCheckIn)
        .filter(WeeklyCheckIn.user_id == user.id)
        .order_by(WeeklyCheckIn.week_start.asc(), WeeklyCheckIn.id.asc())
        .all()
    )
    daily_wellbeing_check_ins = (
        db.query(DailyWellbeingCheckIn)
        .filter(DailyWellbeingCheckIn.user_id == user.id)
        .order_by(DailyWellbeingCheckIn.local_date.asc(), DailyWellbeingCheckIn.id.asc())
        .all()
    )
    auth_identities = (
        db.query(AuthIdentity)
        .filter(AuthIdentity.user_id == user.id)
        .order_by(AuthIdentity.created_at.asc(), AuthIdentity.id.asc())
        .all()
    )
    local_credential = db.query(LocalCredential).filter(LocalCredential.user_id == user.id).first()
    private_foods = (
        db.query(Food)
        .filter(Food.owner_user_id == user.id)
        .order_by(Food.created_at.asc(), Food.id.asc())
        .all()
    )
    favorite_foods = (
        db.query(FoodFavorite, Food)
        .join(Food, Food.id == FoodFavorite.food_id)
        .filter(
            FoodFavorite.user_id == user.id,
            or_(Food.owner_user_id.is_(None), Food.owner_user_id == user.id),
        )
        .order_by(FoodFavorite.created_at.asc(), FoodFavorite.food_id.asc())
        .all()
    )
    recipes = (
        db.query(Recipe)
        .options(selectinload(Recipe.ingredients))
        .filter(Recipe.owner_user_id == user.id)
        .order_by(Recipe.created_at.asc(), Recipe.id.asc())
        .all()
    )
    diary_entries = (
        db.query(FoodDiaryEntry)
        .filter(FoodDiaryEntry.user_id == user.id)
        .order_by(FoodDiaryEntry.diary_date.asc(), FoodDiaryEntry.id.asc())
        .all()
    )
    diary_day_statuses = (
        db.query(FoodDiaryDayStatus)
        .filter(FoodDiaryDayStatus.user_id == user.id)
        .order_by(FoodDiaryDayStatus.diary_date.asc())
        .all()
    )
    diary_copy_operations = (
        db.query(FoodDiaryCopyOperation)
        .filter(FoodDiaryCopyOperation.user_id == user.id)
        .order_by(FoodDiaryCopyOperation.created_at.asc(), FoodDiaryCopyOperation.id.asc())
        .all()
    )
    program_templates = (
        db.query(ProgramTemplate)
        .options(
            selectinload(ProgramTemplate.days)
            .selectinload(ProgramTemplateDay.exercises)
            .options(
                joinedload(ProgramTemplateExercise.exercise),
                selectinload(ProgramTemplateExercise.weekly_prescriptions),
            )
        )
        .filter(ProgramTemplate.owner_user_id == user.id)
        .order_by(ProgramTemplate.created_at.asc(), ProgramTemplate.id.asc())
        .all()
    )
    hidden_templates = (
        db.query(HiddenProgramTemplate)
        .filter(HiddenProgramTemplate.user_id == user.id)
        .order_by(HiddenProgramTemplate.hidden_at.asc(), HiddenProgramTemplate.id.asc())
        .all()
    )
    custom_exercises = (
        db.query(Exercise)
        .options(
            selectinload(Exercise.muscle_links).joinedload(ExerciseMuscle.muscle),
            selectinload(Exercise.equipment_links).joinedload(ExerciseEquipment.equipment),
            selectinload(Exercise.guide_metadata),
        )
        .filter(Exercise.created_by_user_id == user.id)
        .order_by(Exercise.id.asc())
        .all()
    )
    custom_exercise_ids = {row.id for row in custom_exercises}
    visible_exercise_ids = {
        row.id
        for row in db.query(Exercise.id)
        .filter(or_(Exercise.created_by_user_id.is_(None), Exercise.created_by_user_id == user.id))
        .all()
    }
    alternatives = (
        db.query(ExerciseAlternative)
        .filter(
            or_(
                ExerciseAlternative.exercise_id.in_(custom_exercise_ids),
                ExerciseAlternative.alternative_exercise_id.in_(custom_exercise_ids),
            ),
            ExerciseAlternative.exercise_id.in_(visible_exercise_ids),
            ExerciseAlternative.alternative_exercise_id.in_(visible_exercise_ids),
        )
        .all()
        if custom_exercise_ids
        else []
    )
    alternatives_by_exercise = {
        exercise_id: sorted(
            {
                row.alternative_exercise_id if row.exercise_id == exercise_id else row.exercise_id
                for row in alternatives
                if exercise_id in {row.exercise_id, row.alternative_exercise_id}
            }
        )
        for exercise_id in custom_exercise_ids
    }
    setting = db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
    reminder_template_schedules = (
        db.query(ReminderTemplateSchedule)
        .filter(ReminderTemplateSchedule.user_id == user.id)
        .order_by(ReminderTemplateSchedule.template_key.asc())
        .all()
    )
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.asc(), Notification.id.asc())
        .all()
    )
    web_push_subscriptions = (
        db.query(WebPushSubscription)
        .filter(WebPushSubscription.user_id == user.id)
        .order_by(WebPushSubscription.created_at.asc(), WebPushSubscription.id.asc())
        .all()
    )
    notification_deliveries = (
        db.query(NotificationDelivery)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .filter(Notification.user_id == user.id)
        .order_by(NotificationDelivery.created_at.asc(), NotificationDelivery.id.asc())
        .all()
    )
    digest_preference = (
        db.query(WeeklyDigestPreference).filter(WeeklyDigestPreference.user_id == user.id).first()
    )
    digest_deliveries = (
        db.query(WeeklyDigestDelivery)
        .filter(WeeklyDigestDelivery.user_id == user.id)
        .order_by(WeeklyDigestDelivery.created_at.asc(), WeeklyDigestDelivery.id.asc())
        .all()
    )
    relations = (
        db.query(CoachClient)
        .filter(or_(CoachClient.coach_user_id == user.id, CoachClient.client_user_id == user.id))
        .order_by(CoachClient.created_at.asc(), CoachClient.id.asc())
        .all()
    )
    report_handoffs = (
        db.query(ReportHandoff)
        .filter(
            or_(
                ReportHandoff.sender_user_id == user.id,
                ReportHandoff.trainer_user_id == user.id,
            )
        )
        .order_by(ReportHandoff.created_at.asc(), ReportHandoff.id.asc())
        .all()
    )
    coach_applications = (
        db.query(CoachRoleApplication)
        .filter(CoachRoleApplication.user_id == user.id)
        .order_by(CoachRoleApplication.created_at.asc(), CoachRoleApplication.id.asc())
        .all()
    )
    audit_events = (
        db.query(AuditEvent)
        .filter(or_(AuditEvent.actor_user_id == user.id, AuditEvent.target_user_id == user.id))
        .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        .all()
    )
    ai_coach_consent = (
        db.query(AiCoachConsent).filter(AiCoachConsent.user_id == user.id).one_or_none()
    )
    ai_coach_memory_consent = (
        db.query(AiCoachMemoryConsent).filter(AiCoachMemoryConsent.user_id == user.id).one_or_none()
    )
    ai_coach_memories = (
        db.query(AiCoachMemory)
        .filter(AiCoachMemory.user_id == user.id)
        .order_by(AiCoachMemory.created_at.asc(), AiCoachMemory.id.asc())
        .all()
    )
    workout_comments = (
        db.query(WorkoutComment)
        .options(joinedload(WorkoutComment.revisions))
        .filter(WorkoutComment.client_user_id == user.id)
        .order_by(WorkoutComment.created_at.asc(), WorkoutComment.id.asc())
        .all()
    )
    profile = user.profile
    return {
        "schema_version": ACCOUNT_EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC),
        "account": {
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "photo_url": user.photo_url,
            "created_at": user.created_at,
            "is_coach": user.is_coach,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        },
        "custom_avatar": (
            {
                "content_type": user.custom_avatar_content_type,
                "byte_size": user.custom_avatar_byte_size,
                "width": user.custom_avatar_width,
                "height": user.custom_avatar_height,
                "sha256": user.custom_avatar_sha256,
                "created_at": user.custom_avatar_created_at,
                "updated_at": user.custom_avatar_updated_at,
                "file": "avatar/avatar.webp",
            }
            if user.custom_avatar_updated_at is not None
            else None
        ),
        "auth_identities": [
            _fields(
                identity,
                (
                    "id",
                    "provider",
                    "subject",
                    "email",
                    "email_verified",
                    "created_at",
                    "last_login_at",
                ),
            )
            for identity in auth_identities
        ],
        "local_credential": (
            _fields(
                local_credential,
                ("username_normalized", "created_at", "password_changed_at"),
            )
            if local_credential
            else None
        ),
        "profile": (
            {
                "full_name": profile.full_name,
                "birth_date": profile.birth_date,
                "sex": profile.sex,
                "goal": profile.goal,
                "level": profile.level,
                "height_cm": profile.height_cm,
                "weight_kg": profile.weight_kg,
                "workouts_per_week": profile.workouts_per_week,
                "cardio_trainings_per_week": profile.cardio_trainings_per_week,
                "resting_heart_rate": profile.resting_heart_rate,
                "body_priority": serialize_body_priority(profile),
                "training_preferences": {
                    "preferred_duration_min": profile.preferred_workout_duration_min,
                    "preferred_duration_max": profile.preferred_workout_duration_max,
                    "preferred_weekdays": profile.preferred_training_weekdays,
                    "preferred_time": profile.preferred_training_time,
                    "location_profiles": profile.training_location_profiles,
                    "preferred_exercise_ids": profile.preferred_exercise_ids,
                    "avoided_exercises": profile.avoided_exercises,
                    "note": profile.training_preferences_note,
                    "updated_at": profile.training_preferences_updated_at,
                    "updated_by_user_id": profile.training_preferences_updated_by_user_id,
                },
                "timezone": profile.timezone,
            }
            if profile
            else None
        ),
        "nutrition": (_fields(nutrition, NUTRITION_FIELDS) if nutrition else None),
        "nutrition_target_history": [
            _fields(target, NUTRITION_FIELDS) for target in nutrition_history
        ],
        "hydration": {
            "goals": [
                _fields(
                    row,
                    (
                        "id",
                        "status",
                        "target_ml",
                        "source",
                        "method_version",
                        "reference_scope",
                        "sex",
                        "adult_confirmed",
                        "effective_from",
                        "effective_to",
                        "created_at",
                    ),
                )
                for row in hydration_goals
            ],
            "entries": [
                _fields(
                    row,
                    (
                        "id",
                        "occurred_at",
                        "diary_date",
                        "timezone",
                        "volume_ml",
                        "beverage_type",
                        "source",
                        "created_at",
                        "updated_at",
                    ),
                )
                for row in hydration_entries
            ],
            "presets": [
                _fields(
                    row,
                    ("id", "label", "volume_ml", "beverage_type", "position", "created_at"),
                )
                for row in hydration_presets
            ],
        },
        "energy_calibrations": [
            _fields(row, ENERGY_CALIBRATION_FIELDS) for row in energy_calibrations
        ],
        "weekly_check_ins": [_fields(row, WEEKLY_CHECK_IN_FIELDS) for row in weekly_check_ins],
        "daily_wellbeing_check_ins": [
            _fields(row, DAILY_WELLBEING_FIELDS) for row in daily_wellbeing_check_ins
        ],
        "measurements": [_fields(row, MEASUREMENT_FIELDS) for row in measurements],
        "cardio_sessions": [
            _fields(
                row,
                (
                    "id",
                    "activity_type",
                    "duration_minutes",
                    "distance_km",
                    "average_heart_rate_bpm",
                    "heart_rate_zone",
                    "note",
                    "scheduled_at",
                    "status",
                    "source",
                    "completed_at",
                    "created_at",
                    "updated_at",
                ),
            )
            for row in cardio_sessions
        ],
        "private_foods": [_serialize_food(row) for row in private_foods],
        "food_favorites": [
            {"created_at": favorite.created_at, "food": _serialize_food(food)}
            for favorite, food in favorite_foods
        ],
        "recipes": [
            {
                **_fields(recipe, ("id", "name", "final_weight_g", "created_at", "updated_at")),
                "ingredients": [
                    _serialize_recipe_ingredient(ingredient) for ingredient in recipe.ingredients
                ],
            }
            for recipe in recipes
        ],
        "food_diary_entries": [
            {
                **_fields(
                    row,
                    (
                        "id",
                        "food_id",
                        "recipe_id",
                        "copy_operation_id",
                        "copied_from_entry_id",
                        "diary_date",
                        "meal_type",
                        "logged_at",
                        "entry_kind",
                        "amount",
                        "amount_unit",
                        "weight_g",
                        "quick_energy_kcal",
                        "quick_protein_g",
                        "quick_fat_g",
                        "quick_carbs_g",
                    ),
                ),
                **_fields(row, SNAPSHOT_NUTRIENT_FIELDS),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in diary_entries
        ],
        "food_diary_day_statuses": [
            _fields(row, ("diary_date", "status", "updated_at")) for row in diary_day_statuses
        ],
        "food_diary_copy_operations": [
            _fields(
                row,
                (
                    "id",
                    "copy_scope",
                    "source_entry_id",
                    "source_date",
                    "source_meal_type",
                    "target_date",
                    "target_meal_type",
                    "created_at",
                ),
            )
            for row in diary_copy_operations
        ],
        "program_templates": [_serialize_program_template(row) for row in program_templates],
        "hidden_program_templates": [
            _fields(row, ("id", "template_id", "hidden_at")) for row in hidden_templates
        ],
        "programs": [_serialize_program(program) for program in programs],
        "custom_exercises": [
            {
                **_fields(
                    exercise,
                    (
                        "id",
                        "slug",
                        "title",
                        "primary_muscle",
                        "equipment",
                        "difficulty_level",
                        "source_exercise_id",
                        "is_deleted",
                    ),
                ),
                "muscles": [
                    {
                        "identifier": link.muscle.identifier,
                        "role": link.role,
                        "position": link.position,
                    }
                    for link in exercise.muscle_links
                ],
                "equipment_items": [
                    {
                        "identifier": link.equipment.identifier,
                        "position": link.position,
                    }
                    for link in exercise.equipment_links
                ],
                "guide": (
                    _fields(
                        exercise.guide_metadata,
                        (
                            "safety_notes",
                            "source_name",
                            "source_url",
                            "source_license",
                            "source_license_url",
                            "media_reference",
                        ),
                    )
                    if exercise.guide_metadata
                    else None
                ),
                "alternative_exercise_ids": alternatives_by_exercise[exercise.id],
            }
            for exercise in custom_exercises
        ],
        "coaching_relationships": [
            {
                "id": relation.id,
                "role": "coach" if relation.coach_user_id == user.id else "client",
                "status": relation.status,
                "created_at": relation.created_at,
                "accepted_at": relation.accepted_at,
                "ended_at": relation.ended_at,
                "ended_reason": relation.ended_reason,
            }
            for relation in relations
        ],
        "report_handoffs": [
            {
                "id": handoff.id,
                "role": "sender" if handoff.sender_user_id == user.id else "trainer",
                "sender_user_id": handoff.sender_user_id,
                "trainer_user_id": handoff.trainer_user_id,
                "relationship_id": handoff.relationship_id,
                "period": handoff.period,
                "period_start": handoff.period_start,
                "period_end": handoff.period_end,
                "timezone": handoff.timezone,
                "report_contract_version": handoff.report_contract_version,
                "included_section_ids": handoff.included_section_ids,
                "delivery_attempt": handoff.delivery_attempt,
                "notification_id": handoff.notification_id,
                "created_at": handoff.created_at,
            }
            for handoff in report_handoffs
        ],
        "workout_comments": [
            {
                "id": comment.id,
                "trainer_author_id": comment.trainer_author_id,
                "workout_id": comment.workout_id,
                "workout_exercise_id": comment.workout_exercise_id,
                "body": comment.body,
                "body_format": "plain_text",
                "created_at": comment.created_at,
                "updated_at": comment.updated_at,
                "revisions": [
                    _fields(
                        revision,
                        ("revision_number", "body", "edited_by_user_id", "created_at"),
                    )
                    for revision in comment.revisions
                ],
            }
            for comment in workout_comments
        ],
        "coach_role_applications": [
            _fields(
                application,
                ("id", "status", "source", "created_at", "reviewed_at"),
            )
            for application in coach_applications
        ],
        "notification_settings": (
            _fields(
                setting,
                (
                    "workout_reminders_enabled",
                    "weekly_check_in_reminders_enabled",
                    "measurement_reminders_enabled",
                    "meal_reminders_enabled",
                    "hydration_reminders_enabled",
                    "movement_reminders_enabled",
                    "telegram_enabled",
                    "reminder_hour",
                    "quiet_hours_start",
                    "quiet_hours_end",
                ),
            )
            if setting
            else None
        ),
        "reminder_template_schedules": [
            _fields(
                schedule,
                (
                    "template_key",
                    "template_version",
                    "weekdays",
                    "schedule_times",
                    "window_start",
                    "window_end",
                    "interval_minutes",
                    "max_per_day",
                    "minimum_spacing_minutes",
                    "created_at",
                    "updated_at",
                ),
            )
            for schedule in reminder_template_schedules
        ],
        "notifications": [
            _fields(
                row,
                (
                    "id",
                    "channel",
                    "category",
                    "event_kind",
                    "title",
                    "body",
                    "scheduled_for",
                    "status",
                    "created_at",
                    "sent_at",
                    "read_at",
                    "action_url",
                ),
            )
            for row in notifications
        ],
        # Browser capability URLs and encryption keys are intentionally excluded from exports.
        "web_push_subscriptions": [
            _fields(
                subscription,
                (
                    "id",
                    "created_at",
                    "updated_at",
                    "last_success_at",
                    "last_failure_at",
                    "failure_count",
                    "last_error",
                ),
            )
            for subscription in web_push_subscriptions
        ],
        "notification_deliveries": [
            _fields(
                delivery,
                (
                    "id",
                    "notification_id",
                    "subscription_id",
                    "channel",
                    "status",
                    "attempt_count",
                    "last_error",
                    "created_at",
                    "sent_at",
                ),
            )
            for delivery in notification_deliveries
        ],
        "weekly_digest_preference": (
            _fields(
                digest_preference,
                (
                    "weekly_news_digest_enabled",
                    "consent_version",
                    "subscribed_at",
                    "unsubscribed_at",
                    "disabled_reason",
                    "last_digest_issue_id",
                    "last_sent_at",
                ),
            )
            if digest_preference
            else None
        ),
        "weekly_digest_deliveries": [
            _fields(
                row,
                (
                    "issue_id",
                    "status",
                    "attempt_count",
                    "last_error_code",
                    "created_at",
                    "sent_at",
                ),
            )
            for row in digest_deliveries
        ],
        "audit_events": [
            _fields(
                event,
                ("id", "action", "resource_type", "resource_id", "details", "created_at"),
            )
            for event in audit_events
        ],
        "ai_coach_consent": (
            _fields(
                ai_coach_consent,
                (
                    "status",
                    "scope",
                    "consent_version",
                    "provider_name",
                    "provider_policy_revision",
                    "consent_source",
                    "granted_at",
                    "revoked_at",
                    "created_at",
                    "updated_at",
                ),
            )
            if ai_coach_consent is not None
            else None
        ),
        "ai_coach_memory_consent": (
            _fields(
                ai_coach_memory_consent,
                (
                    "status",
                    "scope",
                    "consent_version",
                    "consent_source",
                    "granted_at",
                    "paused_at",
                    "revoked_at",
                    "created_at",
                    "updated_at",
                ),
            )
            if ai_coach_memory_consent is not None
            else None
        ),
        "ai_coach_memories": [
            _fields(
                memory,
                (
                    "id",
                    "category",
                    "value_text",
                    "source_kind",
                    "confidence",
                    "status",
                    "source_ref",
                    "version",
                    "created_at",
                    "updated_at",
                    "last_used_at",
                    "expires_at",
                ),
            )
            for memory in ai_coach_memories
        ],
    }
