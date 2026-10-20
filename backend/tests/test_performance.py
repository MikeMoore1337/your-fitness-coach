import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import and_, event, func, or_

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

        # An unrelated account with a newer weight must not enter Coach OS.
        outsider = User(
            telegram_user_id=911_999,
            username="unlinked_scale_client",
            profile=UserProfile(full_name="Unlinked Client"),
        )
        db.add(outsider)
        db.flush()

        local_today = today_for_user(clients[0])
        db.add(
            BodyMeasurement(
                user_id=outsider.id,
                measured_on=local_today,
                weight_kg=310.0,
            )
        )
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
    assert all(item["telegram_user_id"] != 911_999 for item in result)
    assert metrics.query_count == 5
    assert result[-1]["kbju"].assigned_by.full_name == "Scale Coach"
    assert result[-1]["weight_kg"] == 80.0
    assert result[0]["weight_kg"] == 104.0
    assert len(weight_queries) == 1
    weight_sql, weight_params = weight_queries[0]
    # One shared local-day predicate, not 25 per-client predicates.
    assert weight_sql.count("measured_on <=") == 1
    assert isinstance(weight_params, (tuple, list, dict))
    # Client-ID values, one local-date cutoff, and the rank == 1 filter.
    assert len(weight_params) == len(clients) + 2


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


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="SQL plan benchmarking requires isolated PostgreSQL fixtures",
)
@pytest.mark.parametrize("client_count", (10, 30, 100))
def test_coach_weight_query_postgres_profile_is_bounded_and_equivalent(
    client_count: int,
) -> None:
    """Synthetic PostgreSQL 16 comparison; never a production latency claim."""
    with get_session_context() as db:
        coach = User(
            telegram_user_id=9_500_000 + client_count,
            username=f"perf_weight_coach_{client_count}",
            is_coach=True,
        )
        db.add(coach)
        db.flush()
        clients = []
        timezones = ("UTC", "Pacific/Honolulu", "Pacific/Kiritimati")
        for index in range(client_count):
            user = User(
                telegram_user_id=9_600_000 + client_count * 1000 + index,
                username=f"perf_weight_{client_count}_{index}",
                profile=UserProfile(timezone=timezones[index % len(timezones)]),
            )
            clients.append(user)
        db.add_all(clients)
        db.flush()
        db.add_all(
            [CoachClient(coach_user_id=coach.id, client_user_id=user.id) for user in clients]
        )
        for index, user in enumerate(clients):
            local_today = today_for_user(user)
            for days_ago in range(12):
                db.add(
                    BodyMeasurement(
                        user_id=user.id,
                        measured_on=local_today - timedelta(days=days_ago + 1),
                        weight_kg=70.0 + index / 10 + days_ago / 100,
                    )
                )
            db.add(
                BodyMeasurement(
                    user_id=user.id,
                    measured_on=local_today + timedelta(days=1),
                    weight_kg=250.0,
                )
            )
        db.commit()
        db.refresh(coach)

        with capture_ranked_measurement_queries() as final_capture:
            token = begin_sql_metrics()
            try:
                final_clients = list_clients(db, coach)
                final_metrics = current_sql_metrics()
            finally:
                reset_sql_metrics(token)
        assert len(final_clients) == client_count
        # Coach's full read path must remain bounded at 10/30/100 clients.
        assert final_metrics.query_count == 5
        assert final_metrics.duration_ms >= 0
        assert len(final_capture) == 1

        # Preserve the original exact per-user cutoff query for the controlled
        # BEFORE comparison. Run it only on this isolated synthetic test DB.
        client_ids = [user.id for user in clients]
        ranked = (
            db.query(
                BodyMeasurement.user_id.label("user_id"),
                BodyMeasurement.weight_kg.label("weight_kg"),
                func.row_number()
                .over(
                    partition_by=BodyMeasurement.user_id,
                    order_by=(
                        BodyMeasurement.measured_on.desc(),
                        BodyMeasurement.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .filter(
                BodyMeasurement.user_id.in_(client_ids),
                BodyMeasurement.weight_kg.is_not(None),
                or_(
                    *[
                        and_(
                            BodyMeasurement.user_id == user.id,
                            BodyMeasurement.measured_on <= today_for_user(user),
                        )
                        for user in clients
                    ]
                ),
            )
            .subquery()
        )
        with capture_ranked_measurement_queries() as before_capture:
            old_weight_rows = (
                db.query(ranked.c.user_id, ranked.c.weight_kg).filter(ranked.c.rank == 1).all()
            )
        assert len(before_capture) == 1

        old_weights = dict(old_weight_rows)
        assert old_weights == {item["id"]: item["weight_kg"] for item in final_clients}
        assert all(value < 250.0 for value in old_weights.values())

        before_sql, before_params = before_capture[0]
        final_sql, final_params = final_capture[0]
        day_count = len({today_for_user(user) for user in clients})
        assert before_sql.count("measured_on <=") == client_count
        assert final_sql.count("measured_on <=") == day_count
        assert isinstance(before_params, (dict, tuple, list))
        assert isinstance(final_params, (dict, tuple, list))
        assert len(before_params) == client_count * 3 + 1
        assert len(final_params) == client_count + day_count + 1
        assert len(final_sql) < len(before_sql)

        # EXPLAIN ANALYZE runs only read-only SELECT statements against the
        # isolated PostgreSQL test database. Use a transaction-scoped timeout
        # and do not assert fragile absolute time/cost thresholds.
        db.connection().exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
        plan_times = []
        for statement, params in (before_capture[0], final_capture[0]):
            plan_value = (
                db.connection()
                .exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement,
                    params,
                )
                .scalar_one()
            )
            plan = json.loads(plan_value) if isinstance(plan_value, str) else plan_value
            assert isinstance(plan, list) and len(plan) == 1
            details = plan[0]
            assert isinstance(details, dict)
            assert details["Plan"]["Node Type"]
            assert float(details["Execution Time"]) >= 0
            plan_times.append(float(details["Execution Time"]))

        # Opt-in "pytest -s" prints machine-independent diagnostics. An isolated
        # three-sample/one-order EXPLAIN is not a robust speedup estimate.
        print(
            "V11_02_SYNTHETIC_POSTGRES"
            f" clients={client_count} local_days={day_count}"
            f" before_bindings={len(before_params)} final_bindings={len(final_params)}"
            f" before_sql_chars={len(before_sql)} final_sql_chars={len(final_sql)}"
            f" final_full_route_sql_count={final_metrics.query_count}"
            f" final_full_route_sql_ms={final_metrics.duration_ms:.3f}"
            f" before_explain_ms={plan_times[0]:.3f}"
            f" final_explain_ms={plan_times[1]:.3f}"
        )


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
