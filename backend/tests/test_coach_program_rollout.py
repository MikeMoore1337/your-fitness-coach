from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import ProgramRevision, UserProgram
from fitminiapp_api.models.user import CoachClient, User


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _setup_coach_clients(client, *, count: int = 2):
    coach_headers = _auth(client, 97501, is_coach=True)
    client_headers = [_auth(client, 97501 + index) for index in range(1, count + 1)]
    with get_session_context() as db:
        coach = db.query(User).filter(User.telegram_user_id == 97501).one()
        clients = [
            db.query(User).filter(User.telegram_user_id == 97501 + index).one()
            for index in range(1, count + 1)
        ]
        client_values = [(managed.id, managed.telegram_user_id) for managed in clients]
        db.add_all(
            [
                CoachClient(
                    coach_user_id=coach.id,
                    client_user_id=managed.id,
                    status="active",
                )
                for managed in clients
            ]
        )
        db.commit()
    return coach_headers, client_headers, client_values


def _template_payload(exercise_id: int, *, title: str, sets: int, telegram_user_id: int):
    start = today_msk()
    return {
        "title": title,
        "goal": "recomposition",
        "level": "intermediate",
        "mode": "coach",
        "target_telegram_user_id": telegram_user_id,
        "assign_after_create": False,
        "start_date": start.isoformat(),
        "duration_weeks": 1,
        "schedule_weekdays": [start.weekday()],
        "days": [
            {
                "title": "Силовая",
                "exercises": [
                    {
                        "exercise_id": exercise_id,
                        "prescribed_sets": sets,
                        "prescribed_reps": "8-10",
                        "rest_seconds": 90,
                    }
                ],
            }
        ],
    }


