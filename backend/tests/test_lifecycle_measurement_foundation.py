from __future__ import annotations

from datetime import timedelta
from math import ceil
from statistics import median
from time import perf_counter

import pytest

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import local_naive_to_utc_naive, now_msk_naive
from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.lifecycle_milestone import LifecycleMilestone
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import CoachClient, User, UserProfile
from fitminiapp_api.services.lifecycle_milestones import record_lifecycle_milestone
from fitminiapp_api.services.lifecycle_reporting import lifecycle_funnel_report
from fitminiapp_api.services.trainer_capacity_reporting import build_trainer_capacity_report


def _user(db, telegram_user_id: int) -> User:
    return db.query(User).filter(User.telegram_user_id == telegram_user_id).one()


def test_lifecycle_writer_rejects_cross_account_instance_context() -> None:
    with get_session_context() as db:
        first = _user(db, 2001)
        second = _user(db, 2002)
        program = UserProgram(
            user_id=second.id,
            start_date=now_msk_naive().date(),
            duration_weeks=1,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        db.add(program)
        db.flush()

        assert (
            record_lifecycle_milestone(
                db,
                first,
                "recovery_action_confirmed",
                workout_id=999_999,
                program_id=program.id,
            )
            is False
        )
        assert (
            record_lifecycle_milestone(
                db,
                first,
                "program_activated",
                program_id=program.id,
            )
            is False
        )
        assert (
            db.query(LifecycleMilestone).filter(LifecycleMilestone.user_id == first.id).count() == 0
        )


def test_lifecycle_report_reconciles_quality_boundaries_without_identity_output(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        client = _user(db, 2001)
        other_client = _user(db, 2002)
        coach = _user(db, 1001)
        now = now_msk_naive()
        registration_at = local_naive_to_utc_naive(client.created_at, "Europe/Moscow")
        test_account = User(
            telegram_user_id=2_009_999,
            created_at=now,
            measurement_eligibility="test",
        )
        db.add(test_account)
        db.flush()

        other_program = UserProgram(
            user_id=other_client.id,
            start_date=now.date(),
            duration_weeks=1,
            schedule_weekdays=[0],
            status="active",
            is_active=True,
        )
        db.add(other_program)
        db.flush()
        db.add_all(
            [
                # A valid row before registration is an impossible-order fact.
                LifecycleMilestone(
                    user_id=client.id,
                    milestone_type="program_activated",
                    schema_version=2,
                    occurred_at=registration_at - timedelta(hours=1),
                ),
                # Future schema versions are retained for reconciliation but
                # never become KPI evidence.
                LifecycleMilestone(
                    user_id=client.id,
                    milestone_type="workout_started",
                    schema_version=999,
                    occurred_at=now - timedelta(hours=2),
                ),
                # Internal IDs are not sufficient authorization: the owner of
                # the referenced program must match the milestone account.
                LifecycleMilestone(
                    user_id=client.id,
                    milestone_type="program_activated",
                    schema_version=2,
                    occurred_at=now - timedelta(hours=1),
                    program_id=other_program.id,
                ),
                # Role-account rows are visible to reconciliation, never KPI.
                LifecycleMilestone(
                    user_id=coach.id,
                    milestone_type="program_activated",
                    schema_version=2,
                    occurred_at=now - timedelta(hours=1),
                ),
                LifecycleMilestone(
                    user_id=test_account.id,
                    milestone_type="program_activated",
                    schema_version=2,
                    occurred_at=now - timedelta(hours=1),
                ),
                # The worker should remove this row; the report makes lag
                # visible and excludes it from current KPI calculations.
                LifecycleMilestone(
                    user_id=client.id,
                    milestone_type="workout_completed",
                    schema_version=2,
                    occurred_at=now - timedelta(days=181),
                ),
            ]
        )
        db.commit()

        report = lifecycle_funnel_report(db, period_days=30)

    quality = report["data_quality"]
    assert quality["status"] == "attention"
    assert quality["impossible_order"] >= 1
    assert quality["demo_test_contamination"] >= 1
    assert quality["unauthorized_cross_account_outcomes"] >= 1
    assert quality["malformed_schema_versions"] >= 1
    assert quality["retention_expired_milestones"] >= 1
    assert quality["post_deletion_milestones"] == 0
    assert quality["duplicate_web_tma_outcomes"] == quality["duplicate_milestones"]
    assert report["sample_status"] == "INSUFFICIENT_SAMPLE"
    assert report["milestone_retention_days"] == 180
    assert report["aggregate_retention_days"] == 730
    assert "2001" not in str(report)
    assert "user_id" not in str(report)


def test_web_and_tma_retries_share_one_authoritative_milestone(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        user = _user(db, 2001)
        # Accounts created before the eligibility column existed have NULL and
        # remain eligible as legacy real clients.
        user.measurement_eligibility = None
        occurred_at = local_naive_to_utc_naive(
            now_msk_naive() - timedelta(hours=1),
            "Europe/Moscow",
        )
        assert record_lifecycle_milestone(
            db, user, "weekly_review_completed", occurred_at=occurred_at
        )
        assert not record_lifecycle_milestone(
            db,
            user,
            "weekly_review_completed",
            occurred_at=occurred_at,
        )
        db.commit()

        rows = (
            db.query(LifecycleMilestone)
            .filter(
                LifecycleMilestone.user_id == user.id,
                LifecycleMilestone.milestone_type == "weekly_review_completed",
            )
            .all()
        )
        report = lifecycle_funnel_report(db, period_days=30)

    assert len(rows) == 1
    assert report["data_quality"]["duplicate_web_tma_outcomes"] == 0
    assert report["data_quality"]["authoritative_success_count"] >= 1


@pytest.mark.parametrize("fixture_size", (10, 30, 100))
def test_product_v7_scale_evidence_is_bounded_to_client_and_trainer_reports(
    monkeypatch, fixture_size: int
) -> None:
    monkeypatch.setattr(settings, "app_env", "prod")
    with get_session_context() as db:
        now = now_msk_naive()
        trainer = User(
            telegram_user_id=5_440_000 + fixture_size,
            is_coach=True,
            is_admin=False,
            created_at=now,
        )
        clients = [
            User(
                telegram_user_id=5_450_000 + fixture_size * 1000 + index,
                created_at=now - timedelta(days=40),
                profile=UserProfile(timezone="UTC"),
            )
            for index in range(fixture_size)
        ]
        db.add(trainer)
        db.add_all(clients)
        db.flush()
        db.add_all(
            [
                LifecycleMilestone(
                    user_id=user.id,
                    milestone_type="program_activated",
                    schema_version=2,
                    occurred_at=local_naive_to_utc_naive(
                        user.created_at + timedelta(hours=1),
                        "Europe/Moscow",
                    ),
                )
                for user in clients
            ]
        )
        db.add_all(
            [CoachClient(coach_user_id=trainer.id, client_user_id=user.id) for user in clients]
        )
        db.commit()

        lifecycle_samples: list[float] = []
        lifecycle_queries: list[int] = []
        trainer_samples: list[float] = []
        trainer_queries: list[int] = []
        for _ in range(3):
            token = begin_sql_metrics()
            started = perf_counter()
            lifecycle_funnel_report(db, period_days=30)
            lifecycle_samples.append((perf_counter() - started) * 1000)
            lifecycle_queries.append(current_sql_metrics().query_count)
            reset_sql_metrics(token)

            token = begin_sql_metrics()
            started = perf_counter()
            trainer_report = build_trainer_capacity_report(db, period_days=30)
            trainer_samples.append((perf_counter() - started) * 1000)
            trainer_queries.append(current_sql_metrics().query_count)
            reset_sql_metrics(token)

    def p95(values: list[float]) -> float:
        return sorted(values)[max(0, ceil(len(values) * 0.95) - 1)]

    assert trainer_report["active_client_count"] == fixture_size
    assert all(query_count > 0 for query_count in lifecycle_queries + trainer_queries)
    print(
        "scale_evidence"
        f" fixture={fixture_size}"
        f" lifecycle_query_count={max(lifecycle_queries)}"
        f" lifecycle_p50_ms={median(lifecycle_samples):.3f}"
        f" lifecycle_p95_ms={p95(lifecycle_samples):.3f}"
        f" trainer_query_count={max(trainer_queries)}"
        f" trainer_p50_ms={median(trainer_samples):.3f}"
        f" trainer_p95_ms={p95(trainer_samples):.3f}"
    )
