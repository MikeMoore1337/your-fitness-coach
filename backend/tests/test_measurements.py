from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event

import pytest

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.core.timezone import today_for_user
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.nutrition import NutritionTarget
from fitminiapp_api.models.user import (
    BodyMeasurement,
    BodyMeasurementCustomValue,
    BodyMeasurementDefinition,
    CoachClient,
    User,
)
from fitminiapp_api.services.measurements import _upsert_measurement


def _auth(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).scalar()


def _link_client(coach_telegram_id: int, client_telegram_id: int) -> tuple[int, int]:
    with get_session_context() as db:
        coach_id = db.query(User.id).filter(User.telegram_user_id == coach_telegram_id).scalar()
        client_id = db.query(User.id).filter(User.telegram_user_id == client_telegram_id).scalar()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=client_id, status="active"))
    return coach_id, client_id


def _nutrition_payload(weight_kg: float) -> dict[str, object]:
    return {
        "sex": "male",
        "weight_kg": weight_kg,
        "height_cm": 180,
        "age": 30,
        "daily_routine": "mixed",
        "steps_range": "from_4000_to_7000",
        "strength_trainings_per_week": 3,
        "strength_training_duration_minutes": 60,
        "strength_training_type": "regular",
        "strength_rest": "varied",
        "cardio_trainings": [],
        "goal": "maintenance",
    }


def _fix_utc_now(monkeypatch, value: datetime) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(timezone_module, "datetime", FixedDateTime)


def test_personal_and_coach_measurements_use_owner_timezone_boundary(client, monkeypatch) -> None:
    _fix_utc_now(monkeypatch, datetime(2030, 1, 1, 23, 30, tzinfo=UTC))
    coach_headers = _auth(client, 46_201, is_coach=True)
    client_headers = _auth(client, 46_202, is_coach=False)
    _, client_id = _link_client(46_201, 46_202)

    with get_session_context() as db:
        coach = db.query(User).filter(User.telegram_user_id == 46_201).one()
        owner = db.query(User).filter(User.telegram_user_id == 46_202).one()
        coach.profile.timezone = "Asia/Tokyo"
        owner.profile.timezone = "America/Los_Angeles"

    personal_future = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2030-01-02", "weight_kg": 75},
        headers=client_headers,
    )
    assert personal_future.status_code == 400
    assert personal_future.json()["detail"] == "Дата замера не может быть в будущем"

    coach_future = client.post(
        f"/api/v1/coach/clients/{client_id}/measurements",
        json={"measured_on": "2030-01-02", "weight_kg": 75},
        headers=coach_headers,
    )
    assert coach_future.status_code == 400

    defaulted = client.post(
        f"/api/v1/coach/clients/{client_id}/measurements",
        json={"weight_kg": 75},
        headers=coach_headers,
    )
    assert defaulted.status_code == 200
    assert defaulted.json()["measured_on"] == "2030-01-01"


def test_measurement_chronology_reconciles_current_state_and_preserves_future_history(
    client,
    monkeypatch,
) -> None:
    _fix_utc_now(monkeypatch, datetime(2030, 1, 10, 9, 0, tzinfo=UTC))
    headers = _auth(client, 46_210, is_coach=False)
    owner_id = _user_id(46_210)
    profile = client.patch(
        "/api/v1/me/profile",
        json={"weight_kg": 80, "timezone": "Europe/Moscow"},
        headers=headers,
    )
    assert profile.status_code == 200
    target = client.post(
        "/api/v1/nutrition/targets",
        json=_nutrition_payload(80),
        headers=headers,
    )
    assert target.status_code == 200

    with get_session_context() as db:
        db.add(
            BodyMeasurement(
                user_id=owner_id,
                measured_on=date(2030, 1, 11),
                weight_kg=120,
                note="legacy future fixture",
            )
        )

    current = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2030-01-10", "weight_kg": 79},
        headers=headers,
    )
    assert current.status_code == 200
    historical = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": "2030-01-05", "weight_kg": 90},
        headers=headers,
    )
    assert historical.status_code == 200

    me = client.get("/api/v1/me", headers=headers).json()
    assert me["profile"]["kbju"]["weight_kg"] == 79
    summary = client.get(
        "/api/v1/workouts/progress/summary?period_days=30",
        headers=headers,
    )
    assert summary.status_code == 200
    assert summary.json()["body"]["latest_measurement"]["measured_on"] == "2030-01-10"
    assert summary.json()["body"]["latest_measurement"]["weight_kg"] == 79
    legacy_progress = client.get("/api/v1/workouts/progress", headers=headers).json()
    assert [point["measured_on"] for point in legacy_progress["weights"]] == [
        "2030-01-05",
        "2030-01-10",
    ]

    history = client.get("/api/v1/workouts/diary", headers=headers).json()
    assert history[0]["measured_on"] == "2030-01-11"
    exported = client.get("/api/v1/me/export", headers=headers).json()
    assert exported["measurements"][-1]["measured_on"] == "2030-01-11"

    deleted_current = client.delete(
        f"/api/v1/workouts/diary/{current.json()['id']}",
        headers=headers,
    )
    assert deleted_current.status_code == 204
    assert client.get("/api/v1/me", headers=headers).json()["profile"]["kbju"]["weight_kg"] == 90

    deleted_last_valid = client.delete(
        f"/api/v1/workouts/diary/{historical.json()['id']}",
        headers=headers,
    )
    assert deleted_last_valid.status_code == 204
    assert client.get("/api/v1/me", headers=headers).json()["profile"]["kbju"]["weight_kg"] == 80
    with get_session_context() as db:
        assert (
            db.query(BodyMeasurement)
            .filter(
                BodyMeasurement.user_id == owner_id, BodyMeasurement.measured_on > date(2030, 1, 10)
            )
            .count()
            == 1
        )
        targets = db.query(NutritionTarget).filter(NutritionTarget.user_id == owner_id).all()
        assert len(targets) == 4
        assert sum(target.effective_to is None for target in targets) == 1


