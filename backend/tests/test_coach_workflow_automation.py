from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import SessionLocal, engine, get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachTask
from fitminiapp_api.models.program import ProgramRevision, UserProgram, UserWorkout
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.coach_workflow_automation import evaluate_coach_workflow


def _login(client, telegram_user_id: int, *, is_coach: bool) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "username": f"workflow_{telegram_user_id}",
            "is_coach": is_coach,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def _program(db, client: User) -> UserProgram:
    program = UserProgram(
        user_id=client.id,
        start_date=today_msk() - timedelta(days=14),
        duration_weeks=8,
        status="active",
        is_active=True,
        current_revision_number=0,
    )
    db.add(program)
    db.flush()
    return program


def _create_workflow_facts(client, *, with_all_events: bool = True) -> tuple[int, int]:
    _login(client, 985_001, is_coach=True)
    _login(client, 985_002, is_coach=True)
    for telegram_user_id in range(985_010, 985_014):
        _login(client, telegram_user_id, is_coach=False)

    now = now_msk_naive()
    today = today_msk()
    with get_session_context() as db:
        coach = _user(db, 985_001)
        other_coach = _user(db, 985_002)
        recent, due, missed, revised = (_user(db, value) for value in range(985_010, 985_014))
        db.add_all(
            [
                CoachClient(coach_user_id=coach.id, client_user_id=target.id, status="active")
                for target in (recent, due, missed, revised)
            ]
        )
        db.flush()
        if with_all_events:
            db.add(
                WeeklyCheckIn(
                    user_id=recent.id,
                    week_start=today - timedelta(days=7),
                    week_end=today - timedelta(days=1),
                    submitted_on=today - timedelta(days=1),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="test-v1",
                    summary={"private": "not exposed"},
                    note="private note not exposed",
                    created_at=now - timedelta(hours=1),
                )
            )
            db.add(
                WeeklyCheckIn(
                    user_id=due.id,
                    week_start=today - timedelta(days=14),
                    week_end=today - timedelta(days=8),
                    submitted_on=today - timedelta(days=8),
                    timezone="Europe/Moscow",
                    status="completed",
                    summary_version="test-v1",
                    summary={},
                    created_at=now - timedelta(days=3),
                )
            )
            missed_program = _program(db, missed)
            db.add(
                UserWorkout(
                    user_program_id=missed_program.id,
                    scheduled_date=today - timedelta(days=2),
                    day_number=1,
                    week_number=1,
                    title="Тренировка",
                    status="planned",
                )
            )
            revised_program = _program(db, revised)
            revised_program.current_revision_number = 1
            db.add(
                ProgramRevision(
                    user_program_id=revised_program.id,
                    revision_number=1,
                    changed_by_user_id=revised.id,
                    actor_role="self",
                    change_kind="plan_updated",
                    reason="internal test reason",
                    changed_fields={"operation": "test"},
                    snapshot={"private": "not exposed"},
                    created_at=now - timedelta(hours=2),
                )
            )
        return coach.id, other_coach.id


def test_workflow_automation_materializes_authoritative_events_once(client) -> None:
    coach_headers = _login(client, 985_101, is_coach=True)
    _login(client, 985_110, is_coach=False)
    with get_session_context() as db:
        coach = _user(db, 985_101)
        managed = _user(db, 985_110)
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=managed.id, status="active"))
        db.flush()
        db.add(
            WeeklyCheckIn(
                user_id=managed.id,
                week_start=today_msk() - timedelta(days=7),
                week_end=today_msk() - timedelta(days=1),
                submitted_on=today_msk() - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={"secret": "must not appear"},
                note="secret note",
                created_at=now_msk_naive() - timedelta(hours=1),
            )
        )

    preview = client.get("/api/v1/coach/workflow-automation/preview", headers=coach_headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["mode"] == "preview"
    assert preview.json()["tasks_created"] == 0
    assert preview.json()["proposals"][0]["outcome"] == "draft"
    assert "secret" not in preview.text

    first = client.post("/api/v1/coach/workflow-automation/evaluate", headers=coach_headers)
    assert first.status_code == 200, first.text
    assert first.json()["events_evaluated"] == 1
    assert first.json()["tasks_created"] == 1
    assert first.json()["proposals"][0]["task_state"] == "open"

    second = client.post("/api/v1/coach/workflow-automation/evaluate", headers=coach_headers)
    assert second.status_code == 200, second.text
    assert second.json()["tasks_created"] == 0
    assert second.json()["tasks_reused"] == 1
    assert second.json()["proposals"][0]["outcome"] == "already_processed"
    with get_session_context() as db:
        coach = _user(db, 985_101)
        assert db.query(CoachTask).filter(CoachTask.coach_user_id == coach.id).count() == 1
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "coach.workflow_automation_evaluated",
                AuditEvent.actor_user_id == coach.id,
            )
            .order_by(AuditEvent.id.desc())
            .first()
        )
        assert audit is not None
        assert "secret" not in str(audit.details).lower()


