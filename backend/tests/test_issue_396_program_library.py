from __future__ import annotations

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.seed import seed_demo_data

SOURCE_SLUGS = {
    "stronglifts-5x5",
    "gzclp",
    "531-for-beginners",
    "phul",
    "nsuns-4d",
    "metallicdpa-linear-progression-ppl",
    "bwf-recommended-routine",
    "dumbbell-ppl-gregarioushermit",
}


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_issue_396_seeded_library_exposes_16_templates_and_periodization(client) -> None:
    headers = _auth(client, 396001)
    response = client.get("/api/v1/programs/templates/mine", headers=headers)
    assert response.status_code == 200, response.text

    templates = {item["slug"]: item for item in response.json()}
    assert len(templates) == 16
    assert templates.keys() >= SOURCE_SLUGS
    assert sum(item["provenance_type"] == "YFC_GENERIC" for item in templates.values()) == 8
    assert all(templates[slug]["provenance_type"] == "SOURCE_ADAPTATION" for slug in SOURCE_SLUGS)

    assert templates["phul"]["default_duration_weeks"] == 12
    assert all(
        len(exercise["weekly_prescriptions"]) == 12
        for day in templates["phul"]["days"]
        for exercise in day["exercises"]
    )
    assert all(
        len(exercise["weekly_prescriptions"]) == 4
        for day in templates["531-for-beginners"]["days"]
        for exercise in day["exercises"]
    )
    assert templates["phul"]["provenance"]["creator"] == "Brandon Campbell"
    assert templates["dumbbell-ppl-gregarioushermit"]["provenance"]["creator"] == (
        "u/gregariousHermit"
    )
    assert templates["nsuns-4d"]["program_metadata"]["frequency_model"]

    training_max_plans = [
        exercise["prescription"]
        for slug in ("531-for-beginners", "nsuns-4d")
        for day in templates[slug]["days"]
        for exercise in day["exercises"]
        if exercise["prescription"]
    ]
    assert any(
        any(
            segment["load_target"]["kind"] == "percent_training_max" for segment in plan["segments"]
        )
        for plan in training_max_plans
    )

    stronglifts = templates["stronglifts-5x5"]
    assert [day["title"] for day in stronglifts["days"]] == ["Workout A", "Workout B"]
    assert stronglifts["days"][0]["exercises"][0]["prescribed_sets"] == 5
    assert stronglifts["days"][1]["exercises"][-1]["prescribed_sets"] == 1

    gzclp = templates["gzclp"]
    gzclp_notes = {
        exercise["notes"]
        for day in gzclp["days"]
        for exercise in day["exercises"]
        if exercise["notes"]
    }
    assert any("T1" in note for note in gzclp_notes)
    assert any("T2" in note for note in gzclp_notes)
    assert any("T3" in note for note in gzclp_notes)
    assert any(
        segment["rep_target"]["kind"] == "amrap"
        for day in gzclp["days"]
        for exercise in day["exercises"]
        for segment in exercise["prescription"]["segments"]
    )

    assert [day["title"] for day in templates["phul"]["days"]] == [
        "Upper Power",
        "Lower Power",
        "Upper Hypertrophy",
        "Lower Hypertrophy",
    ]
    assert all(len(day["exercises"]) == 2 for day in templates["nsuns-4d"]["days"])
    assert len(templates["metallicdpa-linear-progression-ppl"]["days"]) == 6
    assert all(
        exercise["group_kind"] in {"superset", "circuit"}
        for day in templates["bwf-recommended-routine"]["days"]
        for exercise in day["exercises"]
    )
    assert [day["title"] for day in templates["dumbbell-ppl-gregarioushermit"]["days"]] == [
        "Push A",
        "Pull A",
        "Legs A",
        "Push B",
        "Pull B",
        "Legs B",
    ]


