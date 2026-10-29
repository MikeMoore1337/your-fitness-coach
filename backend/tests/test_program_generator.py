from __future__ import annotations

from datetime import timedelta

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.exercise import Exercise, ExerciseAlternative
from fitminiapp_api.models.program import (
    HiddenProgramTemplate,
    ProgramTemplate,
    UserProgram,
    UserWorkout,
)
from fitminiapp_api.models.user import User

ALL_EQUIPMENT = [
    "bodyweight",
    "dumbbell",
    "barbell",
    "bench",
    "cable",
    "machine",
    "kettlebell",
    "cardio",
    "other",
]


def _auth(client, telegram_user_id: int, *, is_coach: bool = False):
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _payload(**overrides):
    payload = {
        "goal": "recomposition",
        "experience": "intermediate",
        "days_per_week": 3,
        "preferred_session_duration_minutes": 60,
        "training_location": "gym",
        "available_equipment_ids": ALL_EQUIPMENT,
        "priority_muscle_ids": ["back"],
        "preferred_exercise_ids": [],
        "excluded_exercise_ids": [],
    }
    payload.update(overrides)
    return payload


def _preview(client, headers, **overrides):
    response = client.post(
        "/api/v1/programs/generator/preview",
        headers=headers,
        json=_payload(**overrides),
    )
    assert response.status_code == 200, response.text
    return response


def _exercise_by_slug(client, headers, slug: str) -> dict:
    response = client.get("/api/v1/programs/exercises", headers=headers)
    assert response.status_code == 200, response.text
    return next(item for item in response.json() if item["slug"] == slug)


@pytest.mark.parametrize(
    ("experience", "days_per_week"),
    [
        ("beginner", 3),
        ("intermediate", 4),
        ("intermediate", 5),
        ("advanced", 6),
    ],
)
def test_generator_supports_the_required_frequency_and_experience_matrix(
    client, experience, days_per_week
):
    headers = _auth(client, 53000 + days_per_week)
    response = _preview(
        client,
        headers,
        experience=experience,
        days_per_week=days_per_week,
        goal=(
            "strength"
            if days_per_week == 2
            else "muscle_gain"
            if days_per_week >= 4
            else "recomposition"
        ),
    )

    assert response.json()["status"] == "preview", response.json()
    body = response.json()
    assert body["selection_policy_version"] == "program_generator_v2"
    assert body["source"]["template_id"] > 0
    assert body["program"]["days_per_week"] == days_per_week


@pytest.mark.parametrize("days_per_week", [1, 7])
def test_generator_rejects_unsupported_frequency_without_rounding(client, days_per_week):
    headers = _auth(client, 53100 + days_per_week)
    response = client.post(
        "/api/v1/programs/generator/preview",
        headers=headers,
        json=_payload(days_per_week=days_per_week),
    )

    assert response.status_code == 422


def test_generator_requires_explicit_deterministic_inputs(client):
    headers = _auth(client, 53110)
    response = client.post(
        "/api/v1/programs/generator/preview",
        headers=headers,
        json={"days_per_week": 3},
    )

    assert response.status_code == 422
    assert client.post("/api/v1/programs/generator/preview", json=_payload()).status_code == 401


def test_generator_replay_is_stable_and_explains_fit(client):
    headers = _auth(client, 53120)
    first = _preview(client, headers)
    second = _preview(client, headers)
    first_body = first.json()
    second_body = second.json()
    first_body.pop("draft_token")
    second_body.pop("draft_token")

    assert first_body == second_body
    assert first.json()["fit_reasons"]
    assert first.json()["message"]


def test_preview_does_not_persist_program_or_revision(client):
    headers = _auth(client, 53130)
    with get_session_context() as db:
        before_templates = db.query(ProgramTemplate).count()
        before_programs = db.query(UserProgram).count()
        before_audit_events = db.query(AuditEvent).count()

    response = _preview(client, headers)
    assert response.json()["status"] == "preview"

    with get_session_context() as db:
        assert db.query(ProgramTemplate).count() == before_templates
        assert db.query(UserProgram).count() == before_programs
        assert db.query(AuditEvent).count() == before_audit_events