def test_custom_measurements_are_owner_scoped_factual_and_archivable(client) -> None:
    owner_headers = _auth(client, 46_230, is_coach=False)
    other_headers = _auth(client, 46_231, is_coach=False)
    today = date.today()

    blank = client.post(
        "/api/v1/workouts/diary",
        json={"measured_on": today.isoformat(), "note": "только текст"},
        headers=owner_headers,
    )
    assert blank.status_code == 400
    assert "числовой" in blank.json()["detail"]

    created_definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": "  Живот  "},
        headers=owner_headers,
    )
    assert created_definition.status_code == 201
    definition = created_definition.json()
    assert definition["label"] == "Живот"
    assert definition["unit"] == "cm"
    assert definition["archived"] is False

    duplicate_definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": " живот "},
        headers=owner_headers,
    )
    blank_definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": "   "},
        headers=owner_headers,
    )
    oversized_definition = client.post(
        "/api/v1/workouts/diary/custom-definitions",
        json={"label": "x" * 65},
        headers=owner_headers,
    )
    assert duplicate_definition.status_code == 409
    assert blank_definition.status_code == 422
    assert oversized_definition.status_code == 422
    assert (
        client.get(
            "/api/v1/workouts/diary/custom-definitions",
            headers=other_headers,
        ).json()
        == []
    )

    foreign_write = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": today.isoformat(),
            "custom_values": [{"definition_id": definition["id"], "value": 88}],
        },
        headers=other_headers,
    )
    assert foreign_write.status_code == 400

    for offset, value in ((14, 88), (7, 87), (0, 86)):
        saved = client.post(
            "/api/v1/workouts/diary",
            json={
                "measured_on": (today - timedelta(days=offset)).isoformat(),
                "custom_values": [{"definition_id": definition["id"], "value": value}],
            },
            headers=owner_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["custom_values"][0]["label"] == "Живот"

    summary = client.get(
        "/api/v1/workouts/progress/summary?period_days=30",
        headers=owner_headers,
    )
    assert summary.status_code == 200
    custom_trend = next(
        trend
        for trend in summary.json()["body"]["trends"]
        if trend["definition_id"] == definition["id"]
    )
    assert custom_trend["metric"] == f"custom:{definition['id']}"
    assert custom_trend["label"] == "Живот"
    assert custom_trend["unit"] == "cm"
    assert custom_trend["interpretation_status"] == "available"
    assert custom_trend["change"] == -2.0

    mixed = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": today.isoformat(),
            "weight_kg": 77,
            "waist_cm": 82,
            "custom_values": [{"definition_id": definition["id"], "value": 86}],
        },
        headers=owner_headers,
    )
    assert mixed.status_code == 200, mixed.text
    edited_custom_only = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": today.isoformat(),
            "custom_values": [{"definition_id": definition["id"], "value": 85}],
        },
        headers=owner_headers,
    )
    assert edited_custom_only.status_code == 200, edited_custom_only.text
    assert edited_custom_only.json()["weight_kg"] == 77
    assert edited_custom_only.json()["waist_cm"] == 82
    assert edited_custom_only.json()["custom_values"][0]["value"] == 85

    renamed = client.patch(
        f"/api/v1/workouts/diary/custom-definitions/{definition['id']}",
        json={"label": "Талия нижняя"},
        headers=owner_headers,
    )
    assert renamed.status_code == 200
    history = client.get("/api/v1/workouts/diary", headers=owner_headers)
    assert history.status_code == 200
    assert history.json()[0]["custom_values"][0]["definition_id"] == definition["id"]
    assert history.json()[0]["custom_values"][0]["label"] == "Талия нижняя"

    archived = client.delete(
        f"/api/v1/workouts/diary/custom-definitions/{definition['id']}",
        headers=owner_headers,
    )
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    historical_report = client.get(
        "/api/v1/workouts/progress/report?period=days_30",
        headers=owner_headers,
    )
    assert historical_report.status_code == 200, historical_report.text
    assert any(
        trend["label"] == "Талия нижняя"
        for trend in historical_report.json()["body"]["trends"]
        if trend["definition_id"] == definition["id"]
    )
    blocked_new_value = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": (today - timedelta(days=1)).isoformat(),
            "custom_values": [{"definition_id": definition["id"], "value": 85}],
        },
        headers=owner_headers,
    )
    assert blocked_new_value.status_code == 400

    restored = client.post(
        f"/api/v1/workouts/diary/custom-definitions/{definition['id']}/restore",
        headers=owner_headers,
    )
    assert restored.status_code == 200
    allowed_after_restore = client.post(
        "/api/v1/workouts/diary",
        json={
            "measured_on": (today - timedelta(days=1)).isoformat(),
            "custom_values": [{"definition_id": definition["id"], "value": 85}],
        },
        headers=owner_headers,
    )
    assert allowed_after_restore.status_code == 200

    with get_session_context() as db:
        assert db.query(BodyMeasurementDefinition).filter_by(id=definition["id"]).one().label == (
            "Талия нижняя"
        )
        assert (
            db.query(BodyMeasurementCustomValue)
            .join(BodyMeasurement)
            .filter(BodyMeasurement.user_id == _user_id(46_230))
            .count()
            == 4
        )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL concurrency")
