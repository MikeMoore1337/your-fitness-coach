"""Issue #960: trusted rest capture, ownership, uniqueness, idempotency and null semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4


def _auth(client, user_id):
    login = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": user_id, "is_coach": False}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _new_workout(client, headers):
    catalog = client.get("/api/v1/programs/exercises", headers=headers).json()
    bench = next(item for item in catalog if item["slug"] == "bench-press")
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Проверка отдыха",
            "goal": "recomposition",
            "level": "intermediate",
            "mode": "self",
            "assign_after_create": True,
            "days": [
                {
                    "title": "Силовая",
                    "exercises": [
                        {
                            "exercise_id": bench["id"],
                            "prescribed_sets": 3,
                            "prescribed_reps": "8-10",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    workout = client.get("/api/v1/workouts/today", headers=headers).json()
    started = client.post(f"/api/v1/workouts/{workout['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    return started.json()


def test_rest_start_requires_accepted_working_set_and_workout_owner(client):
    owner = _auth(client, 996001)
    stranger = _auth(client, 996002)
    workout = _new_workout(client, owner)
    workout_id = workout["id"]
    set_id = workout["exercises"][0]["sets"][0]["id"]
    now = datetime.now(UTC).isoformat()
    url = f"/api/v1/workouts/{workout_id}/rest-sessions"
    body = {"source_set_id": set_id, "started_at": now, "mutation_id": str(uuid4())}
    assert client.post(url, headers=owner, json=body).status_code == 409
    assert client.post(url, headers=stranger, json=body).status_code == 404
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{set_id}",
            headers=owner,
            json={"actual_reps": 8, "actual_weight": 50, "is_completed": True},
        ).status_code
        == 200
    )
    created = client.post(url, headers=owner, json=body)
    assert created.status_code == 200, created.text
    session = created.json()
    assert session["planned_seconds"] == 90
    assert session["measured_seconds"] is None
    assert session["status"] == "running"
    assert session["adjusted_seconds"] == 90
    retry = client.post(url, headers=owner, json=body)
    assert retry.status_code == 200
    assert retry.json()["id"] == session["id"]
    assert (
        client.get(f"/api/v1/workouts/{workout_id}/rest-sessions", headers=stranger).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/workouts/{workout_id}/rest-sessions", headers=owner).json()[0]["id"]
        == session["id"]
    )


def test_rest_mutations_preserve_prescription_and_replay_once(client):
    headers = _auth(client, 996003)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={
                "actual_reps": 8,
                "actual_weight": 40,
                "is_completed": True,
            },
        ).status_code
        == 200
    )
    start_time = datetime.now(UTC) - timedelta(seconds=34)
    session = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": start_time.isoformat(),
            "mutation_id": str(uuid4()),
        },
    ).json()
    url = f"/api/v1/workouts/rest-sessions/{session['id']}/actions"
    action_id = str(uuid4())
    action = {"action": "add30", "mutation_id": action_id, "expected_version": 1}
    added = client.post(url, headers=headers, json=action)
    assert added.status_code == 200, added.text
    assert added.json()["adjusted_seconds"] == 120
    assert added.json()["version"] == 2
    assert client.post(url, headers=headers, json=action).json()["version"] == 2
    assert client.post(url, headers=headers, json={**action, "action": "add60"}).status_code == 409
    assert (
        client.post(url, headers=headers, json={**action, "mutation_id": str(uuid4())}).status_code
        == 409
    )
    stopped = client.post(
        url,
        headers=headers,
        json={
            "action": "complete",
            "mutation_id": str(uuid4()),
            "expected_version": 2,
            "ended_at": datetime.now(UTC).isoformat(),
        },
    )
    assert stopped.status_code == 200, stopped.text
    result = stopped.json()
    assert result["status"] == "completed"
    assert result["measured_seconds"] >= 34
    assert result["source"] == "USER_CONFIRMED"
    assert (
        client.post(
            url,
            headers=headers,
            json={
                "action": "skip",
                "mutation_id": str(uuid4()),
                "expected_version": 3,
            },
        ).status_code
        == 409
    )
    latest = client.get("/api/v1/workouts/today", headers=headers).json()
    assert latest["exercises"][0]["rest_seconds"] == 90
    assert latest["exercises"][0]["sets"][1]["is_completed"] is False


def test_skipped_rest_has_null_measurement(client):
    headers = _auth(client, 996004)
    workout = _new_workout(client, headers)
    sid = workout["exercises"][0]["sets"][0]["id"]
    wid = workout["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={
                "actual_reps": 8,
                "is_completed": True,
            },
        ).status_code
        == 200
    )
    row = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": datetime.now(UTC).isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert row.status_code == 200
    done = client.post(
        f"/api/v1/workouts/rest-sessions/{row.json()['id']}/actions",
        headers=headers,
        json={
            "action": "skip",
            "mutation_id": str(uuid4()),
            "expected_version": 1,
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "skipped"
    assert done.json()["measured_seconds"] is None



def test_offline_skip_then_manual_restart_preserves_event_timestamps(client):
    """Queued skip/restart must not invent time while offline or overwrite the first interval."""
    headers = _auth(client, 996031)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    completed = client.patch(
        f"/api/v1/workouts/sets/{sid}",
        headers=headers,
        json={"actual_reps": 8, "is_completed": True},
    )
    assert completed.status_code == 200, completed.text

    now = datetime.now(UTC)
    first_started = now - timedelta(minutes=4)
    skip_at = now - timedelta(minutes=3)
    next_started = now - timedelta(minutes=2)
    first = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": first_started.isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["id"]
    skip_payload = {
        "action": "skip",
        "mutation_id": str(uuid4()),
        "expected_version": 1,
        "occurred_at": skip_at.isoformat(),
    }
    skipped = client.post(
        f"/api/v1/workouts/rest-sessions/{first_id}/actions",
        headers=headers,
        json=skip_payload,
    )
    assert skipped.status_code == 200, skipped.text
    assert datetime.fromisoformat(skipped.json()["ended_at"]).replace(
        tzinfo=None
    ) == skip_at.replace(tzinfo=None)
    assert skipped.json()["measured_seconds"] is None
    assert client.post(
        f"/api/v1/workouts/rest-sessions/{first_id}/actions",
        headers=headers,
        json=skip_payload,
    ).json()["version"] == skipped.json()["version"]

    repeat = client.post(
        f"/api/v1/workouts/rest-sessions/{first_id}/restart",
        headers=headers,
        json={"started_at": next_started.isoformat(), "mutation_id": str(uuid4())},
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["id"] != first_id
    assert repeat.json()["status"] == "running"
    assert datetime.fromisoformat(repeat.json()["started_at"]).replace(
        tzinfo=None
    ) == next_started.replace(tzinfo=None)
    history = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 2
    assert history.json()[0]["status"] == "skipped"
    assert history.json()[0]["measured_seconds"] is None


def test_rest_history_and_progress_exclude_unknown_intervals(client):
    headers = _auth(client, 996005)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 50, "is_completed": True},
        ).status_code
        == 200
    )
    now = datetime.now(UTC)
    started = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": (now - timedelta(seconds=65)).isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert started.status_code == 200, started.text
    session_id = started.json()["id"]
    completed = client.post(
        f"/api/v1/workouts/rest-sessions/{session_id}/actions",
        headers=headers,
        json={
            "action": "complete",
            "mutation_id": str(uuid4()),
            "expected_version": 1,
            "ended_at": now.isoformat(),
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["measured_seconds"] >= 65

    finished = client.post(
        f"/api/v1/workouts/{wid}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    history = client.get("/api/v1/workouts/history", headers=headers)
    assert history.status_code == 200, history.text
    records = next(row for row in history.json() if row["id"] == wid)
    assert len(records["rest_sessions"]) == 1
    assert records["rest_sessions"][0]["measured_seconds"] >= 65
    assert records["rest_sessions"][0]["planned_seconds"] == 90

    report = client.get(
        "/api/v1/workouts/progress/report",
        params={"period": "days_7"},
        headers=headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["training"]["rest"]["observation_count"] >= 1


def test_delayed_offline_rest_can_sync_after_workout_finish(client):
    """Finishing a workout must not silently discard an earlier accepted offline rest."""
    headers = _auth(client, 996006)
    workout = _new_workout(client, headers)
    workout_id = workout["id"]
    set_id = workout["exercises"][0]["sets"][0]["id"]
    started_at = datetime.now(UTC).isoformat()
    marked = client.patch(
        f"/api/v1/workouts/sets/{set_id}",
        headers=headers,
        json={"actual_reps": 8, "actual_weight": 45, "is_completed": True},
    )
    assert marked.status_code == 200, marked.text
    finished = client.post(
        f"/api/v1/workouts/{workout_id}/finish",
        headers=headers,
        json={"confirm_incomplete": True},
    )
    assert finished.status_code == 200, finished.text
    queued = client.post(
        f"/api/v1/workouts/{workout_id}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": set_id,
            "started_at": started_at,
            "mutation_id": str(uuid4()),
        },
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "running"


def test_owner_corrects_forgotten_rest_duration(client):
    """A confirmed manual value must not use wall clock elapsed in statistics."""
    owner = _auth(client, 996007)
    stranger = _auth(client, 996008)
    workout = _new_workout(client, owner)
    sid = workout["exercises"][0]["sets"][0]["id"]
    wid = workout["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=owner,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    started_at = datetime.now(UTC) - timedelta(minutes=20)
    response = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=owner,
        json={
            "source_set_id": sid,
            "started_at": started_at.isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    url = f"/api/v1/workouts/rest-sessions/{response.json()['id']}/actions"
    corrected = {
        "action": "complete",
        "mutation_id": str(uuid4()),
        "expected_version": 1,
        "ended_at": datetime.now(UTC).isoformat(),
        "corrected": True,
        "corrected_seconds": 150,
    }
    assert client.post(url, headers=stranger, json=corrected).status_code == 404
    assert (
        client.post(
            url,
            headers=owner,
            json={**corrected, "corrected_seconds": None},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            headers=owner,
            json={**corrected, "corrected": False},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            headers=owner,
            json={
                **corrected,
                "ended_at": (started_at - timedelta(seconds=1)).isoformat(),
            },
        ).status_code
        == 422
    )
    saved = client.post(url, headers=owner, json=corrected)
    assert saved.status_code == 200, saved.text
    assert saved.json()["measured_seconds"] == 150
    assert saved.json()["source"] == "USER_CORRECTED"
    retried = client.post(url, headers=owner, json=corrected)
    assert retried.status_code == 200
    assert retried.json()["version"] == saved.json()["version"]
    assert (
        client.post(
            url,
            headers=owner,
            json={**corrected, "mutation_id": str(uuid4())},
        ).status_code
        == 409
    )
