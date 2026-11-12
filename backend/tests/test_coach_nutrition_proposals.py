from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest

from fitminiapp_api.core.timezone import today_msk
from fitminiapp_api.db.session import engine, get_session_context
from fitminiapp_api.models.food import Food
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.user import CoachClient, User


def _auth(client, telegram_id: int, coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login", json={"telegram_user_id": telegram_id, "is_coach": coach}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _setup(client):
    athlete = _auth(client, 954001)
    coach = _auth(client, 954002, coach=True)
    outsider = _auth(client, 954003, coach=True)
    with get_session_context() as db:
        athlete_id = db.query(User.id).filter_by(telegram_user_id=954001).scalar()
        coach_id = db.query(User.id).filter_by(telegram_user_id=954002).scalar()
        relation = CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active")
        db.add(relation)
        db.flush()
        relation_id = relation.id
    payload = {
        "target_date": (today_msk() + timedelta(days=1)).isoformat(),
        "expected_target_id": None,
        "expected_plan_revision": 0,
        "calories": 2000,
        "protein_g": 150,
        "fat_g": 70,
        "carbs_g": 180,
    }
    return athlete, coach, outsider, athlete_id, relation_id, payload


def test_create_accept_and_retry_without_rewriting_history(client) -> None:
    athlete, coach, outsider, athlete_id, _, payload = _setup(client)
    path = f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}"
    assert (
        client.post(
            path, json=payload, headers={**outsider, "Idempotency-Key": "outsider-954"}
        ).status_code
        == 404
    )
    created = client.post(
        path, json=payload, headers={**coach, "Idempotency-Key": "proposal-954-1"}
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert proposal["status"] == "pending" and proposal["before"]["target"] is None
    retry = client.post(path, json=payload, headers={**coach, "Idempotency-Key": "proposal-954-1"})
    assert retry.json()["id"] == proposal["id"]
    before = client.get(
        "/api/v1/nutrition/targets/for-date",
        params={"target_date": payload["target_date"]},
        headers=athlete,
    )
    assert before.json()["target"] is None
    decision = {"decision": "accept", "version": proposal["version"]}
    url = f"/api/v1/coach-nutrition-proposals/{proposal['id']}/decision"
    assert (
        client.post(
            url, json=decision, headers={**coach, "Idempotency-Key": "decision-954"}
        ).status_code
        == 404
    )
    accepted = client.post(
        url, json=decision, headers={**athlete, "Idempotency-Key": "decision-954"}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    again = client.post(url, json=decision, headers={**athlete, "Idempotency-Key": "decision-954"})
    assert again.status_code == 200
    changed = client.get(
        "/api/v1/nutrition/targets/for-date",
        params={"target_date": payload["target_date"]},
        headers=athlete,
    )
    assert changed.json()["target"]["calories"] == 2000
    assert changed.json()["target"]["source"] == "trainer"
    past = client.get(
        "/api/v1/nutrition/targets/for-date",
        params={"target_date": today_msk().isoformat()},
        headers=athlete,
    )
    assert past.json()["target"] is None


def test_coach_reads_web_client_target_history_by_client_identity(client) -> None:
    athlete, coach, outsider, athlete_id, relation_id, _ = _setup(client)
    saved = client.post(
        "/api/v1/nutrition/targets/manual",
        headers=athlete,
        json={"calories": 2000, "protein_g": 150, "fat_g": 70, "carbs_g": 180},
    )
    assert saved.status_code == 200
    with get_session_context() as db:
        db.get(User, athlete_id).telegram_user_id = None
    url = f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}/target-history"
    history = client.get(url, headers=coach)
    assert history.status_code == 200 and history.json()["items"][0]["id"] == saved.json()["id"]
    assert client.get(url, headers=outsider).status_code == 404
    with get_session_context() as db:
        db.get(CoachClient, relation_id).nutrition_access = False
    assert client.get(url, headers=coach).status_code == 404


def test_revocation_and_stale_target_prevent_acceptance(client) -> None:
    athlete, coach, _, athlete_id, relation_id, payload = _setup(client)
    path = f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}"
    created = client.post(
        path, json=payload, headers={**coach, "Idempotency-Key": "proposal-954-2"}
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    with get_session_context() as db:
        db.get(CoachClient, relation_id).nutrition_access = False
    url = f"/api/v1/coach-nutrition-proposals/{proposal['id']}/decision"
    response = client.post(
        url,
        json={"decision": "accept", "version": 1},
        headers={**athlete, "Idempotency-Key": "decision-954-2"},
    )
    assert response.status_code == 404
    with get_session_context() as db:
        db.get(CoachClient, relation_id).nutrition_access = True
    changed = client.post(
        "/api/v1/nutrition/targets/dates",
        json={
            **{k: payload[k] for k in ("calories", "protein_g", "fat_g", "carbs_g")},
            "effective_from": payload["target_date"],
        },
        headers={**athlete, "Idempotency-Key": "external-954-2"},
    )
    assert changed.status_code == 200
    response = client.post(
        url,
        json={"decision": "accept", "version": 1},
        headers={**athlete, "Idempotency-Key": "decision-954-2"},
    )
    assert response.status_code == 409


def test_changed_program_prevents_acceptance(client) -> None:
    athlete, coach, _, athlete_id, _, payload = _setup(client)
    created = client.post(
        f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}",
        json=payload,
        headers={**coach, "Idempotency-Key": "proposal-program-954"},
    )
    assert created.status_code == 201
    with get_session_context() as db:
        db.add(UserProgram(user_id=athlete_id, is_active=True))
    response = client.post(
        f"/api/v1/coach-nutrition-proposals/{created.json()['id']}/decision",
        json={"decision": "accept", "version": 1},
        headers={**athlete, "Idempotency-Key": "decision-program-954"},
    )
    assert response.status_code == 409
    assert "Программа изменилась" in response.json()["detail"]
    assert (
        client.get(
            "/api/v1/nutrition/targets/for-date",
            params={"target_date": payload["target_date"]},
            headers=athlete,
        ).json()["target"]
        is None
    )


