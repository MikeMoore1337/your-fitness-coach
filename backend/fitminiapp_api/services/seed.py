from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.notification import NotificationSetting
from fitminiapp_api.models.program import (
    ProgramTemplate,
    ProgramTemplateDay,
    ProgramTemplateExercise,
    ProgramTemplateExerciseWeekPrescription,
)
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services.auth_identities import ensure_telegram_identity
from fitminiapp_api.services.exercise_domain import (
    canonical_muscle_identifier,
    sync_catalog_exercise_domain_metadata,
)
from fitminiapp_api.services.news_sources import bootstrap_default_news_sources
from fitminiapp_api.services.prescription_semantics import ensure_plan
from fitminiapp_api.services.program_seed_data import (
    EXERCISE_CATALOG,
    LEGACY_TEMPLATE_SLUGS,
    STRENGTH_TEMPLATE_SPECS,
    TemplateDaySeed,
    TemplateExerciseSeed,
    exercise_difficulty_level,
)
from fitminiapp_api.services.workout_metrics import exercise_metric_type


def _legacy_slug(slug: str) -> str:
    return f"{slug}-legacy-{uuid4().hex[:8]}"


def _seed_exercise_catalog(db: Session) -> None:
    catalog_slugs = {slug for slug, *_ in EXERCISE_CATALOG}
    catalog_rows = db.query(Exercise).filter(Exercise.slug.in_(catalog_slugs)).all()
    base_by_slug = {
        row.slug: row
        for row in catalog_rows
        if row.created_by_user_id is None and row.source_exercise_id is None
    }
    conflict_by_slug = {row.slug: row for row in catalog_rows}

    for slug, title, primary_muscle, equipment in EXERCISE_CATALOG:
        exercise = base_by_slug.get(slug)
        if not exercise:
            conflicting = conflict_by_slug.get(slug)
            if conflicting is not None:
                conflicting.slug = _legacy_slug(slug)
                db.flush()

            exercise = Exercise(
                slug=slug,
                created_by_user_id=None,
                source_exercise_id=None,
            )
            db.add(exercise)
            base_by_slug[slug] = exercise

        exercise.title = title
        exercise.primary_muscle = primary_muscle
        exercise.equipment = equipment
        exercise.metric_type = (
            "cardio" if canonical_muscle_identifier(primary_muscle) == "cardio" else "strength"
        )
        exercise.difficulty_level = exercise_difficulty_level(slug)
        exercise.is_deleted = False

    db.query(Exercise).filter(
        Exercise.created_by_user_id.is_(None),
        Exercise.source_exercise_id.is_(None),
        Exercise.slug.notin_(catalog_slugs),
    ).update(
        {Exercise.is_deleted: True},
        synchronize_session=False,
    )

    sync_catalog_exercise_domain_metadata(
        db,
        [base_by_slug[slug] for slug, *_ in EXERCISE_CATALOG],
    )
    db.flush()


def _delete_legacy_templates(db: Session) -> None:
    templates = (
        db.query(ProgramTemplate).filter(ProgramTemplate.slug.in_(LEGACY_TEMPLATE_SLUGS)).all()
    )
    for template in templates:
        from fitminiapp_api.services.programs import delete_template_cascade

        delete_template_cascade(db, template)
        db.flush()


def _unpack_template_exercise(
    seed: TemplateExerciseSeed,
) -> tuple[str, int, str, int, dict[str, object]]:
    if len(seed) == 4:
        slug, sets, reps, rest = seed
        return slug, sets, reps, rest, {}
    slug, sets, reps, rest, metadata = seed
    return slug, sets, reps, rest, metadata


def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise RuntimeError(f"Template metadata {key} must be an integer")
    return value


def _metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Template metadata {key} must be text")
    return value


def _seed_plan(
    exercise: Exercise,
    *,
    plan: object | None,
    sets: int,
    reps: str,
    rest: int,
) -> tuple[dict, int, str, int]:
    structured, projection = ensure_plan(
        plan,
        metric_type=exercise_metric_type(exercise),
        prescribed_sets=sets,
        prescribed_reps=reps,
        prescribed_duration_minutes=None,
        rest_seconds=rest,
    )
    if exercise_metric_type(exercise) == "strength" and projection.rest_seconds < 15:
        raise RuntimeError(f"Seed rest must be at least 15 seconds: {exercise.slug}")
    return (
        structured.model_dump(mode="json"),
        projection.prescribed_sets,
        projection.prescribed_reps,
        projection.rest_seconds,
    )


