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
)
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services.auth_identities import ensure_telegram_identity
from fitminiapp_api.services.exercise_domain import (
    canonical_muscle_identifier,
    sync_catalog_exercise_domain_metadata,
)
from fitminiapp_api.services.news_sources import reconcile_default_news_sources
from fitminiapp_api.services.program_seed_data import (
    EXERCISE_CATALOG,
    LEGACY_TEMPLATE_SLUGS,
    STRENGTH_TEMPLATE_SPECS,
    TemplateDaySeed,
    exercise_difficulty_level,
)


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
        template.owner_user_id = None
        template.created_by_user_id = None
        template.is_public = True
        db.flush()

        days: list[TemplateDaySeed] = spec["days"]  # type: ignore[assignment]
        for day_number, (day_title, exercises) in enumerate(days, start=1):
            day = ProgramTemplateDay(
                program_id=template.id,
                day_number=day_number,
                title=day_title,
            )
            db.add(day)
            db.flush()

            for sort_order, (exercise_slug, sets, reps, rest) in enumerate(exercises, start=1):
                exercise = exercise_map.get(exercise_slug)
                if exercise is None:
                    raise RuntimeError(f"Seed exercise is missing: {exercise_slug}")

                db.add(
                    ProgramTemplateExercise(
                        day_id=day.id,
                        exercise_id=exercise.id,
                        sort_order=sort_order,
                        prescribed_sets=sets,
                        prescribed_reps=reps,
                        prescribed_duration_minutes=None,
                        rest_seconds=rest,
                    )
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
        reconcile_default_news_sources(db)
    db.commit()


def main() -> None:
    with get_session_context() as db:
        seed_demo_data(db, include_demo_users=settings.app_env == "dev")


if __name__ == "__main__":
    main()
