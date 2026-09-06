from __future__ import annotations

import csv
import io
import time
import zipfile
from datetime import timedelta
from xml.sax.saxutils import escape

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import UserProgram, UserWorkout, UserWorkoutExercise
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


def _xlsx_column_label(column_number: int) -> str:
    value = column_number
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _xlsx_inline_cell(row_number: int, column_number: int, value: str) -> str:
    address = f"{_xlsx_column_label(column_number)}{row_number}"
    return f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def _weekly_matrix_xlsx(*, reorder_exercises: bool = False) -> bytes:
    day_header_rows = (2, 7, 12, 17)
    day_names = (
        ("Приседания с собственным весом", "Жим гантелей лежа", "Скручивания"),
        ("Румынская тяга", "Жим гантелей на наклонной скамье", "Разгибание ног"),
        ("Тяга штанги в наклоне", "Вертикальная тяга", "Тяга к подбородку"),
        ("Сгибание ног лежа", "Французский жим лежа", "Подъемы на носки стоя"),
    )
    cells_by_row: dict[int, list[tuple[int, str]]] = {}
    merge_ranges: list[str] = []

    def add_cell(row_number: int, column_number: int, value: str) -> None:
        cells_by_row.setdefault(row_number, []).append(
            (column_number, _xlsx_inline_cell(row_number, column_number, value))
        )

    for week_number in range(1, 13):
        block_start = 1 + (week_number - 1) * 3
        source_order = (1, 2, 3, 4) if week_number == 1 else (1, 3, 2, 4)
        add_cell(2, block_start + 2, f"Неделя {week_number}")
        for slot, source_day_number in enumerate(source_order):
            header_row = day_header_rows[slot]
            add_cell(header_row, block_start, f"ДЕНЬ {source_day_number}")
            merge_ranges.append(
                f"{_xlsx_column_label(block_start)}{header_row}:"
                f"{_xlsx_column_label(block_start + 1)}{header_row}"
            )
            exercises = list(enumerate(day_names[slot]))
            if reorder_exercises and week_number > 1 and slot == 0:
                exercises.reverse()
            for exercise_index, exercise_name in exercises:
                if week_number >= 4 and slot == 2 and exercise_index == 2:
                    exercise_name = "Приседания в Смите"
                source_row = header_row + 1 + exercise_index
                add_cell(
                    source_row,
                    block_start,
                    f"{exercise_name}\n{2 + (week_number % 3)}×{8 + week_number}",
                )
                if week_number == 1:
                    add_cell(source_row, block_start + 2, "32.5")

    rows_xml = "".join(
        f'<row r="{row_number}">{"".join(value for _, value in sorted(cells))}</row>'
        for row_number, cells in sorted(cells_by_row.items())
    )
    merges_xml = "".join(f'<mergeCell ref="{reference}"/>' for reference in merge_ranges)
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{rows_xml}</sheetData>"
        f'<mergeCells count="{len(merge_ranges)}">{merges_xml}</mergeCells>'
        '<hyperlinks><hyperlink ref="C3" r:id="rId1"/></hyperlinks>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="План" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    sheet_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        'Target="https://example.test/video" TargetMode="External"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels)
    return output.getvalue()


def _generic_xlsx_with_header_in_first_row() -> bytes:
    headers = [
        "Название программы",
        "Цель",
        "Уровень",
        "День",
        "Название дня",
        "Упражнение",
        "Подходы",
        "Повторы",
    ]
    values = [
        "Первая строка",
        "maintenance",
        "beginner",
        "1",
        "Силовая",
        "Приседания без веса",
        "3",
        "8-12",
    ]
    rows_xml = "".join(
        f'<row r="{row_number}">'
        + "".join(
            _xlsx_inline_cell(row_number, column_number, value)
            for column_number, value in enumerate(row, start=1)
        )
        + "</row>"
        for row_number, row in enumerate((headers, values), start=1)
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{rows_xml}</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="План" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


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


def test_semicolon_generic_csv_is_detected_without_canonical_marker(client):
    headers = _auth(client, 931011)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            "Название программы",
            "Цель",
            "Уровень",
            "День",
            "Название дня",
            "Упражнение",
            "Подходы",
            "Повторы",
            "Отдых",
            "Вес",
            "Неделя",
        ]
    )
    writer.writerow(
        [
            "Табличная программа",
            "maintenance",
            "beginner",
            "День 1",
            "Силовая 1",
            "Приседания с собственным весом",
            "3",
            "8-12",
            "90",
            "32.5",
            "1",
        ]
    )

    preview = _upload(client, headers, "generic-semicolon.csv", output.getvalue().encode("utf-8"))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["layout_version"] == "generic-table-v1"
    assert body["duration_weeks"] == 1
    assert body["summary"]["blocking_issue_count"] == 0, body
    assert body["rows"][0]["source_auxiliary"] == "32.5"
    assert "auxiliary_values_ignored" in {issue["code"] for issue in body["issues"]}


