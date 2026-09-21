from __future__ import annotations

import csv
import io
import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserWorkout, UserWorkoutExercise
from fitminiapp_api.schemas.program import ExercisePrescriptionPlan
from fitminiapp_api.services.program_imports import PROGRAM_IMPORT_COLUMNS


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _strength_exercises(client, headers: dict[str, str]) -> list[dict]:
    response = client.get("/api/v1/programs/exercises", headers=headers)
    assert response.status_code == 200, response.text
    return [item for item in response.json() if item["metric_type"] == "strength"]


def _segment(
    position: int,
    role: str,
    *,
    reps: tuple[int, int] | int = (8, 10),
    load: dict | None = None,
    group_id: int | None = None,
    group_position: int | None = None,
    round_number: int | None = None,
) -> dict:
    rep_target = (
        {"kind": "exact", "value": reps}
        if isinstance(reps, int)
        else {"kind": "range", "min_reps": reps[0], "max_reps": reps[1]}
    )
    return {
        "position": position,
        "role": role,
        "rep_target": rep_target,
        "load_target": load or {"kind": "user_selected"},
        "rest_after_seconds": 90,
        "group_id": group_id,
        "group_position": group_position,
        "round_number": round_number,
    }


def _top_backoff_plan() -> dict:
    return {
        "version": 1,
        "metric_type": "strength",
        "segments": [
            {
                **_segment(1, "top", reps=(5, 8)),
                "effort_target": {"kind": "rir", "value": 1},
            },
            {
                **_segment(
                    2,
                    "backoff",
                    reps=(8, 10),
                    load={"kind": "relative_to_top", "value": 0.8},
                ),
            },
            {
                **_segment(
                    3,
                    "backoff",
                    reps=(8, 10),
                    load={"kind": "relative_to_previous", "value": 1.0},
                ),
            },
        ],
        "groups": [],
    }


def _method_plans() -> list[tuple[str, dict]]:
    return [
        ("top_backoff", _top_backoff_plan()),
        (
            "ascending_pyramid",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", reps=12, load={"kind": "absolute", "value": 50}),
                    _segment(2, "working", reps=10, load={"kind": "absolute", "value": 60}),
                    _segment(3, "working", reps=8, load={"kind": "absolute", "value": 70}),
                ],
                "groups": [],
            },
        ),
        (
            "reverse_pyramid",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", reps=8, load={"kind": "absolute", "value": 70}),
                    _segment(2, "working", reps=10, load={"kind": "absolute", "value": 60}),
                    _segment(3, "working", reps=12, load={"kind": "absolute", "value": 50}),
                ],
                "groups": [],
            },
        ),
        (
            "drop_chain",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", group_id=1, group_position=1),
                    _segment(2, "drop", reps=8, group_id=1, group_position=2),
                    _segment(3, "drop", reps=6, group_id=1, group_position=3),
                ],
                "groups": [
                    {
                        "group_id": 1,
                        "kind": "drop_chain",
                        "rest_after_group_seconds": 120,
                    }
                ],
            },
        ),
        (
            "rest_pause",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", group_id=2, group_position=1),
                    _segment(2, "mini_set", reps=3, group_id=2, group_position=2),
                    _segment(3, "mini_set", reps=3, group_id=2, group_position=3),
                ],
                "groups": [{"group_id": 2, "kind": "rest_pause", "intra_group_rest_seconds": 20}],
            },
        ),
        (
            "myo_reps",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "activation", reps=15, group_id=3, group_position=1),
                    _segment(2, "mini_set", reps=5, group_id=3, group_position=2),
                    _segment(3, "mini_set", reps=5, group_id=3, group_position=3),
                ],
                "groups": [{"group_id": 3, "kind": "myo_reps", "intra_group_rest_seconds": 15}],
            },
        ),
        (
            "cluster",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", group_id=4, group_position=1),
                    _segment(2, "cluster_member", reps=2, group_id=4, group_position=2),
                    _segment(3, "cluster_member", reps=2, group_id=4, group_position=3),
                ],
                "groups": [{"group_id": 4, "kind": "cluster", "intra_group_rest_seconds": 20}],
            },
        ),
        (
            "circuit_density",
            {
                "version": 1,
                "metric_type": "strength",
                "segments": [
                    _segment(1, "working", group_id=5, group_position=1, round_number=1),
                    _segment(2, "working", group_id=5, group_position=2, round_number=1),
                    _segment(3, "working", group_id=5, group_position=1, round_number=2),
                    _segment(4, "working", group_id=5, group_position=2, round_number=2),
                ],
                "groups": [{"group_id": 5, "kind": "circuit", "rounds": 2}],
            },
        ),
    ]


