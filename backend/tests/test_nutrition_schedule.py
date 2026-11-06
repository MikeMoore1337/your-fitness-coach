from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from test_program_week_cycle import _auth, _payload

from fitminiapp_api.core import timezone as timezone_module
from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.performance import begin_sql_metrics, current_sql_metrics, reset_sql_metrics
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.nutrition import (
    NutritionScheduleBinding,
    NutritionTarget,
    NutritionTargetScheduleRule,
)
from fitminiapp_api.models.program import ProgramRevision, UserProgram
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.nutrition import get_nutrition_target_for_date
from fitminiapp_api.services.nutrition_schedule import load_scheduled_nutrition_targets
from fitminiapp_api.services.program_versioning import record_program_revision


def test_schedule_resolves_cycle_types_future_repeats_and_date_priority(client) -> None:
    headers = _auth(client, 952400)
    payload = _payload(client, headers)
    payload["week_cycle"] = {
        "length_weeks": 3,
        "repeat": True,
        "week_types": ["light", "medium", "heavy"],
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 30},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    context = client.get("/api/v1/nutrition/targets/schedule/program", headers=headers)
    assert context.status_code == 200
    assert context.json()["program_id"] == program_id
    assert context.json()["revision_number"] == 1
    assert context.json()["week_types"] == ["light", "medium", "heavy"]
    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952400).scalar()
        program = db.get(UserProgram, program_id)
        start = program.start_date

    for index, (scope, day_type, week_type, calories, carbs, first_day) in enumerate(
        [
            ("template", "training", None, 2200, 242, start + timedelta(days=1)),
            ("template", "training", "medium", 2300, 270, start + timedelta(days=1)),
            ("template", "rest", None, 1900, 170, start + timedelta(days=1)),
            ("future", "training", "medium", 2500, 315, start + timedelta(weeks=1)),
        ]
    ):
        rule_payload = {
            **base,
            "calories": calories,
            "carbs_g": carbs,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": first_day.isoformat(),
            "scope": scope,
            "day_type": day_type,
            "week_type": week_type,
        }
        if index == 0:
            preview = client.post(
                "/api/v1/nutrition/targets/schedule/preview",
                json={
                    **rule_payload,
                    "date_from": first_day.isoformat(),
                    "date_to": (first_day + timedelta(days=20)).isoformat(),
                },
                headers=headers,
            )
            assert preview.status_code == 200, preview.text
            assert preview.json()["changes"]
            with get_session_context() as db:
                assert db.query(NutritionTargetScheduleRule).filter_by(user_id=user_id).count() == 0
                assert db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count() == 0
            rule_payload.update(
                expected_binding_id=preview.json()["expected_binding_id"],
                expected_target_version=preview.json()["expected_target_version"],
            )
        response = client.post(
            "/api/v1/nutrition/targets/schedule",
            json=rule_payload,
            headers={**headers, "Idempotency-Key": f"schedule-rule-{index}"},
        )
        assert response.status_code == 200, response.text
        if index == 0:
            with get_session_context() as db:
                for change in preview.json()["changes"]:
                    from datetime import date

                    target = get_nutrition_target_for_date(
                        db, user_id, date.fromisoformat(change["date"])
                    )
                    assert target.calories == change["after"]["calories"]
            retry = client.post(
                "/api/v1/nutrition/targets/schedule",
                json=rule_payload,
                headers={**headers, "Idempotency-Key": "schedule-rule-0"},
            )
            assert retry.status_code == 200
            assert retry.json()["id"] == response.json()["id"]
            conflict = client.post(
                "/api/v1/nutrition/targets/schedule",
                json={**rule_payload, "calories": 2300, "carbs_g": 270},
                headers={**headers, "Idempotency-Key": "schedule-rule-0"},
            )
            assert conflict.status_code == 409
    history = client.get("/api/v1/nutrition/targets/schedule", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 4
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, start).calories == 2000
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(days=1)).calories == 1900
        )
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=1)).calories == 2500
        )
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=2)).calories == 2200
        )
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=4)).calories == 2500
        )

    selected = start + timedelta(weeks=4)
    override = client.post(
        "/api/v1/nutrition/targets/dates",
        json={**base, "calories": 2700, "carbs_g": 370, "effective_from": selected.isoformat()},
        headers={**headers, "Idempotency-Key": "schedule-date-override"},
    )
    assert override.status_code == 200, override.text
    resolved = client.get(
        "/api/v1/nutrition/targets/for-date",
        params={"target_date": selected.isoformat()},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["origin"] == "date"
    assert resolved.json()["target"]["calories"] == 2700
    plan = client.get(
        "/api/v1/nutrition/plans/day", params={"plan_date": selected.isoformat()}, headers=headers
    )
    assert plan.status_code == 200
    assert Decimal(plan.json()["targets"]["energy_kcal"]) == 2700

    changed = client.patch(
        f"/api/v1/programs/assigned/{program_id}/cycle",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "effective_from_week": 5,
            "copy_day_number": 1,
            "new_day_weekday": (start.weekday() + 1) % 7,
            "new_day_title": "Дополнительная тренировка",
        },
    )
    assert changed.status_code == 200, changed.text
    first_changed = start + timedelta(weeks=4, days=1)
    later_changed = start + timedelta(weeks=7, days=1)
    status = client.get(
        "/api/v1/nutrition/targets/schedule/binding",
        params={"target_date": later_changed.isoformat()},
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["program_changed"] is True
    assert status.json()["revision_number"] == 1
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, later_changed).calories == 1900
        before_bindings = db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count()
    protected = client.post(
        "/api/v1/nutrition/targets/dates",
        json={
            **base,
            "calories": 2700,
            "carbs_g": 370,
            "effective_from": first_changed.isoformat(),
        },
        headers={**headers, "Idempotency-Key": "protected-date-952"},
    )
    assert protected.status_code == 200
    preview_request = {
        "program_id": program_id,
        "revision_number": 2,
        "effective_from": (start + timedelta(weeks=4)).isoformat(),
        "date_from": first_changed.isoformat(),
        "date_to": later_changed.isoformat(),
    }
    preview = client.post(
        "/api/v1/nutrition/targets/schedule/binding/preview", json=preview_request, headers=headers
    )
    assert preview.status_code == 200, preview.text
    changes = {row["date"]: row for row in preview.json()["changes"]}
    assert first_changed.isoformat() not in changes
    assert changes[later_changed.isoformat()]["before"]["calories"] == 1900
    assert changes[later_changed.isoformat()]["after"]["calories"] == 2500
    with get_session_context() as db:
        assert (
            db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count() == before_bindings
        )
        assert get_nutrition_target_for_date(db, user_id, later_changed).calories == 1900
    confirm_payload = {
        "program_id": program_id,
        "revision_number": 2,
        "effective_from": preview_request["effective_from"],
        "expected_binding_id": preview.json()["expected_binding_id"],
        "confirm": True,
    }
    unconfirmed = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json={**confirm_payload, "confirm": False},
        headers={**headers, "Idempotency-Key": "unconfirmed-binding-952"},
    )
    assert unconfirmed.status_code == 422
    with get_session_context() as db:
        program = db.get(UserProgram, program_id)
        user = db.get(User, user_id)
        record_program_revision(
            db,
            program,
            actor=user,
            change_kind="plan_updated",
            changed_fields={"operation": "concurrent_test_edit"},
        )
    outdated = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json=confirm_payload,
        headers={**headers, "Idempotency-Key": "outdated-binding-952"},
    )
    assert outdated.status_code == 409
    preview = client.post(
        "/api/v1/nutrition/targets/schedule/binding/preview",
        json={**preview_request, "revision_number": 3},
        headers=headers,
    )
    assert preview.status_code == 200
    confirm_payload["revision_number"] = 3
    confirm_payload["expected_binding_id"] = preview.json()["expected_binding_id"]
    confirm_payload["expected_target_version"] = preview.json()["expected_target_version"]
    stale = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json={**confirm_payload, "expected_binding_id": 999999},
        headers={**headers, "Idempotency-Key": "stale-binding-952"},
    )
    assert stale.status_code == 409
    concurrent = client.post(
        "/api/v1/nutrition/targets/dates",
        json={**base, "effective_from": (start + timedelta(weeks=3, days=2)).isoformat()},
        headers={**headers, "Idempotency-Key": "concurrent-binding-preview-952"},
    )
    assert concurrent.status_code == 200
    stale_targets = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json=confirm_payload,
        headers={**headers, "Idempotency-Key": "stale-targets-binding-952"},
    )
    assert stale_targets.status_code == 409
    preview = client.post(
        "/api/v1/nutrition/targets/schedule/binding/preview",
        json={**preview_request, "revision_number": 3},
        headers=headers,
    )
    assert preview.status_code == 200
    confirm_payload["expected_target_version"] = preview.json()["expected_target_version"]
    confirmed = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json=confirm_payload,
        headers={**headers, "Idempotency-Key": "confirm-binding-952"},
    )
    assert confirmed.status_code == 200, confirmed.text
    replay = client.post(
        "/api/v1/nutrition/targets/schedule/binding/confirm",
        json=confirm_payload,
        headers={**headers, "Idempotency-Key": "confirm-binding-952"},
    )
    assert replay.status_code == 200
    assert replay.json() == confirmed.json()
    status_after = client.get(
        "/api/v1/nutrition/targets/schedule/binding",
        params={"target_date": later_changed.isoformat()},
        headers=headers,
    )
    assert status_after.json()["program_changed"] is False
    assert status_after.json()["revision_number"] == 3
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, first_changed).calories == 2700
        assert get_nutrition_target_for_date(db, user_id, later_changed).calories == 2500
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=1)).calories == 2500
        )
        assert (
            db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count()
            == before_bindings + 1
        )
    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200
    assert len(exported.json()["nutrition_schedule_bindings"]) == 2
    assert len(exported.json()["nutrition_target_schedule_rules"]) == 4
    deleted = client.request(
        "DELETE", "/api/v1/me/account", json={"confirmation": "DELETE"}, headers=headers
    )
    assert deleted.status_code == 204
    with get_session_context() as db:
        assert db.get(UserProgram, program_id) is None
        assert db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count() == 0
        assert db.query(NutritionTargetScheduleRule).filter_by(user_id=user_id).count() == 0


