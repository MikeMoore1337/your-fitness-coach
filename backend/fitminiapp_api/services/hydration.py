from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitminiapp_api.core.timezone import (
    get_timezone,
    get_user_timezone_name,
    now_for_user_naive,
    today_for_user,
)
from fitminiapp_api.models.hydration import HydrationEntry, HydrationGoal, HydrationPreset
from fitminiapp_api.models.user import User, UserProfile
from fitminiapp_api.schemas.hydration import (
    HydrationEntryCreate,
    HydrationEntryUpdate,
    HydrationGoalSave,
    HydrationGoalSource,
    HydrationPresetSave,
)

HYDRATION_METHOD_VERSION = "nasem-ai-2005-observed-beverages-v1"
DEFAULT_PRESETS = (
    {"label": "Стакан", "volume_ml": 250, "beverage_type": "water"},
    {"label": "Большой стакан", "volume_ml": 350, "beverage_type": "water"},
    {"label": "Бутылка", "volume_ml": 500, "beverage_type": "water"},
)


class HydrationError(ValueError):
    pass


class HydrationConflictError(HydrationError):
    pass


def _fingerprint(payload: object) -> str:
    data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _entry_response(entry: HydrationEntry) -> dict:
    return {
        "id": entry.id,
        "volume_ml": entry.volume_ml,
        "beverage_type": entry.beverage_type,
        "occurred_at": _aware_utc(entry.occurred_at),
        "diary_date": entry.diary_date,
        "timezone": entry.timezone,
        "source": entry.source,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def _goal_response(goal: HydrationGoal | None) -> dict | None:
    if goal is None:
        return None
    return {
        "id": goal.id,
        "enabled": goal.status == "enabled",
        "target_ml": goal.target_ml,
        "source": goal.source,
        "method_version": goal.method_version,
        "reference_scope": goal.reference_scope,
        "sex": goal.sex,
        "adult_confirmed": goal.adult_confirmed,
        "effective_from": goal.effective_from,
        "effective_to": goal.effective_to,
        "created_at": goal.created_at,
    }


def get_active_hydration_goal(db: Session, user_id: int) -> HydrationGoal | None:
    return (
        db.query(HydrationGoal)
        .filter(HydrationGoal.user_id == user_id, HydrationGoal.effective_to.is_(None))
        .order_by(HydrationGoal.id.desc())
        .first()
    )


def get_hydration_goal_on(db: Session, user_id: int, diary_date: date) -> HydrationGoal | None:
    return (
        db.query(HydrationGoal)
        .filter(
            HydrationGoal.user_id == user_id,
            HydrationGoal.effective_from <= diary_date,
            (HydrationGoal.effective_to.is_(None) | (HydrationGoal.effective_to > diary_date)),
        )
        .order_by(HydrationGoal.effective_from.desc(), HydrationGoal.id.desc())
        .first()
    )


def save_hydration_goal(
    db: Session,
    user: User,
    payload: HydrationGoalSave,
    request_key: str,
) -> dict:
    request_key = request_key.strip()
    if not request_key or len(request_key) > 128:
        raise HydrationError("Некорректный Idempotency-Key")
    fingerprint = _fingerprint(payload)
    replay = (
        db.query(HydrationGoal)
        .filter(HydrationGoal.user_id == user.id, HydrationGoal.request_key == request_key)
        .first()
    )
    if replay is not None:
        if replay.payload_fingerprint != fingerprint:
            raise HydrationConflictError("Idempotency-Key уже использован с другими данными")
        return _goal_response(replay) or {}

    effective_from = payload.effective_from or today_for_user(user)
    if effective_from > today_for_user(user):
        raise HydrationError("Цель нельзя включить будущей датой")
    target_ml: int | None
    if payload.source == HydrationGoalSource.NATIONAL_ACADEMIES_BEVERAGES:
        profile = user.profile
        if profile and profile.birth_date:
            today = today_for_user(user)
            age = (
                today.year
                - profile.birth_date.year
                - ((today.month, today.day) < (profile.birth_date.month, profile.birth_date.day))
            )
            if age < 18:
                raise HydrationError("Расчётная цель предназначена только для взрослых")
        target_ml = 3000 if payload.sex == "male" else 2200
    else:
        target_ml = payload.target_ml
    if not payload.enabled:
        target_ml = None

    current = get_active_hydration_goal(db, user.id)
    if current is not None and effective_from < current.effective_from:
        raise HydrationError("Новая версия цели не может начинаться раньше текущей")
    try:
        if current is not None:
            current.effective_to = effective_from
            db.flush()
        goal = HydrationGoal(
            user_id=user.id,
            status="enabled" if payload.enabled else "disabled",
            target_ml=target_ml,
            source=payload.source.value,
            method_version=(
                HYDRATION_METHOD_VERSION
                if payload.source == HydrationGoalSource.NATIONAL_ACADEMIES_BEVERAGES
                else "manual-v1"
            ),
            reference_scope="beverages",
            sex=payload.sex,
            adult_confirmed=payload.adult_confirmed,
            effective_from=effective_from,
            request_key=request_key,
            payload_fingerprint=fingerprint,
        )
        db.add(goal)
        db.flush()
        if current is not None:
            current.superseded_by_id = goal.id
        if payload.save_sex_to_profile and payload.sex:
            profile = user.profile
            if profile is None:
                profile = UserProfile(user_id=user.id)
                db.add(profile)
            profile.sex = payload.sex
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(HydrationGoal)
            .filter(HydrationGoal.user_id == user.id, HydrationGoal.request_key == request_key)
            .first()
        )
        if replay is None:
            raise HydrationConflictError("Не удалось сохранить версию цели") from exc
        if replay.payload_fingerprint != fingerprint:
            raise HydrationConflictError(
                "Idempotency-Key уже использован с другими данными"
            ) from exc
        return _goal_response(replay) or {}
    db.refresh(goal)
    return _goal_response(goal) or {}