@pytest.mark.parametrize(
    "name, plan", _method_plans(), ids=[name for name, _plan in _method_plans()]
)
def test_accepted_ordered_prescription_shapes_round_trip(name: str, plan: dict) -> None:
    parsed = ExercisePrescriptionPlan.model_validate(plan)
    dumped = parsed.model_dump(mode="json")

    assert name
    assert [segment["position"] for segment in dumped["segments"]] == list(
        range(1, len(dumped["segments"]) + 1)
    )
    assert json.loads(json.dumps(dumped, ensure_ascii=False)) == dumped


def test_unsupported_execution_fields_are_rejected_instead_of_flattened() -> None:
    plan = _top_backoff_plan()
    plan["segments"][0]["tempo"] = "3-1-1"

    with pytest.raises(ValidationError):
        ExercisePrescriptionPlan.model_validate(plan)


def test_structured_assignment_keeps_ordered_roles_legacy_fields_and_export(client) -> None:
    headers = _auth(client, 397001)
    exercises = _strength_exercises(client, headers)
    top_plan = _top_backoff_plan()
    drop_plan = next(plan for name, plan in _method_plans() if name == "drop_chain")
    payload = {
        "title": "Структурированная проверка 397",
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "self",
        "assign_after_create": True,
        "start_date": today_msk().isoformat(),
        "days": [
            {
                "title": "Сила",
                "exercises": [
                    {
                        "exercise_id": exercises[0]["id"],
                        "prescribed_sets": 3,
                        "prescribed_reps": "5-8",
                        "rest_seconds": 180,
                        "prescription": top_plan,
                    },
                    {
                        "exercise_id": exercises[1]["id"],
                        "prescribed_sets": 3,
                        "prescribed_reps": "8-10",
                        "rest_seconds": 90,
                        "group_id": 10,
                        "group_kind": "drop_chain",
                        "group_order": 1,
                        "prescription": drop_plan,
                    },
                ],
            }
        ],
    }
    created = client.post("/api/v1/programs/templates", headers=headers, json=payload)
    assert created.status_code == 200, created.text
    template = created.json()["template"]
    template_exercises = template["days"][0]["exercises"]
    assert [item["prescription"]["segments"][0]["role"] for item in template_exercises] == [
        "top",
        "working",
    ]
    assert template_exercises[1]["group_kind"] == "drop_chain"

    workout = client.get("/api/v1/workouts/today", headers=headers)
    assert workout.status_code == 200, workout.text
    structured = workout.json()["exercises"]
    assert structured[0]["source_template_exercise_id"] == template_exercises[0]["id"]
    assert structured[0]["source_weekly_prescription_id"] is None
    assert [item["planned_role"] for item in structured[0]["sets"]] == [
        "top",
        "backoff",
        "backoff",
    ]
    assert all(item["set_kind"] == "working" for item in structured[0]["sets"])
    assert [item["planned_role"] for item in structured[1]["sets"]] == [
        "working",
        "drop",
        "drop",
    ]
    assert all(item["planned_group_kind"] == "drop_chain" for item in structured[1]["sets"])

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    export_exercises = exported.json()["programs"][0]["workouts"][0]["exercises"]
    assert export_exercises[0]["prescription"]["segments"][1]["role"] == "backoff"
    assert export_exercises[1]["sets"][1]["planned_role"] == "drop"