@pytest.mark.parametrize("length", [1, 3, 5, 10, 12, 14])
def test_future_rule_repeats_only_for_selected_cycle_week_and_program_term(
    client, length: int
) -> None:
    headers = _auth(client, 952500 + length)
    payload = _payload(client, headers)
    payload["week_cycle"] = {
        "length_weeks": length,
        "repeat": True,
        "week_types": ["light" if index == 0 else "heavy" for index in range(length)],
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    duration = length * 3 + 1
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": duration},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952500 + length).scalar()
        start = db.get(UserProgram, program_id).start_date
    anchor = start + timedelta(weeks=length)
    saved = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={
            **base,
            "calories": 2500,
            "carbs_g": 315,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": anchor.isoformat(),
            "scope": "future",
            "day_type": "training",
            "week_type": "light",
        },
        headers={**headers, "Idempotency-Key": f"future-cycle-{length}"},
    )
    assert saved.status_code == 200, saved.text
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, anchor).calories == 2500
        assert (
            get_nutrition_target_for_date(db, user_id, anchor + timedelta(weeks=length)).calories
            == 2500
        )
        if length > 1:
            assert (
                get_nutrition_target_for_date(db, user_id, anchor + timedelta(weeks=1)).calories
                == 2000
            )
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=duration)).calories
            == 2000
        )


