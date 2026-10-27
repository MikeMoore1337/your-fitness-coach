from datetime import UTC, date, datetime, time, timedelta

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import local_naive_to_utc_naive, now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.food_diary import FoodDiaryCopyOperation, FoodDiaryRepeatPreview
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.program import UserProgram, UserWorkout
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
            ("progress_next_action_completed", timedelta(days=6, hours=1)),
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
        assert (
            after_kpis["progress_next_action_completion_rate"]["numerator"]
            == before_kpis["progress_next_action_completion_rate"]["numerator"] + 1
        )
        assert after_kpis["progress_next_action_completion_rate"]["median_seconds"] == 3600.0
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


def test_lifecycle_report_exposes_privacy_safe_repeat_metrics(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        before = lifecycle_funnel_report(db, period_days=30)
        user = User(
            telegram_user_id=991006,
            is_coach=False,
            is_admin=False,
            created_at=now_msk_naive() - timedelta(days=10),
        )
        user.profile = UserProfile(timezone="UTC")
        db.add(user)
        db.flush()
        preview = FoodDiaryRepeatPreview(
            user_id=user.id,
            token_hash="a" * 64,
            request_fingerprint="b" * 64,
            source_snapshot_hash="c" * 64,
            copy_scope="meal",
            source_date=date(2026, 9, 20),
            source_meal_type="breakfast",
            target_date=date(2026, 9, 21),
            target_meal_type="breakfast",
            persistence_failure_count=1,
        )
        db.add(preview)
        db.flush()
        operation = FoodDiaryCopyOperation(
            user_id=user.id,
            preview_id=preview.id,
            idempotency_key="metrics-repeat-0001",
            request_fingerprint="d" * 64,
            copy_scope="meal",
            source_date=date(2026, 9, 20),
            source_meal_type="breakfast",
            target_date=date(2026, 9, 21),
            target_meal_type="breakfast",
            replay_count=2,
        )
        db.add(operation)
        db.commit()

        report = lifecycle_funnel_report(db, period_days=30)

    metrics = report["nutrition_repeat_metrics"]
    assert (
        metrics["eligible_opportunities"]
        == before["nutrition_repeat_metrics"]["eligible_opportunities"] + 1
    )
    assert (
        metrics["confirmed_repeats"] == before["nutrition_repeat_metrics"]["confirmed_repeats"] + 1
    )
    assert metrics["preview_to_confirmed_percent"] == 100.0
    assert metrics["persistence_failures"] == 1
    assert metrics["duplicate_prevention_count"] == 2
    assert "metrics-repeat-0001" not in str(report)


def test_lifecycle_report_uses_instance_recovery_facts_for_all_client_accounts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        before = lifecycle_funnel_report(db, period_days=30)
        missed_date = now_msk_naive().date() - timedelta(days=3)
        missed_at = local_naive_to_utc_naive(
            datetime.combine(missed_date + timedelta(days=1), time.min),
            "UTC",
        )
        recovery_at = missed_at + timedelta(hours=2)

        outstanding_user = User(
            telegram_user_id=991004,
            is_coach=False,
            is_admin=False,
            created_at=now_msk_naive() - timedelta(days=10),
        )
        outstanding_user.profile = UserProfile(timezone="UTC")
        recovered_user = User(
            telegram_user_id=991005,
            is_coach=False,
            is_admin=False,
            created_at=now_msk_naive() - timedelta(days=10),
        )
        recovered_user.profile = UserProfile(timezone="UTC")
        db.add_all([outstanding_user, recovered_user])
        db.flush()

        outstanding_program = UserProgram(
            user_id=outstanding_user.id,
            start_date=missed_date - timedelta(days=1),
            duration_weeks=1,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        recovered_program = UserProgram(
            user_id=recovered_user.id,
            start_date=missed_date - timedelta(days=1),
            duration_weeks=1,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        db.add_all([outstanding_program, recovered_program])
        db.flush()
        outstanding_workout = UserWorkout(
            user_program_id=outstanding_program.id,
            scheduled_date=missed_date,
            day_number=1,
            week_number=1,
            title="Невыполненная тренировка",
            status="planned",
        )
        recovered_workout = UserWorkout(
            user_program_id=recovered_program.id,
            scheduled_date=missed_date,
            day_number=1,
            week_number=1,
            title="Восстановленная тренировка",
            status="completed",
            completed_at=recovery_at + timedelta(hours=2),
        )
        db.add_all([outstanding_workout, recovered_workout])
        db.flush()
        assert record_lifecycle_milestone(
            db,
            recovered_user,
            "workout_missed",
            occurred_at=missed_at,
            workout_id=recovered_workout.id,
            program_id=recovered_program.id,
            program_revision_number=0,
            missed_at=missed_at,
        )
        assert record_lifecycle_milestone(
            db,
            recovered_user,
            "recovery_action_confirmed",
            occurred_at=recovery_at,
            workout_id=recovered_workout.id,
            program_id=recovered_program.id,
            program_revision_number=0,
            missed_at=missed_at,
        )
        db.commit()

        report = lifecycle_funnel_report(db, period_days=30)

    before_kpis = _kpis(before)
    after_kpis = _kpis(report)
    assert (
        after_kpis["missed_workout_recovery_conversion"]["denominator"]
        == before_kpis["missed_workout_recovery_conversion"]["denominator"] + 2
    )
    assert (
        after_kpis["missed_workout_recovery_conversion"]["numerator"]
        == before_kpis["missed_workout_recovery_conversion"]["numerator"] + 1
    )
    assert (
        after_kpis["recovery_to_completion_rate"]["denominator"]
        == before_kpis["recovery_to_completion_rate"]["denominator"] + 1
    )
    assert (
        after_kpis["recovery_to_completion_rate"]["numerator"]
        == before_kpis["recovery_to_completion_rate"]["numerator"] + 1
    )
    assert after_kpis["time_to_recovery"]["median_seconds"] is not None
    assert report["recovery_eligible_real_account_count"] >= (
        before["recovery_eligible_real_account_count"] + 2
    )
    assert "991004" not in str(report)


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