def test_equipment_adaptation_and_exclusions_use_canonical_ids(client):
    headers = _auth(client, 53140)
    dumbbell = _exercise_by_slug(client, headers, "dumbbell-bench-press")
    response = _preview(
        client,
        headers,
        training_location="home",
        available_equipment_ids=["bodyweight", "dumbbell", "bench"],
        excluded_exercise_ids=[dumbbell["id"]],
    )
    body = response.json()

    assert body["status"] == "no_compatible"
    assert body["suggestions"]
    for suggestion in body["suggestions"]:
        assert suggestion["inputs"]["excluded_exercise_ids"] == [dumbbell["id"]]
        checked = client.post(
            "/api/v1/programs/generator/preview", headers=headers, json=suggestion["inputs"]
        )
        assert checked.status_code == 200, checked.text
        assert checked.json()["status"] == "preview"
        ids = {
            exercise["exercise_id"]
            for day in checked.json()["program"]["days"]
            for exercise in day["exercises"]
        }
        assert dumbbell["id"] not in ids


def test_duration_pressure_is_bounded_or_returns_no_compatible(client):
    headers = _auth(client, 53150)
    response = _preview(
        client,
        headers,
        preferred_session_duration_minutes=20,
        priority_muscle_ids=["back"],
    )
    body = response.json()

    assert body["status"] in {"preview", "no_compatible"}
    if body["status"] == "preview":
        assert body["program"]["estimated_duration_minutes"] <= 34
        assert all(item["code"] == "duration_accessory_reduction" for item in body["adaptations"])
    else:
        assert "duration_incompatible" in body["reason_codes"]


def test_preference_is_soft_and_priority_is_explained(client):
    headers = _auth(client, 53160)
    squat = _exercise_by_slug(client, headers, "squat")
    response = _preview(
        client,
        headers,
        preferred_exercise_ids=[squat["id"]],
        priority_muscle_ids=["quadriceps"],
    )
    body = response.json()

    assert body["status"] == "preview"
    assert any("приоритет" in reason.lower() for reason in body["fit_reasons"] + body["tradeoffs"])


def test_confirm_persists_exactly_once_and_preserves_provenance(client):
    headers = _auth(client, 53170)
    preview = _preview(client, headers)
    token = preview.json()["draft_token"]

    confirmed = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": token},
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["idempotent"] is False
    assert body["template"]["provenance_type"] == "SOURCE_ADAPTATION"
    assert body["template"]["provenance"]["selection_policy_version"] == "program_generator_v2"
    assert body["template"]["provenance"]["adaptation_ledger"] == list(
        body["template"]["program_metadata"]["generator"]["adaptations"]
    )

    repeated = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": token},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["assigned_program_id"] == body["assigned_program_id"]
    with get_session_context() as db:
        assert db.query(UserProgram).count() == 1


def test_confirm_requires_explicit_replacement_for_current_program(client):
    headers = _auth(client, 53180)
    first = _preview(client, headers)
    first_confirm = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": first.json()["draft_token"]},
    )
    assert first_confirm.status_code == 200, first_confirm.text

    second = _preview(client, headers)
    blocked = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": second.json()["draft_token"]},
    )
    assert blocked.status_code == 409
    assert "архив" in blocked.json()["detail"].lower()

    replaced = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": second.json()["draft_token"], "replace_active": True},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["idempotent"] is False


def test_confirm_rejects_tampered_and_foreign_drafts(client):
    owner_headers = _auth(client, 53190)
    foreign_headers = _auth(client, 53191)
    token = _preview(client, owner_headers).json()["draft_token"]

    tampered = token[:10] + ("a" if token[10] != "a" else "b") + token[11:]
    tampered_response = client.post(
        "/api/v1/programs/generator/confirm",
        headers=owner_headers,
        json={"draft_token": tampered},
    )
    assert tampered_response.status_code in {409, 422}

    foreign_response = client.post(
        "/api/v1/programs/generator/confirm",
        headers=foreign_headers,
        json={"draft_token": token},
    )
    assert foreign_response.status_code == 422