def test_recovery_is_applied_only_to_explicitly_selected_repeating_day(client) -> None:
    headers = _auth(client, 952600)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 8},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]
    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952600).scalar()
        start = db.get(UserProgram, program_id).start_date
    recovery = start + timedelta(days=1)
    saved = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={
            **base,
            "calories": 2200,
            "carbs_g": 242,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": recovery.isoformat(),
            "scope": "recovery",
            "day_type": "recovery",
            "week_type": None,
        },
        headers={**headers, "Idempotency-Key": "explicit-recovery-day"},
    )
    assert saved.status_code == 200, saved.text
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, recovery).calories == 2200
        assert (
            get_nutrition_target_for_date(db, user_id, recovery + timedelta(weeks=1)).calories
            == 2200
        )
        assert (
            get_nutrition_target_for_date(db, user_id, recovery + timedelta(days=1)).calories
            == 2000
        )
        assert (
            get_nutrition_target_for_date(db, user_id, start + timedelta(weeks=1)).calories == 2000
        )

    template = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={
            **base,
            "calories": 2300,
            "carbs_g": 270,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": recovery.isoformat(),
            "scope": "template",
            "day_type": "recovery",
            "week_type": None,
        },
        headers={**headers, "Idempotency-Key": "recovery-template-goal"},
    )
    assert template.status_code == 200, template.text
    future = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={
            **base,
            "calories": 2500,
            "carbs_g": 315,
            "program_id": program_id,
            "revision_number": 1,
            "effective_from": (recovery + timedelta(weeks=1)).isoformat(),
            "scope": "future",
            "day_type": "recovery",
            "week_type": None,
        },
        headers={**headers, "Idempotency-Key": "recovery-future-goal"},
    )
    assert future.status_code == 200, future.text
    with get_session_context() as db:
        assert get_nutrition_target_for_date(db, user_id, recovery).calories == 2300
        assert (
            get_nutrition_target_for_date(db, user_id, recovery + timedelta(weeks=1)).calories
            == 2500
        )
        assert (
            get_nutrition_target_for_date(db, user_id, recovery + timedelta(days=1)).calories
            == 2000
        )