def test_workflow_automation_supports_all_events_and_isolates_coaches(client) -> None:
    coach_headers = _login(client, 985_201, is_coach=True)
    other_headers = _login(client, 985_202, is_coach=True)
    _login(client, 985_210, is_coach=False)
    foreign_headers = _login(client, 985_211, is_coach=False)
    _login(client, 985_212, is_coach=False)
    with get_session_context() as db:
        coach = _user(db, 985_201)
        other_coach = _user(db, 985_202)
        managed = _user(db, 985_210)
        foreign = _user(db, 985_211)
        due_managed = _user(db, 985_212)
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=managed.id, status="active"))
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=due_managed.id, status="active"))
        db.add(
            CoachClient(coach_user_id=other_coach.id, client_user_id=foreign.id, status="active")
        )
        db.flush()
        db.add(
            WeeklyCheckIn(
                user_id=managed.id,
                week_start=today_msk() - timedelta(days=7),
                week_end=today_msk() - timedelta(days=1),
                submitted_on=today_msk() - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={},
                created_at=now_msk_naive() - timedelta(hours=1),
            )
        )
        db.add(
            WeeklyCheckIn(
                user_id=due_managed.id,
                week_start=today_msk() - timedelta(days=14),
                week_end=today_msk() - timedelta(days=8),
                submitted_on=today_msk() - timedelta(days=8),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={},
                created_at=now_msk_naive() - timedelta(days=3),
            )
        )
        missed_program = _program(db, managed)
        db.add(
            UserWorkout(
                user_program_id=missed_program.id,
                scheduled_date=today_msk() - timedelta(days=2),
                day_number=1,
                week_number=1,
                title="Тренировка",
                status="planned",
            )
        )
        revised_program = missed_program
        revised_program.current_revision_number = 1
        db.add(
            ProgramRevision(
                user_program_id=revised_program.id,
                revision_number=1,
                changed_by_user_id=managed.id,
                actor_role="self",
                change_kind="plan_updated",
                changed_fields={},
                snapshot={},
                created_at=now_msk_naive() - timedelta(hours=1),
            )
        )

    preview = client.get("/api/v1/coach/workflow-automation/preview", headers=coach_headers)
    assert preview.status_code == 200, preview.text
    assert {item["event_kind"] for item in preview.json()["proposals"]} == {
        "check_in_submitted",
        "review_due",
        "missed_workout",
        "program_revision_ready",
    }
    other = client.get("/api/v1/coach/workflow-automation/preview", headers=other_headers)
    assert other.status_code == 200, other.text
    assert other.json()["proposals"] == []
    assert (
        client.get("/api/v1/coach/workflow-automation/preview", headers=foreign_headers).status_code
        == 403
    )


def test_workflow_automation_failed_flush_is_retryable(client, monkeypatch) -> None:
    _login(client, 985_301, is_coach=True)
    _login(client, 985_310, is_coach=False)
    with get_session_context() as db:
        coach = _user(db, 985_301)
        managed = _user(db, 985_310)
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=managed.id, status="active"))
        db.add(
            WeeklyCheckIn(
                user_id=managed.id,
                week_start=today_msk() - timedelta(days=7),
                week_end=today_msk() - timedelta(days=1),
                submitted_on=today_msk() - timedelta(days=1),
                timezone="Europe/Moscow",
                status="completed",
                summary_version="test-v1",
                summary={},
                created_at=now_msk_naive() - timedelta(hours=1),
            )
        )
        db.commit()
        coach_id = coach.id

    db = SessionLocal()
    coach = db.get(User, coach_id)
    assert coach is not None
    original_flush = db.flush
    failed = True

    def fail_once(*args, **kwargs):
        nonlocal failed
        if failed:
            failed = False
            raise RuntimeError("transient workflow failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_once)
    with pytest.raises(RuntimeError, match="transient workflow failure"):
        evaluate_coach_workflow(db, coach, apply=True)
    db.rollback()
    db.close()

    with get_session_context() as retry_db:
        retry_coach = retry_db.get(User, coach_id)
        assert retry_coach is not None
        result = evaluate_coach_workflow(retry_db, retry_coach, apply=True)
        assert result["tasks_created"] == 1
        assert retry_db.query(CoachTask).filter(CoachTask.coach_user_id == coach_id).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL concurrency")
def test_concurrent_workflow_evaluations_materialize_one_task(client) -> None:
    coach_id, _other_coach_id = _create_workflow_facts(client, with_all_events=True)
    barrier = Barrier(2)

    def run() -> dict[str, object]:
        db = SessionLocal()
        try:
            coach = db.get(User, coach_id)
            assert coach is not None
            barrier.wait(timeout=5)
            return evaluate_coach_workflow(db, coach, apply=True)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(lambda _index: run(), range(2))

    assert first["tasks_created"] + second["tasks_created"] == 4
    assert first["tasks_reused"] + second["tasks_reused"] == 4
    with get_session_context() as db:
        assert db.query(CoachTask).filter(CoachTask.coach_user_id == coach_id).count() == 4