def _seed_template_exercise(
    db: Session,
    day: ProgramTemplateDay,
    *,
    sort_order: int,
    exercise: Exercise,
    seed: TemplateExerciseSeed,
    duration_weeks: int,
) -> None:
    exercise_slug, sets, reps, rest, metadata = _unpack_template_exercise(seed)
    raw_plan = metadata.get("prescription")
    structured_plan: dict | None = None
    projected_sets = sets
    projected_reps = reps
    projected_rest = rest
    if raw_plan is not None:
        structured_plan, projected_sets, projected_reps, projected_rest = _seed_plan(
            exercise,
            plan=raw_plan,
            sets=sets,
            reps=reps,
            rest=rest,
        )

    template_exercise = ProgramTemplateExercise(
        day_id=day.id,
        exercise_id=exercise.id,
        sort_order=sort_order,
        prescribed_sets=projected_sets,
        prescribed_reps=projected_reps,
        prescribed_duration_minutes=None,
        rest_seconds=projected_rest,
        notes=_metadata_text(metadata, "notes"),
        group_id=_metadata_int(metadata, "group_id"),
        group_kind=_metadata_text(metadata, "group_kind"),
        group_order=_metadata_int(metadata, "group_order"),
        prescription=structured_plan,
    )
    db.add(template_exercise)
    db.flush()

    if duration_weeks <= 1:
        return
    if raw_plan is None:
        raise RuntimeError(f"Periodized seed has no structured plan: {exercise_slug}")

    weekly_value = metadata.get("weekly_plans")
    if weekly_value is None:
        weekly_plans = [raw_plan] * duration_weeks
    elif isinstance(weekly_value, list) and len(weekly_value) == duration_weeks:
        weekly_plans = weekly_value
    else:
        raise RuntimeError(
            f"Periodized seed must provide {duration_weeks} weekly plans: {exercise_slug}"
        )

    for week_number, weekly_plan in enumerate(weekly_plans, start=1):
        weekly_structured, weekly_sets, weekly_reps, weekly_rest = _seed_plan(
            exercise,
            plan=weekly_plan,
            sets=sets,
            reps=reps,
            rest=rest,
        )
        db.add(
            ProgramTemplateExerciseWeekPrescription(
                template_exercise_id=template_exercise.id,
                exercise_id=exercise.id,
                week_number=week_number,
                prescribed_sets=weekly_sets,
                prescribed_reps=weekly_reps,
                prescribed_duration_minutes=None,
                rest_seconds=weekly_rest,
                prescription=weekly_structured,
            )
        )


def _generic_program_metadata(
    spec: dict[str, object],
    exercise_map: dict[str, Exercise],
    days: list[TemplateDaySeed],
) -> dict[str, object]:
    exercise_slugs = {
        _unpack_template_exercise(seed)[0] for _day_title, exercises in days for seed in exercises
    }
    equipment_values = {exercise_map[slug].equipment for slug in exercise_slugs}
    equipment = sorted(value for value in equipment_values if value is not None)
    days_per_week = len(days)
    return {
        "level": str(spec["level"]),
        "goal": str(spec["goal"]),
        "days_per_week": days_per_week,
        "representation_days": days_per_week,
        "split": str(spec["split_type"]),
        "equipment": equipment,
        "progression_style": "fixed_yfc_authored",
        "cycle_length_weeks": None,
        "advanced_method_flags": [],
        "frequency_model": f"{days_per_week} training days",
    }


