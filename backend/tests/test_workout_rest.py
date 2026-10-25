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


def test_rest_restart_creates_new_interval_preserving_history_and_replay(client):
    headers = _auth(client, 996021)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    now = datetime.now(UTC)
    initial_start = now - timedelta(seconds=35)
    initial_mutation = str(uuid4())
    first = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": initial_start.isoformat(),
            "mutation_id": initial_mutation,
        },
    )
    assert first.status_code == 200, first.text
    parent = first.json()
    assert parent["start_mutation_id"] == initial_mutation
    assert (
        client.post(
            f"/api/v1/workouts/{wid}/rest-sessions",
            headers=headers,
            json={
                "source_set_id": sid,
                "started_at": (now - timedelta(seconds=30)).isoformat(),
                "mutation_id": initial_mutation,
            },
        ).status_code
        == 409
    )
    finished = client.post(
        f"/api/v1/workouts/rest-sessions/{parent['id']}/actions",
        headers=headers,
        json={
            "action": "complete",
            "mutation_id": str(uuid4()),
            "expected_version": 1,
            "ended_at": (now - timedelta(seconds=25)).isoformat(),
        },
    )
    assert finished.status_code == 200, finished.text
    measured_before = finished.json()["measured_seconds"]
    restarted_at = now - timedelta(seconds=24)
    mutation = str(uuid4())
    url = f"/api/v1/workouts/rest-sessions/{parent['id']}/restart"
    request = {"started_at": restarted_at.isoformat(), "mutation_id": mutation}
    created = client.post(url, headers=headers, json=request)
    assert created.status_code == 200, created.text
    child = created.json()
    assert child["id"] != parent["id"]
    assert child["workout_id"] == wid
    assert child["source_set_id"] == sid
    assert child["status"] == "running"
    assert child["start_mutation_id"] == mutation
    assert client.post(url, headers=headers, json=request).json()["id"] == child["id"]
    assert (
        client.post(
            url,
            headers=headers,
            json={**request, "started_at": (now - timedelta(seconds=23)).isoformat()},
        ).status_code
        == 409
    )
    assert (
        client.post(
            url,
            headers=headers,
            json={**request, "mutation_id": str(uuid4())},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/workouts/rest-sessions/{child['id']}/restart",
            headers=headers,
            json={"started_at": now.isoformat(), "mutation_id": str(uuid4())},
        ).status_code
        == 409
    )
    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=headers).json()
    assert len(rows) == 2
    assert rows[0]["id"] == parent["id"]
    assert rows[0]["measured_seconds"] == measured_before
    assert rows[0]["status"] == "completed"


def test_rest_restart_rejects_foreign_predecessor_and_active_another_rest(client):
    owner = _auth(client, 996022)
    stranger = _auth(client, 996023)
    workout = _new_workout(client, owner)
    wid = workout["id"]
    first_set, second_set = (s["id"] for s in workout["exercises"][0]["sets"][:2])
    for sid in (first_set, second_set):
        assert (
            client.patch(
                f"/api/v1/workouts/sets/{sid}",
                headers=owner,
                json={"actual_reps": 8, "is_completed": True},
            ).status_code
            == 200
        )
    started_at = (datetime.now(UTC) - timedelta(seconds=12)).isoformat()
    initial = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=owner,
        json={
            "source_set_id": first_set,
            "started_at": started_at,
            "mutation_id": str(uuid4()),
        },
    )
    assert initial.status_code == 200, initial.text
    parent_id = initial.json()["id"]
    request = {"started_at": datetime.now(UTC).isoformat(), "mutation_id": str(uuid4())}
    url = f"/api/v1/workouts/rest-sessions/{parent_id}/restart"
    assert client.post(url, headers=stranger, json=request).status_code == 404
    assert client.post(url, headers=owner, json=request).status_code == 409
    assert (
        client.post(
            f"/api/v1/workouts/{wid}/rest-sessions",
            headers=owner,
            json={**request, "source_set_id": second_set},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/workouts/rest-sessions/{parent_id}/actions",
            headers=owner,
            json={"action": "skip", "expected_version": 1, "mutation_id": str(uuid4())},
        ).status_code
        == 200
    )
    # Restart begins after the skip action has persisted its terminal timestamp.
    request["started_at"] = datetime.now(UTC).isoformat()
    assert client.post(url, headers=owner, json=request).status_code == 200


