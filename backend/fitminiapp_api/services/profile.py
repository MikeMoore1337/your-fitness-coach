from datetime import date

from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import DEFAULT_TIMEZONE, is_valid_timezone
from fitminiapp_api.models.exercise import Muscle
from fitminiapp_api.models.notification import NotificationSetting
from fitminiapp_api.models.user import User, UserProfile, UserProfilePriorityMuscle
from fitminiapp_api.schemas.user import (
    BodyPriorityPreference,
    TrainingPreferencesUpdate,
    UserProfileUpdate,
)
from fitminiapp_api.services.exercise_domain import BODY_PRIORITY_TAXONOMY
from fitminiapp_api.services.heart_rate import (
    HeartRateCalculation,
    calculate_heart_rates,
    calculate_max_heart_rate,
)
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone


class ProfileError(ValueError):
    pass


BODY_PRIORITY_IDS = frozenset(identifier for identifier, _name in BODY_PRIORITY_TAXONOMY)


def serialize_body_priority(profile: UserProfile | None) -> dict | None:
    if profile is None or profile.body_priority_mode is None:
        return None
    return {
        "mode": profile.body_priority_mode,
        "muscle_group_ids": [link.muscle.identifier for link in profile.body_priority_links],
    }


def _replace_body_priority(
    db: Session,
    profile: UserProfile,
    preference: BodyPriorityPreference | None,
) -> None:
    profile.body_priority_links.clear()
    db.flush()
    if preference is None:
        profile.body_priority_mode = None
        return

    profile.body_priority_mode = preference.mode
    if preference.mode == "balanced":
        return

    identifiers = preference.muscle_group_ids
    if not set(identifiers).issubset(BODY_PRIORITY_IDS):
        raise ProfileError("Unknown body priority muscle group")
    muscles = db.query(Muscle).filter(Muscle.identifier.in_(identifiers)).all()
    by_identifier = {muscle.identifier: muscle for muscle in muscles}
    if set(by_identifier) != set(identifiers):
        raise ProfileError("Unknown body priority muscle group")
    profile.body_priority_links.extend(
        UserProfilePriorityMuscle(
            muscle_id=by_identifier[identifier].id,
            position=position,
        )
        for position, identifier in enumerate(identifiers)
    )


def calculate_profile_heart_rates(
    birth_date: date | None,
    resting_heart_rate: int | None,
    goal: str | None,
    *,
    today: date | None = None,
) -> HeartRateCalculation | None:
    if birth_date is None:
        return None
    reference_date = today or date.today()
    age = (
        reference_date.year
        - birth_date.year
        - ((reference_date.month, reference_date.day) < (birth_date.month, birth_date.day))
    )
    return calculate_heart_rates(age, resting_heart_rate, goal)


def ensure_profile(db: Session, user: User, *, commit: bool = True) -> UserProfile:
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.flush()

    setting = db.query(NotificationSetting).filter(NotificationSetting.user_id == user.id).first()
    if setting is None:
        db.add(NotificationSetting(user_id=user.id))

    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    user: User,
    payload: UserProfileUpdate,
    *,
    changed_by: User | None = None,
    commit: bool = True,
) -> User:
    profile = ensure_profile(db, user, commit=commit)
    onboarding_was_complete = profile.goal is not None
    changes = payload.model_dump(exclude_unset=True)
    body_priority = changes.pop("body_priority", ...)
    training_preferences = changes.pop("training_preferences", ...)
    birth_date = changes.get("birth_date", profile.birth_date)
    resting_heart_rate = changes.get("resting_heart_rate", profile.resting_heart_rate)
    if birth_date is not None and resting_heart_rate is not None:
        reference_date = date.today()
        age = (
            reference_date.year
            - birth_date.year
            - ((reference_date.month, reference_date.day) < (birth_date.month, birth_date.day))
        )
        if resting_heart_rate >= calculate_max_heart_rate(age):
            raise ProfileError("Resting heart rate must be below maximum heart rate")
    nutrition_field_map = {
        "goal": "goal",
        "height_cm": "height_cm",
        "weight_kg": "weight_kg",
        "workouts_per_week": "strength_trainings_per_week",
        "cardio_trainings_per_week": "cardio_trainings_per_week",
    }
    nutrition_updates: dict[str, object] = {}
    for field, value in changes.items():
        if field == "timezone":
            if not value:
                value = DEFAULT_TIMEZONE
            elif not is_valid_timezone(value):
                continue
        if field in nutrition_field_map and value is not None and getattr(profile, field) != value:
            nutrition_updates[nutrition_field_map[field]] = value
        setattr(profile, field, value)

    if body_priority is not ...:
        _replace_body_priority(
            db,
            profile,
            BodyPriorityPreference.model_validate(body_priority)
            if body_priority is not None
            else None,
        )

    if training_preferences is not ...:
        from fitminiapp_api.services.training_preferences import replace_training_preferences

        try:
            replace_training_preferences(
                db,
                profile,
                user,
                TrainingPreferencesUpdate.model_validate(training_preferences)
                if training_preferences is not None
                else None,
                changed_by or user,
            )
        except ValueError as exc:
            raise ProfileError(str(exc)) from exc

    if nutrition_updates:
        # Local import avoids a module cycle: nutrition uses ensure_profile on first save.
        from fitminiapp_api.services.nutrition import recalculate_nutrition_target

        recalculate_nutrition_target(
            db,
            user,
            nutrition_updates,
            changed_by or user,
        )
    if not onboarding_was_complete and profile.goal is not None:
        record_lifecycle_milestone(
            db,
            user,
            "onboarding_completed",
            account_scope=True,
        )
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(user)
    return user