def test_confirm_rejects_stale_preview_after_program_state_changes(client):
    headers = _auth(client, 53200)
    preview = _preview(client, headers)
    squat = _exercise_by_slug(client, headers, "squat")
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Existing program",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": squat["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text

    stale = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": preview.json()["draft_token"]},
    )
    assert stale.status_code == 409
    assert "заново" in stale.json()["detail"].lower()


def test_confirm_rejects_stale_preview_after_catalog_changes(client):
    headers = _auth(client, 53205)
    preview = _preview(client, headers)
    with get_session_context() as db:
        exercise = db.query(Exercise).filter(Exercise.slug == "squat").one()
        exercise.title = "Приседание со штангой (обновлённый каталог)"
        db.commit()

    stale = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": preview.json()["draft_token"]},
    )
    assert stale.status_code == 409
    assert "заново" in stale.json()["detail"].lower()


def test_generator_rejects_malformed_payload_and_never_accepts_client_program_json(client):
    headers = _auth(client, 53210)
    payload = _payload()
    payload["preferred_exercise_ids"] = [999999]
    response = client.post("/api/v1/programs/generator/preview", headers=headers, json=payload)
    assert response.status_code == 422

    arbitrary = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": '{"program": {"exercise_id": 999999}}'},
    )
    assert arbitrary.status_code == 422


def test_preview_response_keeps_advanced_set_and_coaching_metadata(client):
    headers = _auth(client, 53220)
    response = _preview(
        client,
        headers,
        goal="strength",
        experience="beginner",
        days_per_week=3,
        preferred_session_duration_minutes=120,
        priority_muscle_ids=[],
    )
    body = response.json()
    assert body["status"] == "preview", body
    exercises = [item for day in body["program"]["days"] for item in day["exercises"]]
    assert exercises
    assert any(item["prescription"] is not None for item in exercises)
    assert any(
        item["prescription"].get("segments")
        for item in exercises
        if item["prescription"] is not None
    )


