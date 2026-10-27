from __future__ import annotations

from datetime import timedelta

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import ProgramTemplate, UserProgram

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
        ("beginner", 2),
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
    assert body["selection_policy_version"] == "program_generator_v1"
    assert body["source"]["template_id"] > 0
    assert len(body["program"]["days"]) == days_per_week or days_per_week == 2


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

    assert body["status"] in {"preview", "no_compatible"}
    if body["status"] == "preview":
        ids = [
            exercise["exercise_id"]
            for day in body["program"]["days"]
            for exercise in day["exercises"]
        ]
        assert dumbbell["id"] not in ids
        assert all(
            exercise["exercise_id"] > 0
            for day in body["program"]["days"]
            for exercise in day["exercises"]
        )


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
    assert body["template"]["provenance"]["selection_policy_version"] == "program_generator_v1"
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
        days_per_week=2,
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
