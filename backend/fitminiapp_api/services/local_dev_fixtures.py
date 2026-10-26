"""Synthetic, repeatable fixture data for the isolated Windows-only DEV stack.

This is never called by ordinary dev/test/production seeding unless the precise
local DEV Compose identity and opt-in fixed-account flag are both present.
Existing user-entered records are not overwritten on subsequent starts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from hashlib import sha256

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachBusinessSession
from fitminiapp_api.models.food import Food, FoodFavorite
from fitminiapp_api.models.food_diary import FoodDiaryDayStatus, FoodDiaryEntry
from fitminiapp_api.models.hydration import HydrationEntry, HydrationGoal
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import (
    ProgramTemplate,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import (
    BodyMeasurement,
    BodyMeasurementCustomValue,
    BodyMeasurementDefinition,
    CoachClient,
    User,
    UserProfile,
)
from fitminiapp_api.services.auth_identities import ensure_telegram_identity

FIXTURE_VERSION = "yfc-local-dev-v1"
TIMEZONE = "Europe/Moscow"

# Per 100 g: kcal, protein, fat, carbohydrates, fibre. Illustrative values,
# NOT medical advice or a verified nutrition database.
FOOD_SPECS = (
    ("Овсяные хлопья", "370", "13.0", "7.0", "62.0", "10.0"),
    ("Молоко 2,5%", "52", "3.0", "2.5", "4.7", "0"),
    ("Яйцо куриное", "155", "12.7", "10.9", "0.7", "0"),
    ("Банан", "89", "1.1", "0.3", "23", "2.6"),
    ("Творог 5%", "121", "17", "5", "3", "0"),
    ("Рис отварной", "130", "2.7", "0.3", "28.2", "0.4"),
    ("Куриная грудка", "165", "31", "3.6", "0", "0"),
    ("Гречка отварная", "110", "4", "1.1", "21", "2.7"),
    ("Огурец", "15", "0.7", "0.1", "3.6", "0.5"),
    ("Помидор", "18", "0.9", "0.2", "3.9", "1.2"),
    ("Лосось", "208", "20", "13", "0", "0"),
    ("Картофель отварной", "87", "1.9", "0.1", "20.1", "1.8"),
    ("Йогурт натуральный", "61", "3.5", "3.3", "4.7", "0"),
    ("Яблоко", "52", "0.3", "0.2", "14", "2.4"),
    ("Хлеб цельнозерновой", "247", "13", "4.2", "41", "7"),
    ("Индейка", "135", "29", "1.6", "0", "0"),
)

MEAL_SPECS = (
    ("breakfast", ((0, 80), (1, 200), (3, 120))),
    ("lunch", ((5, 180), (6, 170), (8, 140))),
    ("dinner", ((7, 180), (10, 150), (9, 120))),
    ("snacks", ((4, 180), (13, 180))),
)


def _local_dev_database_only() -> bool:
    if settings.app_env != "dev" or not settings.dev_auth_fixed_accounts_only:
        return False
    url = make_url(settings.database_url)
    return (
        url.get_backend_name() == "postgresql"
        and url.host == "db"
        and url.username == "yfc_dev"
        and url.database == "yfc_dev"
    )


def maybe_seed_local_dev_data(db: Session) -> None:
    """Fail closed instead of seeding a production-looking database."""
    if settings.dev_auth_fixed_accounts_only and not _local_dev_database_only():
        raise RuntimeError("Fixed-account DEV fixtures require isolated yfc_dev PostgreSQL")
    if _local_dev_database_only():
        seed_local_dev_data(db)


def _user(
    db: Session, telegram_id: int, *, name: str, coach: bool = False, admin: bool = False
) -> User:
    user = db.query(User).filter_by(telegram_user_id=telegram_id).one_or_none()
    if user is None:
        user = User(telegram_user_id=telegram_id, username=f"dev_{telegram_id}")
        db.add(user)
        db.flush()
        ensure_telegram_identity(db, user, mark_login=False)
    # Only the synthetic, dedicated fixed-account DEV environment invokes this.
    user.is_coach = coach
    user.is_admin = admin
    user.measurement_eligibility = "synthetic"
    if not db.query(UserProfile).filter_by(user_id=user.id).first():
        db.add(
            UserProfile(
                user_id=user.id,
                full_name=name,
                goal="muscle_gain" if not coach else "recomposition",
                level="intermediate",
                height_cm=178 if telegram_id == 2001 else 171,
                weight_kg=78.25 if telegram_id == 2001 else 70.4,
                workouts_per_week=3,
                preferred_training_weekdays=[1, 3, 5],
                preferred_workout_duration_min=50,
                preferred_workout_duration_max=90,
                training_preferences_note="Искусственный DEV-профиль; не использовать как реальные данные.",
            )
        )
    return user


def _coach_links(db: Session, coach_id: int, client_ids: list[int]) -> None:
    for client_id in client_ids:
        if not db.query(CoachClient).filter_by(client_user_id=client_id).first():
            db.add(
                CoachClient(
                    coach_user_id=coach_id,
                    client_user_id=client_id,
                    private_name=f"DEV / клиент {client_id}",
                    status="active",
                    operational_status="active",
                    labels=["DEV", "тестовый"],
                )
            )


def _program_history(
    db: Session, *, client_id: int, coach_id: int, template: ProgramTemplate, today: date
) -> None:
    if db.query(UserProgram).filter_by(user_id=client_id).first():
        return
    start = today - timedelta(days=today.weekday() + 10 * 7)
    days = template.days[:3]
    if not days:
        raise RuntimeError("DEV template has no training days")
    program = UserProgram(
        user_id=client_id,
        assigned_by_user_id=coach_id,
        template_id=template.id,
        start_date=start,
        duration_weeks=16,
        schedule_weekdays=[1 + index * 2 for index in range(len(days))],
        status="active",
        is_active=True,
    )
    db.add(program)
    db.flush()

    for week in range(1, 17):
        for day_index, template_day in enumerate(days):
            scheduled = start + timedelta(days=(week - 1) * 7 + day_index * 2)
            completed = scheduled < today
            workout = UserWorkout(
                user_program_id=program.id,
                scheduled_date=scheduled,
                scheduled_time=time(18, 30),
                day_number=template_day.day_number,
                week_number=week,
                title=template_day.title,
                status="completed" if completed else "planned",
                started_at=datetime.combine(scheduled, time(18, 31)) if completed else None,
                completed_at=datetime.combine(scheduled, time(19, 38)) if completed else None,
                completion_feedback="as_expected" if completed else None,
                completion_note=(
                    "Жим ногами можно прибавить. Сравнить вес в каждом подходе на следующей неделе."
                    if completed and day_index == 1
                    else None
                ),
            )
            db.add(workout)
            db.flush()
            for exercise_index, source in enumerate(template_day.exercises):
                metric = source.exercise.metric_type or "strength"
                item = UserWorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=source.exercise_id,
                    source_template_exercise_id=source.id,
                    metric_type=metric,
                    sort_order=exercise_index + 1,
                    prescribed_sets=source.prescribed_sets,
                    prescribed_reps=source.prescribed_reps,
                    prescribed_duration_minutes=source.prescribed_duration_minutes,
                    rest_seconds=source.rest_seconds,
                    notes=source.notes,
                    prescription=source.prescription,
                )
                db.add(item)
                db.flush()
                for set_index in range(1, source.prescribed_sets + 1):
                    weight = (
                        Decimal("20.25")
                        + Decimal(exercise_index * 9)
                        + Decimal(week) * Decimal("1.25")
                        + Decimal(set_index - 1) * Decimal("2.50")
                    )
                    is_cardio = metric == "cardio"
                    db.add(
                        UserWorkoutSet(
                            workout_exercise_id=item.id,
                            set_number=set_index,
                            actual_weight=float(weight) if completed and not is_cardio else None,
                            actual_reps=(8 + (set_index % 3))
                            if completed and not is_cardio
                            else None,
                            duration_minutes=20 if completed and is_cardio else None,
                            rir="2" if completed and not is_cardio else None,
                            set_kind="working",
                            is_completed=completed,
                        )
                    )


def _measurements(db: Session, user_id: int, today: date, *, base_weight: Decimal) -> None:
    existing = db.query(BodyMeasurement).filter_by(user_id=user_id).first()
    if existing is not None:
        return
    definition = (
        db.query(BodyMeasurementDefinition)
        .filter_by(user_id=user_id, normalized_label="шея")
        .one_or_none()
    )
    if definition is None:
        definition = BodyMeasurementDefinition(
            user_id=user_id, label="Шея", normalized_label="шея", unit="cm"
        )
        db.add(definition)
        db.flush()
    monday = today - timedelta(days=today.weekday())
    for week_back in range(12, -1, -1):
        measured = monday - timedelta(weeks=week_back)
        weight = base_weight + Decimal(week_back) * Decimal("0.17")
        entry = BodyMeasurement(
            user_id=user_id,
            measured_on=measured,
            weight_kg=float(weight),
            chest_cm=float(Decimal("101.25") + Decimal(12 - week_back) * Decimal("0.08")),
            waist_cm=float(Decimal("86.34") - Decimal(12 - week_back) * Decimal("0.13")),
            hips_cm=99.25,
            biceps_cm=35.75,
            thigh_cm=58.24,
            note="Синтетический замер; проверка сотых долей.",
        )
        db.add(entry)
        db.flush()
        db.add(
            BodyMeasurementCustomValue(
                measurement_id=entry.id, definition_id=definition.id, value=39.25
            )
        )


def _nutrition(db: Session, *, user_id: int, coach_id: int, today: date, days: int) -> None:
    start = today - timedelta(days=days - 1)
    if not db.query(NutritionTarget).filter_by(user_id=user_id).first():
        db.add(
            NutritionTarget(
                user_id=user_id,
                assigned_by_user_id=coach_id,
                effective_from=start,
                source="trainer",
                goal="muscle_gain",
                calories=2500,
                protein_g=160,
                fat_g=80,
                carbs_g=285,
                note="Учебная цель для локального DEV, не рекомендация.",
            )
        )
    if not db.query(HydrationGoal).filter_by(user_id=user_id).first():
        db.add(
            HydrationGoal(
                user_id=user_id,
                status="enabled",
                target_ml=2500,
                source="manual",
                method_version=FIXTURE_VERSION,
                effective_from=start,
            )
        )

    existing_foods = db.query(Food).filter_by(owner_user_id=user_id).all()
    if not existing_foods:
        for name, energy, protein, fat, carbs, fibre in FOOD_SPECS:
            db.add(
                Food(
                    name=name,
                    owner_user_id=user_id,
                    food_type="user",
                    provenance="user",
                    legacy_provenance="user",
                    trust_level="verified",
                    catalog_quality="private",
                    status="active",
                    nutrition_basis_kind="per_100_g",
                    nutrition_basis_amount=Decimal("100"),
                    nutrition_basis_unit="g",
                    energy_kcal_per_100g=Decimal(energy),
                    protein_g_per_100g=Decimal(protein),
                    fat_g_per_100g=Decimal(fat),
                    carbs_g_per_100g=Decimal(carbs),
                    fiber_g_per_100g=Decimal(fibre),
                )
            )
        db.flush()
        existing_foods = db.query(Food).filter_by(owner_user_id=user_id).all()
    by_name = {food.name: food for food in existing_foods}
    if not all(spec[0] in by_name for spec in FOOD_SPECS):
        return  # Preserve an existing, user-curated catalog; don't replace it.
    foods = [by_name[spec[0]] for spec in FOOD_SPECS]
    for food in foods[:6]:
        if not db.query(FoodFavorite).filter_by(user_id=user_id, food_id=food.id).first():
            db.add(FoodFavorite(user_id=user_id, food_id=food.id))

    # Any existing diary entry is a signal that the owner already started
    # working with nutrition, including edited data. Never fill around it.
    if not db.query(FoodDiaryEntry).filter_by(user_id=user_id).first():
        for delta in range(days):
            diary_day = start + timedelta(days=delta)
            for meal_type, products in MEAL_SPECS:
                for food_index, grams in products:
                    food = foods[
                        (food_index + (delta % 3 if meal_type == "dinner" else 0)) % len(foods)
                    ]
                    qty = Decimal(grams) + Decimal(delta % 4) * Decimal("2.25")
                    db.add(
                        FoodDiaryEntry(
                            user_id=user_id,
                            food_id=food.id,
                            diary_date=diary_day,
                            meal_type=meal_type,
                            entry_kind="food",
                            nutrition_source="internal",
                            amount=qty,
                            amount_unit="g",
                            weight_g=qty,
                            food_name=food.name,
                            energy_kcal_per_100g=food.energy_kcal_per_100g,
                            protein_g_per_100g=food.protein_g_per_100g,
                            fat_g_per_100g=food.fat_g_per_100g,
                            carbs_g_per_100g=food.carbs_g_per_100g,
                            fiber_g_per_100g=food.fiber_g_per_100g,
                            nutrition_basis_kind="per_100_g",
                            nutrition_basis_amount=Decimal("100"),
                            nutrition_basis_unit="g",
                        )
                    )
            # Leave today open for hands-on testing of input/edit/copy.
            if diary_day < today:
                db.add(
                    FoodDiaryDayStatus(
                        user_id=user_id,
                        diary_date=diary_day,
                        status="complete" if delta % 7 != 0 else "incomplete",
                    )
                )

    if not db.query(HydrationEntry).filter_by(user_id=user_id).first():
        for delta in range(days):
            diary_day = start + timedelta(days=delta)
            for index, volume in enumerate((250, 350, 500, 300, 450)):
                token = f"{FIXTURE_VERSION}:water:{user_id}:{diary_day}:{index}"
                db.add(
                    HydrationEntry(
                        user_id=user_id,
                        diary_date=diary_day,
                        occurred_at=datetime.combine(
                            diary_day, time(8 + index * 3, 10), tzinfo=UTC
                        ),
                        timezone=TIMEZONE,
                        beverage_type="water",
                        source="manual",
                        volume_ml=volume,
                        request_key=token,
                        payload_fingerprint=sha256(token.encode()).hexdigest(),
                    )
                )


def _check_ins(db: Session, *, user_id: int, today: date) -> None:
    if db.query(WeeklyCheckIn).filter_by(user_id=user_id).first():
        return
    monday = today - timedelta(days=today.weekday())
    for index in range(8, 0, -1):
        week_start = monday - timedelta(weeks=index)
        db.add(
            WeeklyCheckIn(
                user_id=user_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                submitted_on=week_start + timedelta(days=6),
                timezone=TIMEZONE,
                status="completed",
                summary_version=FIXTURE_VERSION,
                summary={
                    "training": {"planned_workouts": 3, "completed_workouts": 3},
                    "nutrition": {"logged_days": 7, "complete_days": 6},
                    "weight_trend": {"latest_value": 78.2 + index * 0.17},
                },
                training_load=2 + (index % 3),
                recovery=3 + (index % 2),
                hunger=3,
                adherence_difficulty=2,
                note="Синтетический еженедельный отчёт для панели тренера.",
            )
        )


def _crm(db: Session, *, coach_id: int, client_id: int, today: date) -> None:
    if (
        db.query(CoachBusinessSession)
        .filter_by(coach_user_id=coach_id, client_user_id=client_id)
        .first()
    ):
        return
    for week_back in range(6, -2, -1):
        scheduled = today - timedelta(days=week_back * 7)
        token = f"{FIXTURE_VERSION}:session:{client_id}:{week_back}"
        db.add(
            CoachBusinessSession(
                coach_user_id=coach_id,
                client_user_id=client_id,
                idempotency_key=token,
                starts_at_utc=datetime.combine(scheduled, time(16, 0)),
                timezone=TIMEZONE,
                duration_minutes=60,
                format="gym",
                status="completed" if week_back >= 0 else "scheduled",
                private_note="Синтетическая заметка тренера: проверить план и прогрессию.",
            )
        )


def seed_local_dev_data(db: Session) -> None:
    """Populate rich synthetic fixtures; caller must pass the DEV-only gate."""
    today = today_msk()
    admin = _user(db, 1001, name="Администратор DEV", coach=True, admin=True)
    coach = _user(db, 1002, name="Тренер DEV", coach=True)
    client = _user(db, 2001, name="Клиент DEV")
    extra_clients = [
        _user(db, 2002, name="Клиент DEV / поддержание"),
        _user(db, 2003, name="Клиент DEV / новичок"),
    ]
    db.flush()
    _coach_links(db, coach.id, [client.id, *[row.id for row in extra_clients]])
    templates = (
        db.query(ProgramTemplate).filter_by(is_public=True).order_by(ProgramTemplate.slug).all()
    )
    three_day = [item for item in templates if len(item.days) >= 3]
    if not three_day:
        raise RuntimeError("DEV fixtures require a three-day seeded program template")
    for index, trainee in enumerate([client, *extra_clients]):
        template = three_day[index % len(three_day)]
        _program_history(
            db, client_id=trainee.id, coach_id=coach.id, template=template, today=today
        )
        _measurements(
            db,
            trainee.id,
            today,
            base_weight=Decimal("78.25") - Decimal(index * 5),
        )
        _nutrition(
            db,
            user_id=trainee.id,
            coach_id=coach.id,
            today=today,
            days=35 if index == 0 else 14,
        )
        _check_ins(db, user_id=trainee.id, today=today)
        _crm(db, coach_id=coach.id, client_id=trainee.id, today=today)
    # Admin is intentionally a separate security identity, not a coached user.
    assert admin.is_admin and coach.is_coach and not client.is_coach
