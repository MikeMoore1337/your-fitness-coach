"""End-to-end authorization and deterministic real-world-like DEV fixtures."""

from datetime import timedelta

import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.check_in import WeeklyCheckIn
from fitminiapp_api.models.coach_crm import CoachBusinessSession
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.food_diary import FoodDiaryEntry
from fitminiapp_api.models.hydration import HydrationEntry
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutSet
from fitminiapp_api.models.user import BodyMeasurement, CoachClient, User
from fitminiapp_api.services.local_dev_fixtures import (
    maybe_seed_local_dev_data,
    seed_local_dev_data,
)


def _login(client, telegram_user_id: int, coach: bool, admin: bool = False) -> dict:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={
            "telegram_user_id": telegram_user_id,
            "is_coach": coach,
            "is_admin": admin,
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_dev_fixture_is_rich_idempotent_and_user_scoped() -> None:
    with get_session_context() as db:
        seed_local_dev_data(db)
        db.flush()
        ids = {
            user.telegram_user_id: user.id
            for user in db.query(User).filter(
                User.telegram_user_id.in_((1001, 1002, 2001, 2002, 2003))
            )
        }
        assert len(ids) == 5
        coach = db.get(User, ids[1002])
        client = db.get(User, ids[2001])
        admin = db.get(User, ids[1001])
        assert coach is not None and coach.is_coach and not coach.is_admin
        assert client is not None and not client.is_coach and not client.is_admin
        assert admin is not None and admin.is_coach and admin.is_admin
        assert all(
            db.get(User, user_id).measurement_eligibility == "synthetic" for user_id in ids.values()
        )
        assert db.query(CoachClient).filter_by(coach_user_id=coach.id, status="active").count() == 3
        assert db.query(UserProgram).filter_by(user_id=client.id, is_active=True).count() == 1
        program = db.query(UserProgram).filter_by(user_id=client.id).one()
        assert db.query(UserWorkout).filter_by(user_program_id=program.id).count() >= 32
        assert db.query(UserWorkoutSet).filter(UserWorkoutSet.is_completed.is_(True)).count() > 200
        assert db.query(BodyMeasurement).filter_by(user_id=client.id).count() == 13
        assert db.query(Food).filter_by(owner_user_id=client.id).count() == 16
        assert db.query(FoodDiaryEntry).filter_by(user_id=client.id).count() >= 300
        assert db.query(HydrationEntry).filter_by(user_id=client.id).count() == 175
        assert db.query(WeeklyCheckIn).filter_by(user_id=client.id).count() == 8
        assert (
            db.query(CoachBusinessSession)
            .filter_by(coach_user_id=coach.id, client_user_id=client.id)
            .count()
            == 8
        )
        assert (
            db.query(UserWorkout)
            .filter(
                UserWorkout.user_program_id == program.id,
                UserWorkout.scheduled_date >= today_msk(),
                UserWorkout.status == "planned",
            )
            .count()
            >= 10
        )
        measurements = db.query(BodyMeasurement).filter_by(user_id=client.id).all()
        assert any(round(m.weight_kg * 100) % 10 != 0 for m in measurements)
        assert any(m.measured_on < today_msk() - timedelta(days=60) for m in measurements)

        tables = (
            User,
            CoachClient,
            UserProgram,
            UserWorkout,
            UserWorkoutSet,
            Food,
            FoodDiaryEntry,
            HydrationEntry,
            BodyMeasurement,
            WeeklyCheckIn,
            CoachBusinessSession,
        )
        before = tuple(db.query(table).count() for table in tables)
        seed_local_dev_data(db)
        db.flush()
        assert before == tuple(db.query(table).count() for table in tables)


def test_fixed_dev_roles_authorization_and_coach_tenant_scope(client, monkeypatch) -> None:
    with get_session_context() as db:
        seed_local_dev_data(db)
        db.commit()
        trainee_id = db.query(User.id).filter_by(telegram_user_id=2001).scalar()
        other_id = db.query(User.id).filter_by(telegram_user_id=2002).scalar()

    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "1001")
    client_headers = _login(client, 2001, False)
    coach_headers = _login(client, 1002, True)
    root_headers = _login(client, 1001, True, True)

    for headers, coach, root in (
        (client_headers, False, False),
        (coach_headers, True, False),
        (root_headers, True, True),
    ):
        me = client.get("/api/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["is_coach"] is coach
        assert me.json()["is_root"] is root

    assert client.get("/api/v1/coach/clients", headers=client_headers).status_code == 403
    coaching = client.get("/api/v1/coach/clients", headers=coach_headers)
    assert coaching.status_code == 200, coaching.text
    assert {item["id"] for item in coaching.json()} >= {trainee_id, other_id}

    admin_endpoint = "/api/v1/admin/users?q=2001"
    assert client.get(admin_endpoint, headers=client_headers).status_code == 403
    assert client.get(admin_endpoint, headers=coach_headers).status_code == 403
    assert client.get(admin_endpoint, headers=root_headers).status_code == 200
    assert client.get("/api/v1/admin/users?q=2001").status_code == 401

    # No other synthetic user can log in, even though the coach manages them.
    assert (
        client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": 2002, "is_coach": False},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/dev-login",
            json={"telegram_user_id": 2001, "is_coach": True, "is_admin": True},
        ).status_code
        == 403
    )


def test_fixed_dev_fixture_refuses_non_local_database(monkeypatch) -> None:
    monkeypatch.setattr(settings, "dev_auth_fixed_accounts_only", True)
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg://yfc_dev:testing@remote.example/yfc_dev",
    )
    with get_session_context() as db, pytest.raises(RuntimeError, match="isolated yfc_dev"):
        maybe_seed_local_dev_data(db)