def _seed_strength_templates(db: Session) -> None:
    exercise_map = {
        row.slug: row
        for row in db.query(Exercise)
        .filter(
            Exercise.created_by_user_id.is_(None),
            Exercise.source_exercise_id.is_(None),
            Exercise.is_deleted.is_(False),
        )
        .all()
    }

    spec_slugs = {str(spec["slug"]) for spec in STRENGTH_TEMPLATE_SPECS}
    templates_by_slug = {
        row.slug: row
        for row in db.query(ProgramTemplate).filter(ProgramTemplate.slug.in_(spec_slugs)).all()
    }
    existing_template_ids = [row.id for row in templates_by_slug.values()]
    if existing_template_ids:
        existing_day_ids = [
            row.id
            for row in db.query(ProgramTemplateDay.id)
            .filter(ProgramTemplateDay.program_id.in_(existing_template_ids))
            .all()
        ]
        if existing_day_ids:
            db.query(ProgramTemplateExercise).filter(
                ProgramTemplateExercise.day_id.in_(existing_day_ids)
            ).delete(synchronize_session=False)
            db.query(ProgramTemplateDay).filter(ProgramTemplateDay.id.in_(existing_day_ids)).delete(
                synchronize_session=False
            )
            db.flush()

    for spec in STRENGTH_TEMPLATE_SPECS:
        slug = str(spec["slug"])
        template = templates_by_slug.get(slug)
        if not template:
            template = ProgramTemplate(slug=slug)
            db.add(template)

        template.title = str(spec["title"])
        template.goal = str(spec["goal"])
        template.level = str(spec["level"])
        template.split_type = str(spec["split_type"])
        duration_weeks = spec.get("default_duration_weeks", 1)
        if not isinstance(duration_weeks, int):
            raise RuntimeError(f"Template duration must be an integer: {slug}")
        template.default_duration_weeks = duration_weeks
        template.provenance_type = (
            "SOURCE_ADAPTATION" if spec.get("provenance") is not None else "YFC_GENERIC"
        )
        template.provenance = cast(dict[str, object] | None, spec.get("provenance"))
        template.owner_user_id = None
        template.created_by_user_id = None
        template.is_public = True
        db.flush()

        days = cast(list[TemplateDaySeed], spec["days"])
        template.program_metadata = cast(
            dict[str, object],
            spec.get("program_metadata") or _generic_program_metadata(spec, exercise_map, days),
        )
        for day_number, (day_title, exercises) in enumerate(days, start=1):
            day = ProgramTemplateDay(
                program_id=template.id,
                day_number=day_number,
                title=day_title,
            )
            db.add(day)
            db.flush()

            for sort_order, seed in enumerate(exercises, start=1):
                exercise_slug, _sets, _reps, _rest, _metadata = _unpack_template_exercise(seed)
                exercise = exercise_map.get(exercise_slug)
                if exercise is None:
                    raise RuntimeError(f"Seed exercise is missing: {exercise_slug}")
                _seed_template_exercise(
                    db,
                    day,
                    sort_order=sort_order,
                    exercise=exercise,
                    seed=seed,
                    duration_weeks=template.effective_duration_weeks,
                )


def seed_demo_data(db: Session, include_demo_users: bool = True) -> None:
    if include_demo_users and db.query(User).count() == 0:
        coach = User(telegram_user_id=1001, username="coach_1001", is_coach=True, is_admin=True)
        client1 = User(telegram_user_id=2001, username="client_2001")
        client2 = User(telegram_user_id=2002, username="client_2002")
        db.add_all([coach, client1, client2])
        db.flush()
        for user in (coach, client1, client2):
            ensure_telegram_identity(db, user, mark_login=False)
        db.add_all(
            [
                UserProfile(
                    user_id=coach.id,
                    full_name="Тренер Demo",
                    goal="recomposition",
                    level="advanced",
                ),
                UserProfile(
                    user_id=client1.id,
                    full_name="Клиент 2001",
                    goal="muscle_gain",
                    level="intermediate",
                ),
                UserProfile(
                    user_id=client2.id, full_name="Клиент 2002", goal="fat_loss", level="beginner"
                ),
                NotificationSetting(user_id=coach.id),
                NotificationSetting(user_id=client1.id),
                NotificationSetting(user_id=client2.id),
            ]
        )

    _seed_exercise_catalog(db)

    _delete_legacy_templates(db)
    _seed_strength_templates(db)
    if settings.news_ingestion_enabled:
        bootstrap_default_news_sources(db)
    db.commit()


def main() -> None:
    with get_session_context() as db:
        seed_demo_data(db, include_demo_users=settings.app_env == "dev")


if __name__ == "__main__":
    main()
