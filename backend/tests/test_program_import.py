from __future__ import annotations

import io
import time
import zipfile
from datetime import timedelta

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import UserProgram
from fitminiapp_api.models.program_import import ProgramImport
from fitminiapp_api.models.user import User
from fitminiapp_api.services.program_imports import (
    PROGRAM_IMPORT_COLUMNS,
    build_program_import_template,
    expire_program_imports,
    parse_program_import,
)


def _auth(client, telegram_user_id: int) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": False},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _csv_payload(rows: list[list[str]], *, marker: bool = True) -> bytes:
    lines = []
    if marker:
        lines.append("#yfc_template_version,1")
    lines.append(",".join(PROGRAM_IMPORT_COLUMNS))
    lines.extend(",".join(row) for row in rows)
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def _valid_row(
    *, exercise_name: str = "Приседания без веса", exercise_slug: str = "bodyweight-squat"
) -> list[str]:
    return [
        "Синтетический импорт",
        "maintenance",
        "beginner",
        "1",
        "Силовая 1",
        exercise_name,
        "3",
        "8-12",
        "90",
        "",
        exercise_slug,
        "strength",
        "",
        "",
        "",
        "",
    ]


def _upload(client, headers: dict[str, str], filename: str, source: bytes):
    return client.post(
        "/api/v1/programs/imports",
        headers=headers,
        files={"file": (filename, source, "application/octet-stream")},
    )


def _synthetic_corpus_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for day_number in range(1, 9):
        for exercise_number in range(1, 21):
            row = _valid_row()
            row[3] = str(day_number)
            row[4] = f"Синтетический день {day_number}"
            row[13] = f"synthetic-row-{day_number}-{exercise_number}"
            rows.append(row)
    return rows


def test_canonical_csv_and_xlsx_round_trip_to_private_unassigned_template(client):
    headers = _auth(client, 931001)

    for source_format in ("csv", "xlsx"):
        source, _, filename = build_program_import_template(source_format)
        preview = _upload(client, headers, filename, source)
        assert preview.status_code == 201, preview.text
        body = preview.json()
        assert body["schema_version"] == 1
        assert body["source_format"] == source_format
        assert body["summary"]["blocking_issue_count"] == 0, body
        assert body["rows"][0]["match_status"] == "matched"
        assert body["rows"][0]["source_range"] == "A3:P3"
        assert body["rows"][0]["source_cells"]["exercise_name"] == "F3"
        assert body["rows"][0]["source_sheet"] == (
            "YFC Import" if source_format == "xlsx" else None
        )
        duplicate = _upload(client, headers, filename, source)
        assert duplicate.status_code == 409, duplicate.text

        confirmed = client.post(
            f"/api/v1/programs/imports/{body['id']}/confirm",
            headers=headers,
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()
        assert result["assigned_program_id"] is None
        assert result["workouts_created"] == 0
        assert result["template"]["is_public"] is False
        assert result["template"]["owner_user_id"] == result["target_user"]["id"]

        replay = client.post(
            f"/api/v1/programs/imports/{body['id']}/confirm",
            headers=headers,
        )
        assert replay.status_code == 200
        assert replay.json()["template"]["id"] == result["template"]["id"]

    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931001).one()
        imports = db.query(ProgramImport).filter(ProgramImport.owner_user_id == user.id).all()
        assert len(imports) == 2
        assert all(row.status == "confirmed" and row.draft_json == {} for row in imports)
        assert db.query(UserProgram).filter(UserProgram.user_id == user.id).count() == 0


