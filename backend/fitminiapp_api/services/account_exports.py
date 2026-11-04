from __future__ import annotations

import csv
import hashlib
import io
import json
import secrets
import tempfile
import uuid
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import now_msk_naive
from fitminiapp_api.models.account import AccountDataExport
from fitminiapp_api.models.user import User
from fitminiapp_api.services.account_export import build_account_export
from fitminiapp_api.services.workout_history_import_parser import CSV_COLUMNS_V2

ACCOUNT_EXPORT_RETENTION = timedelta(minutes=15)
ACCOUNT_EXPORT_DOWNLOAD_TOKEN_RETENTION = timedelta(minutes=2)
ACCOUNT_EXPORT_MAX_SOURCE_BYTES = 64 * 1024 * 1024
ACCOUNT_EXPORT_MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
ACCOUNT_EXPORT_SPOOL_BYTES = 2 * 1024 * 1024


class AccountExportError(ValueError):
    error_code = "generation_failed"


class AccountExportTooLargeError(AccountExportError):
    error_code = "archive_too_large"


def _json_bytes(value: object, *, indent: int | None = None) -> bytes:
    return json.dumps(
        jsonable_encoder(value),
        ensure_ascii=False,
        indent=indent,
        separators=None if indent else (",", ":"),
    ).encode("utf-8")


def _csv_cell(value: object) -> object:
    if value is None:
        return ""
    encoded = jsonable_encoder(value)
    if isinstance(encoded, str):
        if encoded.startswith(("=", "+", "-", "@", "\t", "\r")):
            return f"'{encoded}"
        return encoded
    if isinstance(encoded, (int, float, bool)):
        return encoded
    return json.dumps(encoded, ensure_ascii=False, separators=(",", ":"))


def _csv_bytes(rows: Iterable[dict[str, object]], columns: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _csv_cell(row.get(column)) for column in columns})
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, object], row) for row in value if isinstance(row, dict)]


def _workout_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    programs: list[dict[str, object]] = [
        *_rows(payload.get("programs")),
        {"workouts": _rows(payload.get("imported_workouts"))},
    ]
    for program in programs:
        for workout in _rows(program.get("workouts")):
            exercises = _rows(workout.get("exercises"))
            if not exercises:
                rows.append(
                    {
                        "program_id": program.get("id"),
                        "program_title": program.get("title"),
                        "workout_id": workout.get("id"),
                        "scheduled_date": workout.get("scheduled_date"),
                        "workout_status": workout.get("status"),
                    }
                )
                continue
            for exercise in exercises:
                sets = _rows(exercise.get("sets"))
                if not sets:
                    sets = [{}]
                for workout_set in sets:
                    sides = workout_set.get("sides")
                    sides = sides if isinstance(sides, dict) else {}
                    left_raw, right_raw = sides.get("left"), sides.get("right")
                    left = cast(dict[str, object], left_raw) if isinstance(left_raw, dict) else {}
                    right = (
                        cast(dict[str, object], right_raw) if isinstance(right_raw, dict) else {}
                    )
                    rows.append(
                        {
                            "program_id": program.get("id"),
                            "program_title": program.get("title"),
                            "workout_id": workout.get("id"),
                            "scheduled_date": workout.get("scheduled_date"),
                            "workout_status": workout.get("status"),
                            "exercise_id": exercise.get("exercise_id"),
                            "exercise_title": exercise.get("title"),
                            "set_id": workout_set.get("id"),
                            "set_number": workout_set.get("set_number"),
                            "actual_reps": workout_set.get("actual_reps"),
                            "actual_weight": workout_set.get("actual_weight"),
                            "rir": workout_set.get("rir"),
                            "set_kind": workout_set.get("set_kind"),
                            "reached_failure": workout_set.get("reached_failure"),
                            "is_completed": workout_set.get("is_completed"),
                            "execution_mode": workout_set.get("execution_mode"),
                            "first_side": workout_set.get("first_side"),
                            **{
                                f"{side}_{key}": facts.get(key)
                                for side, facts in (("left", left), ("right", right))
                                for key in (
                                    "actual_reps",
                                    "actual_weight",
                                    "rir",
                                    "reached_failure",
                                    "is_completed",
                                )
                            },
                        }
                    )
    return rows