def test_pg16_concurrent_starts_of_different_sets_are_serialized(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import pytest

    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent invariants require PostgreSQL, not SQLite")
    owner = _auth(client, 996024)
    workout = _new_workout(client, owner)
    wid = workout["id"]
    sets = [s["id"] for s in workout["exercises"][0]["sets"][:2]]
    for sid in sets:
        assert (
            client.patch(
                f"/api/v1/workouts/sets/{sid}",
                headers=owner,
                json={"actual_reps": 8, "is_completed": True},
            ).status_code
            == 200
        )
    barrier = Barrier(2)

    def submit(sid):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/workouts/{wid}/rest-sessions",
            headers=owner,
            json={
                "source_set_id": sid,
                "started_at": datetime.now(UTC).isoformat(),
                "mutation_id": str(uuid4()),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, sets))
    assert sorted(result.status_code for result in results) == [200, 409], [
        result.text for result in results
    ]
    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=owner).json()
    assert len([r for r in rows if r["status"] == "running"]) == 1


def test_pg16_concurrent_restart_same_mutation_is_one_interval(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import pytest

    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("Idempotent concurrent rest start requires PostgreSQL 16")
    owner = _auth(client, 996025)
    workout = _new_workout(client, owner)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=owner,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    parent = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=owner,
        json={
            "source_set_id": sid,
            "started_at": (datetime.now(UTC) - timedelta(seconds=15)).isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert parent.status_code == 200, parent.text
    parent_id = parent.json()["id"]
    assert (
        client.post(
            f"/api/v1/workouts/rest-sessions/{parent_id}/actions",
            headers=owner,
            json={"action": "skip", "expected_version": 1, "mutation_id": str(uuid4())},
        ).status_code
        == 200
    )
    payload = {
        "started_at": datetime.now(UTC).isoformat(),
        "mutation_id": str(uuid4()),
    }
    barrier = Barrier(2)

    def restart(_):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/workouts/rest-sessions/{parent_id}/restart",
            headers=owner,
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(restart, range(2)))
    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=owner).json()
    assert len(rows) == 2
    assert len([r for r in rows if r["status"] == "running"]) == 1


def test_pg16_simultaneous_same_set_click_replays_one_initial_interval(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import pytest

    from fitminiapp_api.db.session import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrent double click requires PostgreSQL")
    owner = _auth(client, 996026)
    workout = _new_workout(client, owner)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=owner,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    payload = {
        "source_set_id": sid,
        "started_at": datetime.now(UTC).isoformat(),
        "mutation_id": str(uuid4()),
    }
    barrier = Barrier(2)

    def start(_):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v1/workouts/{wid}/rest-sessions",
            headers=owner,
            json=payload,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, range(2)))
    assert [response.status_code for response in results] == [200, 200], [
        response.text for response in results
    ]
    assert results[0].json()["id"] == results[1].json()["id"]
    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=owner).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "running"


def test_offline_skip_then_restart_preserves_tap_order_and_interval_facts(client):
    """Delayed delivery must not turn a legitimate offline successor into 422."""
    headers = _auth(client, 996031)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={"actual_reps": 8, "actual_weight": 40, "is_completed": True},
        ).status_code
        == 200
    )

    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=80)
    skipped_at = now - timedelta(seconds=50)
    restarted_at = now - timedelta(seconds=48)
    initial = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": started_at.isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert initial.status_code == 200, initial.text
    parent = initial.json()
    skip_url = f"/api/v1/workouts/rest-sessions/{parent['id']}/actions"
    skip_action = {
        "action": "skip",
        "occurred_at": skipped_at.isoformat(),
        "expected_version": 1,
        "mutation_id": str(uuid4()),
    }
    # Simulate an offline journal flushing all three operations after reconnection.
    terminal = client.post(skip_url, headers=headers, json=skip_action)
    assert terminal.status_code == 200, terminal.text
    assert datetime.fromisoformat(terminal.json()["ended_at"]) == skipped_at
    assert terminal.json()["measured_seconds"] is None
    assert client.post(skip_url, headers=headers, json=skip_action).status_code == 200

    restart_url = f"/api/v1/workouts/rest-sessions/{parent['id']}/restart"
    restart_payload = {"started_at": restarted_at.isoformat(), "mutation_id": str(uuid4())}
    successor = client.post(restart_url, headers=headers, json=restart_payload)
    assert successor.status_code == 200, successor.text
    child = successor.json()
    assert child["id"] != parent["id"]
    assert child["status"] == "running"
    assert datetime.fromisoformat(child["started_at"]) == restarted_at
    assert (
        client.post(restart_url, headers=headers, json=restart_payload).json()["id"] == child["id"]
    )

    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=headers)
    assert rows.status_code == 200
    assert [row["id"] for row in rows.json()] == [parent["id"], child["id"]]
    assert rows.json()[0]["status"] == "skipped"
    assert rows.json()[0]["measured_seconds"] is None
    current = client.get("/api/v1/workouts/today", headers=headers).json()
    assert current["exercises"][0]["sets"][0]["actual_weight"] == 40
    assert not current["exercises"][0]["sets"][1]["is_completed"]


