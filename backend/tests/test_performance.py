from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

from sqlalchemy import event

from fitminiapp_api.api.v1.me import _build_user_response
from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.db.performance import (
    begin_sql_metrics,
    current_sql_metrics,
    reset_sql_metrics,
)
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.program import ProgramTemplate, UserProgram, UserWorkout
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User, UserProfile
from fitminiapp_api.services.program_versioning import list_program_import_targets
from fitminiapp_api.services.programs import list_clients


@contextmanager
def capture_ranked_measurement_queries() -> Iterator[list[tuple[str, object]]]:
    queries: list[tuple[str, object]] = []

    def capture(_conn, _cursor, statement: str, parameters: object, _context, _many) -> None:
        if "body_measurements" in statement and "row_number" in statement.lower():
            queries.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def test_coach_client_list_query_count_is_constant() -> None:
    with get_session_context() as db:
        coach = User(telegram_user_id=910_000, username="scale_coach", is_coach=True)
        db.add(coach)
        db.flush()
        db.add(UserProfile(user_id=coach.id, full_name="Scale Coach"))

        clients: list[User] = []
        for index in range(25):
            user = User(
                telegram_user_id=911_000 + index,
                username=f"scale_client_{index}",
            )
            db.add(user)
            db.flush()
            db.add(UserProfile(user_id=user.id, full_name=f"Scale Client {index}"))
            db.add(
                CoachClient(
                    coach_user_id=coach.id,
                    client_user_id=user.id,
                    private_name=f"Private Client {index}",
                )
            )
            clients.append(user)

        local_today = today_for_user(clients[0])
        db.add_all(
            [
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=local_today - timedelta(days=1),
                    weight_kg=80.0 + index,
                )
                for index, user in enumerate(clients)
            ]
        )
        # Tomorrow's weight must not leak into a client's local-today snapshot.
        db.add(
            BodyMeasurement(
                user_id=clients[0].id,
                measured_on=local_today + timedelta(days=1),
                weight_kg=250.0,
            )
        )

        db.add(
            NutritionTarget(
                user_id=clients[0].id,
                assigned_by_user_id=coach.id,
                sex="male",
                weight_kg=80,
                height_cm=180,
                age=30,
                daily_activity_level="moderate",
                daily_routine="mixed",
                steps_range="from_7000_to_10000",
                strength_trainings_per_week=3,
                strength_training_duration_minutes=60,
                strength_training_type="regular",
                strength_rest="one_to_two",
                cardio_trainings_per_week=1,
                cardio_training_duration_minutes=30,
                cardio_intensity="moderate",
                cardio_trainings=[],
                goal="maintenance",
                bmr=1800,
                tdee=2500,
                calories=2500,
                protein_g=160,
                fat_g=72,
                carbs_g=303,
            )
        )
        db.commit()
        db.refresh(coach)

        with capture_ranked_measurement_queries() as weight_queries:
            token = begin_sql_metrics()
            try:
                result = list_clients(db, coach)
                metrics = current_sql_metrics()
            finally:
                reset_sql_metrics(token)

    assert len(result) == 25
    assert metrics.query_count == 5
    assert result[-1]["kbju"].assigned_by.full_name == "Scale Coach"
    assert result[-1]["weight_kg"] == 80.0
    assert result[0]["weight_kg"] == 104.0
    assert len(weight_queries) == 1
    weight_sql, weight_params = weight_queries[0]
    # One shared local-day predicate, not 25 per-client predicates.
    assert weight_sql.count("measured_on <=") == 1
    assert isinstance(weight_params, (tuple, list, dict))
    assert len(weight_params) == len(clients) + 1


def test_coach_client_latest_weight_respects_distinct_local_days() -> None:
    with get_session_context() as db:
        coach = User(telegram_user_id=920_000, username="timezone_coach", is_coach=True)
        db.add(coach)
        db.flush()
        clients: list[User] = []
        for index, timezone in enumerate(("Pacific/Honolulu", "Pacific/Kiritimati")):
            user = User(telegram_user_id=920_100 + index, username=f"timezone_client_{index}")
            db.add(user)
            db.flush()
            db.add(UserProfile(user_id=user.id, timezone=timezone))
            db.add(CoachClient(coach_user_id=coach.id, client_user_id=user.id))
            clients.append(user)
        db.flush()

        local_dates = [today_for_user(user) for user in clients]
        assert local_dates[0] != local_dates[1]
        for index, user in enumerate(clients):
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=local_dates[index] - timedelta(days=1),
                    weight_kg=70.0 + index,
                )
            )
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=local_dates[index] + timedelta(days=1),
                    weight_kg=200.0 + index,
                )
            )
        db.commit()
        db.refresh(coach)

        client_ids = [user.id for user in clients]
        with capture_ranked_measurement_queries() as weight_queries:
            result = list_clients(db, coach)

    assert {row["id"]: row["weight_kg"] for row in result} == {
        client_ids[0]: 70.0,
        client_ids[1]: 71.0,
    }
    assert len(weight_queries) == 1
    # Two local days require two groups, preserving the individual cutoff.
    assert weight_queries[0][0].count("measured_on <=") == 2


def test_me_response_needs_six_queries_after_authentication() -> None:
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 2001).one()
        token = begin_sql_metrics()
        try:
            response = _build_user_response(db, user)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    assert response.telegram_user_id == 2001
    assert response.auth_providers == ["telegram"]
    assert metrics.query_count == 6


def test_coach_program_import_targets_keep_query_count_bounded_at_client_scale() -> None:
    with get_session_context() as db:
        coach = User(telegram_user_id=912_000, username="import_scale_coach", is_coach=True)
        db.add(coach)
        db.flush()
        template = ProgramTemplate(
            slug="import-scale-template",
            title="Import scale",
            goal="maintenance",
            level="beginner",
            default_duration_weeks=1,
        )
        db.add(template)
        db.flush()

        for index in range(25):
            client = User(
                telegram_user_id=913_000 + index,
                username=f"import_scale_client_{index}",
                profile=UserProfile(full_name=f"Import scale client {index}"),
            )
            db.add(client)
            db.flush()
            db.add(CoachClient(coach_user_id=coach.id, client_user_id=client.id))
            program = UserProgram(
                user_id=client.id,
                template_id=template.id,
                assigned_by_user_id=coach.id,
                start_date=date.today(),
                duration_weeks=1,
                schedule_weekdays=[date.today().weekday()],
                status="active",
                is_active=True,
            )
            program.workouts.append(
                UserWorkout(
                    scheduled_date=date.today(),
                    day_number=1,
                    week_number=1,
                    title="Import scale workout",
                    status="planned",
                )
            )
            db.add(program)
        db.commit()
        db.refresh(coach)

        token = begin_sql_metrics()
        try:
            result = list_program_import_targets(db, coach)
            metrics = current_sql_metrics()
        finally:
            reset_sql_metrics(token)

    assert len(result) == 25
    assert metrics.query_count <= 5
    assert all(row["day_numbers"] == [1] for row in result)
