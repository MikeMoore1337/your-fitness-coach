from __future__ import annotations

import csv
import io
import json
import time
import zipfile
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from fitminiapp_api.core.config import settings
from fitminiapp_api.core.timezone import now_msk_naive, today_msk
from fitminiapp_api.db.session import get_session_context
from fitminiapp_api.models.audit import AuditEvent
from fitminiapp_api.models.program import (
    ProgramRevision,
    TrainingBlock,
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
)
from fitminiapp_api.models.program_import import ProgramImport
from fitminiapp_api.models.user import CoachClient, User
from fitminiapp_api.services.program_import_ai import (
    ProgramImportAiProposal,
    ProgramImportAiResponse,
)
from fitminiapp_api.services.program_imports import (
    PROGRAM_IMPORT_COLUMNS,
    build_program_import_template,
    expire_program_imports,
    parse_program_import,
)


def _auth(client, telegram_user_id: int, *, is_coach: bool = False) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"telegram_user_id": telegram_user_id, "is_coach": is_coach},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _csv_payload(rows: list[list[str]], *, marker: bool = True) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    if marker:
        writer.writerow(("#yfc_template_version", "1"))
    writer.writerow(PROGRAM_IMPORT_COLUMNS)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


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


def _docx_payload(
    paragraphs: list[str],
    tables: list[list[list[str]]],
    *,
    external_relationship: bool = False,
    nested_archive: bool = False,
) -> bytes:
    def paragraph(value: str) -> str:
        return f'<w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t></w:r></w:p>'

    def table(rows: list[list[str]]) -> str:
        return (
            "<w:tbl>"
            + "".join(
                "<w:tr>"
                + "".join(
                    f'<w:tc><w:p><w:r><w:t xml:space="preserve">{escape(value)}</w:t>'
                    "</w:r></w:p></w:tc>"
                    for value in row
                )
                + "</w:tr>"
                for row in rows
            )
            + "</w:tbl>"
        )

    body = "".join(paragraph(value) for value in paragraphs) + "".join(
        table(rows) for rows in tables
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    ).encode()
    content_types = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b"</Types>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
        if external_relationship:
            relationships = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rId1" '
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                b'Target="https://example.test" TargetMode="External"/>'
                b"</Relationships>"
            )
            archive.writestr("word/_rels/document.xml.rels", relationships)
        if nested_archive:
            archive.writestr("word/media/nested.zip", b"PK\x03\x04")
    return output.getvalue()


def _corpus_case(case_id: str) -> dict[str, object]:
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "program_import_corpus_v1.json").read_text(
            encoding="utf-8"
        )
    )
    return next(case for case in payload["cases"] if case["id"] == case_id)


