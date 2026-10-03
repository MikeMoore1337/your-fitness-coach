from datetime import UTC, datetime, timedelta

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import local_naive_to_utc_naive, now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.services.accounts import delete_user_cascade
from fitminiapp_api.services.lifecycle_milestones import (
    prune_lifecycle_milestones,
    record_lifecycle_milestone,
)
from fitminiapp_api.services.lifecycle_reporting import lifecycle_funnel_report


def _kpis(report: dict) -> dict[str, dict]:
    return {row["key"]: row for row in report["kpis"]}


def test_milestones_are_server_confirmed_daily_deduped_and_role_scoped() -> None:
    with get_session_context() as db:
        client = db.query(User).filter(User.telegram_user_id == 2001).one()
        if client.profile is None:
            client.profile = UserProfile(timezone="Europe/Moscow")
        else:
            client.profile.timezone = "Europe/Moscow"
        coach = User(telegram_user_id=991001, is_coach=True, is_admin=False)
        db.add(coach)
        db.flush()

        first = datetime(2026, 1, 2, 9, tzinfo=UTC)
        assert (
            record_lifecycle_milestone(
                db,
                client,
                "nutrition_entry_confirmed",
                occurred_at=first,
                day_scope=True,
            )
            is True
        )
        assert (
            record_lifecycle_milestone(
                db,
                client,
                "nutrition_entry_confirmed",
                occurred_at=first + timedelta(hours=4),
                day_scope=True,
            )
            is False
        )
        assert (
            record_lifecycle_milestone(
                db,
                coach,
                "nutrition_entry_confirmed",
                occurred_at=first,
            )
            is False
        )
        db.commit()

        rows = db.query(LifecycleMilestone).filter(LifecycleMilestone.user_id == client.id).all()
        assert len(rows) == 1
        assert rows[0].surface == "server"
        assert rows[0].server_confirmed is True
        assert rows[0].authoritative_outcome_status == "confirmed"
        assert rows[0].occurred_at == datetime(2026, 1, 1, 21, tzinfo=None)


def test_lifecycle_report_tracks_complete_windows_and_excludes_raw_identity(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        before = lifecycle_funnel_report(db, period_days=60)
        registration_msk = now_msk_naive() - timedelta(days=40)
        user = User(
            telegram_user_id=991002,
            is_coach=False,
            is_admin=False,
            created_at=registration_msk,
        )
        user.profile = UserProfile(timezone="UTC")
        db.add(user)
        db.flush()
        registration = local_naive_to_utc_naive(registration_msk, "Europe/Moscow")

        events = (
            ("onboarding_completed", timedelta(hours=1)),
            ("program_activated", timedelta(hours=2)),
            ("workout_started", timedelta(hours=3)),
            ("workout_completed", timedelta(hours=4)),
            ("workout_started", timedelta(days=1)),
            ("nutrition_entry_confirmed", timedelta(days=2)),
            ("nutrition_entry_confirmed", timedelta(days=3)),
            ("weekly_review_completed", timedelta(days=6)),
            ("workout_completed", timedelta(days=7)),
            ("workout_started", timedelta(days=30)),
        )
        for milestone_type, offset in events:
            assert (
                record_lifecycle_milestone(
                    db,
                    user,
                    milestone_type,
                    occurred_at=registration + offset,
                )
                is True
            )
        db.commit()

        report = lifecycle_funnel_report(db, period_days=60)
        before_kpis = _kpis(before)
        after_kpis = _kpis(report)

        assert report["effect_status"] == "NOT_YET_PROVEN"
        assert report["analytics_provider_status"] == "not_connected"
        assert report["cohort_size"] == before["cohort_size"] + 1
        assert (
            after_kpis["activation_rate"]["numerator"]
            == before_kpis["activation_rate"]["numerator"] + 1
        )
        assert (
            after_kpis["time_to_first_useful_action"]["numerator"]
            == before_kpis["time_to_first_useful_action"]["numerator"] + 1
        )
        assert (
            after_kpis["first_workout_completion_rate"]["numerator"]
            == before_kpis["first_workout_completion_rate"]["numerator"] + 1
        )
        assert (
            after_kpis["first_week_value_rate"]["numerator"]
            == before_kpis["first_week_value_rate"]["numerator"] + 1
        )
        assert (
            after_kpis["d1_meaningful_return"]["numerator"]
            == before_kpis["d1_meaningful_return"]["numerator"] + 1
        )
        assert (
            after_kpis["d7_meaningful_return"]["numerator"]
            == before_kpis["d7_meaningful_return"]["numerator"] + 1
        )
        assert (
            after_kpis["d30_meaningful_return"]["numerator"]
            == before_kpis["d30_meaningful_return"]["numerator"] + 1
        )
        assert (
            after_kpis["nutrition_repeat_rate"]["numerator"]
            == before_kpis["nutrition_repeat_rate"]["numerator"] + 1
        )
        assert (
            after_kpis["weekly_loop_completion"]["numerator"]
            == before_kpis["weekly_loop_completion"]["numerator"] + 1
        )
        assert "user_id" not in str(report)
        assert "nutrition" not in report["coverage_note"].lower()


def test_lifecycle_report_is_empty_outside_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    with get_session_context() as db:
        report = lifecycle_funnel_report(db, period_days=30)

    assert report["cohort_size"] == 0
    assert report["eligible_real_account_count"] == 0
    assert "non-production" in report["coverage_note"]
    assert report["exclusions"][0] == "любые аккаунты и события non-production окружений"


def test_milestone_retention_and_account_deletion_remove_evidence() -> None:
    with get_session_context() as db:
        user = User(telegram_user_id=991003, is_coach=False, is_admin=False)
        db.add(user)
        db.flush()
        now = datetime(2026, 1, 1, 12)
        record_lifecycle_milestone(
            db,
            user,
            "program_activated",
            occurred_at=now - timedelta(days=181),
        )
        record_lifecycle_milestone(
            db,
            user,
            "workout_started",
            occurred_at=now - timedelta(days=1),
        )
        db.commit()

        assert prune_lifecycle_milestones(db, retention_days=180, now=now) == 1
        db.commit()
        assert (
            db.query(LifecycleMilestone).filter(LifecycleMilestone.user_id == user.id).count() == 1
        )

        delete_user_cascade(db, user)
        db.delete(user)
        db.commit()
        assert (
            db.query(LifecycleMilestone).filter(LifecycleMilestone.user_id == user.id).count() == 0
        )