def _neutral_history_csv(payload: dict[str, object]) -> bytes:
    result: list[dict[str, object]] = []
    programs: list[dict[str, object]] = [
        *_rows(payload.get("programs")),
        {"workouts": _rows(payload.get("imported_workouts"))},
    ]
    for program in programs:
        for workout in _rows(program.get("workouts")):
            if workout.get("status") != "completed":
                continue
            completed_at = workout.get("completed_at_utc")
            timestamp = (
                completed_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
                if isinstance(completed_at, datetime)
                else ""
            )
            for exercise in _rows(workout.get("exercises")):
                if exercise.get("metric_type") != "strength":
                    continue
                for workout_set in _rows(exercise.get("sets")):
                    if not workout_set.get("is_completed") and not workout_set.get("sides"):
                        continue
                    row: dict[str, object] = {
                        "workout_ref": str(workout.get("id")),
                        "completed_at": timestamp,
                        "timezone": "UTC",
                        "performed_on": workout.get("scheduled_date"),
                        "workout_title": workout.get("title"),
                        "status": "completed",
                        "exercise_ref": str(exercise.get("id")),
                        "exercise_name": exercise.get("title"),
                        "set_number": workout_set.get("set_number"),
                        "set_status": "completed"
                        if workout_set.get("is_completed")
                        else "incomplete",
                        "set_kind": workout_set.get("set_kind"),
                        "reps": workout_set.get("actual_reps"),
                        "weight": workout_set.get("actual_weight"),
                        "weight_unit": "kg" if workout_set.get("actual_weight") is not None else "",
                        "rir": workout_set.get("rir"),
                        "execution_mode": workout_set.get("execution_mode"),
                        "first_side": workout_set.get("first_side"),
                    }
                    failure = workout_set.get("reached_failure")
                    row["reached_failure"] = str(failure).lower() if failure is not None else ""
                    sides = workout_set.get("sides")
                    if isinstance(sides, dict):
                        for side in ("left", "right"):
                            facts = sides.get(side)
                            if not isinstance(facts, dict):
                                continue
                            row.update(
                                {
                                    f"{side}_reps": facts.get("actual_reps"),
                                    f"{side}_weight": facts.get("actual_weight"),
                                    f"{side}_weight_unit": "kg"
                                    if facts.get("actual_weight") is not None
                                    else "",
                                    f"{side}_rir": facts.get("rir"),
                                    f"{side}_status": "completed"
                                    if facts.get("is_completed")
                                    else "incomplete",
                                }
                            )
                            side_failure = facts.get("reached_failure")
                            row[f"{side}_reached_failure"] = (
                                str(side_failure).lower() if side_failure is not None else ""
                            )
                    result.append(row)
    return b"\xef\xbb\xbf" + b"yfc_workout_history,2\r\n" + _csv_bytes(result, CSV_COLUMNS_V2)[3:]


def _custom_avatar_export_snapshot(
    db: Session, user_id: int
) -> tuple[dict[str, object] | None, bytes | None]:
    avatar = (
        db.query(
            User.custom_avatar_image_bytes,
            User.custom_avatar_content_type,
            User.custom_avatar_byte_size,
            User.custom_avatar_width,
            User.custom_avatar_height,
            User.custom_avatar_sha256,
            User.custom_avatar_created_at,
            User.custom_avatar_updated_at,
        )
        .filter(User.id == user_id)
        .one()
    )
    if avatar.custom_avatar_updated_at is None:
        return None, None
    required_values = (
        avatar.custom_avatar_image_bytes,
        avatar.custom_avatar_content_type,
        avatar.custom_avatar_byte_size,
        avatar.custom_avatar_width,
        avatar.custom_avatar_height,
        avatar.custom_avatar_sha256,
        avatar.custom_avatar_created_at,
    )
    if any(value is None for value in required_values):
        raise AccountExportError("Custom avatar storage is incomplete")
    image_bytes = bytes(avatar.custom_avatar_image_bytes)
    if (
        avatar.custom_avatar_byte_size != len(image_bytes)
        or avatar.custom_avatar_sha256 != hashlib.sha256(image_bytes).hexdigest()
    ):
        raise AccountExportError("Custom avatar metadata does not match stored bytes")
    return (
        {
            "content_type": avatar.custom_avatar_content_type,
            "byte_size": avatar.custom_avatar_byte_size,
            "width": avatar.custom_avatar_width,
            "height": avatar.custom_avatar_height,
            "sha256": avatar.custom_avatar_sha256,
            "created_at": avatar.custom_avatar_created_at,
            "updated_at": avatar.custom_avatar_updated_at,
            "file": "avatar/avatar.webp",
        },
        image_bytes,
    )