def test_scope_a_replacement_is_blocked_after_workout_start(client) -> None:
    headers = _auth(client, 397002)
    exercises = _strength_exercises(client, headers)
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Scope A gate",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "start_date": today_msk().isoformat(),
            "days": [
                {
                    "title": "A",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 1,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    target = workout["exercises"][0]
    alternatives = client.get(
        f"/api/v1/workouts/{workout['id']}/exercises/{target['id']}/alternatives",
        headers=headers,
        params={"available_equipment_ids": ["dumbbell", "bench"]},
    )
    assert alternatives.status_code == 200, alternatives.text
    replacement = next(
        item for item in alternatives.json() if item["exercise_id"] != target["exercise_id"]
    )

    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    preview = client.post(
        f"/api/v1/workouts/{workout['id']}/adaptations/preview",
        headers=headers,
        json={
            "reason": "replace_exercise",
            "target_workout_exercise_id": target["id"],
            "replacement_exercise_id": replacement["exercise_id"],
            "available_equipment_ids": ["dumbbell", "bench"],
        },
    )
    assert preview.status_code == 409
    with get_session_context() as db:
        stored = db.get(UserWorkoutExercise, target["id"])
        assert stored is not None
        assert stored.exercise_id == target["exercise_id"]


def test_scope_b_replaces_only_future_rows_and_records_lineage(client) -> None:
    headers = _auth(client, 397003)
    exercises = _strength_exercises(client, headers)
    start_date = today_msk() + timedelta(days=1)
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Scope B lineage",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "start_date": start_date.isoformat(),
            "duration_weeks": 3,
            "schedule_weekdays": [start_date.weekday()],
            "days": [
                {
                    "title": "B",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
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
    program_id = created.json()["assigned_program_id"]
    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc())
            .all()
        )
        source_id = workouts[0].exercises[0].source_template_exercise_id
        original_id = workouts[0].exercises[0].exercise_id
        workouts[0].status = "completed"
        workouts[0].completed_at = now_msk_naive()
        db.commit()

    replaced = client.post(
        f"/api/v1/programs/assigned/{program_id}/exercises",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "exercise_id": exercises[1]["id"],
            "target_template_exercise_id": source_id,
            "prescription": _top_backoff_plan(),
            "reason": "Перенести замену только на будущие тренировки",
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["workouts_updated"] == 2

    with get_session_context() as db:
        refreshed = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.scheduled_date.asc())
            .all()
        )
        assert refreshed[0].exercises[0].exercise_id == original_id
        assert all(
            workout.exercises[0].exercise_id == exercises[1]["id"]
            and workout.exercises[0].source_template_exercise_id == source_id
            for workout in refreshed[1:]
        )
        assert all(
            item.actual_weight is None
            for workout in refreshed[1:]
            for item in workout.exercises[0].sets
        )

    history = client.get(f"/api/v1/programs/assigned/{program_id}/revisions", headers=headers)
    assert history.status_code == 200, history.text
    latest = history.json()[0]
    assert latest["change_kind"] == "exercise_replaced"
    lineage = latest["changed_fields"]["lineage"]
    assert len(lineage) == 2
    assert {item["scope"] for item in lineage} == {"assigned_program"}
    assert {item["compatibility"] for item in lineage} == {"compatible_with_load_reset"}


def test_scope_c_is_owner_scoped_and_does_not_rewrite_existing_assignment(client) -> None:
    headers = _auth(client, 397004)
    other_headers = _auth(client, 397005)
    exercises = _strength_exercises(client, headers)
    created = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Scope C custom template",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": False,
            "days": [
                {
                    "title": "C",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
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
    template = created.json()["template"]
    template_exercise_id = template["days"][0]["exercises"][0]["id"]
    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"start_date": (today_msk() + timedelta(days=1)).isoformat()},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]

    denied = client.post(
        f"/api/v1/programs/templates/{template['id']}/exercises/{template_exercise_id}/replace",
        headers=other_headers,
        json={"replacement_exercise_id": exercises[1]["id"]},
    )
    assert denied.status_code == 403

    replaced = client.post(
        f"/api/v1/programs/templates/{template['id']}/exercises/{template_exercise_id}/replace",
        headers=headers,
        json={"replacement_exercise_id": exercises[1]["id"], "reason": "Точная замена"},
    )
    assert replaced.status_code == 200, replaced.text
    updated_template_exercise = replaced.json()["days"][0]["exercises"][0]
    assert updated_template_exercise["exercise_id"] == exercises[1]["id"]
    assert updated_template_exercise["prescription"] is None

    with get_session_context() as db:
        existing = db.query(UserWorkout).filter(UserWorkout.user_program_id == program_id).one()
        assert existing.exercises[0].exercise_id == exercises[0]["id"]


def test_structured_import_preserves_ordered_prescription(client) -> None:
    headers = _auth(client, 397006)
    plan_json = json.dumps(_top_backoff_plan(), ensure_ascii=False, separators=(",", ":"))
    row = {
        "program_title": "Импортированный top backoff",
        "goal": "recomposition",
        "level": "intermediate",
        "day_number": "1",
        "day_title": "Сила",
        "exercise_name": "Приседания без веса",
        "prescribed_sets": "3",
        "prescribed_reps": "5-8",
        "rest_seconds": "180",
        "exercise_id": "",
        "exercise_slug": "bodyweight-squat",
        "metric_type": "strength",
        "prescribed_duration_minutes": "",
        "notes": "",
        "superset_group": "",
        "superset_order": "",
        "prescription": plan_json,
    }
    output = io.StringIO(newline="")
    output.write("#yfc_template_version,1\n")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(PROGRAM_IMPORT_COLUMNS)
    writer.writerow([row[column] for column in PROGRAM_IMPORT_COLUMNS])
    preview = client.post(
        "/api/v1/programs/imports",
        headers=headers,
        files={"file": ("structured.csv", output.getvalue().encode("utf-8-sig"), "text/csv")},
    )
    assert preview.status_code == 201, preview.text
    preview_body = preview.json()
    assert preview_body["summary"]["blocking_issue_count"] == 0, preview_body
    assert [item["role"] for item in preview_body["rows"][0]["prescription"]["segments"]] == [
        "top",
        "backoff",
        "backoff",
    ]

    confirmed = client.post(
        f"/api/v1/programs/imports/{preview_body['id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    imported = confirmed.json()["template"]["days"][0]["exercises"][0]
    assert [item["role"] for item in imported["prescription"]["segments"]] == [
        "top",
        "backoff",
        "backoff",
    ]