def test_generic_xlsx_accepts_header_in_first_row(client):
    headers = _auth(client, 931013)
    preview = _upload(
        client,
        headers,
        "generic-first-row.xlsx",
        _generic_xlsx_with_header_in_first_row(),
    )
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["layout_version"] == "generic-table-v1"
    assert body["summary"]["row_count"] == 1
    assert body["summary"]["blocking_issue_count"] == 0, body
    assert body["rows"][0]["exercise_name"] == "Приседания без веса"


def test_weekly_matrix_extracts_four_days_and_preserves_exercise_changes(client):
    headers = _auth(client, 931012)
    preview = _upload(
        client,
        headers,
        "weekly-matrix.xlsx",
        _weekly_matrix_xlsx(reorder_exercises=True),
    )
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["layout_version"] == "weekly-matrix-v1"
    assert body["duration_weeks"] == 12
    assert body["summary"]["row_count"] == 12 * 4 * 3
    assert {row["day_number"] for row in body["rows"]} == {1, 2, 3, 4}
    assert "day_order_normalized" in {issue["code"] for issue in body["issues"]}
    assert "xlsx_external_hyperlinks_ignored" in {issue["code"] for issue in body["issues"]}
    assert "weekly_structure_incomplete" not in {issue["code"] for issue in body["issues"]}

    resolved = client.post(
        f"/api/v1/programs/imports/{body['id']}/resolve",
        headers=headers,
        json={
            "title": "12-недельная программа",
            "goal": "maintenance",
            "level": "intermediate",
        },
    )
    assert resolved.status_code == 200, resolved.text
    resolved_body = resolved.json()
    assert resolved_body["summary"]["blocking_issue_count"] == 0, resolved_body
    assert "weekly_exercise_variation" in {issue["code"] for issue in resolved_body["issues"]}

    confirmed = client.post(
        f"/api/v1/programs/imports/{body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    template = confirmed.json()["template"]
    assert template["default_duration_weeks"] == 12
    assert len(template["days"]) == 4
    day_three = next(day for day in template["days"] if day["day_number"] == 3)
    changed_exercise = day_three["exercises"][2]
    assert len(changed_exercise["weekly_prescriptions"]) == 12
    assert len({item["exercise_id"] for item in changed_exercise["weekly_prescriptions"]}) == 2

    edited = client.patch(
        f"/api/v1/programs/templates/{template['id']}",
        headers=headers,
        json={
            "title": "12-недельная программа — обновлена",
            "goal": template["goal"],
            "level": template["level"],
            "mode": "self",
            "duration_weeks": 1,
            "assign_after_create": False,
            "days": [
                {
                    "title": (
                        f"{day['title']} — обновлён" if day["day_number"] == 1 else day["title"]
                    ),
                    "exercises": [
                        {
                            "exercise_id": exercise["exercise_id"],
                            "prescribed_sets": exercise["prescribed_sets"],
                            "prescribed_reps": exercise["prescribed_reps"],
                            "prescribed_duration_minutes": exercise["prescribed_duration_minutes"],
                            "rest_seconds": exercise["rest_seconds"],
                            "notes": exercise["notes"],
                            "superset_group": exercise["superset_group"],
                            "superset_order": exercise["superset_order"],
                        }
                        for exercise in day["exercises"]
                    ],
                }
                for day in template["days"]
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    edited_template = edited.json()
    assert edited_template["title"] == "12-недельная программа — обновлена"
    assert edited_template["default_duration_weeks"] == 12
    assert edited_template["days"][0]["title"].endswith("— обновлён")
    assert len(edited_template["days"][0]["exercises"][0]["weekly_prescriptions"]) == 12

    assigned = client.post(
        f"/api/v1/programs/templates/{template['id']}/assign-to-me",
        headers=headers,
        json={"duration_weeks": 12},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["workouts_created"] == 48
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931012).one()
        week_four_exercise = (
            db.query(UserWorkoutExercise)
            .join(UserWorkout)
            .filter(
                UserWorkout.user_program_id == assigned.json()["user_program_id"],
                UserWorkout.week_number == 4,
                UserWorkout.day_number == 3,
                UserWorkoutExercise.sort_order == 3,
            )
            .one()
        )
        assert (
            week_four_exercise.exercise_id
            == changed_exercise["weekly_prescriptions"][3]["exercise_id"]
        )
        week_two_exercises = (
            db.query(UserWorkoutExercise)
            .join(UserWorkout)
            .filter(
                UserWorkout.user_program_id == assigned.json()["user_program_id"],
                UserWorkout.week_number == 2,
                UserWorkout.day_number == 1,
            )
            .order_by(UserWorkoutExercise.sort_order)
            .all()
        )
        day_one = next(day for day in template["days"] if day["day_number"] == 1)
        assert [item.exercise_id for item in week_two_exercises] == [
            exercise["exercise_id"] for exercise in day_one["exercises"]
        ]
        assert user.id == week_four_exercise.workout.user_program.user_id
