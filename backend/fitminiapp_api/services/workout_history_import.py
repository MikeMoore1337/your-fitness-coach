"""Owner-scoped, deterministic previews of neutral completed-workout imports."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import null
from sqlalchemy.orm import Session

from fitminiapp_api.models.exercise import Exercise
from fitminiapp_api.models.program import (
    UserProgram,
    UserWorkout,
    UserWorkoutExercise,
    UserWorkoutSet,
)
from fitminiapp_api.models.user import User
from fitminiapp_api.models.workout_history_import import ImportedWorkout, WorkoutHistoryImportDraft
from fitminiapp_api.services.exercise_catalog import get_visible_exercise_display_map
from fitminiapp_api.services.exercise_catalog_metadata import exercise_catalog_metadata
from fitminiapp_api.services.workout_history_import_parser import parse_workout_history_csv
from fitminiapp_api.services.workout_ownership import workout_owner_id

PROVIDER = "yfc-neutral-csv"
PARSER_VERSION = "1.0"
DRAFT_TTL = timedelta(hours=24)
TOMBSTONE_TTL = timedelta(days=7)
MAX_ACTIVE_DRAFTS = 3
MAX_WORKOUTS = 200
MAX_SETS_PER_WORKOUT = 200
MAX_CANDIDATE_WORKOUTS = 200
MAX_CANDIDATE_SETS = 5000
MAX_COMPARISON_VALUES = 20000


class HistoryImportError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()).replace("ё", "е")


def _catalog(db: Session, user: User) -> tuple[dict[int, dict], dict[str, list[int]]]:
    visible_ids = set(get_visible_exercise_display_map(db, user))
    rows = (
        db.query(Exercise)
        .filter(
            Exercise.id.in_(visible_ids),
            Exercise.created_by_user_id.is_(None),
            Exercise.source_exercise_id.is_(None),
            Exercise.is_deleted.is_(False),
        )
        .order_by(Exercise.id)
        .all()
    )
    by_id: dict[int, dict] = {}
    by_name: dict[str, list[int]] = defaultdict(list)
    for exercise in rows:
        metadata = exercise_catalog_metadata(exercise.slug)
        variants = set(metadata["execution_variant_tags"]) if metadata else set()
        item = {
            "exercise_id": exercise.id,
            "title": exercise.title,
            "metric_type": exercise.metric_type or "strength",
            "unsupported_side": bool(variants & {"unilateral", "alternating"}),
        }
        by_id[exercise.id] = item
        labels = (exercise.title, *(metadata["aliases"] if metadata else ()))
        for label in labels:
            name = _key(label)
            if name and exercise.id not in by_name[name]:
                by_name[name].append(exercise.id)
    return by_id, by_name


def _rows(source: bytes, by_name: dict[str, list[int]]) -> list[dict[str, Any]]:
    parsed = parse_workout_history_csv(source)
    workout_refs = {item.source["workout_ref"] for item in parsed}
    if len(workout_refs) > MAX_WORKOUTS:
        raise HistoryImportError("workout_limit", "В файле слишком много тренировок")
    workout_sizes: dict[str, int] = defaultdict(int)
    for item in parsed:
        workout_sizes[item.source["workout_ref"]] += 1
    if any(size > MAX_SETS_PER_WORKOUT for size in workout_sizes.values()):
        raise HistoryImportError("workout_size", "В одной тренировке слишком много строк")
    rows: list[dict[str, Any]] = []
    for item in parsed:
        candidates = by_name.get(_key(item.source["exercise_name"]), [])
        rows.append(
            {
                "line": item.line,
                "source": item.source,
                "completed_at_utc": item.completed_at_utc.isoformat()
                if item.completed_at_utc
                else None,
                "completed_on": item.completed_on.isoformat() if item.completed_on else None,
                "set_number": item.set_number,
                "reps": item.reps,
                "weight_kg": str(item.weight_kg) if item.weight_kg is not None else None,
                "issues": [asdict(issue) for issue in item.issues],
                "exercise_id": candidates[0] if len(candidates) == 1 else None,
                "match_mode": "auto" if len(candidates) == 1 else None,
                "excluded": False,
            }
        )
    return rows


def _lock_user(db: Session, user: User) -> None:
    db.query(User.id).filter(User.id == user.id).with_for_update().one()


def _get_draft(
    db: Session, user: User, draft_id: str, *, lock: bool = False
) -> WorkoutHistoryImportDraft:
    query = db.query(WorkoutHistoryImportDraft).filter(
        WorkoutHistoryImportDraft.id == draft_id,
        WorkoutHistoryImportDraft.owner_user_id == user.id,
    )
    if lock:
        query = query.with_for_update()
    draft = query.first()
    if draft is None:
        raise HistoryImportError("not_found", "Черновик не найден", 404)
    return draft


def _require_pending(draft: WorkoutHistoryImportDraft, version: int | None = None) -> None:
    if draft.status != "pending" or draft.expires_at <= _now() or draft.draft_json is None:
        raise HistoryImportError("draft_unavailable", "Черновик больше недоступен", 410)
    if version is not None and draft.version != version:
        raise HistoryImportError("stale_version", "Черновик изменился. Обновите предпросмотр", 409)


def expire_history_import_drafts(
    db: Session, *, now: datetime | None = None, limit: int = 100
) -> int:
    now = now or _now()
    rows = (
        db.query(WorkoutHistoryImportDraft)
        .filter(WorkoutHistoryImportDraft.expires_at <= now)
        .order_by(WorkoutHistoryImportDraft.expires_at, WorkoutHistoryImportDraft.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    for draft in rows:
        if draft.status == "pending":
            draft.status = "expired"
            draft.draft_json = None
            draft.result_json = None
            draft.expires_at = now + TOMBSTONE_TTL
        else:
            db.delete(draft)
    return len(rows)


def create_history_import(db: Session, user: User, source: bytes) -> WorkoutHistoryImportDraft:
    _lock_user(db, user)
    expire_history_import_drafts(db)
    active = (
        db.query(WorkoutHistoryImportDraft.id)
        .filter(
            WorkoutHistoryImportDraft.owner_user_id == user.id,
            WorkoutHistoryImportDraft.status == "pending",
            WorkoutHistoryImportDraft.expires_at > _now(),
        )
        .count()
    )
    if active >= MAX_ACTIVE_DRAFTS:
        raise HistoryImportError(
            "draft_limit", "Сначала завершите или удалите предыдущие черновики", 409
        )
    by_id, by_name = _catalog(db, user)
    del by_id
    rows = _rows(source, by_name)
    draft = WorkoutHistoryImportDraft(
        id=str(uuid4()),
        owner_user_id=user.id,
        provider=PROVIDER,
        source_sha256=hashlib.sha256(source).hexdigest(),
        schema_version=1,
        parser_version=PARSER_VERSION,
        status="pending",
        version=1,
        draft_json={"rows": rows, "duplicate_choices": {}},
        result_json=None,
        created_at=_now(),
        expires_at=_now() + DRAFT_TTL,
    )
    db.add(draft)
    db.flush()
    return draft


def _source_set_facts(rows: list[dict]) -> list[list]:
    facts = [
        [
            row["exercise_id"],
            row["set_number"],
            row["reps"],
            row["weight_kg"],
            row["source"]["set_kind"],
            row["source"]["rir"] or None,
        ]
        for row in rows
    ]
    return sorted(facts, key=lambda item: json.dumps(item, ensure_ascii=False))


def _enriched_rows(db: Session, user: User, payload: dict) -> list[dict]:
    by_id, by_name = _catalog(db, user)
    result = []
    for stored in payload["rows"]:
        row = dict(stored)
        candidates = by_name.get(_key(row["source"]["exercise_name"]), [])
        chosen = by_id.get(row["exercise_id"])
        if row["match_mode"] == "auto" and candidates != [row["exercise_id"]]:
            chosen = None
        row["candidates"] = [by_id[candidate] for candidate in candidates]
        row["resolved_title"] = chosen["title"] if chosen else None
        row["match_status"] = (
            "matched" if chosen else ("ambiguous" if len(candidates) > 1 else "unknown")
        )
        row["blocking_issues"] = list(row["issues"])
        if chosen is None:
            row["blocking_issues"].append(
                {
                    "code": "exercise_unresolved",
                    "field": "exercise_name",
                    "message": "Выберите упражнение из каталога",
                }
            )
        elif chosen["metric_type"] != "strength":
            row["blocking_issues"].append(
                {
                    "code": "unsupported_metric",
                    "field": "exercise_name",
                    "message": "Этот формат не переносит кардиопоказатели",
                }
            )
        elif chosen["unsupported_side"]:
            row["blocking_issues"].append(
                {
                    "code": "unsupported_side",
                    "field": "exercise_name",
                    "message": "Стороны этого упражнения пока нельзя перенести без потери смысла",
                }
            )
        result.append(row)
    return result


def _duplicates(
    db: Session, user: User, rows: list[dict], choices: dict, source_sha256: str
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row["excluded"] and row["source"]["workout_ref"]:
            grouped[row["source"]["workout_ref"]].append(row)
    relevant = {
        ref: group
        for ref, group in grouped.items()
        if choices.get(ref) != "skip" and all(not row["blocking_issues"] for row in group)
    }
    dates = {date.fromisoformat(group[0]["completed_on"]) for group in relevant.values()}
    existing: list[UserWorkout] = []
    if dates:
        existing = (
            db.query(UserWorkout)
            .outerjoin(UserProgram, UserProgram.id == UserWorkout.user_program_id)
            .outerjoin(ImportedWorkout, ImportedWorkout.workout_id == UserWorkout.id)
            .filter(
                workout_owner_id() == user.id,
                UserWorkout.status == "completed",
                UserWorkout.scheduled_date.in_(dates),
            )
            .order_by(UserWorkout.id)
            .limit(MAX_CANDIDATE_WORKOUTS + 1)
            .all()
        )
        if len(existing) > MAX_CANDIDATE_WORKOUTS:
            raise HistoryImportError(
                "candidate_limit", "Разделите файл на части для проверки совпадений", 409
            )
    existing_facts: dict[int, list[list]] = defaultdict(list)
    existing_sources: dict[int, str] = {}
    if existing:
        existing_sources = {
            item.workout_id: item.source_ref_hash
            for item in db.query(ImportedWorkout.workout_id, ImportedWorkout.source_ref_hash)
            .filter(
                ImportedWorkout.owner_user_id == user.id,
                ImportedWorkout.workout_id.in_([workout.id for workout in existing]),
            )
            .all()
        }
        set_rows = (
            db.query(
                UserWorkoutExercise.workout_id,
                UserWorkoutExercise.exercise_id,
                UserWorkoutSet.set_number,
                UserWorkoutSet.actual_reps,
                UserWorkoutSet.actual_weight,
                UserWorkoutSet.set_kind,
                UserWorkoutSet.rir,
            )
            .join(UserWorkoutSet, UserWorkoutSet.workout_exercise_id == UserWorkoutExercise.id)
            .filter(
                UserWorkoutExercise.workout_id.in_([workout.id for workout in existing]),
                UserWorkoutSet.is_completed.is_(True),
            )
            .limit(MAX_CANDIDATE_SETS + 1)
            .all()
        )
        if len(set_rows) > MAX_CANDIDATE_SETS:
            raise HistoryImportError(
                "candidate_limit", "Разделите файл на части для проверки совпадений", 409
            )
        for item in set_rows:
            existing_facts[item.workout_id].append(
                [
                    item.exercise_id,
                    item.set_number,
                    item.actual_reps,
                    str(item.actual_weight) if item.actual_weight is not None else None,
                    item.set_kind,
                    item.rir,
                ]
            )
        for facts in existing_facts.values():
            facts.sort(key=lambda item: json.dumps(item, ensure_ascii=False))
    comparisons = sum(
        1 + len(existing_facts[workout.id])
        for group in relevant.values()
        for workout in existing
        if workout.scheduled_date.isoformat() == group[0]["completed_on"]
    ) + sum(
        1 + len(other)
        for ref, group in relevant.items()
        for other_ref, other in relevant.items()
        if ref != other_ref and group[0]["completed_on"] == other[0]["completed_on"]
    )
    if comparisons > MAX_COMPARISON_VALUES:
        raise HistoryImportError(
            "candidate_limit", "Разделите файл на части для проверки совпадений", 409
        )
    result = []
    for ref, group in sorted(relevant.items()):
        source_facts = _source_set_facts(group)
        date_value = group[0]["completed_on"]
        instant = group[0]["completed_at_utc"]
        candidates = []
        for workout in existing:
            if workout.scheduled_date.isoformat() != date_value:
                continue
            facts = existing_facts[workout.id]
            exact = bool(
                workout.completed_at_utc
                and workout.completed_at_utc.isoformat() == instant
                and facts == source_facts
            )
            same_source = existing_sources.get(workout.id) == _hash([source_sha256, ref])
            candidates.append(
                {
                    "kind": "exact" if exact else ("source" if same_source else "possible"),
                    "workout_id": workout.id,
                    "title": workout.title,
                    "completed_at_utc": workout.completed_at_utc.isoformat()
                    if workout.completed_at_utc
                    else None,
                    "sets": facts,
                }
            )
        for other_ref, other in sorted(relevant.items()):
            if other_ref == ref or other[0]["completed_on"] != date_value:
                continue
            facts = _source_set_facts(other)
            exact = other[0]["completed_at_utc"] == instant and facts == source_facts
            candidates.append(
                {
                    "kind": "exact" if exact else "possible",
                    "source_ref": other_ref,
                    "title": other[0]["source"]["workout_title"],
                    "completed_at_utc": other[0]["completed_at_utc"],
                    "sets": facts,
                }
            )
        result.append(
            {
                "workout_ref": ref,
                "source_sets": source_facts,
                "candidates": candidates,
                "choice": choices.get(ref),
            }
        )
    return result


def history_import_preview(db: Session, user: User, draft: WorkoutHistoryImportDraft) -> dict:
    if draft.expires_at <= _now():
        raise HistoryImportError("draft_unavailable", "Черновик больше недоступен", 410)
    if draft.status == "confirmed":
        return {
            "id": draft.id,
            "version": draft.version,
            "status": draft.status,
            "result": draft.result_json,
        }
    _require_pending(draft)
    assert draft.draft_json is not None
    rows = _enriched_rows(db, user, draft.draft_json)
    duplicates = _duplicates(
        db, user, rows, draft.draft_json["duplicate_choices"], draft.source_sha256
    )
    signature = _hash({"rows": rows, "duplicates": duplicates})
    return {
        "id": draft.id,
        "version": draft.version,
        "status": draft.status,
        "provider": draft.provider,
        "schema_version": draft.schema_version,
        "parser_version": draft.parser_version,
        "expires_at": draft.expires_at.isoformat() + "Z",
        "rows": rows,
        "duplicates": duplicates,
        "duplicate_choices": dict(draft.draft_json["duplicate_choices"]),
        "preview_signature": signature,
    }


def resolve_history_import(
    db: Session,
    user: User,
    draft_id: str,
    *,
    version: int,
    exercise_choices: dict[int, int],
    excluded_lines: list[int],
    duplicate_choices: Mapping[str, str],
) -> WorkoutHistoryImportDraft:
    _lock_user(db, user)
    draft = _get_draft(db, user, draft_id, lock=True)
    _require_pending(draft, version)
    assert draft.draft_json is not None
    payload = json.loads(json.dumps(draft.draft_json, ensure_ascii=False))
    rows = payload["rows"]
    row_by_line = {row["line"]: row for row in rows}
    if (
        len(set(excluded_lines)) != len(excluded_lines)
        or not set(excluded_lines) <= row_by_line.keys()
    ):
        raise HistoryImportError("invalid_lines", "Некоторые строки не найдены", 422)
    by_id, _ = _catalog(db, user)
    selected_groups: dict[tuple[str, str], int] = {}
    for line, exercise_id in exercise_choices.items():
        row = row_by_line.get(line)
        if row is None or exercise_id not in by_id:
            raise HistoryImportError("invalid_exercise", "Упражнение недоступно в каталоге", 422)
        identity = (row["source"]["workout_ref"], row["source"]["exercise_ref"])
        if identity in selected_groups and selected_groups[identity] != exercise_id:
            raise HistoryImportError(
                "conflicting_exercise", "Выберите одно упражнение для каждой группы", 422
            )
        selected_groups[identity] = exercise_id
        for related in rows:
            if (related["source"]["workout_ref"], related["source"]["exercise_ref"]) == identity:
                related["exercise_id"] = exercise_id
                related["match_mode"] = "manual"
    refs = {row["source"]["workout_ref"] for row in rows}
    if not set(duplicate_choices) <= refs or any(
        value not in {"keep", "skip"} for value in duplicate_choices.values()
    ):
        raise HistoryImportError("invalid_decision", "Проверьте решение по совпадениям", 422)
    excluded = set(excluded_lines)
    for row in rows:
        row["excluded"] = row["line"] in excluded
    payload["duplicate_choices"] = dict(duplicate_choices)
    draft.draft_json = payload
    draft.version += 1
    db.flush()
    return draft


def confirm_history_import(
    db: Session, user: User, draft_id: str, *, version: int, preview_signature: str
) -> WorkoutHistoryImportDraft:
    _lock_user(db, user)
    draft = _get_draft(db, user, draft_id, lock=True)
    if draft.status == "confirmed":
        if draft.expires_at <= _now():
            raise HistoryImportError("draft_unavailable", "Черновик больше недоступен", 410)
        if draft.version != version:
            raise HistoryImportError(
                "stale_version", "Черновик изменился. Обновите предпросмотр", 409
            )
        return draft
    _require_pending(draft, version)
    assert draft.draft_json is not None
    if (
        draft.provider != PROVIDER
        or draft.schema_version != 1
        or draft.parser_version != PARSER_VERSION
    ):
        raise HistoryImportError(
            "source_changed", "Версия источника изменилась. Загрузите файл снова", 409
        )

    raw_rows = draft.draft_json["rows"]
    dates = {
        date.fromisoformat(row["completed_on"])
        for row in raw_rows
        if row["completed_on"] is not None
    }
    if dates:
        (
            db.query(UserProgram.id)
            .filter(
                UserProgram.user_id == user.id,
                UserProgram.workouts.any(UserWorkout.scheduled_date.in_(dates)),
            )
            .order_by(UserProgram.id)
            .with_for_update()
            .all()
        )
    preview = history_import_preview(db, user, draft)
    if preview_signature != preview["preview_signature"]:
        raise HistoryImportError(
            "preview_changed", "История или каталог изменились. Проверьте предпросмотр снова", 409
        )
    choices = draft.draft_json["duplicate_choices"]
    included = [
        row
        for row in preview["rows"]
        if not row["excluded"] and choices.get(row["source"]["workout_ref"]) != "skip"
    ]
    if not included:
        raise HistoryImportError(
            "nothing_to_import", "Выберите хотя бы один подход для импорта", 409
        )
    if any(row["blocking_issues"] for row in included):
        raise HistoryImportError(
            "unresolved_rows", "Исправьте или исключите строки с проблемами", 409
        )
    for item in preview["duplicates"]:
        if item["candidates"] and item["choice"] != "keep":
            raise HistoryImportError("duplicate_decision", "Проверьте возможные совпадения", 409)
        if any(candidate["kind"] in {"exact", "source"} for candidate in item["candidates"]):
            raise HistoryImportError("duplicate_exact", "Исключите повторяющуюся тренировку", 409)

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in included:
        groups[row["source"]["workout_ref"]].append(row)
    workout_ids = []
    for ref, group in groups.items():
        first = group[0]
        timestamp = datetime.fromisoformat(first["source"]["completed_at"].replace("Z", "+00:00"))
        workout = UserWorkout(
            user_program_id=None,
            history_imported=True,
            scheduled_date=date.fromisoformat(first["completed_on"]),
            scheduled_time=None,
            day_number=None,
            week_number=null(),
            plan_materialized=null(),
            title=first["source"]["workout_title"],
            status="completed",
            completed_at=timestamp.replace(tzinfo=None),
            completed_at_utc=datetime.fromisoformat(first["completed_at_utc"]),
        )
        db.add(workout)
        db.flush()
        exercise_groups: dict[str, list[dict]] = defaultdict(list)
        for row in group:
            exercise_groups[row["source"]["exercise_ref"]].append(row)
        for sort_order, exercise_rows in enumerate(exercise_groups.values(), start=1):
            exercise = UserWorkoutExercise(
                workout_id=workout.id,
                history_imported=True,
                exercise_id=exercise_rows[0]["exercise_id"],
                metric_type="strength",
                sort_order=sort_order,
                prescribed_sets=None,
                prescribed_reps=None,
                rest_seconds=null(),
            )
            db.add(exercise)
            db.flush()
            for row in exercise_rows:
                db.add(
                    UserWorkoutSet(
                        workout_exercise_id=exercise.id,
                        set_number=row["set_number"],
                        actual_reps=row["reps"],
                        actual_weight=Decimal(row["weight_kg"])
                        if row["weight_kg"] is not None
                        else None,
                        rir=row["source"]["rir"] or None,
                        set_kind=row["source"]["set_kind"],
                        is_completed=True,
                    )
                )
        db.add(
            ImportedWorkout(
                workout_id=workout.id,
                owner_user_id=user.id,
                provider=draft.provider,
                source_ref_hash=_hash([draft.source_sha256, ref]),
                fact_hash=_hash([first["completed_at_utc"], _source_set_facts(group)]),
                parser_version=draft.parser_version,
                source_timezone=first["source"]["timezone"],
            )
        )
        workout_ids.append(workout.id)
    db.flush()
    draft.status = "confirmed"
    draft.result_json = {
        "workout_ids": workout_ids,
        "workout_count": len(workout_ids),
        "set_count": len(included),
    }
    draft.draft_json = None
    draft.expires_at = _now() + TOMBSTONE_TTL
    db.flush()
    return draft


def cancel_history_import(db: Session, user: User, draft_id: str, *, version: int) -> None:
    _lock_user(db, user)
    draft = _get_draft(db, user, draft_id, lock=True)
    _require_pending(draft, version)
    draft.status = "cancelled"
    draft.draft_json = None
    draft.result_json = None
    draft.expires_at = _now() + TOMBSTONE_TTL
    db.flush()