def build_account_export_archive(db: Session, user: User) -> tuple[bytes, str]:
    """Build a bounded ZIP without durable filesystem artifacts."""

    avatar_metadata, avatar_bytes = _custom_avatar_export_snapshot(db, user.id)
    payload = build_account_export(db, user)
    payload["custom_avatar"] = avatar_metadata
    files: dict[str, bytes] = {
        "account.json": _json_bytes(payload, indent=2),
        "workout-history-neutral-v2.csv": _neutral_history_csv(payload),
        "measurements.csv": _csv_bytes(
            _rows(payload.get("measurements")),
            (
                "id",
                "measured_on",
                "weight_kg",
                "chest_cm",
                "waist_cm",
                "hips_cm",
                "biceps_cm",
                "thigh_cm",
                "note",
                "created_at",
            ),
        ),
        "nutrition-target-history.csv": _csv_bytes(
            _rows(payload.get("nutrition_target_history")),
            (
                "id",
                "effective_from",
                "effective_to",
                "source",
                "calories",
                "protein_g",
                "fat_g",
                "carbs_g",
                "saved_at",
            ),
        ),
        "weekly-check-ins.csv": _csv_bytes(
            _rows(payload.get("weekly_check_ins")),
            (
                "id",
                "week_start",
                "week_end",
                "submitted_on",
                "status",
                "training_load",
                "recovery",
                "hunger",
                "adherence_difficulty",
                "note",
                "created_at",
            ),
        ),
        "daily-wellbeing-check-ins.csv": _csv_bytes(
            _rows(payload.get("daily_wellbeing_check_ins")),
            (
                "id",
                "local_date",
                "timezone_at_entry",
                "sleep_quality",
                "sleep_duration_minutes",
                "mood",
                "note",
                "source",
                "created_at",
                "updated_at",
            ),
        ),
        "food-diary.csv": _csv_bytes(
            _rows(payload.get("food_diary_entries")),
            (
                "id",
                "diary_date",
                "meal_type",
                "logged_at",
                "entry_kind",
                "food_name",
                "food_brand",
                "amount",
                "amount_unit",
                "weight_g",
                "energy_kcal_per_100g",
                "protein_g_per_100g",
                "fat_g_per_100g",
                "carbs_g_per_100g",
                "fiber_g_per_100g",
                "created_at",
                "updated_at",
            ),
        ),
        "workout-history.csv": _csv_bytes(
            _workout_rows(payload),
            (
                "program_id",
                "program_title",
                "workout_id",
                "scheduled_date",
                "workout_status",
                "exercise_id",
                "exercise_title",
                "set_id",
                "set_number",
                "actual_reps",
                "actual_weight",
                "rir",
                "set_kind",
                "reached_failure",
                "is_completed",
                "execution_mode",
                "first_side",
                "left_actual_reps",
                "left_actual_weight",
                "left_rir",
                "left_reached_failure",
                "left_is_completed",
                "right_actual_reps",
                "right_actual_weight",
                "right_rir",
                "right_reached_failure",
                "right_is_completed",
            ),
        ),
    }
    if avatar_bytes is not None:
        files["avatar/avatar.webp"] = avatar_bytes
    source_size = sum(len(content) for content in files.values())
    if source_size > ACCOUNT_EXPORT_MAX_SOURCE_BYTES:
        raise AccountExportTooLargeError("Account export source exceeds the bounded limit")

    manifest = {
        "schema_version": 1,
        "account_export_schema_version": payload["schema_version"],
        "exported_at": payload["exported_at"],
        "format": "zip+json+csv",
        "files": sorted(files),
        "notes": [
            "account.json is the complete portability document.",
            "CSV files are tabular views of selected account-owned domains.",
            "The neutral workout CSV contains completed strength workouts; missing timestamps require review.",
            "Temporary report artifacts and authentication credentials are not included.",
            "A custom avatar, when present, is normalized WebP without source EXIF metadata.",
        ],
    }
    files["manifest.json"] = _json_bytes(manifest, indent=2)

    with tempfile.SpooledTemporaryFile(max_size=ACCOUNT_EXPORT_SPOOL_BYTES, mode="w+b") as spool:
        with zipfile.ZipFile(spool, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)
        archive_size = spool.tell()
        if archive_size > ACCOUNT_EXPORT_MAX_ARCHIVE_BYTES:
            raise AccountExportTooLargeError("Account export archive exceeds the bounded limit")
        spool.seek(0)
        archive_bytes = spool.read(ACCOUNT_EXPORT_MAX_ARCHIVE_BYTES + 1)
    if len(archive_bytes) > ACCOUNT_EXPORT_MAX_ARCHIVE_BYTES:
        raise AccountExportTooLargeError("Account export archive exceeds the bounded limit")
    filename = f"your-fitness-coach-data-{now_msk_naive().date().isoformat()}.zip"
    return archive_bytes, filename