def test_generator_does_not_replace_trainer_owned_program(client):
    coach_headers = _auth(client, 53240, is_coach=True)
    client_headers = _auth(client, 53241)
    client_user = client.get("/api/v1/me", headers=client_headers).json()
    invite = client.post("/api/v1/coach/invite-links", headers=coach_headers)
    assert invite.status_code == 201, invite.text
    token = invite.json()["start_param"].removeprefix("trainer_")
    assert (
        client.post(
            "/api/v1/me/coach-invites/link/preview",
            headers=client_headers,
            json={"token": token},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/me/coach-invites/link/confirm",
            headers=client_headers,
            json={"token": token},
        ).status_code
        == 204
    )

    exercise = next(
        item
        for item in client.get("/api/v1/programs/exercises", headers=coach_headers).json()
        if item["metric_type"] == "strength"
    )
    created = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json={
            "title": "Тренерская программа для границы generator",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "10",
                            "rest_seconds": 60,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    template_id = created.json()["template"]["id"]
    assigned = client.post(
        f"/api/v1/coach/clients/{client_user['id']}/templates/{template_id}/assign",
        headers=coach_headers,
        json={"start_date": (today_msk() + timedelta(days=1)).isoformat()},
    )
    assert assigned.status_code == 200, assigned.text

    preview = _preview(client, client_headers)
    body = preview.json()
    assert body["active_program"]["trainer_owned"] is True
    blocked = client.post(
        "/api/v1/programs/generator/confirm",
        headers=client_headers,
        json={"draft_token": body["draft_token"], "replace_active": True},
    )
    assert blocked.status_code == 403
    assert "тренером" in blocked.json()["detail"].lower()


def test_generator_accepts_only_canonical_priority_values(client):
    headers = _auth(client, 53230)
    response = client.post(
        "/api/v1/programs/generator/preview",
        headers=headers,
        json=_payload(priority_muscle_ids=["made_up_muscle"]),
    )

    assert response.status_code == 422


def _only_source(user_id: int, slug: str) -> None:
    with get_session_context() as db:
        db.add_all(
            [
                HiddenProgramTemplate(user_id=user_id, template_id=template.id)
                for template in db.query(ProgramTemplate).filter(ProgramTemplate.slug != slug)
            ]
        )


@pytest.mark.parametrize(
    ("slug", "goal", "experience", "frequency", "weeks", "distinct_days"),
    [
        ("stronglifts-5x5", "strength", "beginner", 3, 4, 2),
        ("gzclp", "strength", "beginner", 3, 4, 4),
        ("531-for-beginners", "strength", "beginner", 3, 3, 3),
        ("phul", "muscle_gain", "intermediate", 4, 1, 4),
        ("dumbbell-ppl-gregarioushermit", "muscle_gain", "intermediate", 6, 1, 6),
    ],
)
def test_source_frequency_rotation_and_weekly_mapping_after_confirm(
    client, slug, goal, experience, frequency, weeks, distinct_days
):
    headers = _auth(client, 53300)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _only_source(user_id, slug)
    body = _preview(
        client,
        headers,
        goal=goal,
        experience=experience,
        days_per_week=frequency,
        preferred_session_duration_minutes=90,
    ).json()
    assert body["status"] == "preview", body
    assert body["source"]["slug"] == slug
    assert body["program"]["days_per_week"] == frequency
    assert len(body["program"]["days"]) == distinct_days
    response = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": body["draft_token"], "duration_weeks": weeks},
    )
    assert response.status_code == 200, response.text
    assert response.json()["workouts_created"] == frequency * weeks
    with get_session_context() as db:
        program = db.get(UserProgram, response.json()["assigned_program_id"])
        source = db.query(ProgramTemplate).filter(ProgramTemplate.slug == slug).one()
        days = sorted(source.days, key=lambda row: row.day_number)
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program.id)
            .order_by(UserWorkout.scheduled_date)
            .all()
        )
        assert len(workouts) == frequency * weeks
        for index, workout in enumerate(workouts):
            day = days[index % distinct_days]
            assert workout.day_number == day.day_number
            assert workout.week_number == index // frequency + 1
            expected_offset = (index // frequency) * 7 + (
                (index % frequency) * 7 // frequency
                if distinct_days != frequency
                else index % frequency
            )
            assert (workout.scheduled_date - program.start_date).days == expected_offset
            assert len(workout.exercises) == len(day.exercises)
            for actual, original in zip(
                sorted(workout.exercises, key=lambda row: row.sort_order),
                sorted(day.exercises, key=lambda row: row.sort_order),
                strict=True,
            ):
                weekly = next(
                    (
                        row
                        for row in original.weekly_prescriptions
                        if row.week_number == workout.week_number
                    ),
                    None,
                )
                expected = weekly or original
                assert actual.exercise_id == expected.exercise_id
                assert actual.prescribed_sets == expected.prescribed_sets
                assert actual.prescribed_reps == expected.prescribed_reps
                assert actual.rest_seconds == expected.rest_seconds
                assert actual.prescription == (expected.prescription or original.prescription)
                assert actual.group_kind == original.group_kind
                assert actual.group_order == original.group_order
                assert bool(actual.source_weekly_prescription_id) == bool(weekly)


def test_verified_paths_for_typical_beginner_requests_preserve_hard_constraints(client):
    headers = _auth(client, 53310)
    for inventory in (
        ["bodyweight"],
        ["bodyweight", "dumbbell"],
        ["bodyweight", "dumbbell", "bench"],
    ):
        for days in (2, 3):
            for duration in (45, 60):
                body = _preview(
                    client,
                    headers,
                    experience="beginner",
                    training_location="home",
                    available_equipment_ids=inventory,
                    days_per_week=days,
                    preferred_session_duration_minutes=duration,
                ).json()
                assert body["status"] == "no_compatible", body
                assert body["draft_token"] is None
                assert 1 <= len(body["suggestions"]) <= 3
                assert len(body["reason_codes"]) == 1
                for suggestion in body["suggestions"]:
                    inputs = suggestion["inputs"]
                    assert inputs["experience"] == "beginner"
                    assert inputs["training_location"] == "home"
                    assert inputs["priority_muscle_ids"] == ["back"]
                    assert set(inventory) <= set(inputs["available_equipment_ids"])
                    checked = client.post(
                        "/api/v1/programs/generator/preview", headers=headers, json=inputs
                    )
                    assert checked.status_code == 200, checked.text
                    assert checked.json()["status"] == "preview", checked.json()
                    assert checked.json()["program"]["goal"] == inputs["goal"]
    with get_session_context() as db:
        assert db.query(UserProgram).count() == 0
        assert db.query(UserWorkout).count() == 0
        assert db.query(ProgramTemplate).count() == 16


