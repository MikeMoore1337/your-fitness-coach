from __future__ import annotations

import re

from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import ProgramTemplate
from fitminiapp_api.models.public_share import PublicShareImport
from fitminiapp_api.models.user import CoachClient, User

OPAQUE_SHARE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user_id(telegram_user_id: int) -> int:
    with get_session_context() as db:
        return db.query(User.id).filter(User.telegram_user_id == telegram_user_id).one()[0]


def _create_template(client, headers: dict[str, str], title: str) -> int:
    with get_session_context() as db:
        exercise_id = (
            db.query(Exercise.id)
            .filter(Exercise.created_by_user_id.is_(None), Exercise.is_deleted.is_(False))
            .order_by(Exercise.id)
            .first()
        )[0]
    response = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": title,
            "goal": "muscle_gain",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": False,
            "duration_weeks": 2,
            "days": [
                {
                    "title": "Силовой день",
                    "exercises": [
                        {
                            "exercise_id": exercise_id,
                            "prescribed_sets": 3,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["template"]["id"]


def _assert_public_snapshot_has_no_private_keys(value: object) -> None:
    private_keys = {
        "id",
        "user_id",
        "owner_user_id",
        "created_by_user_id",
        "template_id",
        "user_program_id",
        "trainer_id",
    }
    if isinstance(value, dict):
        assert not private_keys.intersection(value)
        for child in value.values():
            _assert_public_snapshot_has_no_private_keys(child)
    elif isinstance(value, list):
        for child in value:
            _assert_public_snapshot_has_no_private_keys(child)


def test_progress_share_is_explicit_immutable_and_revocable(client) -> None:
    headers = _auth(client, 524_001)
    preview_response = client.post(
        "/api/v1/shares/progress/preview",
        headers=headers,
        json={"period": "days_30"},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()

    created_response = client.post(
        "/api/v1/shares/progress",
        headers=headers,
        json={"period": "days_30", "preview_hash": preview["preview_hash"]},
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    assert OPAQUE_SHARE_PATTERN.fullmatch(created["share_id"])
    assert created["public_url"].endswith(f"/share/{created['share_id']}")
    _assert_public_snapshot_has_no_private_keys(created["snapshot"])
    assert "nutrition" not in created["snapshot"]
    assert "body" not in created["snapshot"]

    public_response = client.get(f"/api/v1/public/shares/{created['share_id']}")
    assert public_response.status_code == 200, public_response.text
    assert public_response.headers["cache-control"] == "no-store"
    assert public_response.headers["x-robots-tag"] == "noindex, nofollow"
    assert public_response.json()["snapshot"] == created["snapshot"]

    page = client.get(f"/share/{created['share_id']}")
    assert page.status_code == 200
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "Прогресс тренировок" in page.text

    revoked = client.delete(f"/api/v1/shares/{created['share_id']}", headers=headers)
    assert revoked.status_code == 204, revoked.text
    unavailable = client.get(f"/api/v1/public/shares/{created['share_id']}")
    nonexistent = client.get("/api/v1/public/shares/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert unavailable.status_code == nonexistent.status_code == 404
    assert unavailable.json() == nonexistent.json()


def test_program_share_is_preview_first_snapshot_based_and_bounded(client) -> None:
    owner_headers = _auth(client, 524_002)
    template_id = _create_template(client, owner_headers, "Программа для общей ссылки")
    preview_response = client.post(
        "/api/v1/shares/program/preview",
        headers=owner_headers,
        json={"template_id": template_id},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    _assert_public_snapshot_has_no_private_keys(preview["snapshot"])

    created_response = client.post(
        "/api/v1/shares/program",
        headers=owner_headers,
        json={"template_id": template_id, "preview_hash": preview["preview_hash"]},
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()

    with get_session_context() as db:
        source = db.get(ProgramTemplate, template_id)
        assert source is not None
        source.title = "Изменённый исходник"
        db.flush()

    public_response = client.get(f"/api/v1/public/shares/{created['share_id']}")
    assert public_response.status_code == 200, public_response.text
    assert public_response.json()["snapshot"]["title"] == "Программа для общей ссылки"

    recipient_headers = _auth(client, 524_003)
    recipient_id = _user_id(524_003)
    with get_session_context() as db:
        assert (
            db.query(PublicShareImport)
            .filter(PublicShareImport.recipient_user_id == recipient_id)
            .count()
            == 0
        )

    imported = client.post(
        f"/api/v1/shares/{created['share_id']}/import",
        headers=recipient_headers,
        json={"preview_hash": created["preview_hash"]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["status"] == "imported"
    assert imported.json()["template_id"] > 0
    assert imported.json()["user_program_id"] > 0

    duplicate = client.post(
        f"/api/v1/shares/{created['share_id']}/import",
        headers=recipient_headers,
        json={"preview_hash": created["preview_hash"]},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "already_imported"
    assert duplicate.json()["template_id"] == imported.json()["template_id"]

    with get_session_context() as db:
        imports = (
            db.query(PublicShareImport)
            .filter(PublicShareImport.recipient_user_id == recipient_id)
            .all()
        )
        assert len(imports) == 1
        imported_template = db.get(ProgramTemplate, imported.json()["template_id"])
        assert imported_template is not None
        assert imported_template.owner_user_id == recipient_id
        assert imported_template.provenance == {"source": "public_share_snapshot"}

    outsider = _auth(client, 524_004)
    assert (
        client.delete(f"/api/v1/shares/{created['share_id']}", headers=outsider).status_code == 404
    )


def test_program_share_rejects_coach_access_to_client_template(client) -> None:
    owner_headers = _auth(client, 524_005)
    template_id = _create_template(client, owner_headers, "Программа клиента")
    coach_headers = _auth(client, 524_006, is_coach=True)
    owner_id = _user_id(524_005)
    coach_id = _user_id(524_006)
    with get_session_context() as db:
        db.add(CoachClient(coach_user_id=coach_id, client_user_id=owner_id))
        db.commit()

    response = client.post(
        "/api/v1/shares/program/preview",
        headers=coach_headers,
        json={"template_id": template_id},
    )
    assert response.status_code == 404