def test_failed_plan_change_rolls_back_the_target_and_decision(client) -> None:
    athlete, coach, _, athlete_id, _, payload = _setup(client)
    with get_session_context() as db:
        food = Food(
            name="Продукт",
            energy_kcal_per_100g=Decimal("120"),
            protein_g_per_100g=Decimal("12"),
            fat_g_per_100g=Decimal("4"),
            carbs_g_per_100g=Decimal("8"),
            food_type="system",
            provenance="internal",
            source_name="yfc-test",
            trust_level="verified",
            status="active",
        )
        db.add(food)
        db.flush()
        food_id = food.id
    added = client.post(
        "/api/v1/nutrition/plans/items",
        headers={**athlete, "Idempotency-Key": "food-plan-954"},
        params={"plan_date": payload["target_date"], "meal_type": "lunch", "expected_revision": 0},
        json={"food_id": food_id, "amount": "100", "amount_unit": "g"},
    )
    assert added.status_code == 201, added.text
    item = next(item for slot in added.json()["slots"] for item in slot["items"])
    payload.update(expected_plan_revision=1, item_id=item["id"], item_amount="150")
    created = client.post(
        f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}",
        json=payload,
        headers={**coach, "Idempotency-Key": "proposal-954-rollback"},
    )
    assert created.status_code == 201, created.text
    with get_session_context() as db:
        db.get(Food, food_id).status = "disabled"
    response = client.post(
        f"/api/v1/coach-nutrition-proposals/{created.json()['id']}/decision",
        json={"decision": "accept", "version": 1},
        headers={**athlete, "Idempotency-Key": "decision-954-rollback"},
    )
    assert response.status_code == 409
    target = client.get(
        "/api/v1/nutrition/targets/for-date",
        params={"target_date": payload["target_date"]},
        headers=athlete,
    )
    assert target.json()["target"] is None
    proposals = client.get("/api/v1/coach-nutrition-proposals", headers=athlete)
    assert proposals.json()[0]["status"] == "pending"