def test_rollout_preview_apply_is_idempotent_and_auditable(client):
    coach_headers, _client_headers, clients = _setup_coach_clients(client)
    catalog = client.get("/api/v1/programs/exercises", headers=coach_headers)
    assert catalog.status_code == 200, catalog.text
    exercise_id = next(item["id"] for item in catalog.json() if item["metric_type"] == "strength")
    start = today_msk()

    base = _template_payload(
        exercise_id,
        title="Исходный rollout",
        sets=2,
        telegram_user_id=clients[0][1],
    )
    base.update({"assign_after_create": True})
    created = client.post("/api/v1/programs/templates", headers=coach_headers, json=base)
    assert created.status_code == 200, created.text
    base_template_id = created.json()["template"]["id"]
    client_two_id = clients[1][0]
    assigned = client.post(
        f"/api/v1/coach/clients/{client_two_id}/templates/{base_template_id}/assign",
        headers=coach_headers,
        json={
            "start_date": start.isoformat(),
            "duration_weeks": 1,
            "schedule_weekdays": [start.weekday()],
            "replace_active": False,
        },
    )
    assert assigned.status_code == 200, assigned.text

    rollout_template = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json=_template_payload(
            exercise_id,
            title="Новый rollout",
            sets=3,
            telegram_user_id=clients[0][1],
        ),
    )
    assert rollout_template.status_code == 200, rollout_template.text
    template_id = rollout_template.json()["template"]["id"]

    programs = client.get("/api/v1/coach/assigned-programs", headers=coach_headers)
    assert programs.status_code == 200, programs.text
    target_programs = {
        row["client_id"]: row
        for row in programs.json()
        if row["client_id"] in {item[0] for item in clients}
    }
    assert set(target_programs) == {item[0] for item in clients}

    preview = client.post(
        "/api/v1/coach/program-rollouts/preview",
        headers=coach_headers,
        json={"template_id": template_id, "client_ids": list(target_programs)},
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert {row["classification"] for row in preview_body["targets"]} == {"compatible"}
    assert all(row["can_apply"] for row in preview_body["targets"])
    assert all(row["diff"] for row in preview_body["targets"])

    apply_body = {
        "template_id": template_id,
        "template_fingerprint": preview_body["template_fingerprint"],
        "targets": [
            {
                "client_id": row["client_id"],
                "program_id": row["program_id"],
                "expected_revision_number": row["current_revision_number"],
            }
            for row in preview_body["targets"]
        ],
        "confirmed": True,
        "reason": "Единое обновление будущего плана после предпросмотра",
        "idempotency_key": "rollout-test-97501",
    }
    stale_body = {
        **apply_body,
        "targets": [
            *apply_body["targets"][:1],
            {
                **apply_body["targets"][1],
                "expected_revision_number": apply_body["targets"][1]["expected_revision_number"]
                + 1,
            },
        ],
    }
    partial = client.post(
        "/api/v1/coach/program-rollouts/apply",
        headers={**coach_headers, "Idempotency-Key": "rollout-test-97501"},
        json=stale_body,
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["applied_count"] == 1
    assert partial.json()["failed_count"] == 1
    assert partial.json()["results"][1]["code"] == "stale_revision"

    applied = client.post(
        "/api/v1/coach/program-rollouts/apply",
        headers={**coach_headers, "Idempotency-Key": "rollout-test-97501"},
        json=apply_body,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_count"] == 1
    assert applied.json()["already_applied_count"] == 1
    assert applied.json()["failed_count"] == 0

    replay = client.post(
        "/api/v1/coach/program-rollouts/apply",
        headers={**coach_headers, "Idempotency-Key": "rollout-test-97501"},
        json=apply_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["already_applied_count"] == 2
    assert replay.json()["applied_count"] == 0

    with get_session_context() as db:
        program_ids = [row["program_id"] for row in apply_body["targets"]]
        revisions = (
            db.query(ProgramRevision).filter(ProgramRevision.user_program_id.in_(program_ids)).all()
        )
        assert (
            sum(
                revision.changed_fields.get("rollout_id") == applied.json()["rollout_id"]
                for revision in revisions
            )
            == 2
        )
        failed_audits = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "coach.program_rollout.failed",
                AuditEvent.resource_id.in_([str(program_id) for program_id in program_ids]),
            )
            .all()
        )
        assert len(failed_audits) == 1
        assert failed_audits[0].details["rollout_id"] == applied.json()["rollout_id"]


def test_rollout_rejects_cross_account_targets_and_reports_stale_client(client):
    coach_headers, _client_headers, clients = _setup_coach_clients(client, count=3)
    other_coach_headers = _auth(client, 97601, is_coach=True)
    _foreign_headers = _auth(client, 97602)
    with get_session_context() as db:
        other_coach = db.query(User).filter(User.telegram_user_id == 97601).one()
        foreign_client = db.query(User).filter(User.telegram_user_id == 97602).one()
        foreign_client_id = foreign_client.id
        db.add(
            CoachClient(
                coach_user_id=other_coach.id,
                client_user_id=foreign_client.id,
                status="active",
            )
        )
        db.commit()

    catalog = client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    exercise_id = next(item["id"] for item in catalog if item["metric_type"] == "strength")
    template = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json=_template_payload(
            exercise_id,
            title="Закрытый rollout",
            sets=2,
            telegram_user_id=clients[0][1],
        ),
    )
    assert template.status_code == 200, template.text
    template_id = template.json()["template"]["id"]

    denied = client.post(
        "/api/v1/coach/program-rollouts/preview",
        headers=other_coach_headers,
        json={"template_id": template_id, "client_ids": [clients[0][0]]},
    )
    assert denied.status_code == 404

    no_program = client.post(
        "/api/v1/coach/program-rollouts/preview",
        headers=coach_headers,
        json={"template_id": template_id, "client_ids": [clients[2][0]]},
    )
    assert no_program.status_code == 200, no_program.text
    assert no_program.json()["targets"][0]["classification"] == "manual_review_required"
    assert no_program.json()["targets"][0]["reason_codes"] == ["no_active_program"]

    with get_session_context() as db:
        foreign_program_count = (
            db.query(UserProgram).filter(UserProgram.user_id == foreign_client_id).count()
        )
        assert foreign_program_count == 0