def test_versioned_heterogeneous_corpus_covers_narrow_go_boundary():
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "program_import_corpus_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == 1
    cases = {case["id"]: case for case in payload["cases"]}
    assert {case["format"] for case in cases.values()} == {"csv", "xlsx", "txt", "docx"}
    assert {"docx_table", "ambiguous_exercise", "no_match_exercise"} <= cases.keys()
    assert {"malformed_text", "external_docx_relationship", "prompt_injection_in_name"} <= (
        cases.keys()
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
        assert body["schema_version"] == 3
        assert body["source_format"] == source_format
        assert body["summary"]["blocking_issue_count"] == 0, body
        assert body["rows"][0]["match_status"] == "matched"
        assert body["rows"][0]["source_range"] == "A3:U3"
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
        assert result["template"]["provenance_type"] == "CUSTOM"
        assert result["template"]["provenance"]["source_type"] == "file_upload"
        assert result["template"]["program_metadata"]["source_format"] == source_format

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


def test_import_uses_catalog_metric_type_when_cardio_row_omits_it(client):
    headers = _auth(client, 931019)
    row = _valid_row(exercise_name="Горизонтальный велотренажёр", exercise_slug="recumbent-bike")
    row[6] = ""
    row[7] = ""
    row[8] = ""
    row[11] = ""
    row[12] = "25"
    preview = _upload(client, headers, "cardio.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["rows"][0]["metric_type"] == "cardio"
    assert body["rows"][0]["prescribed_duration_minutes"] == 25
    assert body["summary"]["blocking_issue_count"] == 0, body

    confirmed = client.post(
        f"/api/v1/programs/imports/{body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text


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


def test_transliteration_is_a_manual_suggestion(client):
    headers = _auth(client, 931020)
    row = _valid_row(exercise_name="Prisedaniya bez vesa", exercise_slug="")
    preview = _upload(client, headers, "transliteration.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    unresolved = preview.json()["rows"][0]
    assert unresolved["match_status"] == "needs_resolution"
    assert unresolved["candidates"][0]["match_type"] == "transliteration"
    assert "exercise_suggested" in {issue["code"] for issue in unresolved["issues"]}

    resolved = client.post(
        f"/api/v1/programs/imports/{preview.json()['id']}/resolve",
        headers=headers,
        json={
            "rows": [{"row_number": 3, "exercise_id": unresolved["candidates"][0]["exercise_id"]}]
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["rows"][0]["match_status"] == "matched"
    assert resolved.json()["rows"][0]["match_type"] == "manual"
    assert resolved.json()["summary"]["blocking_issue_count"] == 0


def test_structured_rules_provenance_advanced_prescription_and_export_round_trip(client):
    headers = _auth(client, 931021)
    row = _valid_row()
    row.extend([""] * (len(PROGRAM_IMPORT_COLUMNS) - len(row)))
    row[6] = "2"
    row[16] = json.dumps(
        {
            "version": 1,
            "metric_type": "strength",
            "segments": [
                {
                    "position": 1,
                    "role": "top",
                    "rep_target": {"kind": "range", "min_reps": 6, "max_reps": 8},
                    "load_target": {"kind": "percent_training_max", "value": 85},
                    "effort_target": {"kind": "rir", "value": 1},
                    "rest_after_seconds": 120,
                },
                {
                    "position": 2,
                    "role": "backoff",
                    "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 10},
                    "load_target": {"kind": "relative_to_top", "value": 0.8},
                    "effort_target": {"kind": "rpe", "value": 8},
                    "rest_after_seconds": 90,
                },
            ],
            "groups": [],
        }
    )
    row[17] = "1"
    row[18] = "Разгрузочная неделя"
    row[19] = "true"
    row[20] = json.dumps(
        {
            "kind": "double_progression",
            "scope": "program",
            "rep_target": {"kind": "range", "min_reps": 8, "max_reps": 12},
            "increment_value": 2.5,
            "increment_unit": "kg",
            "reset_on_failure": True,
        }
    )
    preview = _upload(client, headers, "rules.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["summary"]["blocking_issue_count"] == 0, body
    assert body["blocks"] == [
        {
            "block_number": 1,
            "title": "Разгрузочная неделя",
            "week_start": 1,
            "week_end": 1,
            "is_deload": True,
        }
    ]
    assert body["coaching_rules"][0]["kind"] == "double_progression"

    resolved = client.post(
        f"/api/v1/programs/imports/{body['id']}/resolve",
        headers=headers,
        json={
            "provenance": {
                "provenance_type": "SOURCE_ADAPTATION",
                "source_name": "Исходная программа",
                "creator": "Автор программы",
                "organization": "Сообщество",
                "source_reference": "https://example.test/program",
                "source_version": "редакция 2",
                "source_date": "2026-09-14",
                "adaptation_notes": "Изменён выбор упражнений",
            }
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["summary"]["blocking_issue_count"] == 0
    confirmed = client.post(
        f"/api/v1/programs/imports/{body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    template = confirmed.json()["template"]
    assert template["provenance_type"] == "SOURCE_ADAPTATION"
    assert template["provenance"]["creator"] == "Автор программы"
    assert template["provenance"]["source_date"] == "2026-09-14"
    assert template["provenance"]["imported_at"]
    assert template["program_metadata"]["training_blocks"] == body["blocks"]
    assert template["program_metadata"]["coaching_rules"][0]["reset_on_failure"] is True
    assert template["days"][0]["exercises"][0]["prescription"]["segments"][0]["role"] == "top"

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    exported_template = next(
        item for item in exported.json()["program_templates"] if item["id"] == template["id"]
    )
    assert exported_template["provenance"] == template["provenance"]
    assert exported_template["program_metadata"] == template["program_metadata"]
    assert (
        exported_template["days"][0]["exercises"][0]["prescription"]["segments"][0]["role"] == "top"
    )

    exported_exercise = exported_template["days"][0]["exercises"][0]
    exported_source = exported_template["provenance"]
    round_trip_row = _valid_row(
        exercise_name=exported_exercise["exercise_title"],
        exercise_slug="",
    )
    round_trip_row.extend([""] * (len(PROGRAM_IMPORT_COLUMNS) - len(round_trip_row)))
    round_trip_row[0] = exported_template["title"]
    round_trip_row[1] = exported_template["goal"]
    round_trip_row[2] = exported_template["level"]
    round_trip_row[6] = str(exported_exercise["prescribed_sets"])
    round_trip_row[7] = exported_exercise["prescribed_reps"]
    round_trip_row[8] = str(exported_exercise["rest_seconds"])
    round_trip_row[9] = str(exported_exercise["exercise_id"])
    round_trip_row[16] = json.dumps(exported_exercise["prescription"])
    round_trip_row[17] = "1"
    round_trip_row[18] = template["program_metadata"]["training_blocks"][0]["title"]
    round_trip_row[19] = "true"
    round_trip_row[20] = json.dumps(template["program_metadata"]["coaching_rules"][0])
    round_trip_preview = _upload(
        client, headers, "exported-template.csv", _csv_payload([round_trip_row])
    )
    assert round_trip_preview.status_code == 201, round_trip_preview.text
    round_trip_resolved = client.post(
        f"/api/v1/programs/imports/{round_trip_preview.json()['id']}/resolve",
        headers=headers,
        json={
            "provenance": {
                "provenance_type": exported_template["provenance_type"],
                "source_name": exported_source["source_program_name"],
                "creator": exported_source["creator"],
                "organization": exported_source["organization"],
                "source_reference": exported_source["canonical_source"],
                "source_version": exported_source["source_version"],
                "source_date": exported_source["source_date"],
                "adaptation_notes": exported_source["adaptation_notes"],
            }
        },
    )
    assert round_trip_resolved.status_code == 200, round_trip_resolved.text
    assert round_trip_resolved.json()["summary"]["blocking_issue_count"] == 0
    round_trip_confirmed = client.post(
        f"/api/v1/programs/imports/{round_trip_preview.json()['id']}/confirm",
        headers=headers,
    )
    assert round_trip_confirmed.status_code == 200, round_trip_confirmed.text
    assert (
        round_trip_confirmed.json()["template"]["program_metadata"]["training_blocks"]
        == (template["program_metadata"]["training_blocks"])
    )
    assert (
        round_trip_confirmed.json()["template"]["program_metadata"]["coaching_rules"]
        == (template["program_metadata"]["coaching_rules"])
    )
    assert (
        round_trip_confirmed.json()["template"]["days"][0]["exercises"][0]["prescription"]
        == (template["days"][0]["exercises"][0]["prescription"])
    )


def test_resolve_without_provenance_preserves_existing_source_metadata(client):
    headers = _auth(client, 931027)
    preview = _upload(client, headers, "provenance.csv", _csv_payload([_valid_row()]))
    assert preview.status_code == 201, preview.text
    import_id = preview.json()["id"]

    adapted = client.post(
        f"/api/v1/programs/imports/{import_id}/resolve",
        headers=headers,
        json={
            "provenance": {
                "provenance_type": "SOURCE_ADAPTATION",
                "source_name": "Источник",
                "source_reference": "https://example.test/program",
            }
        },
    )
    assert adapted.status_code == 200, adapted.text

    resolved = client.post(
        f"/api/v1/programs/imports/{import_id}/resolve",
        headers=headers,
        json={"title": "Моя адаптация"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["provenance"]["provenance_type"] == "SOURCE_ADAPTATION"
    assert resolved.json()["provenance"]["source_reference"] == "https://example.test/program"


def test_pending_legacy_draft_without_import_metadata_remains_readable(client):
    headers = _auth(client, 931028)
    preview = _upload(client, headers, "legacy-draft.csv", _csv_payload([_valid_row()]))
    assert preview.status_code == 201, preview.text
    import_id = preview.json()["id"]

    with get_session_context() as db:
        import_row = db.query(ProgramImport).filter(ProgramImport.id == import_id).one()
        legacy_draft = dict(import_row.draft_json)
        for key in ("provenance", "blocks", "coaching_rules"):
            legacy_draft.pop(key, None)
        import_row.schema_version = 2
        import_row.draft_json = legacy_draft
        db.commit()

    readable = client.get(f"/api/v1/programs/imports/{import_id}", headers=headers)
    assert readable.status_code == 200, readable.text
    assert readable.json()["provenance"]["provenance_type"] == "CUSTOM"
    assert readable.json()["blocks"] == []
    assert readable.json()["coaching_rules"] == []


def test_import_can_create_one_revision_and_preserve_completed_workouts_and_blocks(client):
    headers = _auth(client, 931022)
    exercises = [
        item
        for item in client.get("/api/v1/programs/exercises", headers=headers).json()
        if item["metric_type"] == "strength"
    ]
    assert len(exercises) >= 2
    start = today_msk() + timedelta(days=1)
    assigned = client.post(
        "/api/v1/programs/templates",
        headers=headers,
        json={
            "title": "Исходная назначенная программа",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "self",
            "assign_after_create": True,
            "start_date": start.isoformat(),
            "duration_weeks": 1,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                },
                {
                    "title": "День 2",
                    "exercises": [
                        {
                            "exercise_id": exercises[0]["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                },
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["assigned_program_id"]
    with get_session_context() as db:
        workouts = (
            db.query(UserWorkout)
            .filter(UserWorkout.user_program_id == program_id)
            .order_by(UserWorkout.day_number)
            .all()
        )
        workout_dates = [workout.scheduled_date for workout in workouts]
        completed_workout_id = workouts[0].id
        planned_workout_id = workouts[1].id
        workouts[0].status = "completed"
        workouts[0].completed_at = now_msk_naive()
        db.commit()

    block = client.post(
        f"/api/v1/programs/assigned/{program_id}/blocks",
        headers=headers,
        json={
            "expected_revision_number": 1,
            "title": "Текущий блок",
            "start_date": workout_dates[0].isoformat(),
            "end_date": workout_dates[-1].isoformat(),
            "purpose": "Сохранить исходную структуру блока",
        },
    )
    assert block.status_code == 201, block.text
    block_id = block.json()["block"]["id"]

    rows = []
    for day_number in (1, 2):
        row = _valid_row(
            exercise_name=exercises[1]["title"],
            exercise_slug=exercises[1]["slug"],
        )
        row[3] = str(day_number)
        row[4] = f"Импортированный день {day_number}"
        rows.append(row)
    preview = _upload(client, headers, "revision.csv", _csv_payload(rows))
    assert preview.status_code == 201, preview.text
    import_id = preview.json()["id"]
    targets = client.get("/api/v1/programs/imports/targets", headers=headers)
    assert targets.status_code == 200, targets.text
    target = next(item for item in targets.json() if item["program_id"] == program_id)
    assert target["current_revision_number"] == 2
    assert target["day_numbers"] == [1, 2]

    confirm_payload = {
        "target_program_id": program_id,
        "expected_revision_number": 2,
    }
    stale_revision = client.post(
        f"/api/v1/programs/imports/{import_id}/confirm",
        headers=headers,
        json={"target_program_id": program_id, "expected_revision_number": 1},
    )
    assert stale_revision.status_code == 409
    assert stale_revision.json()["detail"] == (
        "Назначенная программа уже изменилась. Обновите список и повторите импорт."
    )
    confirmed = client.post(
        f"/api/v1/programs/imports/{import_id}/confirm",
        headers=headers,
        json=confirm_payload,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["assigned_program_id"] == program_id
    assert confirmed.json()["revision_number"] == 3
    assert confirmed.json()["workouts_updated"] == 1

    replay = client.post(
        f"/api/v1/programs/imports/{import_id}/confirm",
        headers=headers,
        json=confirm_payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["revision_number"] == 3
    assert replay.json()["template"]["id"] == confirmed.json()["template"]["id"]
    conflicting_replay = client.post(
        f"/api/v1/programs/imports/{import_id}/confirm",
        headers=headers,
        json={},
    )
    assert conflicting_replay.status_code == 409

    with get_session_context() as db:
        completed = db.query(UserWorkout).filter(UserWorkout.id == completed_workout_id).one()
        planned = db.query(UserWorkout).filter(UserWorkout.id == planned_workout_id).one()
        assert completed.status == "completed"
        assert [item.exercise_id for item in completed.exercises] == [exercises[0]["id"]]
        assert planned.status == "planned"
        assert [item.exercise_id for item in planned.exercises] == [exercises[1]["id"]]
        assert db.query(TrainingBlock).filter(TrainingBlock.id == block_id).count() == 1
        revisions = (
            db.query(ProgramRevision)
            .filter(ProgramRevision.user_program_id == program_id)
            .order_by(ProgramRevision.revision_number)
            .all()
        )
        assert [row.revision_number for row in revisions] == [1, 2, 3]
        assert revisions[2].snapshot["program"]["provenance_type"] == "CUSTOM"
        assert revisions[2].snapshot["program"]["program_metadata"]["source_type"] == "file_upload"
        assert len(revisions[2].snapshot["training_blocks"]) == 1

    exported = client.get("/api/v1/me/export", headers=headers)
    assert exported.status_code == 200, exported.text
    exported_program = next(
        item for item in exported.json()["programs"] if item["id"] == program_id
    )
    exported_revision = next(
        item for item in exported_program["revisions"] if item["revision_number"] == 3
    )
    assert exported_revision["snapshot"]["program"]["program_metadata"]["schema_version"] == 1

    with get_session_context() as db:
        for workout in db.query(UserWorkout).filter(
            UserWorkout.user_program_id == program_id,
            UserWorkout.status == "planned",
        ):
            workout.scheduled_date = today_msk() - timedelta(days=1)
        db.commit()

    no_future_rows = [list(row) for row in rows]
    for row in no_future_rows:
        row[0] = "Ревизия без будущих тренировок"
    no_future_preview = _upload(
        client,
        headers,
        "revision-without-future-workouts.csv",
        _csv_payload(no_future_rows),
    )
    assert no_future_preview.status_code == 201, no_future_preview.text
    no_future_confirm = client.post(
        f"/api/v1/programs/imports/{no_future_preview.json()['id']}/confirm",
        headers=headers,
        json={"target_program_id": program_id, "expected_revision_number": 3},
    )
    assert no_future_confirm.status_code == 200, no_future_confirm.text
    assert no_future_confirm.json()["revision_number"] == 4
    assert no_future_confirm.json()["workouts_updated"] == 0


def test_import_targets_enforce_trainer_relationship_and_owner_isolation(client):
    coach_headers = _auth(client, 931023, is_coach=True)
    client_headers = _auth(client, 931024)
    outsider_headers = _auth(client, 931025)
    coach_id = client.get("/api/v1/me", headers=coach_headers).json()["id"]
    client_id = client.get("/api/v1/me", headers=client_headers).json()["id"]
    with get_session_context() as db:
        db.add(
            CoachClient(
                coach_user_id=coach_id,
                client_user_id=client_id,
                status="active",
                accepted_at=now_msk_naive(),
            )
        )
        db.commit()

    client_exercises = client.get("/api/v1/programs/exercises", headers=client_headers).json()
    coach_exercises = client.get("/api/v1/programs/exercises", headers=coach_headers).json()
    outsider_exercises = client.get("/api/v1/programs/exercises", headers=outsider_headers).json()
    coach_exercise_ids = {
        item["id"] for item in coach_exercises if item["metric_type"] == "strength"
    }
    outsider_exercise_ids = {
        item["id"] for item in outsider_exercises if item["metric_type"] == "strength"
    }
    exercise = next(
        item
        for item in client_exercises
        if item["metric_type"] == "strength"
        and item["id"] in coach_exercise_ids
        and item["id"] in outsider_exercise_ids
    )
    start = today_msk() + timedelta(days=1)
    assigned = client.post(
        "/api/v1/programs/templates",
        headers=coach_headers,
        json={
            "title": "Программа клиента",
            "goal": "maintenance",
            "level": "beginner",
            "mode": "coach",
            "target_telegram_user_id": 931024,
            "assign_after_create": True,
            "start_date": start.isoformat(),
            "duration_weeks": 1,
            "days": [
                {
                    "title": "День 1",
                    "exercises": [
                        {
                            "exercise_id": exercise["id"],
                            "prescribed_sets": 2,
                            "prescribed_reps": "8",
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        },
    )
    assert assigned.status_code == 200, assigned.text
    program_id = assigned.json()["assigned_program_id"]
    assert [
        item["program_id"]
        for item in client.get("/api/v1/programs/imports/targets", headers=coach_headers).json()
    ] == [program_id]
    assert [
        item["program_id"]
        for item in client.get("/api/v1/programs/imports/targets", headers=client_headers).json()
    ] == [program_id]
    assert client.get("/api/v1/programs/imports/targets", headers=outsider_headers).json() == []

    row = _valid_row(exercise_name=exercise["title"], exercise_slug=exercise["slug"])
    row[9] = str(exercise["id"])
    unresolved_row = _valid_row(exercise_name="Неизвестное упражнение", exercise_slug="")
    trainer_preview = _upload(
        client, coach_headers, "trainer-import.csv", _csv_payload([unresolved_row])
    )
    assert trainer_preview.status_code == 201, trainer_preview.text
    trainer_resolution = client.post(
        f"/api/v1/programs/imports/{trainer_preview.json()['id']}/resolve",
        headers=coach_headers,
        json={"rows": [{"row_number": 3, "exercise_id": exercise["id"]}]},
    )
    assert trainer_resolution.status_code == 200, trainer_resolution.text
    assert trainer_resolution.json()["summary"]["blocking_issue_count"] == 0
    imported = client.post(
        f"/api/v1/programs/imports/{trainer_preview.json()['id']}/confirm",
        headers=coach_headers,
        json={"target_program_id": program_id, "expected_revision_number": 1},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["revision_number"] == 2
    assert imported.json()["target_user"]["id"] == client_id
    assert imported.json()["template"]["owner_user_id"] == client_id

    outsider_preview = _upload(client, outsider_headers, "outsider-import.csv", _csv_payload([row]))
    assert outsider_preview.status_code == 201, outsider_preview.text
    outsider_preview_body = outsider_preview.json()
    assert outsider_preview_body["summary"]["blocking_issue_count"] == 0, [
        issue["code"] for issue in outsider_preview_body["issues"]
    ]
    outsider_confirm = client.post(
        f"/api/v1/programs/imports/{outsider_preview.json()['id']}/confirm",
        headers=outsider_headers,
        json={"target_program_id": program_id, "expected_revision_number": 2},
    )
    assert outsider_confirm.status_code == 404, outsider_confirm.text

    detached = client.delete("/api/v1/me/trainer", headers=client_headers)
    assert detached.status_code == 204, detached.text
    assert client.get("/api/v1/programs/imports/targets", headers=coach_headers).json() == []
    revoked_preview = _upload(client, coach_headers, "revoked-import.csv", _csv_payload([row]))
    assert revoked_preview.status_code == 201, revoked_preview.text
    assert revoked_preview.json()["summary"]["blocking_issue_count"] == 0
    revoked_confirm = client.post(
        f"/api/v1/programs/imports/{revoked_preview.json()['id']}/confirm",
        headers=coach_headers,
        json={"target_program_id": program_id, "expected_revision_number": 2},
    )
    assert revoked_confirm.status_code == 404


def test_unstructured_coaching_rule_blocks_confirmation(client):
    headers = _auth(client, 931026)
    row = _valid_row()
    row.extend([""] * (len(PROGRAM_IMPORT_COLUMNS) - len(row)))
    row[20] = "Добавлять вес, когда все повторения выполнены"
    preview = _upload(client, headers, "unstructured-rule.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["summary"]["blocking_issue_count"] > 0
    assert "coaching_rule_invalid" in {issue["code"] for issue in body["rows"][0]["issues"]}
    confirmed = client.post(
        f"/api/v1/programs/imports/{body['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 409


def test_unsupported_progression_in_notes_blocks_confirmation(client):
    headers = _auth(client, 931029)
    row = _valid_row()
    row.extend([""] * (len(PROGRAM_IMPORT_COLUMNS) - len(row)))
    row[13] = "Add 2.5 kg once all reps are completed"
    preview = _upload(client, headers, "unsupported-progression.csv", _csv_payload([row]))
    assert preview.status_code == 201, preview.text
    body = preview.json()
    assert body["summary"]["blocking_issue_count"] > 0
    assert "coaching_rule_unstructured" in {issue["code"] for issue in body["rows"][0]["issues"]}


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


def test_txt_and_docx_documents_use_the_shared_preview_and_confirm_flow(client):
    headers = _auth(client, 931014)
    text_case = _corpus_case("ru_text_list")
    text_source = str(text_case["source"]).encode("utf-8")
    text_preview = _upload(client, headers, "corpus.txt", text_source)
    assert text_preview.status_code == 201, text_preview.text
    text_body = text_preview.json()
    assert text_body["source_format"] == "txt"
    assert text_body["layout_version"] == "text-list-v1"
    assert text_body["summary"]["row_count"] == 2
    assert text_body["summary"]["blocking_issue_count"] == 0, text_body
    assert text_body["rows"][0]["rest_seconds"] == 120
    assert text_body["rows"][1]["rest_seconds"] == 120
    assert text_body["rows"][0]["source_range"] == "строка 6"
    assert text_body["ai"]["status"] == "not_needed"
    confirmed_text = client.post(
        f"/api/v1/programs/imports/{text_body['id']}/confirm",
        headers=headers,
    )
    assert confirmed_text.status_code == 200, confirmed_text.text
    assert confirmed_text.json()["template"]["is_public"] is False

    docx_case = _corpus_case("docx_table")
    docx_source = _docx_payload(
        [str(value) for value in docx_case["paragraphs"]],
        [[[str(cell) for cell in row] for row in table] for table in docx_case["tables"]],
    )
    docx_preview = _upload(client, headers, "corpus.docx", docx_source)
    assert docx_preview.status_code == 201, docx_preview.text
    docx_body = docx_preview.json()
    assert docx_body["source_format"] == "docx"
    assert docx_body["layout_version"] == "docx-document-v1"
    assert docx_body["summary"]["blocking_issue_count"] == 0, docx_body
    assert docx_body["rows"][0]["source_sheet"] == "DOCX"
    assert docx_body["rows"][0]["source_range"] == "таблица 1, строка 2"
    assert docx_body["rows"][0]["rest_seconds"] == 120
    confirmed_docx = client.post(
        f"/api/v1/programs/imports/{docx_body['id']}/confirm",
        headers=headers,
    )
    assert confirmed_docx.status_code == 200, confirmed_docx.text

    with get_session_context() as db:
        stored = db.query(ProgramImport).filter(ProgramImport.document_format == "docx").one()
        assert stored.source_format == "csv"


def test_document_security_and_no_match_have_controlled_fallback(client):
    headers = _auth(client, 931015)
    malformed_case = _corpus_case("malformed_text")
    malformed = _upload(client, headers, "malformed.txt", str(malformed_case["source"]).encode())
    assert malformed.status_code == 422
    assert "управляющий" in malformed.json()["detail"]

    external_case = _corpus_case("external_docx_relationship")
    external = _upload(
        client,
        headers,
        "external.docx",
        _docx_payload(
            [str(value) for value in external_case["paragraphs"]],
            [],
            external_relationship=True,
        ),
    )
    assert external.status_code == 422
    assert "внешние связи" in external.json()["detail"]

    nested_archive = _upload(
        client,
        headers,
        "nested.docx",
        _docx_payload(["День 1", "Приседания без веса 3x8"], [], nested_archive=True),
    )
    assert nested_archive.status_code == 422
    assert "вложенные архивы" in nested_archive.json()["detail"]

    no_match_case = _corpus_case("no_match_exercise")
    no_match = _upload(client, headers, "no-match.txt", str(no_match_case["source"]).encode())
    assert no_match.status_code == 201, no_match.text
    body = no_match.json()
    assert body["source_format"] == "txt"
    assert body["ai"]["status"] == "disabled"
    assert body["ai"]["fallback"] == "deterministic_manual"
    assert "ai_assistance_unavailable" in {issue["code"] for issue in body["issues"]}
    assert body["rows"][0]["match_status"] == "needs_resolution"
    assert body["summary"]["blocking_issue_count"] > 0

    prompt_case = _corpus_case("prompt_injection_in_name")
    prompt_injection = _upload(
        client,
        headers,
        "prompt-injection.txt",
        str(prompt_case["source"]).encode(),
    )
    assert prompt_injection.status_code == 201, prompt_injection.text
    prompt_body = prompt_injection.json()
    assert prompt_body["ai"]["status"] == "disabled"
    assert prompt_body["rows"][0]["match_status"] == "needs_resolution"
    assert "Ignore previous instructions" in prompt_body["rows"][0]["exercise_name"]


def test_ai_proposals_are_source_grounded_and_never_auto_resolve_exercises(client):
    _auth(client, 931016)

    class FakeAiPort:
        request = None

        def propose(self, request):
            self.request = request
            evidence = request.source_spans[0]
            return ProgramImportAiResponse(
                status="proposed",
                attempts=1,
                proposals=(
                    ProgramImportAiProposal(
                        row_number=3,
                        field="prescribed_sets",
                        value="4",
                        evidence_id=evidence.evidence_id,
                        rationale="Число подходов найдено в строке источника",
                    ),
                    ProgramImportAiProposal(
                        row_number=3,
                        field="prescribed_reps",
                        value="8",
                        evidence_id=evidence.evidence_id,
                    ),
                ),
            )

    ai_port = FakeAiPort()
    source = (
        "Название: AI test\nЦель: maintenance\nУровень: beginner\nДень 1\n"
        "Приседания без веса\nПримечание: внутренний комментарий"
    ).encode()
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931016).one()
        draft = parse_program_import(
            db,
            user,
            source=source,
            source_format="txt",
            ai_port=ai_port,
        )
    assert ai_port.request is not None
    assert ai_port.request.source_format == "txt"
    assert ai_port.request.sensitivity == "personalized"
    assert not hasattr(ai_port.request, "user_id")
    assert "rest_seconds" not in ai_port.request.rows[0].fields
    assert "notes" not in ai_port.request.rows[0].fields
    assert "внутренний комментарий" not in ai_port.request.source_spans[0].text
    assert draft["ai"]["status"] == "proposed"
    assert draft["summary"]["blocking_issue_count"] == 0, draft
    assert draft["rows"][0]["prescribed_sets"] == 4
    assert draft["rows"][0]["prescribed_reps"] == "8"
    assert draft["rows"][0]["ai_proposals"][0]["applied"] is True
    assert draft["rows"][0]["ai_proposals"][0]["source_text"] == "Приседания без веса"

    class MappingOnlyAiPort:
        def propose(self, request):
            evidence = request.source_spans[0]
            return ProgramImportAiResponse(
                status="proposed",
                attempts=1,
                proposals=(
                    ProgramImportAiProposal(
                        row_number=3,
                        field="exercise_mapping",
                        value="bodyweight-squat",
                        evidence_id=evidence.evidence_id,
                    ),
                ),
            )

    unknown_source = (
        "Название: Mapping test\nЦель: maintenance\nУровень: beginner\n"
        "День 1\nНеизвестное упражнение 3x8"
    ).encode()
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931016).one()
        mapping_draft = parse_program_import(
            db,
            user,
            source=unknown_source,
            source_format="txt",
            ai_port=MappingOnlyAiPort(),
        )
    assert mapping_draft["rows"][0]["match_status"] == "needs_resolution"
    assert mapping_draft["rows"][0]["ai_proposals"][0]["applied"] is False
    assert mapping_draft["summary"]["blocking_issue_count"] > 0


def test_invalid_ai_evidence_fails_closed_to_deterministic_values(client):
    _auth(client, 931017)

    class InvalidEvidencePort:
        def propose(self, request):
            del request
            return ProgramImportAiResponse(
                status="proposed",
                attempts=1,
                proposals=(
                    ProgramImportAiProposal(
                        row_number=3,
                        field="prescribed_sets",
                        value="4",
                        evidence_id="source:txt:999",
                    ),
                ),
            )

    source = (
        "Название: Invalid evidence\nЦель: maintenance\nУровень: beginner\n"
        "День 1\nПриседания без веса"
    ).encode()
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931017).one()
        draft = parse_program_import(
            db,
            user,
            source=source,
            source_format="txt",
            ai_port=InvalidEvidencePort(),
        )
    assert draft["ai"]["status"] == "invalid_output"
    assert draft["rows"][0].get("prescribed_sets") is None
    assert draft["summary"]["blocking_issue_count"] > 0


def test_inconsistent_ai_status_payload_fails_closed(client):
    _auth(client, 931018)

    class InconsistentPort:
        def propose(self, request):
            del request
            return {
                "status": "no_change",
                "attempts": 1,
                "proposals": [
                    {
                        "row_number": 3,
                        "field": "prescribed_sets",
                        "value": "4",
                        "evidence_id": "source:txt:3",
                    }
                ],
            }

    source = "День 1\nПриседания без веса".encode()
    with get_session_context() as db:
        user = db.query(User).filter(User.telegram_user_id == 931018).one()
        draft = parse_program_import(
            db,
            user,
            source=source,
            source_format="txt",
            ai_port=InconsistentPort(),
        )
    assert draft["ai"]["status"] == "unavailable"
    assert draft["ai"]["attempts"] == 1
    assert draft["rows"][0].get("prescribed_sets") is None


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