def test_issue_396_assignments_materialize_history_and_export_structured_plans(client) -> None:
    headers = _auth(client, 396002)
    templates_response = client.get("/api/v1/programs/templates/mine", headers=headers)
    assert templates_response.status_code == 200, templates_response.text
    templates = {item["slug"]: item for item in templates_response.json()}

    assignment_ids: list[int] = []
    for offset, slug in enumerate(sorted(SOURCE_SLUGS), start=10):
        user_headers = _auth(client, 396000 + offset)
        item = templates[slug]
        assigned = client.post(
            f"/api/v1/programs/templates/{item['id']}/assign-to-me",
            headers=user_headers,
            json={"start_date": today_msk().isoformat(), "duration_weeks": 1},
        )
        assert assigned.status_code == 200, assigned.text
        assignment = assigned.json()
        assignment_ids.append(assignment["user_program_id"])
        assert assignment["workouts_created"] == len(item["days"])

        history = client.get(
            f"/api/v1/programs/assigned/{assignment['user_program_id']}/revisions",
            headers=user_headers,
        )
        assert history.status_code == 200, history.text
        assert history.json()[0]["change_kind"] == "assigned"

        exported = client.get("/api/v1/me/export", headers=user_headers)
        assert exported.status_code == 200, exported.text
        exported_program = next(
            row for row in exported.json()["programs"] if row["id"] == assignment["user_program_id"]
        )
        assert exported_program["revisions"]
        assert exported_program["workouts"]
        assert exported_program["workouts"][0]["exercises"][0]["prescription"]

    with get_session_context() as db:
        programs = db.query(UserProgram).filter(UserProgram.id.in_(assignment_ids)).all()
        assert len(programs) == len(SOURCE_SLUGS)
        workouts = (
            db.query(UserWorkout).filter(UserWorkout.user_program_id.in_(assignment_ids)).all()
        )
        workout_ids = [workout.id for workout in workouts]
        workout_exercises = (
            db.query(UserWorkoutExercise)
            .filter(UserWorkoutExercise.workout_id.in_(workout_ids))
            .all()
        )
        assert workout_exercises
        assert all(item.prescription for item in workout_exercises)


def test_issue_396_trainer_assignment_keeps_source_lineage(client) -> None:
    with get_session_context() as db:
        coach = db.query(User).filter(User.telegram_user_id == 1001).one()
        client_user = db.query(User).filter(User.telegram_user_id == 2001).one()
        db.add(CoachClient(coach_user_id=coach.id, client_user_id=client_user.id, status="active"))
        db.commit()

    coach_headers = _auth(client, 1001, is_coach=True)
    templates = client.get("/api/v1/programs/templates/mine", headers=coach_headers)
    assert templates.status_code == 200, templates.text
    stronglifts = next(item for item in templates.json() if item["slug"] == "stronglifts-5x5")

    with get_session_context() as db:
        client_id = db.query(User).filter(User.telegram_user_id == 2001).one().id

    assigned = client.post(
        f"/api/v1/coach/clients/{client_id}/templates/{stronglifts['id']}/assign",
        headers=coach_headers,
        json={"start_date": today_msk().isoformat(), "duration_weeks": 1},
    )
    assert assigned.status_code == 200, assigned.text

    with get_session_context() as db:
        program = (
            db.query(UserProgram).filter(UserProgram.id == assigned.json()["user_program_id"]).one()
        )
        assert (
            program.assigned_by_user_id
            == db.query(User).filter(User.telegram_user_id == 1001).one().id
        )
        assert program.template is not None
        assert program.template.provenance_type == "SOURCE_ADAPTATION"
        assert program.template.provenance["source_program_name"] == "StrongLifts 5x5"


def test_issue_396_seed_refresh_preserves_assignment_and_revision_history(client) -> None:
    headers = _auth(client, 396003)
    template = next(
        item
        for item in client.get("/api/v1/programs/templates/mine", headers=headers).json()
        if item["slug"] == "phul"
    )
    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"start_date": today_msk().isoformat(), "duration_weeks": 1},
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["user_program_id"]

    with get_session_context() as db:
        before = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        before_counts = (len(before.workouts), len(before.revisions))
        seed_demo_data(db, include_demo_users=False)
        after = db.query(UserProgram).filter(UserProgram.id == program_id).one()
        assert (len(after.workouts), len(after.revisions)) == before_counts
        assert after.current_revision_number == 1
        assert after.template is not None
        assert after.template.provenance_type == "SOURCE_ADAPTATION"