def test_reject_and_old_relationship_cannot_access_new_proposals(client) -> None:
    athlete, coach, other, athlete_id, relation_id, payload = _setup(client)
    path = f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}"
    created = client.post(
        path, json=payload, headers={**coach, "Idempotency-Key": "reject-proposal-954"}
    )
    assert created.status_code == 201
    proposal = created.json()
    url = f"/api/v1/coach-nutrition-proposals/{proposal['id']}/decision"
    wrong_version = client.post(
        url,
        json={"decision": "reject", "version": 2},
        headers={**athlete, "Idempotency-Key": "reject-954-key"},
    )
    assert wrong_version.status_code == 409
    decision = client.post(
        url,
        json={"decision": "reject", "version": 1},
        headers={**athlete, "Idempotency-Key": "reject-954-key"},
    )
    assert decision.status_code == 200 and decision.json()["status"] == "rejected"
    assert (
        client.post(
            url,
            json={"decision": "accept", "version": 1},
            headers={**athlete, "Idempotency-Key": "other-decision-954"},
        ).status_code
        == 409
    )
    assert (
        client.get(
            "/api/v1/nutrition/targets/for-date",
            params={"target_date": payload["target_date"]},
            headers=athlete,
        ).json()["target"]
        is None
    )
    with get_session_context() as db:
        old = db.get(CoachClient, relation_id)
        old.status = "ended"
        db.flush()
        other_id = db.query(User.id).filter_by(telegram_user_id=954003).scalar()
        db.add(CoachClient(coach_user_id=other_id, client_user_id=athlete_id, status="active"))
    assert (
        client.get(
            "/api/v1/coach-nutrition-proposals", params={"client_id": athlete_id}, headers=coach
        ).status_code
        == 404
    )
    new = client.post(path, json=payload, headers={**other, "Idempotency-Key": "new-coach-954"})
    assert new.status_code == 201
    assert (
        client.get(
            "/api/v1/coach-nutrition-proposals", params={"client_id": athlete_id}, headers=coach
        ).status_code
        == 404
    )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_parallel_decisions_are_idempotent(client) -> None:
    athlete, coach, _, athlete_id, _, payload = _setup(client)
    created = client.post(
        f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}",
        json=payload,
        headers={**coach, "Idempotency-Key": "parallel-create-954"},
    )
    assert created.status_code == 201, created.text
    url = f"/api/v1/coach-nutrition-proposals/{created.json()['id']}/decision"
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=10)
        return client.post(
            url,
            json={"decision": "accept", "version": 1},
            headers={**athlete, "Idempotency-Key": "parallel-decide-954"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: decide(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert all(response.json()["status"] == "accepted" for response in responses)
    history = client.get("/api/v1/nutrition/targets/dates", headers=athlete)
    assert history.status_code == 200
    assert len(history.json()) == 1


def test_reconnected_coach_cannot_revive_old_pending_proposal(client) -> None:
    athlete, coach, _, athlete_id, relation_id, payload = _setup(client)
    created = client.post(
        f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}",
        json=payload,
        headers={**coach, "Idempotency-Key": "old-relationship-954"},
    )
    assert created.status_code == 201
    with get_session_context() as db:
        old = db.get(CoachClient, relation_id)
        coach_id = old.coach_user_id
        old.status = "ended"
        db.flush()
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=athlete_id, status="active"))
    response = client.post(
        f"/api/v1/coach-nutrition-proposals/{created.json()['id']}/decision",
        json={"decision": "accept", "version": 1},
        headers={**athlete, "Idempotency-Key": "old-link-decision-954"},
    )
    assert response.status_code == 404
    listed = client.get(
        "/api/v1/coach-nutrition-proposals", params={"client_id": athlete_id}, headers=coach
    )
    assert listed.status_code == 200 and listed.json() == []


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires PostgreSQL row locks")
def test_parallel_different_decisions_apply_only_once(client) -> None:
    athlete, coach, _, athlete_id, _, payload = _setup(client)
    created = client.post(
        f"/api/v1/coach-nutrition-proposals/clients/{athlete_id}",
        json=payload,
        headers={**coach, "Idempotency-Key": "parallel-create-different"},
    )
    assert created.status_code == 201
    url = f"/api/v1/coach-nutrition-proposals/{created.json()['id']}/decision"
    barrier = Barrier(2)

    def decide(decision):
        barrier.wait(timeout=10)
        return client.post(
            url,
            json={"decision": decision, "version": 1},
            headers={**athlete, "Idempotency-Key": f"parallel-{decision}-954"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(decide, ["accept", "reject"]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    state = client.get("/api/v1/coach-nutrition-proposals", headers=athlete).json()[0]["status"]
    targets = client.get("/api/v1/nutrition/targets/dates", headers=athlete).json()
    assert len(targets) == (1 if state == "accepted" else 0)