def test_schedule_requires_active_trainer_and_rejects_invalid_scope(client) -> None:
    athlete = _auth(client, 952700)
    coach = _auth(client, 952701, is_coach=True)
    payload = _payload(client, athlete)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=athlete, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=athlete,
        json={"duration_weeks": 8},
    )
    assert assigned.status_code == 200
    program_id = assigned.json()["user_program_id"]
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=952700).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=952701).scalar()
        start = db.get(UserProgram, program_id).start_date
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active"))
    rule = {
        "target_telegram_user_id": 952700,
        "calories": 2200,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 242,
        "program_id": program_id,
        "revision_number": 1,
        "effective_from": (start + timedelta(days=1)).isoformat(),
        "scope": "template",
        "day_type": "training",
        "week_type": None,
    }
    request_headers = {**coach, "Idempotency-Key": "coach-schedule-goal"}
    missing_week = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={**rule, "week_type": "heavy"},
        headers=request_headers,
    )
    assert missing_week.status_code == 409
    past = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={**rule, "effective_from": start.isoformat()},
        headers=request_headers,
    )
    assert past.status_code == 409
    invalid_day = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={**rule, "scope": "future"},
        headers=request_headers,
    )
    assert invalid_day.status_code == 409
    with get_session_context() as db:
        assert db.query(NutritionTargetScheduleRule).filter_by(user_id=athlete_id).count() == 0
        assert db.query(NutritionScheduleBinding).filter_by(user_id=athlete_id).count() == 0
    saved = client.post("/api/v1/nutrition/targets/schedule", json=rule, headers=request_headers)
    assert saved.status_code == 200, saved.text
    with get_session_context() as db:
        db.query(CoachClient).filter_by(
            coach_user_id=coach_id, client_user_id=athlete_id
        ).one().status = "ended"
    assert (
        client.post(
            "/api/v1/nutrition/targets/schedule", json=rule, headers=request_headers
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/nutrition/targets/schedule/program?target_telegram_user_id=952700",
            headers=coach,
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/nutrition/targets/schedule?target_telegram_user_id=952700", headers=coach
        ).status_code
        == 403
    )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_schedule_rules_reject_stale_preview(client) -> None:
    headers = _auth(client, 952703)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 8},
    )
    start = (today_msk() + timedelta(days=1)).isoformat()
    rule = {
        "calories": 2200,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 242,
        "program_id": assigned.json()["user_program_id"],
        "revision_number": 1,
        "effective_from": start,
        "scope": "template",
        "day_type": "training",
        "week_type": None,
    }
    preview = client.post(
        "/api/v1/nutrition/targets/schedule/preview",
        headers=headers,
        json={**rule, "date_from": start, "date_to": start},
    )
    assert preview.status_code == 200, preview.text
    rule.update(
        expected_binding_id=preview.json()["expected_binding_id"],
        expected_target_version=preview.json()["expected_target_version"],
    )
    barrier = Barrier(2)

    def save(index: int):
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/targets/schedule",
            json=rule,
            headers={**headers, "Idempotency-Key": f"schedule-stale-{index}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(save, 1), pool.submit(save, 2)
        first, second = first.result(), second.result()
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952703).scalar()
        assert db.query(NutritionTargetScheduleRule).filter_by(user_id=user_id).count() == 1
        assert db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count() == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_concurrent_schedule_retry_creates_one_rule_and_binding(client) -> None:
    headers = _auth(client, 952702)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 8},
    )
    program_id = assigned.json()["user_program_id"]
    rule = {
        "calories": 2200,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 242,
        "program_id": program_id,
        "revision_number": 1,
        "effective_from": (today_msk() + timedelta(days=1)).isoformat(),
        "scope": "template",
        "day_type": "training",
        "week_type": None,
    }
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=5)
        return client.post(
            "/api/v1/nutrition/targets/schedule",
            json=rule,
            headers={**headers, "Idempotency-Key": "concurrent-schedule-rule"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(save), pool.submit(save)
        first, second = first.result(), second.result()
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    with get_session_context() as db:
        user_id = db.query(User.id).filter_by(telegram_user_id=952702).scalar()
        assert db.query(NutritionTargetScheduleRule).filter_by(user_id=user_id).count() == 1
        assert db.query(NutritionScheduleBinding).filter_by(user_id=user_id).count() == 1


def test_schedule_queries_do_not_grow_with_client_count() -> None:
    start = today_msk()
    with get_session_context() as db:
        user_ids = []
        for index in range(10):
            user = User(telegram_user_id=952800 + index, is_coach=False)
            db.add(user)
            db.flush()
            user_ids.append(user.id)
            program = UserProgram(
                user_id=user.id,
                start_date=start,
                duration_weeks=16,
                schedule_weekdays=[start.weekday()],
                status="active",
                is_active=True,
                current_revision_number=1,
            )
            db.add(program)
            db.flush()
            revision = ProgramRevision(
                user_program_id=program.id,
                revision_number=1,
                actor_role="self",
                change_kind="assigned",
                changed_fields={
                    "week_cycle": {
                        "schema_version": 1,
                        "length_weeks": 1,
                        "repeat": True,
                        "week_types": None,
                    },
                    "logical_cycle": [
                        {
                            "week_number": 1,
                            "day_number": 1,
                            "scheduled_date": start.isoformat(),
                            "exercises": [],
                        }
                    ],
                },
                snapshot={
                    "program": {
                        "id": program.id,
                        "start_date": start.isoformat(),
                        "duration_weeks": 16,
                        "status": "active",
                        "schedule_mode": "calendar",
                    },
                    "workouts": [],
                },
            )
            target = NutritionTarget(
                user_id=user.id,
                source="manual",
                target_scope="schedule",
                effective_from=start,
                effective_to=start,
                calories=2200,
                protein_g=150,
                fat_g=70,
                carbs_g=242,
            )
            db.add_all([revision, target])
            db.flush()
            db.add(
                NutritionScheduleBinding(
                    user_id=user.id,
                    program_revision_id=revision.id,
                    effective_from=start,
                    idempotency_key=f"binding-{index}",
                    request_hash="hash",
                )
            )
            db.add(
                NutritionTargetScheduleRule(
                    user_id=user.id,
                    target_id=target.id,
                    scope="template",
                    day_type="training",
                    effective_from=start,
                    idempotency_key=f"rule-{index}",
                    request_hash="hash",
                )
            )
        db.commit()

        counts = []
        for selected in ({user_ids[0]}, set(user_ids)):
            token = begin_sql_metrics()
            try:
                result = load_scheduled_nutrition_targets(db, selected, start, start)
                counts.append(current_sql_metrics().query_count)
            finally:
                reset_sql_metrics(token)
            assert {user_id for user_id, _day in result} == selected
        assert counts == [3, 3]


def test_rule_list_retains_latest_templates_after_many_repeats(client) -> None:
    headers = _auth(client, 952899)
    saved = client.post(
        "/api/v1/nutrition/targets/manual",
        json={"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180},
        headers=headers,
    )
    assert saved.status_code == 200
    with get_session_context() as db:
        user = db.query(User).filter_by(telegram_user_id=952899).one()
        for index in range(102):
            db.add(
                NutritionTargetScheduleRule(
                    user_id=user.id,
                    target_id=saved.json()["id"],
                    scope="template" if index == 0 else "future",
                    day_type="rest" if index == 0 else "training",
                    effective_from=today_msk() + timedelta(days=1),
                    idempotency_key=f"list-retention-{index}",
                    request_hash="hash",
                )
            )
    response = client.get("/api/v1/nutrition/targets/schedule", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 101
    assert any(
        item["scope"] == "template" and item["day_type"] == "rest" for item in response.json()
    )


def test_scheduled_target_survives_dst_and_timezone_change(client, monkeypatch) -> None:
    headers = _auth(client, 952900)
    with get_session_context() as db:
        db.query(User).filter_by(
            telegram_user_id=952900
        ).one().profile.timezone = "America/New_York"
    instant = [datetime(2026, 3, 8, 4, 30, tzinfo=UTC)]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant[0].astimezone(tz) if tz else instant[0].replace(tzinfo=None)

    monkeypatch.setattr(timezone_module, "datetime", FrozenDateTime)
    payload = _payload(client, headers)
    payload["week_cycle"] = {"length_weeks": 1, "repeat": True}
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assigned = client.post(
        f"/api/v1/programs/templates/{created.json()['template']['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 8},
    )
    assert assigned.status_code == 200, assigned.text
    base = {"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180}
    assert (
        client.post("/api/v1/nutrition/targets/manual", json=base, headers=headers).status_code
        == 200
    )
    saved = client.post(
        "/api/v1/nutrition/targets/schedule",
        json={
            **base,
            "calories": 2200,
            "carbs_g": 242,
            "program_id": assigned.json()["user_program_id"],
            "revision_number": 1,
            "effective_from": "2026-03-08",
            "scope": "recovery",
            "day_type": "recovery",
            "week_type": None,
        },
        headers={**headers, "Idempotency-Key": "dst-recovery-schedule"},
    )
    assert saved.status_code == 200, saved.text
    instant[0] = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    completed = client.put(
        "/api/v1/nutrition/diary/status",
        json={"diary_date": "2026-03-08", "status": "fasted"},
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    assert Decimal(completed.json()["targets"]["energy_kcal"]) == 2200
    with get_session_context() as db:
        db.query(User).filter_by(telegram_user_id=952900).one().profile.timezone = "Asia/Tokyo"
    instant[0] = datetime(2026, 3, 8, 15, 30, tzinfo=UTC)
    changed = client.post(
        "/api/v1/nutrition/targets/manual",
        json={**base, "calories": 2500, "carbs_g": 315},
        headers=headers,
    )
    assert changed.status_code == 200
    report = client.get(
        "/api/v1/workouts/progress/nutrition-report",
        params={"period": "custom", "date_from": "2026-03-08", "date_to": "2026-03-09"},
        headers=headers,
    )
    assert report.status_code == 200
    assert [row["target_calories"] for row in report.json()["daily"]] == [2200, 2500]