def _resolve_occurrence(user: User, payload: HydrationEntryCreate) -> tuple[datetime, date, str]:
    timezone_name = get_user_timezone_name(user)
    zone = get_timezone(timezone_name)
    today = today_for_user(user)
    if payload.occurred_at is not None:
        occurred = payload.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=zone)
    elif payload.diary_date is not None and payload.diary_date != today:
        occurred = datetime.combine(payload.diary_date, time(hour=12), tzinfo=zone)
    else:
        occurred = datetime.now(zone)
    local_date = occurred.astimezone(zone).date()
    if payload.diary_date is not None and payload.diary_date != local_date:
        raise HydrationError("Дата записи не соответствует времени в профиле")
    if occurred.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
        raise HydrationError("Нельзя добавить запись из будущего")
    return occurred.astimezone(UTC), local_date, timezone_name


def create_hydration_entry(
    db: Session,
    user: User,
    payload: HydrationEntryCreate,
    request_key: str,
) -> dict:
    request_key = request_key.strip()
    if not request_key or len(request_key) > 128:
        raise HydrationError("Некорректный Idempotency-Key")
    fingerprint = _fingerprint(payload)
    replay = (
        db.query(HydrationEntry)
        .filter(HydrationEntry.user_id == user.id, HydrationEntry.request_key == request_key)
        .first()
    )
    if replay is not None:
        if replay.payload_fingerprint != fingerprint:
            raise HydrationConflictError("Idempotency-Key уже использован с другими данными")
        return _entry_response(replay)
    occurred_at, diary_date, timezone_name = _resolve_occurrence(user, payload)
    entry = HydrationEntry(
        user_id=user.id,
        occurred_at=occurred_at,
        diary_date=diary_date,
        timezone=timezone_name,
        volume_ml=payload.volume_ml,
        beverage_type=payload.beverage_type.value,
        source=payload.source,
        request_key=request_key,
        payload_fingerprint=fingerprint,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = (
            db.query(HydrationEntry)
            .filter(HydrationEntry.user_id == user.id, HydrationEntry.request_key == request_key)
            .first()
        )
        if replay is None:
            raise HydrationConflictError("Не удалось сохранить запись") from exc
        if replay.payload_fingerprint != fingerprint:
            raise HydrationConflictError(
                "Idempotency-Key уже использован с другими данными"
            ) from exc
        return _entry_response(replay)
    db.refresh(entry)
    return _entry_response(entry)


def update_hydration_entry(
    db: Session, user: User, entry_id: int, payload: HydrationEntryUpdate
) -> dict:
    entry = (
        db.query(HydrationEntry)
        .filter(HydrationEntry.id == entry_id, HydrationEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise HydrationError("Запись не найдена")
    timezone_name = get_user_timezone_name(user)
    zone = get_timezone(timezone_name)
    occurred = payload.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=zone)
    if occurred.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
        raise HydrationError("Нельзя сохранить запись из будущего")
    entry.volume_ml = payload.volume_ml
    entry.beverage_type = payload.beverage_type.value
    entry.occurred_at = occurred.astimezone(UTC)
    entry.diary_date = occurred.astimezone(zone).date()
    entry.timezone = timezone_name
    entry.source = "history_edit"
    entry.updated_at = now_for_user_naive(user)
    db.commit()
    db.refresh(entry)
    return _entry_response(entry)


def delete_hydration_entry(db: Session, user: User, entry_id: int) -> None:
    entry = (
        db.query(HydrationEntry)
        .filter(HydrationEntry.id == entry_id, HydrationEntry.user_id == user.id)
        .first()
    )
    if entry is None:
        raise HydrationError("Запись не найдена")
    db.delete(entry)
    db.commit()


def list_hydration_day(db: Session, user: User, diary_date: date) -> dict:
    entries = (
        db.query(HydrationEntry)
        .filter(HydrationEntry.user_id == user.id, HydrationEntry.diary_date == diary_date)
        .order_by(HydrationEntry.occurred_at.desc(), HydrationEntry.id.desc())
        .all()
    )
    goal = get_hydration_goal_on(db, user.id, diary_date)
    custom = (
        db.query(HydrationPreset)
        .filter(HydrationPreset.user_id == user.id)
        .order_by(HydrationPreset.position, HydrationPreset.id)
        .all()
    )
    presets = [{**item, "id": None, "is_default": True} for item in DEFAULT_PRESETS] + [
        {
            "id": row.id,
            "label": row.label,
            "volume_ml": row.volume_ml,
            "beverage_type": row.beverage_type,
            "is_default": False,
        }
        for row in custom
    ]
    total_ml = sum(row.volume_ml for row in entries)
    enabled_goal = goal if goal and goal.status == "enabled" else None
    target_ml = enabled_goal.target_ml if enabled_goal else None
    last_logged_at = max((_aware_utc(row.occurred_at) for row in entries), default=None)
    return {
        "diary_date": diary_date,
        "timezone": get_user_timezone_name(user),
        "total_ml": total_ml,
        "goal": _goal_response(goal),
        "progress_percent": round(total_ml * 100 / target_ml, 1) if target_ml else None,
        "entries": [_entry_response(row) for row in entries],
        "presets": presets,
        "last_logged_at": last_logged_at,
        "reminder_suppression_key": (
            f"hydration-logged:{user.id}:{diary_date.isoformat()}" if entries else None
        ),
        "action_url": f"/app?section=nutrition&date={diary_date.isoformat()}&hydration=quick",
    }


def save_hydration_preset(db: Session, user: User, payload: HydrationPresetSave) -> dict:
    label = payload.label.strip()
    if not label:
        raise HydrationError("Название сосуда не может быть пустым")
    # The unique (user_id, label) constraint protects the invariant, but a
    # concurrent upsert would otherwise surface its IntegrityError as a 500.
    # Serialize the small per-user preset namespace before the read/create step.
    db.query(User.id).filter(User.id == user.id).with_for_update().one()
    existing = (
        db.query(HydrationPreset)
        .filter(HydrationPreset.user_id == user.id, HydrationPreset.label == label)
        .first()
    )
    if existing is None:
        existing = HydrationPreset(user_id=user.id, label=label)
        db.add(existing)
    existing.volume_ml = payload.volume_ml
    existing.beverage_type = payload.beverage_type.value
    db.commit()
    db.refresh(existing)
    return {
        "id": existing.id,
        "label": existing.label,
        "volume_ml": existing.volume_ml,
        "beverage_type": existing.beverage_type,
        "is_default": False,
    }


def delete_hydration_preset(db: Session, user: User, preset_id: int) -> None:
    preset = (
        db.query(HydrationPreset)
        .filter(HydrationPreset.id == preset_id, HydrationPreset.user_id == user.id)
        .first()
    )
    if preset is None:
        raise HydrationError("Сосуд не найден")
    db.delete(preset)
    db.commit()