@pytest.mark.parametrize("duration", [45, 60])
def test_beginner_gym_preview_is_exact_and_usable(client, duration):
    headers = _auth(client, 53320)
    body = _preview(
        client,
        headers,
        experience="beginner",
        available_equipment_ids=["bodyweight", "barbell", "dumbbell", "bench", "cable", "machine"],
        preferred_session_duration_minutes=duration,
    ).json()
    assert body["status"] == "preview", body
    assert body["source"]["slug"] == "strength-fullbody-3d"
    assert body["program"]["goal"] == "recomposition"
    assert body["program"]["days_per_week"] == 3
    assert body["suggestions"] == []


@pytest.mark.parametrize("duration", [45, 60])
@pytest.mark.parametrize(
    "inventory", [["bodyweight", "dumbbell"], ["bodyweight", "dumbbell", "bench"]]
)
def test_beginner_home_preview_is_exact_and_usable(client, duration, inventory):
    headers = _auth(client, 53321)
    body = _preview(
        client,
        headers,
        goal="muscle_gain",
        experience="beginner",
        training_location="home",
        days_per_week=3,
        available_equipment_ids=inventory,
        preferred_session_duration_minutes=duration,
    ).json()
    assert body["status"] == "preview", body
    assert body["source"]["slug"] == "bwf-recommended-routine"
    assert body["program"]["goal"] == "muscle_gain"
    assert body["program"]["days_per_week"] == 3
    assert body["program"]["estimated_duration_minutes"] <= duration + 10


@pytest.mark.parametrize(
    "constraint",
    ["equipment", "exclusion", "duration", "experience", "hidden", "private", "foreign"],
)
def test_incompatible_source_cannot_be_confirmed_or_suggested_unsafely(client, constraint):
    headers = _auth(client, 53330)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _only_source(user_id, "stronglifts-5x5")
    request = _payload(
        goal="strength",
        experience="beginner",
        days_per_week=3,
        preferred_session_duration_minutes=90,
    )
    with get_session_context() as db:
        source = db.query(ProgramTemplate).filter(ProgramTemplate.slug == "stronglifts-5x5").one()
        if constraint in {"equipment", "exclusion"}:
            db.query(ExerciseAlternative).delete()
        if constraint == "equipment":
            request["available_equipment_ids"] = []
        elif constraint == "exclusion":
            request["excluded_exercise_ids"] = [source.days[0].exercises[0].exercise_id]
        elif constraint == "duration":
            request["preferred_session_duration_minutes"] = 10
        elif constraint == "experience":
            source.level = "advanced"
        elif constraint == "hidden":
            db.add(HiddenProgramTemplate(user_id=user_id, template_id=source.id))
        elif constraint == "private":
            source.is_public = False
        elif constraint == "foreign":
            foreign = User(telegram_user_id=53331)
            db.add(foreign)
            db.flush()
            source.owner_user_id = foreign.id
    response = client.post("/api/v1/programs/generator/preview", headers=headers, json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "no_compatible"
    assert body["draft_token"] is None
    assert body["program"] is None
    if constraint in {"exclusion", "experience", "hidden", "private", "foreign"}:
        assert body["suggestions"] == []
    else:
        assert body["suggestions"]
    assert (
        client.post(
            "/api/v1/programs/generator/confirm",
            headers=headers,
            json={"draft_token": body["draft_token"]},
        ).status_code
        == 422
    )


def test_rotation_preserves_generated_set_limit(client, monkeypatch):
    from fitminiapp_api.services import programs

    headers = _auth(client, 53340)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _only_source(user_id, "stronglifts-5x5")
    body = _preview(
        client,
        headers,
        goal="strength",
        experience="beginner",
        preferred_session_duration_minutes=90,
    ).json()
    assert body["status"] == "preview"
    monkeypatch.setattr(programs, "MAX_GENERATED_SETS", 130)
    confirmed = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": body["draft_token"], "duration_weeks": 4},
    )
    assert confirmed.status_code == 422, confirmed.text
    with get_session_context() as db:
        assert db.query(UserProgram).count() == 0
        assert db.query(UserWorkout).count() == 0
        assert db.query(ProgramTemplate).count() == 16


