from __future__ import annotations

from datetime import timedelta

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachTask
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