def test_postgresql_upsert_uses_last_committed_write() -> None:
    owner_telegram_id = 46_219
    with get_session_context() as db:
        owner = User(telegram_user_id=owner_telegram_id, is_coach=False)
        db.add(owner)
        db.flush()
        owner_id = owner.id
    measured_on = date(2030, 1, 10)
    first_holds_row_lock = Event()
    second_started = Event()
    release_first = Event()

    def first_write() -> None:
        db = SessionLocal()
        try:
            _upsert_measurement(
                db,
                owner_user_id=owner_id,
                measured_on=measured_on,
                changes={"weight_kg": 74.0},
            )
            first_holds_row_lock.set()
            assert release_first.wait(timeout=5)
            db.commit()
        finally:
            db.close()

    def second_write() -> None:
        assert first_holds_row_lock.wait(timeout=5)
        db = SessionLocal()
        try:
            second_started.set()
            _upsert_measurement(
                db,
                owner_user_id=owner_id,
                measured_on=measured_on,
                changes={"weight_kg": 75.0},
            )
            db.commit()
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_write)
        second = executor.submit(second_write)
        assert second_started.wait(timeout=5)
        release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    with get_session_context() as db:
        row = db.query(BodyMeasurement).filter(BodyMeasurement.user_id == owner_id).one()
        assert row.weight_kg == 75.0


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL concurrency")
@pytest.mark.parametrize("second_writer", ["personal", "coach"])
def test_concurrent_same_day_measurement_writes_are_atomic(client, second_writer: str) -> None:
    coach_headers = _auth(client, 46_220, is_coach=True)
    owner_headers = _auth(client, 46_221, is_coach=False)
    _, owner_id = _link_client(46_220, 46_221)
    with get_session_context() as db:
        owner = db.get(User, owner_id)
        measured_on = today_for_user(owner).isoformat()

    barrier = Barrier(2)

    def write(path: str, headers: dict[str, str], weight_kg: float):
        barrier.wait(timeout=5)
        response = client.post(
            path,
            json={"measured_on": measured_on, "weight_kg": weight_kg},
            headers=headers,
        )
        return response

    second_path = (
        "/api/v1/workouts/diary"
        if second_writer == "personal"
        else f"/api/v1/coach/clients/{owner_id}/measurements"
    )
    second_headers = owner_headers if second_writer == "personal" else coach_headers
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda args: write(*args),
                [
                    ("/api/v1/workouts/diary", owner_headers, 74.0),
                    (second_path, second_headers, 75.0),
                ],
            )
        )

    assert [response.status_code for response in responses] == [200, 200]
    with get_session_context() as db:
        rows = (
            db.query(BodyMeasurement)
            .filter(
                BodyMeasurement.user_id == owner_id,
                BodyMeasurement.measured_on == date.fromisoformat(measured_on),
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].weight_kg in {74.0, 75.0}
