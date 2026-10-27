from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from fitminiapp_api.core.timezone import today_in_timezone
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.hydration import HydrationEntry, HydrationGoal, HydrationPreset
from fitminiapp_api.models.user import User
from fitminiapp_api.schemas.hydration import HydrationEntryCreate, HydrationGoalSave
from fitminiapp_api.services import hydration as hydration_service
from fitminiapp_api.services.account_export import (
    ACCOUNT_EXPORT_SCHEMA_VERSION,
    build_account_export,
)


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False, "is_admin": False},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_hydration_quick_add_is_idempotent_and_isolated(client) -> None:
    headers = _auth(client, 81_001)
    other_headers = _auth(client, 81_002)
    diary_date = today_in_timezone("Europe/Moscow").isoformat()
    request_headers = {**headers, "Idempotency-Key": "hydration-entry-0001"}
    payload = {
        "volume_ml": 350,
        "beverage_type": "water",
        "diary_date": diary_date,
        "source": "quick_preset",
    }

    first = client.post(
        "/api/v1/nutrition/hydration/entries", headers=request_headers, json=payload
    )
    replay = client.post(
        "/api/v1/nutrition/hydration/entries", headers=request_headers, json=payload
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    day = client.get(
        "/api/v1/nutrition/hydration", headers=headers, params={"diary_date": diary_date}
    )
    assert day.status_code == 200
    assert day.json()["total_ml"] == 350
    assert len(day.json()["entries"]) == 1
    assert day.json()["reminder_suppression_key"].endswith(diary_date)
    assert day.json()["action_url"].endswith("hydration=quick")

    other_day = client.get(
        "/api/v1/nutrition/hydration",
        headers=other_headers,
        params={"diary_date": diary_date},
    )
    assert other_day.json()["total_ml"] == 0
    entry_id = first.json()["id"]
    assert (
        client.delete(
            f"/api/v1/nutrition/hydration/entries/{entry_id}", headers=other_headers
        ).status_code
        == 404
    )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_hydration_preset_upserts_keep_one_label(client) -> None:
    headers = _auth(client, 81_009)
    start = Barrier(2)

    def save(volume_ml: int):
        start.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/hydration/presets",
            headers=headers,
            json={"label": "Гонка", "volume_ml": volume_ml, "beverage_type": "water"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(save, (250, 500)))

    assert [response.status_code for response in responses] == [200, 200]
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 81_009).one()
        presets = db.query(HydrationPreset).filter_by(user_id=user.id, label="Гонка").all()
        assert len(presets) == 1
        assert presets[0].volume_ml in {250, 500}


def test_hydration_entry_can_be_edited_backdated_and_deleted(client) -> None:
    headers = _auth(client, 81_003)
    created = client.post(
        "/api/v1/nutrition/hydration/entries",
        headers={**headers, "Idempotency-Key": "hydration-entry-0002"},
        json={"volume_ml": 250, "beverage_type": "water", "source": "manual"},
    )
    assert created.status_code == 201
    occurred_at = datetime(2026, 8, 20, 8, 30, tzinfo=UTC)
    updated = client.patch(
        f"/api/v1/nutrition/hydration/entries/{created.json()['id']}",
        headers=headers,
        json={
            "volume_ml": 420,
            "beverage_type": "tea",
            "occurred_at": occurred_at.isoformat(),
        },
    )
    assert updated.status_code == 200
    assert updated.json()["volume_ml"] == 420
    assert updated.json()["beverage_type"] == "tea"
    assert updated.json()["diary_date"] == "2026-08-20"
    assert updated.json()["source"] == "history_edit"
    assert (
        client.delete(
            f"/api/v1/nutrition/hydration/entries/{created.json()['id']}", headers=headers
        ).status_code
        == 204
    )