def test_import_stays_private_for_verified_root_user(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_telegram_user_ids", "931009")
    headers = _auth(client, 931009)
    source, _, filename = build_program_import_template("csv")
    preview = _upload(client, headers, filename, source)
    assert preview.status_code == 201, preview.text

    confirmed = client.post(
        f"/api/v1/programs/imports/{preview.json()['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["template"]["is_public"] is False
    assert confirmed.json()["template"]["owner_user_id"] == confirmed.json()["target_user"]["id"]


def test_missing_manual_fields_and_unknown_exercise_are_resolvable(client):
    headers = _auth(client, 931002)
    exercise_id = next(
        item["id"]
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["slug"] == "bodyweight-squat"
    )
    row = _valid_row(exercise_name="Неизвестное упражнение", exercise_slug="")
    row[0] = "Программа без цели"
    row[1] = ""
    row[2] = ""
    preview = _upload(client, headers, "manual.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    issue_codes = {issue["code"] for issue in body["issues"] + body["rows"][0]["issues"]}
    assert {"missing_goal", "missing_level", "exercise_not_found"} <= issue_codes
    missing_goal = next(issue for issue in body["issues"] if issue["code"] == "missing_goal")
    missing_level = next(issue for issue in body["issues"] if issue["code"] == "missing_level")
    assert missing_goal["source_cell"] == "B2"
    assert missing_level["source_cell"] == "C2"
    assert body["summary"]["blocking_issue_count"] >= 3

    resolved = client.post(
        f"/api/v1/programs/imports/{body['id']}/resolve",
        headers=headers,
        json={
            "goal": "maintenance",
            "level": "beginner",
            "rows": [{"row_number": 3, "exercise_id": exercise_id}],
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["summary"]["blocking_issue_count"] == 0, resolved.json()

    confirmed = client.post(
        f"/api/v1/programs/imports/{body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text


def test_import_rejects_conflicting_exercise_identities_until_manual_resolution(client):
    headers = _auth(client, 931007)
    conflicting = _valid_row(exercise_name="Приседания без веса", exercise_slug="stationary-bike")
    preview = _upload(client, headers, "conflict.csv", _csv_payload([conflicting]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert "exercise_identity_conflict" in {issue["code"] for issue in body["rows"][0]["issues"]}
    conflict = next(
        issue
        for issue in body["rows"][0]["issues"]
        if issue["code"] == "exercise_identity_conflict"
    )
    assert conflict["source_cell"] == "F3"
    assert body["summary"]["blocking_issue_count"] >= 1

    exercise_id = next(
        item["id"]
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["slug"] == "bodyweight-squat"
    )
    resolved = client.post(
        f"/api/v1/programs/imports/{body['id']}/resolve",
        headers=headers,
        json={"rows": [{"row_number": 3, "exercise_id": exercise_id}]},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["summary"]["blocking_issue_count"] == 0


def test_duplicate_rows_are_blocking_and_empty_rows_are_ignored(client):
    headers = _auth(client, 931008)
    row = _valid_row()
    source = _csv_payload([row, [""] * len(PROGRAM_IMPORT_COLUMNS), row])
    preview = _upload(client, headers, "duplicates.csv", source)
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["summary"]["row_count"] == 2
    assert body["summary"]["blocking_issue_count"] >= 1
    assert "duplicate_row" in {issue["code"] for issue in body["issues"]}


def test_import_draft_is_owner_scoped_and_cancel_clears_content(client):
    owner_headers = _auth(client, 931003)
    other_headers = _auth(client, 931004)
    private_row = _valid_row()
    private_row[13] = "Секретная заметка"
    source = _csv_payload([private_row])
    preview = _upload(client, owner_headers, "private.csv", source)
    assert preview.status_code == 201, preview.text
    import_id = preview.json()["id"]

    assert (
        client.get(f"/api/v1/programs/imports/{import_id}", headers=other_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/programs/imports/{import_id}/confirm",
            headers=other_headers,
        ).status_code
        == 404
    )
    cancelled = client.post(
        f"/api/v1/programs/imports/{import_id}/cancel",
        headers=owner_headers,
    )
    assert cancelled.status_code == 204
    unavailable = client.get(f"/api/v1/programs/imports/{import_id}", headers=owner_headers)
    assert unavailable.status_code == 410

    with get_session_context() as db:
        row = db.get(ProgramImport, import_id)
        assert row is not None
        assert row.draft_json == {}
        audit = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "program_import.previewed", AuditEvent.resource_id == import_id
            )
            .one()
        )
        assert "Секретная заметка" not in repr(audit.details)


def test_upload_rejects_noncanonical_and_adversarial_xlsx(client):
    headers = _auth(client, 931005)
    unsupported = _upload(client, headers, "program.xlsm", b"not-an-xlsx")
    assert unsupported.status_code == 415

    unknown_header = _csv_payload([_valid_row()], marker=True).replace(
        b"program_title,",
        b"program_title,unexpected,",
        1,
    )
    assert _upload(client, headers, "unknown.csv", unknown_header).status_code == 422

    template, _, _ = build_program_import_template("xlsx")
    with zipfile.ZipFile(io.BytesIO(template)) as source_archive:
        formula_archive = io.BytesIO()
        with zipfile.ZipFile(
            formula_archive, "w", compression=zipfile.ZIP_DEFLATED
        ) as output_archive:
            for info in source_archive.infolist():
                content = source_archive.read(info.filename)
                if info.filename == "xl/worksheets/sheet1.xml":
                    content = content.replace(
                        b'<is><t xml:space="preserve">3</t></is>',
                        b"<f>1+2</f><v>3</v>",
                    )
                output_archive.writestr(info.filename, content)
    formula = _upload(client, headers, "formula.xlsx", formula_archive.getvalue())
    assert formula.status_code == 422
    assert "XLSX" in formula.json()["detail"]

    with zipfile.ZipFile(io.BytesIO(template)) as source_archive:
        traversal_archive = io.BytesIO()
        with zipfile.ZipFile(
            traversal_archive, "w", compression=zipfile.ZIP_DEFLATED
        ) as output_archive:
            for info in source_archive.infolist():
                output_archive.writestr(info.filename, source_archive.read(info.filename))
            output_archive.writestr("../outside.xml", b"blocked")
    traversal = _upload(client, headers, "traversal.xlsx", traversal_archive.getvalue())
    assert traversal.status_code == 422


def test_import_cleanup_and_representative_synthetic_benchmark(client):
    headers = _auth(client, 931006)
    source = _csv_payload(_synthetic_corpus_rows())
    filename = "synthetic-corpus.csv"
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931006).one()
        started = time.perf_counter()
        draft = parse_program_import(db, user, source=source, source_format="csv")
        elapsed_ms = (time.perf_counter() - started) * 1000
        assert draft["summary"]["blocking_issue_count"] == 0
        assert draft["summary"]["row_count"] == 160
        assert draft["summary"]["matched_row_count"] == 160
        assert elapsed_ms < 5_000
    preview = _upload(client, headers, filename, source)
    assert preview.status_code == 201
    import_id = preview.json()["id"]
    with get_session_context() as db:
        import_row = db.get(ProgramImport, import_id)
        assert import_row is not None
        expired = expire_program_imports(db, now=now_msk_naive() + timedelta(hours=2))
        assert expired == 1
        assert import_row.status == "expired"
        assert import_row.draft_json == {}


def test_expired_import_is_cleared_before_410_response(client):
    headers = _auth(client, 931010)
    source, _, filename = build_program_import_template("csv")
    preview = _upload(client, headers, filename, source)
    assert preview.status_code == 201
    import_id = preview.json()["id"]

    with get_session_context() as db:
        import_row = db.get(ProgramImport, import_id)
        assert import_row is not None
        import_row.expires_at = now_msk_naive() - timedelta(minutes=1)

    expired = client.get(f"/api/v1/programs/imports/{import_id}", headers=headers)
    assert expired.status_code == 410
    with get_session_context() as db:
        import_row = db.get(ProgramImport, import_id)
        assert import_row is not None
        assert import_row.status == "expired"
        assert import_row.draft_json == {}