def start_account_export(db: Session, user: User) -> AccountDataExport:
    db.query(User.id).filter(User.id == user.id).with_for_update().one()
    row = (
        db.query(AccountDataExport)
        .filter(AccountDataExport.user_id == user.id)
        .with_for_update()
        .first()
    )
    if row is None:
        row = AccountDataExport(user_id=user.id, export_id=str(uuid.uuid4()), status="generating")
        db.add(row)
    else:
        row.export_id = str(uuid.uuid4())
        row.status = "generating"
    row.archive_bytes = None
    row.filename = None
    row.content_size_bytes = None
    row.error_code = None
    row.download_token_hash = None
    row.download_token_expires_at = None
    row.created_at = now_msk_naive()
    row.completed_at = None
    row.expires_at = None
    db.flush()
    return row


def lock_account_export_generation(
    db: Session, user_id: int, export_id: str
) -> AccountDataExport | None:
    """Lock a generation only while it is still the account's current job."""

    db.expire_all()
    return (
        db.query(AccountDataExport)
        .filter(
            AccountDataExport.user_id == user_id,
            AccountDataExport.export_id == export_id,
            AccountDataExport.status == "generating",
        )
        .with_for_update()
        .first()
    )


def complete_account_export(
    row: AccountDataExport, archive_bytes: bytes, filename: str
) -> AccountDataExport:
    completed_at = now_msk_naive()
    row.status = "ready"
    row.archive_bytes = archive_bytes
    row.filename = filename
    row.content_size_bytes = len(archive_bytes)
    row.error_code = None
    row.completed_at = completed_at
    row.expires_at = completed_at + ACCOUNT_EXPORT_RETENTION
    return row


def fail_account_export(row: AccountDataExport, error_code: str) -> AccountDataExport:
    row.status = "error"
    row.archive_bytes = None
    row.filename = None
    row.content_size_bytes = None
    row.error_code = error_code
    row.completed_at = now_msk_naive()
    row.expires_at = None
    row.download_token_hash = None
    row.download_token_expires_at = None
    return row


def expire_account_export(row: AccountDataExport, *, now: datetime | None = None) -> bool:
    current = now or now_msk_naive()
    if row.status != "ready" or row.expires_at is None or row.expires_at > current:
        return False
    row.status = "expired"
    row.archive_bytes = None
    row.content_size_bytes = None
    row.download_token_hash = None
    row.download_token_expires_at = None
    return True


def prune_account_exports(db: Session, *, now: datetime | None = None) -> int:
    current = now or now_msk_naive()
    rows = (
        db.query(AccountDataExport)
        .filter(
            AccountDataExport.status == "ready",
            AccountDataExport.expires_at.is_not(None),
            AccountDataExport.expires_at <= current,
        )
        .all()
    )
    for row in rows:
        expire_account_export(row, now=current)
    return len(rows)


def create_account_export_download_token(
    row: AccountDataExport,
) -> tuple[str, datetime]:
    raw_token = secrets.token_urlsafe(32)
    expires_at = now_msk_naive() + ACCOUNT_EXPORT_DOWNLOAD_TOKEN_RETENTION
    row.download_token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row.download_token_expires_at = expires_at
    return raw_token, expires_at


def account_export_by_download_token(db: Session, raw_token: str) -> AccountDataExport | None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = (
        db.query(AccountDataExport)
        .filter(AccountDataExport.download_token_hash == token_hash)
        .first()
    )
    if row is None:
        return None
    current = now_msk_naive()
    if (
        row.download_token_expires_at is None
        or row.download_token_expires_at <= current
        or expire_account_export(row, now=current)
    ):
        row.download_token_hash = None
        row.download_token_expires_at = None
        return None
    return row