def test_terminal_offline_event_time_rejects_impossible_dates_without_mutation(client):
    headers = _auth(client, 996032)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=60)
    started = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": started_at.isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert started.status_code == 200
    sid_rest = started.json()["id"]
    action_url = f"/api/v1/workouts/rest-sessions/{sid_rest}/actions"
    for action in ("skip", "interrupt", "unknown"):
        for invalid in (
            started_at - timedelta(seconds=1),
            now + timedelta(days=1),
        ):
            result = client.post(
                action_url,
                headers=headers,
                json={
                    "action": action,
                    "mutation_id": str(uuid4()),
                    "expected_version": 1,
                    "occurred_at": invalid.isoformat(),
                },
            )
            assert result.status_code == 422, result.text
    assert (
        client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=headers).json()[0]["status"]
        == "running"
    )
    # Legacy clients do not send occurred_at; they keep working.
    legacy = client.post(
        action_url,
        headers=headers,
        json={"action": "skip", "mutation_id": str(uuid4()), "expected_version": 1},
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["ended_at"] is not None


def test_pg16_concurrent_two_tab_conflicts_do_not_duplicate_terminal_actions(client):
    """One winner and one explicit 409, proven using real PostgreSQL row locks."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import pytest

    from fitminiapp_api.db.session import engine
    from fitminiapp_api.models.workout_rest import WorkoutRestAction

    if engine.dialect.name != "postgresql":
        pytest.skip("Two-tab row-lock oracle requires PostgreSQL 16")
    headers = _auth(client, 996033)
    workout = _new_workout(client, headers)
    wid = workout["id"]
    sid = workout["exercises"][0]["sets"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/workouts/sets/{sid}",
            headers=headers,
            json={"actual_reps": 8, "is_completed": True},
        ).status_code
        == 200
    )
    now = datetime.now(UTC)
    started = client.post(
        f"/api/v1/workouts/{wid}/rest-sessions",
        headers=headers,
        json={
            "source_set_id": sid,
            "started_at": (now - timedelta(seconds=25)).isoformat(),
            "mutation_id": str(uuid4()),
        },
    )
    assert started.status_code == 200
    rest_id = started.json()["id"]
    barrier = Barrier(2)

    def mutate(action):
        barrier.wait(timeout=10)
        body = {"action": action, "mutation_id": str(uuid4()), "expected_version": 1}
        if action == "complete":
            body["ended_at"] = now.isoformat()
        else:
            body["occurred_at"] = now.isoformat()
        return client.post(
            f"/api/v1/workouts/rest-sessions/{rest_id}/actions",
            headers=headers,
            json=body,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(mutate, ["complete", "skip"]))
    assert sorted(reply.status_code for reply in replies) == [200, 409], [
        reply.text for reply in replies
    ]
    rows = client.get(f"/api/v1/workouts/{wid}/rest-sessions", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["status"] in ("completed", "skipped")
    assert rows[0]["version"] == 2
    from fitminiapp_api.db.session import get_session_context

    with get_session_context() as session:
        assert session.query(WorkoutRestAction).filter_by(session_id=rest_id).count() == 1