def test_weekly_exercise_requires_equipment_and_keeps_exclusions(client):
    headers = _auth(client, 53350)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _only_source(user_id, "531-for-beginners")
    with get_session_context() as db:
        source = db.query(ProgramTemplate).filter(ProgramTemplate.slug == "531-for-beginners").one()
        weekly_exercise = db.query(Exercise).filter(Exercise.slug == "leg-press").one()
        weekly_id = weekly_exercise.id
        source.days[0].exercises[0].weekly_prescriptions[-1].exercise_id = weekly_id
        db.query(ExerciseAlternative).delete()
    for equipment, excluded in [
        (["bodyweight", "barbell", "bench"], []),
        (ALL_EQUIPMENT, [weekly_id]),
    ]:
        body = _preview(
            client,
            headers,
            goal="strength",
            experience="beginner",
            preferred_session_duration_minutes=90,
            available_equipment_ids=equipment,
            excluded_exercise_ids=excluded,
        ).json()
        assert body["status"] == "no_compatible", body
        assert body["draft_token"] is None
        if excluded:
            assert body["suggestions"] == []


def test_canonical_substitution_cannot_raise_exercise_difficulty(client):
    from fitminiapp_api.services.program_generator import (
        _CandidateIncompatible,
        _choose_exercise,
        _load_catalog,
    )

    _auth(client, 53360)
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 53360).one()
        source = db.query(Exercise).filter(Exercise.slug == "squat").one()
        alternative = db.query(Exercise).filter(Exercise.slug == "pistol-squat").one()
        alternative.difficulty_level = "advanced"
        db.flush()
        _, visible, _, _, _ = _load_catalog(db, user)
        with pytest.raises(_CandidateIncompatible, match="equipment_no_canonical_substitution"):
            _choose_exercise(
                source,
                visible=visible,
                alternatives={source.id: {alternative.id}},
                available_equipment={"bodyweight"},
                excluded_ids=set(),
                experience="beginner",
            )


def test_generator_matrix_script_calls_real_api_without_durable_writes(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "matrix.json"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/program_generator_matrix.py"),
            "--sample",
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["total"] == 6
    assert len(report["catalog"]) == 16
    assert report["summary"] == {"preview": 2, "verified_path": 4}
    assert report["side_effects"] == "NONE: all table row counts unchanged"
    assert all(len(case["candidates"]) == 16 for case in report["cases"])


def test_rotation_revision_cannot_collapse_repeated_days(client):
    from fitminiapp_api.services.program_common import ProgramError
    from fitminiapp_api.services.program_versioning import apply_imported_template_revision

    headers = _auth(client, 53370)
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    _only_source(user_id, "stronglifts-5x5")
    body = _preview(
        client,
        headers,
        goal="strength",
        experience="beginner",
        preferred_session_duration_minutes=90,
    ).json()
    confirmed = client.post(
        "/api/v1/programs/generator/confirm",
        headers=headers,
        json={"draft_token": body["draft_token"], "duration_weeks": 2},
    )
    assert confirmed.status_code == 200, confirmed.text
    with get_session_context() as db:
        user = db.get(User, user_id)
        program = db.get(UserProgram, confirmed.json()["assigned_program_id"])
        before = [(row.id, row.scheduled_date, row.day_number) for row in program.workouts]
        with pytest.raises(ProgramError, match="Изменение структуры чередующегося цикла"):
            apply_imported_template_revision(
                db,
                user,
                program.id,
                program.template,
                expected_revision_number=program.current_revision_number,
                import_id="synthetic-rotation",
                allow_structure_changes=True,
            )
        assert [(row.id, row.scheduled_date, row.day_number) for row in program.workouts] == before