def test_reference_goal_versions_and_optional_profile_reuse(client) -> None:
    headers = _auth(client, 81_004)
    first = client.post(
        "/api/v1/nutrition/hydration/goal",
        headers={**headers, "Idempotency-Key": "hydration-goal-0001"},
        json={
            "enabled": True,
            "source": "national_academies_beverages",
            "sex": "female",
            "adult_confirmed": True,
            "save_sex_to_profile": True,
        },
    )
    assert first.status_code == 200
    assert first.json()["target_ml"] == 2200
    assert first.json()["method_version"] == "nasem-ai-2005-observed-beverages-v1"
    assert client.get("/api/v1/me", headers=headers).json()["profile"]["sex"] == "female"
    replay = client.post(
        "/api/v1/nutrition/hydration/goal",
        headers={**headers, "Idempotency-Key": "hydration-goal-0001"},
        json={
            "enabled": True,
            "source": "national_academies_beverages",
            "sex": "female",
            "adult_confirmed": True,
            "save_sex_to_profile": True,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    conflict = client.post(
        "/api/v1/nutrition/hydration/goal",
        headers={**headers, "Idempotency-Key": "hydration-goal-0001"},
        json={"enabled": True, "source": "manual", "target_ml": 1900},
    )
    assert conflict.status_code == 409

    disabled = client.post(
        "/api/v1/nutrition/hydration/goal",
        headers={**headers, "Idempotency-Key": "hydration-goal-0002"},
        json={"enabled": False, "source": "manual"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    day = client.get(
        "/api/v1/nutrition/hydration",
        headers=headers,
        params={"diary_date": today_in_timezone("Europe/Moscow").isoformat()},
    ).json()
    assert day["goal"]["enabled"] is False
    assert day["progress_percent"] is None


def test_hydration_validates_future_and_idempotency_conflict(client) -> None:
    headers = _auth(client, 81_005)
    request_headers = {**headers, "Idempotency-Key": "hydration-entry-0003"}
    first = client.post(
        "/api/v1/nutrition/hydration/entries",
        headers=request_headers,
        json={"volume_ml": 250, "beverage_type": "water", "source": "manual"},
    )
    assert first.status_code == 201
    conflict = client.post(
        "/api/v1/nutrition/hydration/entries",
        headers=request_headers,
        json={"volume_ml": 500, "beverage_type": "water", "source": "manual"},
    )
    assert conflict.status_code == 409
    future = client.post(
        "/api/v1/nutrition/hydration/entries",
        headers={**headers, "Idempotency-Key": "hydration-entry-0004"},
        json={
            "volume_ml": 250,
            "beverage_type": "water",
            "source": "manual",
            "occurred_at": "2099-01-01T12:00:00Z",
        },
    )
    assert future.status_code == 422


def test_hydration_entry_uniqueness_race_replays_matching_request() -> None:
    payload = HydrationEntryCreate(volume_ml=250, beverage_type="water", source="manual")
    fingerprint = hydration_service._fingerprint(payload)
    now = datetime.now(UTC)
    existing = HydrationEntry(
        id=91,
        user_id=81_091,
        occurred_at=now,
        diary_date=now.date(),
        timezone="Europe/Moscow",
        volume_ml=250,
        beverage_type="water",
        source="manual",
        request_key="hydration-entry-race",
        payload_fingerprint=fingerprint,
        created_at=now.replace(tzinfo=None),
        updated_at=now.replace(tzinfo=None),
    )
    db = MagicMock()
    filtered = db.query.return_value.filter.return_value
    filtered.first.side_effect = [None, existing]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    result = hydration_service.create_hydration_entry(
        db,
        SimpleNamespace(id=81_091, profile=None),
        payload,
        "hydration-entry-race",
    )

    assert result["id"] == existing.id
    db.rollback.assert_called_once_with()


def test_hydration_goal_uniqueness_race_replays_matching_request() -> None:
    payload = HydrationGoalSave(enabled=True, source="manual", target_ml=3000)
    fingerprint = hydration_service._fingerprint(payload)
    today = today_in_timezone("Europe/Moscow")
    now = datetime.now().replace(tzinfo=None)
    existing = HydrationGoal(
        id=92,
        user_id=81_092,
        status="enabled",
        target_ml=3000,
        source="manual",
        method_version="manual-v1",
        reference_scope="beverages",
        sex=None,
        adult_confirmed=None,
        effective_from=today,
        effective_to=None,
        request_key="hydration-goal-race",
        payload_fingerprint=fingerprint,
        created_at=now,
    )
    db = MagicMock()
    filtered = db.query.return_value.filter.return_value
    filtered.first.side_effect = [None, existing]
    filtered.order_by.return_value.first.return_value = None
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    result = hydration_service.save_hydration_goal(
        db,
        SimpleNamespace(id=81_092, profile=None),
        payload,
        "hydration-goal-race",
    )

    assert result["id"] == existing.id
    db.rollback.assert_called_once_with()


def test_hydration_is_in_nutrition_report_without_invented_zero_days(client) -> None:
    headers = _auth(client, 81_006)
    diary_date = today_in_timezone("Europe/Moscow").isoformat()
    assert (
        client.post(
            "/api/v1/nutrition/hydration/goal",
            headers={**headers, "Idempotency-Key": "hydration-goal-report"},
            json={"enabled": True, "source": "manual", "target_ml": 2000},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/nutrition/hydration/entries",
            headers={**headers, "Idempotency-Key": "hydration-entry-report"},
            json={"volume_ml": 750, "beverage_type": "water", "source": "manual"},
        ).status_code
        == 201
    )
    report = client.get("/api/v1/workouts/progress/nutrition-report?period=days_7", headers=headers)
    assert report.status_code == 200
    hydration = report.json()["hydration"]
    assert hydration["total_ml"] == 750
    assert hydration["logged_days"] == 1
    assert hydration["coverage_percent"] == 14.3
    current = next(point for point in report.json()["daily"] if point["diary_date"] == diary_date)
    assert current["hydration_ml"] == 750
    assert current["hydration_target_ml"] == 2000
    assert current["hydration_progress_percent"] == 37.5


def test_hydration_is_exported_and_removed_with_account(client) -> None:
    telegram_user_id = 81_007
    headers = _auth(client, telegram_user_id)
    assert (
        client.post(
            "/api/v1/nutrition/hydration/goal",
            headers={**headers, "Idempotency-Key": "hydration-goal-export"},
            json={"enabled": True, "source": "manual", "target_ml": 1800},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/nutrition/hydration/entries",
            headers={**headers, "Idempotency-Key": "hydration-entry-export"},
            json={"volume_ml": 420, "beverage_type": "tea", "source": "manual"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/nutrition/hydration/presets",
            headers=headers,
            json={"label": "Термокружка", "volume_ml": 420, "beverage_type": "tea"},
        ).status_code
        == 200
    )
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == telegram_user_id).one()
        user_id = user.id
        exported = build_account_export(db, user)
        assert exported["schema_version"] == ACCOUNT_EXPORT_SCHEMA_VERSION
        assert exported["hydration"]["entries"][0]["volume_ml"] == 420
        assert exported["hydration"]["goals"][0]["target_ml"] == 1800
        assert exported["hydration"]["presets"][0]["label"] == "Термокружка"
        assert "request_key" not in exported["hydration"]["entries"][0]

    deleted = client.request(
        "DELETE", "/api/v1/me/account", headers=headers, json={"confirmation": "DELETE"}
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.query(HydrationEntry).filter(HydrationEntry.user_id == user_id).count() == 0
        assert db.query(HydrationGoal).filter(HydrationGoal.user_id == user_id).count() == 0
        assert db.query(HydrationPreset).filter(HydrationPreset.user_id == user_id).count() == 0
