from __future__ import annotations

from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachBusinessSession, CoachTask
from fitminiapp_api.models.coach_reviews import CoachCheckInReview
from fitminiapp_api.models.user import CoachClient, User


def _login(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"review_{telegram_user_id}",
            "is_coach": is_coach,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def test_check_in_review_is_scoped_and_creates_a_bounded_follow_up(client) -> None:
    coach_headers = _login(client, 985_001, is_coach=True)
    other_coach_headers = _login(client, 985_002, is_coach=True)
    _login(client, 985_010, is_coach=False)

    with get_session_context() as db:
        coach = _user(db, 985_001)
        other_coach = _user(db, 985_002)
        managed = _user(db, 985_010)
        db.add_all(
            [
                CoachClient(coach_user_id=coach.id, client_user_id=managed.id),
                WeeklyCheckIn(
                    user_id=managed.id,
                    week_start=today_msk() - timedelta(days=7),
                    week_end=today_msk() - timedelta(days=1),
                    submitted_on=today_msk() - timedelta(days=1),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="test-v1",
                    summary={"training": {"completed_workouts": 2}},
                    note="Клиентская заметка",
                    created_at=now_msk_naive() - timedelta(hours=2),
                ),
            ]
        )
        db.flush()
        coach_id = coach.id
        other_coach_id = other_coach.id
        managed_id = managed.id
        check_in_id = db.query(WeeklyCheckIn.id).filter_by(user_id=managed.id).scalar()
        db.commit()

    pending = client.get("/api/v1/coach/check-ins/review?status=pending", headers=coach_headers)
    assert pending.status_code == 200, pending.text
    assert pending.json()["total"] == 1
    assert pending.json()["items"][0]["review_status"] == "pending"
    assert pending.json()["items"][0]["summary"] == {"training": {"completed_workouts": 2}}

    forbidden = client.post(
        f"/api/v1/coach/check-ins/{check_in_id}/review",
        headers=other_coach_headers,
        json={"response": "Чужой доступ"},
    )
    assert forbidden.status_code == 404

    reviewed = client.post(
        f"/api/v1/coach/check-ins/{check_in_id}/review",
        headers=coach_headers,
        json={
            "response": "Отмечу прогресс и вернусь с уточнением.",
            "follow_up_title": "Написать клиенту после следующей тренировки",
            "follow_up_due_at": "2030-01-10T12:00:00",
            "follow_up_timezone": "Europe/Moscow",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    payload = reviewed.json()
    assert payload["review_status"] == "reviewed"
    assert payload["review_response"] == "Отмечу прогресс и вернусь с уточнением."
    assert payload["follow_up"]["kind"] == "schedule_follow_up"
    assert payload["follow_up"]["source_kind"] == "weekly_check_in"
    assert payload["follow_up"]["source_id"] == check_in_id

    pending_after = client.get(
        "/api/v1/coach/check-ins/review?status=pending", headers=coach_headers
    )
    assert pending_after.status_code == 200
    assert pending_after.json()["total"] == 0
    reviewed_list = client.get(
        "/api/v1/coach/check-ins/review?status=reviewed",
        headers=coach_headers,
    )
    assert reviewed_list.status_code == 200
    assert reviewed_list.json()["total"] == 1

    with get_session_context() as db:
        review = db.query(CoachCheckInReview).one()
        task = db.query(CoachTask).one()
        assert review.coach_user_id == coach_id
        assert review.client_user_id == managed_id
        assert review.follow_up_task_id == task.id
        assert task.coach_user_id == coach_id
        assert task.source_id == check_in_id
        assert db.query(CoachCheckInReview).filter_by(coach_user_id=other_coach_id).count() == 0


def test_check_in_review_does_not_expose_unmanaged_check_in(client) -> None:
    coach_headers = _login(client, 985_101, is_coach=True)
    _login(client, 985_110, is_coach=False)
    with get_session_context() as db:
        managed = _user(db, 985_110)
        row = WeeklyCheckIn(
            user_id=managed.id,
            week_start=today_msk() - timedelta(days=7),
            week_end=today_msk() - timedelta(days=1),
            submitted_on=today_msk() - timedelta(days=1),
            timezone="Europe/Moscow",
            status="completed",
            summary_version="test-v1",
            summary={},
            created_at=now_msk_naive(),
        )
        db.add(row)
        db.commit()
        check_in_id = row.id

    response = client.post(
        f"/api/v1/coach/check-ins/{check_in_id}/review",
        headers=coach_headers,
        json={"response": "Не должен пройти"},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/coach/check-ins/review", headers=coach_headers).json()["total"] == 0


def test_review_workspace_composes_bounded_facts_and_trainer_private_notes(client) -> None:
    coach_headers = _login(client, 985_201, is_coach=True)
    other_coach_headers = _login(client, 985_202, is_coach=True)
    _login(client, 985_210, is_coach=False)

    with get_session_context() as db:
        coach = _user(db, 985_201)
        managed = _user(db, 985_210)
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=managed.id))
        current_week = today_msk() - timedelta(days=7)
        previous_week = current_week - timedelta(days=7)
        db.add_all(
            [
                WeeklyCheckIn(
                    user_id=managed.id,
                    week_start=previous_week,
                    week_end=previous_week + timedelta(days=6),
                    submitted_on=previous_week + timedelta(days=6),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="test-v1",
                    summary={
                        "training": {
                            "planned_workouts": 3,
                            "completed_workouts": 2,
                            "adherence": {"percent": 66.7},
                        },
                        "nutrition": {
                            "logged_days": 4,
                            "complete_days": 3,
                            "average_calories": 2_000,
                            "target_calories": 2_100,
                            "average_protein_g": 120,
                            "target_protein_g": 130,
                        },
                        "progression": {
                            "training_volume_kg": 1_000,
                            "new_personal_records": 1,
                        },
                        "weight_trend": {
                            "latest_value": 80,
                            "change": 0,
                            "latest_measured_on": previous_week.isoformat(),
                        },
                        "anthropometry_trends": [],
                    },
                    created_at=now_msk_naive() - timedelta(days=8),
                ),
                WeeklyCheckIn(
                    user_id=managed.id,
                    week_start=current_week,
                    week_end=current_week + timedelta(days=6),
                    submitted_on=current_week + timedelta(days=6),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="test-v1",
                    summary={
                        "training": {
                            "planned_workouts": 4,
                            "completed_workouts": 3,
                            "adherence": {"percent": 75},
                        },
                        "nutrition": {
                            "logged_days": 6,
                            "complete_days": 5,
                            "average_calories": 2_100,
                            "target_calories": 2_100,
                            "average_protein_g": 135,
                            "target_protein_g": 130,
                        },
                        "progression": {
                            "training_volume_kg": 1_250,
                            "new_personal_records": 2,
                        },
                        "weight_trend": {
                            "latest_value": 79.2,
                            "change": -0.8,
                            "latest_measured_on": current_week.isoformat(),
                        },
                        "anthropometry_trends": [
                            {"metric": "waist_cm", "latest_value": 84},
                        ],
                    },
                    created_at=now_msk_naive() - timedelta(days=1),
                ),
                CoachBusinessSession(
                    coach_user_id=coach.id,
                    client_user_id=managed.id,
                    starts_at_utc=now_msk_naive() - timedelta(days=1),
                    timezone="Europe/Moscow",
                    duration_minutes=60,
                    format="online",
                    status="completed",
                    private_note="Только для тренера: обсудить технику приседа.",
                ),
            ]
        )
        db.commit()
        managed_id = managed.id

    response = client.get(
        f"/api/v1/coach/clients/{managed_id}/review-workspace",
        headers=coach_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["state"] == "available"
    assert payload["previous_check_in"]["id"] != payload["current_check_in"]["id"]
    assert payload["training_actuals"]["completed_workouts"] == 3
    assert payload["progression_facts"]["training_volume_kg"] == 1_250
    assert payload["nutrition"]["logged_days"] == 6
    assert payload["measurements"]["weight_kg"] == 79.2
    assert {item["key"] for item in payload["meaningful_changes"]} >= {
        "training.completed_workouts",
        "progression.training_volume_kg",
        "nutrition.logged_days",
        "measurements.weight_kg",
    }
    change = next(
        item
        for item in payload["meaningful_changes"]
        if item["key"] == "training.completed_workouts"
    )
    assert change["source"] == "weekly_check_in"
    assert change["source_id"] == payload["current_check_in"]["id"]
    assert change["occurred_at"] == payload["current_check_in"]["submitted_on"]
    assert "Завершённые тренировки" in change["reason"]
    assert payload["private_notes"][0]["text"] == "Только для тренера: обсудить технику приседа."

    assert (
        client.get(
            f"/api/v1/coach/clients/{managed_id}/review-workspace",
            headers=other_coach_headers,
        ).status_code
        == 404
    )
